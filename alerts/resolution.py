"""
alerts/resolution.py
---------------------
ResolutionService — automatic lifecycle closure for OPEN alerts (and their
related tickets) that have been silent beyond their severity-specific
resolution window.

Resolution logic
----------------
An alert is "resolved" when no new ticket activity has been observed for a
duration equal to get_resolution_window(severity).  Call
`ResolutionService.run_resolution_pass()` on a fixed cadence (e.g. Celery beat
every 60 s).

On resolution:
  * Alert  → status = CLOSED, closed_at = now
  * Tickets matching (metric_name, severity, purpose, status OPEN/ACK) → CLOSED
              + meta updated with audit trail (auto_closed, closed_reason, closed_at)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from alerts.models import Alert
from alerts.services import is_resolved
from tickets.models import Ticket
from workflows.models import AppliesTo, WorkflowStatus
from workflows.services import WorkflowService


class ResolutionService:

    # ------------------------------------------------------------------
    # Core resolution
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_alert(alert: Alert) -> None:
        """
        Close a single alert and all its matching open tickets.

        Steps
        -----
        1. Mark the alert CLOSED with a closed_at timestamp.
        2. Query tickets by (metric_name, severity, purpose, status OPEN/ACK) —
           the same key used to group tickets into this alert.
        3. For each ticket, set status=CLOSED and append closure metadata to
           the `meta` JSON field without destroying existing keys.
        """
        now = datetime.now(tz=timezone.utc)

        # 1. Close the alert itself — use terminal status for this purpose/alert scope
        terminal_alert_statuses = WorkflowService.get_terminal_statuses(
            purpose    = alert.purpose,
            applies_to = AppliesTo.ALERT,
        )
        close_status_alert = terminal_alert_statuses[0] if terminal_alert_statuses else "CLOSED"

        alert.status    = close_status_alert
        alert.closed_at = now
        alert.save(update_fields=["status", "closed_at"])

        # 2. Find tickets to close — only those in auto-resolvable statuses for this purpose
        auto_resolvable = WorkflowService.get_auto_resolvable_statuses(
            purpose    = alert.purpose,
            applies_to = AppliesTo.TICKET,
        )
        if not auto_resolvable:
            # Fallback if no workflow configured yet
            auto_resolvable = ["OPEN", "ACK"]

        terminal_ticket_statuses = WorkflowService.get_terminal_statuses(
            purpose    = alert.purpose,
            applies_to = AppliesTo.TICKET,
        )
        close_status_ticket = terminal_ticket_statuses[0] if terminal_ticket_statuses else "CLOSED"

        tickets = Ticket.objects.filter(
            metric_name = alert.metric_name,
            severity    = alert.severity,
            purpose     = alert.purpose,
            status__in  = auto_resolvable,
        )

        for ticket in tickets:
            ticket.status = close_status_ticket

            # 3. Merge closure audit trail into existing meta (non-destructive)
            try:
                meta: dict = json.loads(ticket.meta or "{}")
            except (json.JSONDecodeError, TypeError):
                meta = {}

            meta.update(
                {
                    "auto_closed":   True,
                    "closed_reason": "resolution_window_expired",
                    "closed_at":     now.isoformat(),
                }
            )
            ticket.meta = json.dumps(meta)
            ticket.save(update_fields=["status", "meta"])

    # ------------------------------------------------------------------
    # Batch pass (called by the background worker)
    # ------------------------------------------------------------------

    @staticmethod
    def run_resolution_pass() -> list[int]:
        """
        Scan all non-terminal alerts and resolve any that have exceeded their
        resolution window.  Terminal statuses are looked up dynamically from
        WorkflowService so teams can define their own closed states.

        Returns:
            List of alert IDs that were resolved in this pass.
        """
        # Collect all terminal status keys across all purposes
        terminal_statuses = set(
            ws.key
            for ws in WorkflowStatus.objects.filter(
                is_terminal  = True,
                applies_to__in = [AppliesTo.ALERT, AppliesTo.BOTH],
            )
        ) or {"CLOSED"}   # fallback if no rows exist yet

        open_alerts = Alert.objects.exclude(status__in=terminal_statuses)
        resolved_ids: list[int] = []

        for alert in open_alerts:
            if is_resolved(alert):
                ResolutionService.resolve_alert(alert)
                resolved_ids.append(alert.pk)

        return resolved_ids
