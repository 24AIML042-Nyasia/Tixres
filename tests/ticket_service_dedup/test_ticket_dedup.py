import pytest
import json
from unittest.mock import MagicMock
from datetime import datetime, timedelta
from ticket_service.ticketService import TicketService, Ticket  # adjust import


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    return MagicMock()

@pytest.fixture
def base_ticket():
    t = MagicMock(spec=Ticket)
    t.id = 1
    t.agent_id = "agent_001"
    t.metric_name = "cpu_usage"
    t.severity = "HIGH"
    t.purpose = "general"
    t.status = "OPEN"
    t.detectors = json.dumps(["detector_a"])
    t.occurrence_count = 1
    t.first_occurred_at = datetime.now() - timedelta(minutes=10)
    t.last_occurred_at = datetime.now() - timedelta(minutes=10)
    t.message = "CPU usage high"
    t.meta = "{}"
    return t

TICKET_DEFAULTS = dict(
    agent_id="agent_001",
    metric_name="cpu_usage",
    severity="HIGH",
    purpose="general",
    detector="detector_a",
    meta="{}",
    message="CPU usage high",
)

def make_query_mock(db, return_value):
    """Wire db.query(...).filter(...).first() → return_value."""
    db.query.return_value.filter.return_value.first.return_value = return_value


# ── create_ticket: new ticket ─────────────────────────────────────────────────

class TestCreateTicketNew:

    def test_created_true_when_no_duplicate(self, db):
        make_query_mock(db, None)
        result = TicketService.create_ticket(db=db, **TICKET_DEFAULTS)
        assert result["created"] is True
        assert result["merged"] is False

    def test_occurrence_count_is_1(self, db):
        make_query_mock(db, None)
        result = TicketService.create_ticket(db=db, **TICKET_DEFAULTS)
        assert result["occurrence_count"] == 1

    def test_correct_fields_on_insert(self, db):
        make_query_mock(db, None)
        TicketService.create_ticket(db=db, **TICKET_DEFAULTS)
        ticket = db.add.call_args[0][0]
        assert ticket.agent_id == "agent_001"
        assert ticket.metric_name == "cpu_usage"
        assert ticket.severity == "HIGH"
        assert ticket.purpose == "general"
        assert ticket.status == "OPEN"
        assert ticket.message == "CPU usage high"

    def test_detectors_initialized_as_single_item_list(self, db):
        make_query_mock(db, None)
        TicketService.create_ticket(db=db, **TICKET_DEFAULTS)
        ticket = db.add.call_args[0][0]
        assert json.loads(ticket.detectors) == ["detector_a"]

    def test_db_commit_called(self, db):
        make_query_mock(db, None)
        TicketService.create_ticket(db=db, **TICKET_DEFAULTS)
        db.commit.assert_called_once()

    def test_db_add_called_with_ticket(self, db):
        make_query_mock(db, None)
        TicketService.create_ticket(db=db, **TICKET_DEFAULTS)
        db.add.assert_called_once()
        assert isinstance(db.add.call_args[0][0], Ticket)


# ── create_ticket: merge ──────────────────────────────────────────────────────

class TestCreateTicketMerge:

    def test_merged_true_when_duplicate_found(self, db, base_ticket):
        make_query_mock(db, base_ticket)
        result = TicketService.create_ticket(db=db, **TICKET_DEFAULTS)
        assert result["merged"] is True
        assert result["created"] is False

    def test_occurrence_count_incremented(self, db, base_ticket):
        base_ticket.occurrence_count = 3
        make_query_mock(db, base_ticket)
        result = TicketService.create_ticket(db=db, **TICKET_DEFAULTS)
        assert result["occurrence_count"] == 4

    def test_new_detector_appended(self, db, base_ticket):
        make_query_mock(db, base_ticket)
        TicketService.create_ticket(db=db, **{**TICKET_DEFAULTS, "detector": "detector_b"})
        assert "detector_b" in json.loads(base_ticket.detectors)

    def test_existing_detector_preserved(self, db, base_ticket):
        make_query_mock(db, base_ticket)
        TicketService.create_ticket(db=db, **{**TICKET_DEFAULTS, "detector": "detector_b"})
        assert "detector_a" in json.loads(base_ticket.detectors)

    def test_duplicate_detector_not_added_twice(self, db, base_ticket):
        base_ticket.detectors = json.dumps(["detector_a"])
        make_query_mock(db, base_ticket)
        TicketService.create_ticket(db=db, **TICKET_DEFAULTS)  # detector_a again
        assert json.loads(base_ticket.detectors).count("detector_a") == 1

    def test_message_updated(self, db, base_ticket):
        make_query_mock(db, base_ticket)
        TicketService.create_ticket(db=db, **{**TICKET_DEFAULTS, "message": "New message"})
        assert base_ticket.message == "New message"

    def test_last_occurred_at_updated(self, db, base_ticket):
        old_time = base_ticket.last_occurred_at
        make_query_mock(db, base_ticket)
        TicketService.create_ticket(db=db, **TICKET_DEFAULTS)
        assert base_ticket.last_occurred_at > old_time

    def test_first_occurred_at_unchanged(self, db, base_ticket):
        original = base_ticket.first_occurred_at
        make_query_mock(db, base_ticket)
        TicketService.create_ticket(db=db, **TICKET_DEFAULTS)
        assert base_ticket.first_occurred_at == original

    def test_no_new_row_inserted(self, db, base_ticket):
        make_query_mock(db, base_ticket)
        TicketService.create_ticket(db=db, **TICKET_DEFAULTS)
        db.add.assert_not_called()

    def test_existing_ticket_id_returned(self, db, base_ticket):
        base_ticket.id = 42
        make_query_mock(db, base_ticket)
        result = TicketService.create_ticket(db=db, **TICKET_DEFAULTS)
        assert result["ticket_id"] == 42


# ── create_ticket: deduplication ─────────────────────────────────────────────

class TestDeduplication:

    def test_dedup_false_always_inserts(self, db, base_ticket):
        make_query_mock(db, base_ticket)
        result = TicketService.create_ticket(db=db, dedup=False, **TICKET_DEFAULTS)
        assert result["created"] is True
        assert result["merged"] is False

    def test_dedup_false_skips_query(self, db):
        TicketService.create_ticket(db=db, dedup=False, **TICKET_DEFAULTS)
        db.query.assert_not_called()

    def test_default_dedup_window_constant(self):
        assert TicketService.DEDUP_WINDOW_MINUTES == 60

    def test_dedup_fields_constant(self):
        assert set(TicketService.DEDUP_FIELDS) == {"agent_id", "metric_name", "severity", "purpose"}

    def test_different_severity_no_merge(self, db):
        make_query_mock(db, None)
        result = TicketService.create_ticket(db=db, **{**TICKET_DEFAULTS, "severity": "LOW"})
        assert result["created"] is True

    def test_different_metric_no_merge(self, db):
        make_query_mock(db, None)
        result = TicketService.create_ticket(db=db, **{**TICKET_DEFAULTS, "metric_name": "mem_usage"})
        assert result["created"] is True

    def test_different_agent_no_merge(self, db):
        make_query_mock(db, None)
        result = TicketService.create_ticket(db=db, **{**TICKET_DEFAULTS, "agent_id": "agent_999"})
        assert result["created"] is True

    def test_closed_ticket_not_matched(self, db, base_ticket):
        base_ticket.status = "CLOSED"
        make_query_mock(db, None)  # closed ticket filtered out at query level
        result = TicketService.create_ticket(db=db, **TICKET_DEFAULTS)
        assert result["created"] is True

    def test_custom_dedup_window_passed(self, db):
        make_query_mock(db, None)
        # Should not raise; custom window forwarded to query filter
        TicketService.create_ticket(db=db, dedup_window_minutes=5, **TICKET_DEFAULTS)
        db.query.assert_called()


# ── get_tickets ───────────────────────────────────────────────────────────────

class TestGetTickets:

    def _mock_all(self, db, tickets):
        db.query.return_value.filter.return_value \
            .order_by.return_value.limit.return_value.all.return_value = tickets

    def test_returns_list(self, db, base_ticket):
        self._mock_all(db, [base_ticket])
        assert isinstance(TicketService.get_tickets(db=db, agent_id="agent_001"), list)

    def test_detectors_returned_as_python_list(self, db, base_ticket):
        base_ticket.detectors = json.dumps(["detector_a", "detector_b"])
        self._mock_all(db, [base_ticket])
        result = TicketService.get_tickets(db=db, agent_id="agent_001")
        assert isinstance(result[0]["detectors"], list)

    def test_empty_list_for_unknown_agent(self, db):
        self._mock_all(db, [])
        assert TicketService.get_tickets(db=db, agent_id="ghost") == []

    def test_default_limit_is_100(self, db):
        self._mock_all(db, [])
        TicketService.get_tickets(db=db, agent_id="agent_001")
        limit_arg = db.query.return_value.filter.return_value \
            .order_by.return_value.limit.call_args[0][0]
        assert limit_arg == 100

    def test_custom_limit_respected(self, db):
        self._mock_all(db, [])
        TicketService.get_tickets(db=db, agent_id="agent_001", limit=25)
        limit_arg = db.query.return_value.filter.return_value \
            .order_by.return_value.limit.call_args[0][0]
        assert limit_arg == 25

    def test_multiple_tickets_returned(self, db, base_ticket):
        t2 = MagicMock(spec=Ticket)
        t2.id = 2
        t2.agent_id = "agent_001"
        t2.detectors = json.dumps(["detector_b"])
        self._mock_all(db, [base_ticket, t2])
        result = TicketService.get_tickets(db=db, agent_id="agent_001")
        assert len(result) == 2

    def test_ordered_by_last_occurred_at_desc(self, db, base_ticket):
        t2 = MagicMock(spec=Ticket)
        t2.last_occurred_at = datetime.now() - timedelta(hours=1)
        t2.detectors = json.dumps([])
        self._mock_all(db, [base_ticket, t2])
        result = TicketService.get_tickets(db=db, agent_id="agent_001")
        assert result[0]["last_occurred_at"] >= result[1]["last_occurred_at"]


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_empty_detectors_list_on_merge(self, db, base_ticket):
        base_ticket.detectors = json.dumps([])
        make_query_mock(db, base_ticket)
        TicketService.create_ticket(db=db, **TICKET_DEFAULTS)
        assert "detector_a" in json.loads(base_ticket.detectors)

    def test_meta_stored_as_provided(self, db):
        make_query_mock(db, None)
        meta = json.dumps({"threshold": 90, "host": "server1"})
        TicketService.create_ticket(db=db, **{**TICKET_DEFAULTS, "meta": meta})
        assert db.add.call_args[0][0].meta == meta

    def test_all_severity_levels_accepted(self, db):
        for severity in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
            make_query_mock(db, None)
            result = TicketService.create_ticket(db=db, **{**TICKET_DEFAULTS, "severity": severity})
            assert result["created"] is True
