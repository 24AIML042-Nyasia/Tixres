"""
alerts/services.py
------------------
AlertService — core alert-correlation engine.

Responsibilities
----------------
1. Receive a newly created/merged Ticket from TicketService.
2. Skip P4 tickets entirely — stored in DB but never surfaced as alerts.
3. Find or create an OPEN Alert keyed by (metric_name, severity, purpose).
4. Progressively escalate: SINGLE → GROUP when a second agent fires.

Design decisions
----------------
* Alert key is (metric_name, severity, purpose), NOT per-agent — intentional grouping.
* Cooldown is for *notification throttling* only; it does NOT affect alert lifecycle.
* P4 tickets are silently ignored here.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from django.db import IntegrityError, transaction

from alerts.models import Alert, ALERT_STATUS_OPEN, ALERT_STATUS_ACK
from tickets.models import Ticket
from slas.alert_services import (
    do_ignore_ticket_by_severity,
    get_resolution_window,
    compute_cooldown,
)


# ---------------------------------------------------------------------------
# Helper: is_resolved
# ---------------------------------------------------------------------------

def is_resolved(alert: Alert) -> bool:
    """
    Return True if the alert has been silent long enough to be auto-closed.

    An alert is considered resolved when:
        now - last_seen_at  >  resolution_window(severity)
    """
    if alert.last_seen_at is None:
        return False
    window = get_resolution_window(alert.severity)
    now = datetime.now(tz=timezone.utc)
    last = alert.last_seen_at
    # Make last_seen_at timezone-aware if it isn't (SQLite can return naive)
    if last.tzinfo is None:
        from django.utils import timezone as dj_tz
        last = dj_tz.make_aware(last)
    return (now - last) > window


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_active_alert(metric_name: str, severity: str, purpose: str) -> Alert | None:
    """
    Return the single OPEN/ACK alert for (metric_name, severity, purpose), or None.

    Uses select_for_update() so concurrent callers serialise at DB level
    (effective on Postgres; SQLite ignores row-level locking).
    """
    return (
        Alert.objects
        .select_for_update()
        .filter(
            metric_name=metric_name,
            severity=severity,
            purpose=purpose,
            status__in=[ALERT_STATUS_OPEN, ALERT_STATUS_ACK],
        )
        .first()
    )


def _create_single_alert(ticket: Ticket) -> Alert:
    """Insert a brand-new SINGLE alert seeded from the given ticket."""
    purpose = ticket.purpose or "general"
    alert = Alert.objects.create(
        metric_name       = ticket.metric_name,
        severity          = ticket.severity,
        purpose           = purpose,
        type              = "SINGLE",
        status            = ALERT_STATUS_OPEN,
        agent_ids         = json.dumps([ticket.agent_id]),
        total_occurrence  = ticket.occurrence_count or 1,
        first_seen_at     = ticket.first_occurred_at,
        last_seen_at      = ticket.last_occurred_at,
        cooldown_until    = compute_cooldown(ticket.severity),
    )
    return alert


def _update_alert(alert: Alert, ticket: Ticket) -> Alert:
    """
    Merge an incoming ticket into an existing OPEN/ACK alert.

    Merge rules
    -----------
    * agent_ids : union (no duplicates).
    * type      : escalates SINGLE → GROUP when a *new* agent is added
                  and the set size crosses 2.
    * total_occurrence : incremented by ticket.occurrence_count.
    * last_seen_at     : refreshed to now.
    """
    now = datetime.now(tz=timezone.utc)

    existing_agents: set[str] = set(json.loads(alert.agent_ids or "[]"))
    is_new_agent = ticket.agent_id not in existing_agents

    if is_new_agent:
        existing_agents.add(ticket.agent_id)
        if alert.type == "SINGLE" and len(existing_agents) >= 2:
            alert.type = "GROUP"

    alert.agent_ids        = json.dumps(sorted(existing_agents))
    alert.total_occurrence = (alert.total_occurrence or 0) + (ticket.occurrence_count or 1)
    alert.last_seen_at     = now
    alert.save(update_fields=["agent_ids", "total_occurrence", "last_seen_at", "type"])
    alert.refresh_from_db()
    return alert


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def process_ticket(ticket: Ticket) -> Alert | None:
    """
    Main entry point called after every ticket upsert.

    Flow
    ----
    1. Skip P4 — stored in DB but never surfaced as an alert.
    2. Look for an existing OPEN alert keyed by (metric_name, severity, purpose).
    3. None found → create SINGLE alert.
       Found       → merge / potentially escalate to GROUP.

    Returns:
        The Alert that was created or updated, or None for P4 tickets.
    """
    if do_ignore_ticket_by_severity(ticket.severity):
        return None

    purpose = ticket.purpose or "general"

    try:
        with transaction.atomic():
            alert = _find_active_alert(ticket.metric_name, ticket.severity, purpose)
            if alert is None:
                return _create_single_alert(ticket)
            else:
                return _update_alert(alert, ticket)
    except IntegrityError:
        # Another concurrent writer likely inserted the alert first.
        alert = _find_active_alert(ticket.metric_name, ticket.severity, purpose)
        if alert:
            with transaction.atomic():
                return _update_alert(alert, ticket)
        return None
