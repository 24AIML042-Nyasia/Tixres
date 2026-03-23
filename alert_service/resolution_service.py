"""
ResolutionService
=================
Handles automatic lifecycle closure for OPEN alerts (and their related tickets)
that have been silent beyond their severity-specific resolution window.

Resolution logic
----------------
An alert is "resolved" when no new ticket activity has been observed for a
duration equal to get_resolution_window(severity).  The worker calls
`run_resolution_pass` on a fixed cadence (typically every 60 s).

On resolution:
  * Alert  → status = CLOSED, closed_at = now
  * Tickets matching (metric_name, severity, status=OPEN) → status = CLOSED
             + meta updated with audit trail (auto_closed, closed_reason, closed_at)

Key design notes
----------------
* Only tickets sharing BOTH metric_name AND severity with the alert are closed.
  This prevents accidental cross-contamination when the same metric has tickets
  at different severities.
* P4 tickets may exist in the DB but their alerts are never created, so they
  will never be touched here.
* The `meta` column is kept as a JSON string; the service merges into it rather
  than overwriting, preserving any existing metadata.
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session

from alert_service.models import Alert
from alert_service.alert_service import is_resolved
from ticket_service.models import Ticket


class ResolutionService:

    # ------------------------------------------------------------------
    # Core resolution
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_alert(db: Session, alert: Alert) -> None:
        """
        Close a single alert and all its matching open tickets.

        Steps
        -----
        1. Mark the alert CLOSED with a closed_at timestamp.
        2. Query tickets by (metric_name, severity, status=OPEN) — the same
           key used to group tickets into this alert.
        3. For each ticket, set status=CLOSED and append closure metadata to
           the `meta` JSON field without destroying existing keys.

        Args:
            db:    Active SQLAlchemy session.
            alert: The OPEN Alert ORM object to resolve.
        """
        now = datetime.now()

        # 1. Close the alert itself
        alert.status    = "CLOSED"
        alert.closed_at = now

        # 2. Close all open tickets that belong to this alert's key
        #    ⚠️  Filter on BOTH metric_name AND severity to avoid closing tickets
        #    of a different severity on the same metric (e.g. P2 vs P3).
        tickets: list[Ticket] = (
            db.query(Ticket)
            .filter(
                Ticket.metric_name == alert.metric_name,
                Ticket.severity    == alert.severity,
                Ticket.purpose     == getattr(alert, "purpose", "general"),
                Ticket.status      == "OPEN",
            )
            .all()
        )

        for ticket in tickets:
            ticket.status = "CLOSED"

            # 3. Merge closure audit trail into existing meta (non-destructive)
            try:
                meta: dict = json.loads(ticket.meta or "{}")
            except (json.JSONDecodeError, TypeError):
                meta = {}

            meta.update(
                {
                    "auto_closed"    : True,
                    "closed_reason"  : "resolution_window_expired",
                    "closed_at"      : now.isoformat(),
                }
            )
            ticket.meta = json.dumps(meta)

        db.commit()

    # ------------------------------------------------------------------
    # Batch pass (called by the background worker)
    # ------------------------------------------------------------------

    @staticmethod
    def run_resolution_pass(db: Session) -> list[int]:
        """
        Scan all OPEN alerts and resolve any that have exceeded their
        resolution window.

        This is designed to be called by a background worker on a fixed
        interval (e.g. every 60 seconds).

        Args:
            db: Active SQLAlchemy session.

        Returns:
            List of alert IDs that were resolved in this pass.
        """
        open_alerts: list[Alert] = (
            db.query(Alert)
            .filter(Alert.status == "OPEN")
            .all()
        )

        resolved_ids: list[int] = []

        for alert in open_alerts:
            if is_resolved(alert):
                ResolutionService.resolve_alert(db, alert)
                resolved_ids.append(alert.id)

        return resolved_ids
