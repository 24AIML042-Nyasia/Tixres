from sqlalchemy.orm import Session
from ticket_service.models import Ticket
from datetime import datetime, timedelta
from sqlalchemy import and_
import json


class TicketService:

    DEDUP_WINDOW_MINUTES = 60
    DEDUP_FIELDS = ['agent_id', 'metric_name', 'severity']  # detectors are merged, not matched

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_duplicate(
        db,
        agent_id: str,
        metric_name: str,
        severity: str,
        window_minutes: int = None
    ) -> Ticket | None:
        """
        Find an existing OPEN ticket matching agent_id + metric_name + severity
        within the deduplication time window.

        Note: `detector` is intentionally excluded from matching — duplicate tickets
        from different detectors are merged into the same ticket rather than forked.

        Args:
            db: Active SQLAlchemy session.
            agent_id, metric_name, severity: Identity fields for deduplication.
            window_minutes: Look-back window in minutes. Defaults to DEDUP_WINDOW_MINUTES.

        Returns:
            Matching Ticket or None.
        """
        cutoff = datetime.now() - timedelta(minutes=window_minutes or TicketService.DEDUP_WINDOW_MINUTES)

        return db.query(Ticket).filter(
            and_(
                Ticket.agent_id == agent_id,
                Ticket.metric_name == metric_name,
                Ticket.severity == severity,
                Ticket.status == 'OPEN',
                Ticket.first_occurred_at >= cutoff
            )
        ).first()

    @staticmethod
    def _merge_into(existing: Ticket, detector: str, message: str) -> None:
        """
        Merge an incoming duplicate event into an existing ticket in-place.

        Merge strategy:
        - `detectors`: union of existing + incoming detector (no duplicates).
        - `last_occurred_at`: updated to now.
        - `occurrence_count`: incremented by 1.
        - `message`: updated to the latest message for freshness.
        - All other fields (severity, meta, first_occurred_at) are preserved.

        Args:
            existing: The Ticket ORM object to mutate.
            detector: Detector name from the incoming duplicate event.
            message: Latest message from the incoming event.
        """
        # Merge detectors — preserve as a sorted unique JSON array
        current_detectors: list = json.loads(existing.detectors or '[]')
        if detector not in current_detectors:
            current_detectors.append(detector)
            existing.detectors = json.dumps(sorted(current_detectors))

        existing.last_occurred_at = datetime.now()
        existing.occurrence_count = (existing.occurrence_count or 1) + 1
        existing.message = message  # keep the freshest message

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
        dedup_window_minutes: int = None
    ) -> dict:
        """
        Create a new ticket or merge into an existing one if a duplicate is found.

        Deduplication & merge flow:
        1. Search for an OPEN ticket matching (agent_id, metric_name, severity)
           within the dedup window.
        2. If found → merge: add detector to the detectors list, bump occurrence_count,
           update last_occurred_at and message. No new row is created.
        3. If not found → insert a fresh ticket with detectors=[detector],
           occurrence_count=1, first/last_occurred_at=now.

        Args:
            agent_id: ID of the agent raising the ticket.
            metric_name: Name of the metric that triggered the ticket.
            severity: Severity level (e.g., 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL').
            detector: Name of the detector that identified the issue.
            meta: Additional metadata as a JSON-serialized string.
            message: Human-readable description of the issue.
            dedup: Whether to apply deduplication/merge logic. Defaults to True.
            dedup_window_minutes: Override the default deduplication window.

        Returns:
            dict with:
                - 'created' (bool): True if a new ticket row was inserted.
                - 'merged' (bool): True if an existing ticket was updated.
                - 'ticket_id' (int): ID of the new or existing ticket.
                - 'occurrence_count' (int): Updated occurrence count.
        """
        try:
            if dedup:
                existing = TicketService._find_duplicate(
                    db, agent_id, metric_name, severity, dedup_window_minutes
                )
                if existing:
                    TicketService._merge_into(existing, detector, message)
                    db.commit()
                    db.refresh(existing)
                    return {
                        'created': False,
                        'merged': True,
                        'ticket_id': existing.id,
                        'occurrence_count': existing.occurrence_count
                    }

            ticket = Ticket(
                agent_id=agent_id,
                metric_name=metric_name,
                severity=severity,
                status = 'OPEN',
                detectors=json.dumps([detector]),
                meta=meta,
                message=message,
                occurrence_count=1,
                first_occurred_at=datetime.now(),
                last_occurred_at=datetime.now(),
                created_at=datetime.now()
            )
            db.add(ticket)
            db.commit()
            db.refresh(ticket)

            return {
                'created': True,
                'merged': False,
                'ticket_id': ticket.id,
                'occurrence_count': 1
            }
        finally:
            db.close()

    @staticmethod
    def get_tickets(db : Session, agent_id: str, limit: int = 100) -> list[dict]:
        """
        Retrieve tickets for a given agent, ordered by most recent activity first.

        Args:
            agent_id: ID of the agent whose tickets to fetch.
            limit: Maximum number of tickets to return. Defaults to 100.

        Returns:
            List of ticket dicts. `detectors` is returned as a Python list.
        """
        try:
            tickets = (
                db.query(Ticket)
                .filter(Ticket.agent_id == agent_id)
                .order_by(Ticket.last_occurred_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    'id': t.id,
                    'agent_id': t.agent_id,
                    'metric_name': t.metric_name,
                    'severity': t.severity,
                    'status': t.status,
                    'detectors': json.loads(t.detectors or '[]'),
                    'meta': t.meta,
                    'message': t.message,
                    'occurrence_count': t.occurrence_count,
                    'first_occurred_at': t.first_occurred_at,
                    'last_occurred_at': t.last_occurred_at,
                    'created_at': t.created_at
                }
                for t in tickets
            ]
        finally:
            db.close()