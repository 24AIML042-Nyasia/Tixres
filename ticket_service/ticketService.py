"""
TicketService
=============
Handles creation, deduplication, and retrieval of Tickets.

Deduplication strategy
-----------------------
A duplicate is an OPEN ticket for the same (agent_id, metric_name, severity, purpose)
within the configured time window.  When a duplicate is found the incoming
event is *merged* rather than creating a new row:

  * detectors      → union (sorted, no duplicates)
  * occurrence_count → incremented
  * last_occurred_at → refreshed
  * message          → updated to the latest value

The `detector` field is intentionally excluded from the match key so that
events from different detectors for the same issue collapse into one ticket.

P4 filtering
------------
P4 tickets are stored in the DB for audit purposes but are:
  * Excluded from the deduplication window query via ``_find_duplicate``
    (``severity != 'P4'`` filter).
  * Never forwarded to AlertService.
  * Excluded from ``get_tickets`` by default (``include_p4=False``).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import and_
from sqlalchemy.orm import Session

from server_db.models import Agent, Purpose
from ticket_service.models import Ticket


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_P4_SEVERITY = "P4"


class TicketService:

    DEDUP_WINDOW_MINUTES = 60

    # Fields that must match for two events to be considered duplicates.
    # Note: `detector` is deliberately absent — see module docstring.
    DEDUP_FIELDS = ["agent_id", "metric_name", "severity", "purpose"]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_purpose(db: Session, agent_id: str, explicit: str | None) -> str:
        """
        Prefer an explicit purpose when provided; otherwise fall back to the
        agent's recorded purpose, defaulting to 'general' when unavailable.
        """
        if explicit:
            return explicit
        try:
            agent = db.query(Agent).filter(Agent.agent_id == agent_id).first()
            if agent:
                purpose_obj = getattr(agent, "purpose", None)
                if isinstance(purpose_obj, Purpose) and getattr(purpose_obj, "purpose", None):
                    return purpose_obj.purpose  # type: ignore[return-value]
                if isinstance(purpose_obj, str):
                    return purpose_obj
        except Exception:
            return "general"
        return "general"

    @staticmethod
    def _find_duplicate(
        db: Session,
        agent_id: str,
        metric_name: str,
        severity: str,
        purpose: str,
        window_minutes: int | None = None,
    ) -> Ticket | None:
        """
        Find an existing OPEN, non-P4 ticket that can absorb the incoming event.

        Matching criteria
        -----------------
        * agent_id, metric_name, severity — identity triple.
        * status == 'OPEN'               — don't reopen closed tickets.
        * severity != 'P4'               — P4 tickets are never deduplicated;
                                           each P4 event always inserts a new row
                                           (they are audit-only, not actionable).
        * first_occurred_at >= cutoff    — within the dedup window.

        Args:
            db:             Active SQLAlchemy session.
            agent_id:       Agent identifier.
            metric_name:    Metric that fired.
            severity:       Severity level of the incoming event.
            window_minutes: Override for DEDUP_WINDOW_MINUTES.

        Returns:
            Matching Ticket ORM object, or None.
        """
        # P4 tickets are never deduplicated — early exit keeps the query simple
        if severity == _P4_SEVERITY:
            return None

        cutoff = datetime.now() - timedelta(
            minutes=window_minutes or TicketService.DEDUP_WINDOW_MINUTES
        )

        return (
            db.query(Ticket)
            .filter(
                and_(
                    Ticket.agent_id    == agent_id,
                    Ticket.metric_name == metric_name,
                    Ticket.severity    == severity,
                    Ticket.purpose     == purpose,
                    Ticket.status      == "OPEN",
                    Ticket.first_occurred_at >= cutoff,
                )
            )
            .first()
        )

    @staticmethod
    def _merge_into(existing: Ticket, detector: str, message: str) -> None:
        """
        Merge an incoming duplicate event into an existing ticket in-place.

        Merge strategy
        --------------
        * detectors       : union — new detector appended if not already present,
                            result re-sorted for stable storage.
        * last_occurred_at: set to now (freshness).
        * occurrence_count: incremented by 1.
        * message         : replaced with the latest message.
        * All other fields (severity, meta, first_occurred_at, agent_id) are
          left untouched.

        Args:
            existing: The Ticket ORM object to mutate (not yet committed).
            detector: Detector name from the incoming event.
            message:  Latest human-readable description.
        """
        current_detectors: list[str] = json.loads(existing.detectors or "[]")
        if detector not in current_detectors:
            current_detectors.append(detector)
            existing.detectors = json.dumps(sorted(current_detectors))

        existing.last_occurred_at = datetime.now()
        existing.occurrence_count = (existing.occurrence_count or 1) + 1
        existing.message          = message

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def create_ticket(
        db: Session,
        agent_id: str,
        metric_name: str,
        severity: str,
        detector: str,
        meta: str,
        message: str,
        dedup: bool = True,
        dedup_window_minutes: int | None = None,
        purpose: str | None = None,
    ) -> dict:
        """
        Create a new ticket or merge into an existing one if a duplicate is found.

        P4 behaviour
        ------------
        P4 tickets bypass deduplication and are always inserted as new rows.
        They are stored for audit/observability but are never forwarded to
        AlertService and are excluded from ``get_tickets`` by default.

        Deduplication & merge flow (non-P4)
        ------------------------------------
        1. Search for an OPEN ticket matching (agent_id, metric_name, severity)
           within the dedup window.
        2. Found → merge: union detectors, bump occurrence_count,
                          refresh last_occurred_at and message.
           Not found → insert a fresh ticket row.

        Args:
            db:                   Active SQLAlchemy session.
            agent_id:             ID of the agent raising the ticket.
            metric_name:          Name of the metric that triggered the ticket.
            severity:             Severity level (P1 / P2 / P3 / P4).
            detector:             Name of the detector that identified the issue.
            meta:                 Additional metadata as a JSON-serialized string.
            message:              Human-readable description of the issue.
            dedup:                Whether to apply dedup/merge logic. Default True.
                                  Always False for P4 regardless of this flag.
            dedup_window_minutes: Override the default 60-minute dedup window.

        Returns:
            dict with keys:
              - created (bool)         : True if a new row was inserted.
              - merged (bool)          : True if an existing ticket was updated.
              - ticket_id (int)        : ID of the new or existing ticket.
              - occurrence_count (int) : Updated occurrence count.
              - is_p4 (bool)           : True when severity is P4.
        """
        try:
            purpose_value = TicketService._resolve_purpose(db, agent_id, purpose)
            # P4: always insert; never deduplicate
            effective_dedup = dedup and (severity != _P4_SEVERITY)

            if effective_dedup:
                existing = TicketService._find_duplicate(
                    db, agent_id, metric_name, severity, purpose_value, dedup_window_minutes
                )
                if existing:
                    TicketService._merge_into(existing, detector, message)
                    db.commit()
                    db.refresh(existing)
                    return {
                        "created"         : False,
                        "merged"          : True,
                        "ticket_id"       : existing.id,
                        "occurrence_count": existing.occurrence_count,
                        "is_p4"           : False,
                    }

            ticket = Ticket(
                agent_id          = agent_id,
                metric_name       = metric_name,
                severity          = severity,
                purpose           = purpose_value,
                status            = "OPEN",
                detectors         = json.dumps([detector]),
                meta              = meta,
                message           = message,
                occurrence_count  = 1,
                first_occurred_at = datetime.now(),
                last_occurred_at  = datetime.now(),
                created_at        = datetime.now(),
            )
            db.add(ticket)
            db.commit()
            db.refresh(ticket)

            return {
                "created"         : True,
                "merged"          : False,
                "ticket_id"       : ticket.id,
                "occurrence_count": 1,
                "is_p4"           : severity == _P4_SEVERITY,
            }
        finally:
            db.close()

    @staticmethod
    def get_tickets(
        db: Session,
        agent_id: str,
        limit: int = 100,
        include_p4: bool = False,
    ) -> list[dict]:
        """
        Retrieve tickets for a given agent, ordered by most recent activity first.

        Args:
            db:         Active SQLAlchemy session.
            agent_id:   ID of the agent whose tickets to fetch.
            limit:      Maximum number of tickets to return. Default 100.
            include_p4: When False (default), P4 tickets are excluded from
                        results. Set True only for audit/debug views.

        Returns:
            List of ticket dicts. `detectors` is returned as a Python list.
        """
        try:
            conditions = [Ticket.agent_id == agent_id]
            if not include_p4:
                conditions.append(Ticket.severity != _P4_SEVERITY)

            query = db.query(Ticket).filter(*conditions)

            tickets = (
                query
                .order_by(Ticket.last_occurred_at.desc())
                .limit(limit)
                .all()
            )

            return [
                {
                    "id"              : t.id,
                    "agent_id"        : t.agent_id,
                    "metric_name"     : t.metric_name,
                    "severity"        : t.severity,
                    "purpose"         : t.purpose,
                    "status"          : t.status,
                    "detectors"       : json.loads(t.detectors or "[]"),
                    "meta"            : t.meta,
                    "message"         : t.message,
                    "occurrence_count": t.occurrence_count,
                    "first_occurred_at": t.first_occurred_at,
                    "last_occurred_at" : t.last_occurred_at,
                    "created_at"      : t.created_at,
                }
                for t in tickets
            ]
        finally:
            db.close()
