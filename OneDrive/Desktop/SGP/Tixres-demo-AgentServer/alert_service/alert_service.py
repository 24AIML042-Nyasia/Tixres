"""
AlertService
============
Core alert-correlation engine.

Responsibilities
----------------
1. Receive a newly created/merged Ticket from TicketService.
2. Skip P4 tickets entirely — they are stored in the DB but never surface
   as alerts (filtering also done upstream in TicketService._find_duplicate).
3. Find or create an OPEN Alert keyed by (metric_name, severity).
4. Progressively escalate: SINGLE → GROUP when a second agent fires.
5. Expose helpers for cooldown and resolution-window computation.

Design decisions
----------------
* Alert key is (metric_name, severity), NOT per-agent — intentional grouping.
* Cooldown is for *notification throttling* only; it does NOT affect alert
  open/close lifecycle.
* P4 tickets are silently ignored here; all other logic is severity-agnostic.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from alert_service.models import Alert, ALERT_STATUS_OPEN, ALERT_STATUS_ACK
from ticket_service.models import Ticket

from SLAs.alert_services import (doIgnoreTicketBySeverity,
                                 get_resolution_window,
                                compute_cooldown
)  


def is_resolved(alert: Alert) -> bool:
    """
    Return True if the alert has been silent long enough to be auto-closed.

    An alert is considered resolved when:
        now - last_seen_at  >  resolution_window(severity)
    """
    if alert.last_seen_at is None:
        return False
    window = get_resolution_window(alert.severity)
    return datetime.now() - alert.last_seen_at > window


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_active_alert(db: Session, metric_name: str, severity: str, purpose: str) -> Alert | None:
    """
    Return the single OPEN alert for (metric_name, severity), or None.

    Uses ``with_for_update()`` (SELECT FOR UPDATE) so concurrent callers
    serialise at the DB level.  The second writer blocks until the first
    commits, then re-reads the freshly-updated row — preventing the
    classic lost-update race where two threads both read agent_ids=["A"],
    each add their own agent, and one commit silently overwrites the other.

    SQLite note: SQLite does not implement row-level locking; with_for_update
    is silently ignored there.  For true concurrency safety use Postgres.
    """
    return (
        db.query(Alert)
        .filter(
            Alert.metric_name == metric_name,
            Alert.severity    == severity,
            Alert.purpose     == purpose,
            Alert.status.in_([ALERT_STATUS_OPEN, ALERT_STATUS_ACK]),
        )
        .with_for_update()
        .first()
    )


def _create_single_alert(db: Session, ticket: Ticket) -> Alert:
    """
    Insert a brand-new SINGLE alert seeded from the given ticket.

    Called when no OPEN alert exists for (metric_name, severity).
    """
    alert = Alert(
        metric_name      = ticket.metric_name,
        severity         = ticket.severity,
        purpose          = getattr(ticket, "purpose", "general") or "general",
        type             = "SINGLE",
        status           = ALERT_STATUS_OPEN,
        agent_ids        = json.dumps([ticket.agent_id]),
        total_occurrence = ticket.occurrence_count or 1,
        first_seen_at    = ticket.first_occurred_at or datetime.now(),
        last_seen_at     = ticket.last_occurred_at  or datetime.now(),
        cooldown_until   = compute_cooldown(ticket.severity),
        created_at       = datetime.now(),
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def _update_alert(db: Session, alert: Alert, ticket: Ticket) -> Alert:
    """
    Merge an incoming ticket into an existing OPEN alert.

    Merge rules
    -----------
    * agent_ids : union (no duplicates).
    * type      : escalates SINGLE → GROUP when a *new* agent is added
                  and the set size crosses 2.
    * total_occurrence : incremented by ticket.occurrence_count.
    * last_seen_at     : refreshed to now.
    * cooldown_until   : NOT reset here — cooldown is set once on creation
                         and managed separately by the notification layer.
    """
    now = datetime.now()

    existing_agents: set[str] = set(json.loads(alert.agent_ids or "[]"))
    new_agent = ticket.agent_id not in existing_agents

    if new_agent:
        existing_agents.add(ticket.agent_id)

        # Escalate to GROUP as soon as we have 2+ distinct agents
        if alert.type == "SINGLE" and len(existing_agents) >= 2:
            alert.type = "GROUP"

    alert.agent_ids        = json.dumps(sorted(existing_agents))
    alert.total_occurrence = (alert.total_occurrence or 0) + (ticket.occurrence_count or 1)
    alert.last_seen_at     = now

    db.commit()
    db.refresh(alert)
    return alert


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def process_ticket(db: Session, ticket: Ticket) -> Alert | None:
    """
    Main entry point called by the background worker after every ticket upsert.

    Flow
    ----
    1. Skip P4 — stored in DB but never surfaced as an alert.
    2. Look for an existing OPEN alert keyed by (metric_name, severity).
    3. None found → create SINGLE alert.
       Found       → merge / potentially escalate to GROUP.

    Args:
        db:     Active SQLAlchemy session.
        ticket: The Ticket ORM object just created or merged by TicketService.

    Returns:
        The Alert that was created or updated, or None for P4 tickets.
    """

    if doIgnoreTicketBySeverity(ticket.severity):
        return None  # P4: persisted in DB, silent in alerting

    purpose = getattr(ticket, "purpose", "general") or "general"
    alert = _find_active_alert(db, ticket.metric_name, ticket.severity, purpose)

    if alert is None:
        try:
            return _create_single_alert(db, ticket)
        except IntegrityError:
            # Another concurrent writer likely inserted the alert first.
            db.rollback()
            alert = _find_active_alert(db, ticket.metric_name, ticket.severity, purpose)
            if alert:
                return _update_alert(db, alert, ticket)
            else:
                return None
    else:
        return _update_alert(db, alert, ticket)
