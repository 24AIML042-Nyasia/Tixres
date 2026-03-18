"""
tests/unit/test_ticket_service.py
==================================
Unit tests for TicketService.

Key fixture note
----------------
TicketService.create_ticket() calls db.close() in its finally block.
After each create_ticket() call the session passed in is CLOSED.
For any subsequent query we open a fresh session via the SessionFactory fixture.
The `fresh` fixture helper below does exactly that.

Coverage
--------
✅ Good cases  : creation, dedup merge, P4 insert
❌ Bad cases   : P4 dedup bypass, field isolation
⚠️  Edge cases : dedup window boundary, field stability
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from tests.test_alert_service.conftest import make_ticket
from ticket_service.ticketService import TicketService
from ticket_service.models import Ticket


# ---------------------------------------------------------------------------
# Helper: open a fresh session after create_ticket() closes the previous one
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh(SessionFactory):
    """Returns a callable that opens a new session each time it is called."""
    sessions = []

    def _open():
        s = SessionFactory()
        sessions.append(s)
        return s

    yield _open

    for s in sessions:
        try:
            s.close()
        except Exception:
            pass


# ===========================================================================
# ✅ GOOD CASES
# ===========================================================================

class TestTicketCreation:

    def test_creates_new_ticket_when_none_exists(self, db, fresh):
        result = TicketService.create_ticket(
            db, agent_id="A", metric_name="cpu", severity="P2",
            detector="det1", meta="{}", message="high cpu",
        )

        assert result["created"] is True
        assert result["merged"]  is False
        assert result["occurrence_count"] == 1
        assert result["is_p4"] is False

        s = fresh()
        ticket = s.query(Ticket).filter_by(id=result["ticket_id"]).first()
        assert ticket is not None
        assert ticket.agent_id    == "A"
        assert ticket.metric_name == "cpu"
        assert ticket.severity    == "P2"
        assert ticket.status      == "OPEN"
        assert json.loads(ticket.detectors) == ["det1"]
        assert ticket.occurrence_count == 1

    def test_first_and_last_occurred_at_set_on_create(self, db, fresh):
        before = datetime.now()
        result = TicketService.create_ticket(
            db, agent_id="A", metric_name="cpu", severity="P2",
            detector="det1", meta="{}", message="msg",
        )
        after = datetime.now()

        s = fresh()
        ticket = s.query(Ticket).filter_by(id=result["ticket_id"]).first()
        # Allow 1-second buffer for slow CI environments
        assert before - timedelta(seconds=1) <= ticket.first_occurred_at <= after + timedelta(seconds=1)
        assert before - timedelta(seconds=1) <= ticket.last_occurred_at  <= after + timedelta(seconds=1)

    def test_detectors_stored_as_json_list(self, db, fresh):
        result = TicketService.create_ticket(
            db, agent_id="A", metric_name="mem", severity="P1",
            detector="det_alpha", meta="{}", message="oom",
        )
        s = fresh()
        ticket = s.query(Ticket).filter_by(id=result["ticket_id"]).first()
        detectors = json.loads(ticket.detectors)
        assert isinstance(detectors, list)
        assert "det_alpha" in detectors


class TestDeduplication:

    def test_same_agent_metric_severity_is_merged(self, SessionFactory, fresh):
        s1 = SessionFactory()
        TicketService.create_ticket(
            s1, agent_id="A", metric_name="cpu", severity="P2",
            detector="det1", meta="{}", message="first",
        )
        s2 = SessionFactory()
        result = TicketService.create_ticket(
            s2, agent_id="A", metric_name="cpu", severity="P2",
            detector="det1", meta="{}", message="second",
        )

        assert result["merged"]  is True
        assert result["created"] is False
        assert result["occurrence_count"] == 2

        s = fresh()
        assert s.query(Ticket).filter_by(agent_id="A", metric_name="cpu", severity="P2").count() == 1

    def test_occurrence_count_increments_on_each_merge(self, SessionFactory):
        r = None
        for i in range(5):
            s = SessionFactory()
            r = TicketService.create_ticket(
                s, agent_id="A", metric_name="cpu", severity="P2",
                detector="det1", meta="{}", message=f"event {i}",
            )
        assert r["occurrence_count"] == 5

    def test_new_detector_added_to_detectors_list(self, SessionFactory, fresh):
        s1 = SessionFactory()
        TicketService.create_ticket(
            s1, agent_id="A", metric_name="cpu", severity="P2",
            detector="det1", meta="{}", message="msg",
        )
        s2 = SessionFactory()
        result = TicketService.create_ticket(
            s2, agent_id="A", metric_name="cpu", severity="P2",
            detector="det2", meta="{}", message="msg",
        )
        s = fresh()
        ticket = s.query(Ticket).filter_by(id=result["ticket_id"]).first()
        detectors = json.loads(ticket.detectors)
        assert "det1" in detectors
        assert "det2" in detectors

    def test_same_detector_not_duplicated_in_list(self, SessionFactory, fresh):
        for _ in range(3):
            s = SessionFactory()
            TicketService.create_ticket(
                s, agent_id="A", metric_name="cpu", severity="P2",
                detector="det1", meta="{}", message="msg",
            )
        s = fresh()
        ticket = s.query(Ticket).filter_by(agent_id="A", metric_name="cpu", severity="P2").first()
        detectors = json.loads(ticket.detectors)
        assert detectors.count("det1") == 1

    def test_message_updated_to_latest_on_merge(self, SessionFactory, fresh):
        s1 = SessionFactory()
        TicketService.create_ticket(
            s1, agent_id="A", metric_name="cpu", severity="P2",
            detector="d", meta="{}", message="old message",
        )
        s2 = SessionFactory()
        result = TicketService.create_ticket(
            s2, agent_id="A", metric_name="cpu", severity="P2",
            detector="d", meta="{}", message="new message",
        )
        s = fresh()
        ticket = s.query(Ticket).filter_by(id=result["ticket_id"]).first()
        assert ticket.message == "new message"

    def test_last_occurred_at_updated_on_merge(self, SessionFactory, fresh):
        s1 = SessionFactory()
        TicketService.create_ticket(
            s1, agent_id="A", metric_name="cpu", severity="P2",
            detector="d", meta="{}", message="first",
        )
        before_second = datetime.now()
        s2 = SessionFactory()
        result = TicketService.create_ticket(
            s2, agent_id="A", metric_name="cpu", severity="P2",
            detector="d", meta="{}", message="second",
        )
        s = fresh()
        ticket = s.query(Ticket).filter_by(id=result["ticket_id"]).first()
        assert ticket.last_occurred_at >= before_second - timedelta(seconds=1)

    def test_first_occurred_at_not_changed_on_merge(self, SessionFactory, fresh):
        s1 = SessionFactory()
        r1 = TicketService.create_ticket(
            s1, agent_id="A", metric_name="cpu", severity="P2",
            detector="d", meta="{}", message="first",
        )
        s_read = fresh()
        original_first = s_read.query(Ticket).filter_by(id=r1["ticket_id"]).first().first_occurred_at
        s_read.close()

        s2 = SessionFactory()
        TicketService.create_ticket(
            s2, agent_id="A", metric_name="cpu", severity="P2",
            detector="d", meta="{}", message="second",
        )

        s3 = fresh()
        ticket = s3.query(Ticket).filter_by(agent_id="A", metric_name="cpu", severity="P2").first()
        assert ticket.first_occurred_at == original_first

    def test_different_agent_creates_separate_ticket(self, SessionFactory, fresh):
        s1 = SessionFactory()
        TicketService.create_ticket(
            s1, agent_id="A", metric_name="cpu", severity="P2",
            detector="d", meta="{}", message="msg",
        )
        s2 = SessionFactory()
        result = TicketService.create_ticket(
            s2, agent_id="B", metric_name="cpu", severity="P2",
            detector="d", meta="{}", message="msg",
        )
        assert result["created"] is True
        s = fresh()
        assert s.query(Ticket).filter_by(metric_name="cpu", severity="P2").count() == 2

    def test_different_metric_creates_separate_ticket(self, SessionFactory):
        s1 = SessionFactory()
        TicketService.create_ticket(
            s1, agent_id="A", metric_name="cpu",    severity="P2",
            detector="d", meta="{}", message="msg",
        )
        s2 = SessionFactory()
        result = TicketService.create_ticket(
            s2, agent_id="A", metric_name="memory", severity="P2",
            detector="d", meta="{}", message="msg",
        )
        assert result["created"] is True

    def test_different_severity_creates_separate_ticket(self, SessionFactory):
        s1 = SessionFactory()
        TicketService.create_ticket(
            s1, agent_id="A", metric_name="cpu", severity="P2",
            detector="d", meta="{}", message="msg",
        )
        s2 = SessionFactory()
        result = TicketService.create_ticket(
            s2, agent_id="A", metric_name="cpu", severity="P3",
            detector="d", meta="{}", message="msg",
        )
        assert result["created"] is True

    def test_closed_ticket_not_deduplicated(self, db, SessionFactory, fresh):
        make_ticket(db, agent_id="A", metric_name="cpu", severity="P2", status="CLOSED")
        s2 = SessionFactory()
        result = TicketService.create_ticket(
            s2, agent_id="A", metric_name="cpu", severity="P2",
            detector="d", meta="{}", message="new event",
        )
        assert result["created"] is True

    def test_dedup_disabled_always_creates_new_ticket(self, SessionFactory, fresh):
        s1 = SessionFactory()
        TicketService.create_ticket(
            s1, agent_id="A", metric_name="cpu", severity="P2",
            detector="d", meta="{}", message="msg", dedup=False,
        )
        s2 = SessionFactory()
        result = TicketService.create_ticket(
            s2, agent_id="A", metric_name="cpu", severity="P2",
            detector="d", meta="{}", message="msg", dedup=False,
        )
        assert result["created"] is True
        s = fresh()
        assert s.query(Ticket).filter_by(agent_id="A", metric_name="cpu", severity="P2").count() == 2


class TestP4Behaviour:

    def test_p4_ticket_is_created_in_db(self, db, fresh):
        result = TicketService.create_ticket(
            db, agent_id="A", metric_name="disk", severity="P4",
            detector="d", meta="{}", message="low priority",
        )
        assert result["created"] is True
        assert result["is_p4"]   is True
        s = fresh()
        assert s.query(Ticket).filter_by(severity="P4").count() == 1

    def test_p4_tickets_are_never_deduplicated(self, SessionFactory, fresh):
        for _ in range(3):
            s = SessionFactory()
            TicketService.create_ticket(
                s, agent_id="A", metric_name="disk", severity="P4",
                detector="d", meta="{}", message="p4 event",
            )
        s = fresh()
        assert s.query(Ticket).filter_by(severity="P4").count() == 3

    def test_p4_excluded_from_get_tickets_by_default(self, SessionFactory, fresh):
        s1 = SessionFactory()
        TicketService.create_ticket(
            s1, agent_id="A", metric_name="cpu",  severity="P2",
            detector="d", meta="{}", message="visible",
        )
        s2 = SessionFactory()
        TicketService.create_ticket(
            s2, agent_id="A", metric_name="disk", severity="P4",
            detector="d", meta="{}", message="hidden",
        )
        s = fresh()
        tickets = TicketService.get_tickets(s, agent_id="A")
        assert all(t["severity"] != "P4" for t in tickets)

    def test_p4_visible_when_include_p4_true(self, SessionFactory, fresh):
        s1 = SessionFactory()
        TicketService.create_ticket(
            s1, agent_id="A", metric_name="disk", severity="P4",
            detector="d", meta="{}", message="audit",
        )
        s = fresh()
        tickets = TicketService.get_tickets(s, agent_id="A", include_p4=True)
        assert any(t["severity"] == "P4" for t in tickets)


class TestDedupWindowBoundary:

    def test_event_just_inside_window_is_merged(self, db, SessionFactory):
        window   = TicketService.DEDUP_WINDOW_MINUTES
        old_time = datetime.now() - timedelta(minutes=window - 1)
        make_ticket(
            db, agent_id="A", metric_name="cpu", severity="P2",
            first_occurred_at=old_time, last_occurred_at=old_time,
        )
        s2 = SessionFactory()
        result = TicketService.create_ticket(
            s2, agent_id="A", metric_name="cpu", severity="P2",
            detector="d", meta="{}", message="inside",
        )
        assert result["merged"] is True

    def test_event_just_outside_window_creates_new_ticket(self, db, SessionFactory):
        window   = TicketService.DEDUP_WINDOW_MINUTES
        old_time = datetime.now() - timedelta(minutes=window + 1)
        make_ticket(
            db, agent_id="A", metric_name="cpu", severity="P2",
            first_occurred_at=old_time, last_occurred_at=old_time,
        )
        s2 = SessionFactory()
        result = TicketService.create_ticket(
            s2, agent_id="A", metric_name="cpu", severity="P2",
            detector="d", meta="{}", message="outside",
        )
        assert result["created"] is True


class TestGetTickets:

    def test_returns_tickets_ordered_by_recency(self, db, fresh):
        old_time = datetime.now() - timedelta(hours=2)
        new_time = datetime.now()
        make_ticket(db, agent_id="A", metric_name="cpu",    severity="P2", last_occurred_at=old_time)
        make_ticket(db, agent_id="A", metric_name="memory", severity="P2", last_occurred_at=new_time)

        s = fresh()
        tickets = TicketService.get_tickets(s, agent_id="A")
        assert tickets[0]["metric_name"] == "memory"
        assert tickets[1]["metric_name"] == "cpu"

    def test_does_not_return_tickets_for_other_agents(self, db, fresh):
        make_ticket(db, agent_id="A", metric_name="cpu", severity="P2")
        make_ticket(db, agent_id="B", metric_name="cpu", severity="P2")

        s = fresh()
        tickets = TicketService.get_tickets(s, agent_id="A")
        assert all(t["agent_id"] == "A" for t in tickets)

    def test_limit_is_respected(self, db, fresh):
        for i in range(10):
            make_ticket(db, agent_id="A", metric_name=f"m{i}", severity="P2")

        s = fresh()
        tickets = TicketService.get_tickets(s, agent_id="A", limit=5)
        assert len(tickets) <= 5

    def test_detectors_returned_as_python_list(self, db, fresh):
        make_ticket(db, agent_id="A", metric_name="cpu", severity="P2", detectors=["det1", "det2"])
        s = fresh()
        tickets = TicketService.get_tickets(s, agent_id="A")
        assert isinstance(tickets[0]["detectors"], list)
