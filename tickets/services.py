"""
tickets/services.py
-------------------
TicketService
=============
Handles creation, deduplication, and retrieval of Tickets.

Deduplication strategy
-----------------------
A duplicate is an OPEN/ACK ticket for the same (agent_id, metric_name, severity, purpose)
within the configured time window. When a duplicate is found the incoming
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
  * Excluded from the deduplication window query via _find_duplicate
    (severity != 'P4' filter).
  * Never forwarded to AlertService.
  * Excluded from get_tickets by default (include_p4=False).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from tickets.models import (
    Ticket,
    TICKET_STATUS_OPEN,
    TICKET_STATUS_ACK,
    TICKET_STATUS_CLOSED,
)
from tickets.assignment import AssignmentService

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
    def _resolve_purpose(agent_id: str, explicit: str | None) -> str:
        """
        Prefer an explicit purpose when provided; otherwise fall back to the
        agent's recorded purpose, defaulting to 'general' when unavailable.
        """
        if explicit:
            return explicit
        try:
            from agents.models import Agent
            agent = Agent.objects.filter(agent_id=agent_id).select_related("purpose").first()
            if agent:
                return agent.purpose_name
        except Exception:
            pass
        return "general"

    @staticmethod
    def _find_duplicate(
        agent_id: str,
        metric_name: str,
        severity: str,
        purpose: str,
        window_minutes: int | None = None,
    ) -> Ticket | None:
        """
        Find an existing OPEN/ACK, non-P4 ticket that can absorb the incoming event.
        Returns None for P4 severity (P4 tickets are never deduplicated).
        """
        if severity == _P4_SEVERITY:
            return None

        minutes = window_minutes or TicketService.DEDUP_WINDOW_MINUTES
        cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=minutes)

        return (
            Ticket.objects.filter(
                agent_id=agent_id,
                metric_name=metric_name,
                severity=severity,
                purpose=purpose,
                status__in=[TICKET_STATUS_OPEN, TICKET_STATUS_ACK],
                first_occurred_at__gte=cutoff,
            ).first()
        )

    @staticmethod
    def _merge_into(existing: Ticket, detector: str, message: str) -> None:
        """
        Merge an incoming duplicate event into an existing ticket in-place.

        * detectors       : union — new detector appended if not already present,
                            result re-sorted for stable storage.
        * last_occurred_at: set to now (freshness).
        * occurrence_count: incremented by 1.
        * message         : replaced with the latest message.
        """
        current_detectors: list[str] = json.loads(existing.detectors or "[]")
        if detector not in current_detectors:
            current_detectors.append(detector)
            existing.detectors = json.dumps(sorted(current_detectors))

        existing.last_occurred_at = datetime.now(tz=timezone.utc)
        existing.occurrence_count = (existing.occurrence_count or 1) + 1
        existing.message = message
        existing.save(update_fields=["detectors", "last_occurred_at", "occurrence_count", "message"])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def create_ticket(
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

        Returns dict with keys:
          - created (bool)         : True if a new row was inserted.
          - merged (bool)          : True if an existing ticket was updated.
          - ticket_id (int)        : ID of the new or existing ticket.
          - ticket (Ticket)        : The Ticket ORM object.
          - occurrence_count (int) : Updated occurrence count.
          - is_p4 (bool)           : True when severity is P4.
        """
        purpose_value = TicketService._resolve_purpose(agent_id, purpose)

        # P4: always insert; never deduplicate
        effective_dedup = dedup and (severity != _P4_SEVERITY)

        if effective_dedup:
            existing = TicketService._find_duplicate(
                agent_id, metric_name, severity, purpose_value, dedup_window_minutes
            )
            if existing:
                TicketService._merge_into(existing, detector, message)
                existing.refresh_from_db()
                result = {
                    "created":          False,
                    "merged":           True,
                    "ticket_id":        existing.pk,
                    "ticket":           existing,
                    "occurrence_count": existing.occurrence_count,
                    "is_p4":            False,
                }
                result.update(TicketService._assignment_payload(existing))
                return result

        now = datetime.now(tz=timezone.utc)
        ticket = Ticket.objects.create(
            agent_id          = agent_id,
            metric_name       = metric_name,
            severity          = severity,
            purpose           = purpose_value,
            status            = TICKET_STATUS_OPEN,
            detectors         = json.dumps([detector]),
            meta              = meta,
            message           = message,
            occurrence_count  = 1,
            first_occurred_at = now,
            last_occurred_at  = now,
        )

        decision = AssignmentService.assign(ticket)

        # Refresh ticket so assigned_to select_related is available downstream
        ticket.refresh_from_db()

        result = {
            "created":          True,
            "merged":           False,
            "ticket_id":        ticket.pk,
            "ticket":           ticket,
            "occurrence_count": 1,
            "is_p4":            severity == _P4_SEVERITY,
        }
        result.update(TicketService._assignment_payload(ticket, decision))
        return result

    @staticmethod
    def get_tickets(
        agent_id: str,
        limit: int = 100,
        include_p4: bool = False,
    ) -> list[dict]:
        """
        Retrieve tickets for a given agent, ordered by most recent activity first.
        """
        qs = Ticket.objects.filter(agent_id=agent_id)
        if not include_p4:
            qs = qs.exclude(severity=_P4_SEVERITY)

        tickets = qs.select_related("assigned_to").order_by("-last_occurred_at")[:limit]

        items: list[dict] = []
        for t in tickets:
            payload = {
                "id":               t.pk,
                "agent_id":         t.agent_id,
                "metric_name":      t.metric_name,
                "severity":         t.severity,
                "purpose":          t.purpose,
                "status":           t.status,
                "detectors":        json.loads(t.detectors or "[]"),
                "meta":             t.meta,
                "message":          t.message,
                "occurrence_count": t.occurrence_count,
                "first_occurred_at": t.first_occurred_at,
                "last_occurred_at":  t.last_occurred_at,
                "created_at":       t.created_at,
                "acknowledged_at":  t.acknowledged_at,
                "acknowledged_by":  t.acknowledged_by,
            }
            payload.update(TicketService._assignment_payload(t))
            items.append(payload)
        return items

    @staticmethod
    def _assignment_payload(ticket: Ticket, decision=None) -> dict:
        assignee = ticket.assigned_to if hasattr(ticket, "assigned_to") else None
        return {
            "assigned_to":          ticket.assigned_to_id,
            "assigned_to_email":    getattr(assignee, "email", None),
            "assigned_to_name":     getattr(assignee, "name", None),
            "assigned_at":          ticket.assigned_at,
            "assignment_strategy":  ticket.assignment_strategy,
            "assignment_reason":    ticket.assignment_reason,
            "auto_assigned":        ticket.auto_assigned,
            "assignment_decision":  getattr(decision, "strategy", None) if decision else None,
        }

    @staticmethod
    def acknowledge_ticket(ticket_id: int, acked_by: str) -> bool:
        """
        Acknowledge an OPEN ticket.

        Returns:
            True if status changed from OPEN to ACK.
            False if already ACK/CLOSED.
            Raises ValueError if ticket not found.
        """
        try:
            ticket = Ticket.objects.get(pk=ticket_id)
        except Ticket.DoesNotExist:
            raise ValueError(f"Ticket {ticket_id} not found")

        if ticket.status != TICKET_STATUS_OPEN:
            return False

        ticket.status = TICKET_STATUS_ACK
        ticket.acknowledged_at = datetime.now(tz=timezone.utc)
        ticket.acknowledged_by = acked_by
        ticket.save(update_fields=["status", "acknowledged_at", "acknowledged_by"])
        return True
