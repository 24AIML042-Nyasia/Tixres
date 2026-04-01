"""
tests/integration/test_full_lifecycle.py
=========================================
Integration tests — full Ticket → Alert → Resolution pipeline.

Session management note
-----------------------
TicketService.create_ticket() closes the session it receives.  The ingest()
helper therefore opens a *new* session for each TicketService call.
AlertService functions (process_ticket, ResolutionService) do NOT close their
session, so a single session can be reused across those calls.

All tests use the function-scoped `engine` fixture (fresh schema per test).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from tests.test_alert_service.conftest import make_alert, make_ticket
from ticket_service.ticketService import TicketService
from ticket_service.models import Ticket
from alert_service.alert_service import process_ticket
from alert_service.resolution_service import ResolutionService
from alert_service.models import Alert


# ---------------------------------------------------------------------------
# Helper: create ticket via TicketService, then process via AlertService.
# Opens its own fresh session for the TicketService call, then uses the
# provided `alert_session` (which stays open) for AlertService.
# ---------------------------------------------------------------------------

def ingest(SessionFactory, alert_session, agent_id, metric_name, severity,
           detector="det", message="msg", dedup=True):
    """
    Create (or merge) a ticket then feed it into AlertService.

    Returns (ticket_service_result, alert).
    `alert` is attached to `alert_session`.
    """
    # TicketService needs its own session — it will close it internally
    ts_session = SessionFactory()
    result = TicketService.create_ticket(
        ts_session, agent_id=agent_id, metric_name=metric_name, severity=severity,
        detector=detector, meta="{}", message=message, dedup=dedup,
    )
    # Re-query the ticket in the alert_session so it is attached
    ticket = alert_session.query(Ticket).filter_by(id=result["ticket_id"]).first()
    alert  = process_ticket(alert_session, ticket)
    return result, alert


# ===========================================================================
# ✅ Full happy-path lifecycle
# ===========================================================================

class TestLifecycleHappyPath:

    def test_case1_single_agent_produces_single_alert(self, SessionFactory):
        s = SessionFactory()
        _, alert = ingest(SessionFactory, s, "A", "cpu", "P2")

        assert alert is not None
        assert alert.type   == "SINGLE"
        assert alert.status == "OPEN"
        assert json.loads(alert.agent_ids) == ["A"]

    def test_case2_same_agent_repeated_stays_single(self, SessionFactory):
        s = SessionFactory()
        # dedup=False forces separate ticket rows so each process_ticket call
        # increments total_occurrence on the alert
        _, a1 = ingest(SessionFactory, s, "A", "cpu", "P2", dedup=False)
        for _ in range(3):
            _, alert = ingest(SessionFactory, s, "A", "cpu", "P2", dedup=False)

        assert alert.type == "SINGLE"
        assert alert.total_occurrence >= 4

    def test_case3_second_agent_escalates_to_group(self, SessionFactory):
        s = SessionFactory()
        ingest(SessionFactory, s, "A", "cpu", "P2")
        _, a2 = ingest(SessionFactory, s, "B", "cpu", "P2")

        assert a2.type == "GROUP"
        assert set(json.loads(a2.agent_ids)) == {"A", "B"}

    def test_case4_four_agents_one_alert_group(self, SessionFactory):
        s = SessionFactory()
        for agent in ["A", "B", "C", "D"]:
            ingest(SessionFactory, s, agent, "cpu", "P2")

        assert s.query(Alert).filter_by(
            metric_name="cpu", severity="P2", status="OPEN"
        ).count() == 1

    def test_case5_p4_ticket_stored_no_alert(self, SessionFactory):
        s = SessionFactory()
        result, alert = ingest(SessionFactory, s, "A", "disk", "P4")

        assert result["created"] is True
        assert alert is None
        assert s.query(Alert).filter_by(metric_name="disk").count() == 0

    def test_case6_resolution_closes_alert_and_tickets(self, db, SessionFactory):
        s = SessionFactory()
        stale_time = datetime.now() - timedelta(hours=7)
        alert  = make_alert(db, metric_name="cpu", severity="P2", last_seen_at=stale_time)
        ticket = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2")

        ResolutionService.run_resolution_pass(db)

        db.refresh(alert)
        db.refresh(ticket)

        assert alert.status  == "CLOSED"
        assert ticket.status == "CLOSED"

        meta = json.loads(ticket.meta)
        assert meta["auto_closed"]   is True
        assert meta["closed_reason"] == "resolution_window_expired"

    def test_case7_new_ticket_after_closure_fresh_alert(self, db, SessionFactory):
        make_alert(db, metric_name="cpu", severity="P2", status="CLOSED")

        s = SessionFactory()
        _, new_alert = ingest(SessionFactory, s, "A", "cpu", "P2")

        assert new_alert.status == "OPEN"
        assert new_alert.type   == "SINGLE"
        assert s.query(Alert).filter_by(
            metric_name="cpu", severity="P2", status="OPEN"
        ).count() == 1


# ===========================================================================
# ❌ Anti-patterns must NOT occur
# ===========================================================================

class TestNoBadBehaviours:

    def test_no_duplicate_alerts_two_agents(self, SessionFactory):
        s = SessionFactory()
        ingest(SessionFactory, s, "A", "cpu", "P2")
        ingest(SessionFactory, s, "B", "cpu", "P2")
        assert s.query(Alert).filter_by(
            metric_name="cpu", severity="P2", status="OPEN"
        ).count() == 1

    def test_p4_never_creates_alert(self, SessionFactory):
        s = SessionFactory()
        for agent in ["A", "B", "C"]:
            ingest(SessionFactory, s, agent, "disk", "P4")
        assert s.query(Alert).filter_by(metric_name="disk").count() == 0

    def test_closing_p2_alert_does_not_close_p1_ticket(self, db):
        p2_alert  = make_alert(db, metric_name="cpu", severity="P2",
                               last_seen_at=datetime.now() - timedelta(hours=7))
        p1_ticket = make_ticket(db, agent_id="A", metric_name="cpu", severity="P1")
        p2_ticket = make_ticket(db, agent_id="B", metric_name="cpu", severity="P2")

        ResolutionService.run_resolution_pass(db)

        db.refresh(p1_ticket)
        db.refresh(p2_ticket)

        assert p1_ticket.status == "OPEN"
        assert p2_ticket.status == "CLOSED"

    def test_alert_never_stays_open_forever(self, db):
        ancient = datetime.now() - timedelta(days=30)
        alert   = make_alert(db, severity="P3", last_seen_at=ancient)

        ResolutionService.run_resolution_pass(db)

        db.refresh(alert)
        assert alert.status == "CLOSED"


# ===========================================================================
# ⚠️  Edge-case integration scenarios
# ===========================================================================

class TestEdgeCasesIntegration:

    def test_multi_severity_same_metric_independent_lifecycle(self, db):
        stale = datetime.now() - timedelta(hours=7)
        fresh = datetime.now() - timedelta(hours=1)

        a_p2 = make_alert(db, metric_name="cpu", severity="P2", last_seen_at=stale)
        a_p3 = make_alert(db, metric_name="cpu", severity="P3", last_seen_at=fresh)
        t_p2 = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2")
        t_p3 = make_ticket(db, agent_id="A", metric_name="cpu", severity="P3")

        ResolutionService.run_resolution_pass(db)

        db.refresh(a_p2); db.refresh(a_p3)
        db.refresh(t_p2); db.refresh(t_p3)

        assert a_p2.status == "CLOSED"
        assert a_p3.status == "OPEN"
        assert t_p2.status == "CLOSED"
        assert t_p3.status == "OPEN"

    def test_full_cycle_two_iterations(self, db, SessionFactory):
        s = SessionFactory()
        _, alert1 = ingest(SessionFactory, s, "A", "cpu", "P2")
        assert alert1.status == "OPEN"
        alert1_id = alert1.id

        # Force expiry
        alert1.last_seen_at = datetime.now() - timedelta(hours=7)
        s.commit()

        ResolutionService.run_resolution_pass(s)
        s.refresh(alert1)
        assert alert1.status == "CLOSED"

        # Cycle 2 — needs a new alert_session since we'll be reading/writing alerts
        s2 = SessionFactory()
        _, alert2 = ingest(SessionFactory, s2, "A", "cpu", "P2")
        assert alert2.id     != alert1_id
        assert alert2.status == "OPEN"
        assert alert2.type   == "SINGLE"

    def test_meta_preserved_across_multiple_closure_fields(self, db):
        prior_meta = json.dumps({"env": "prod", "region": "us-east-1"})
        stale_time = datetime.now() - timedelta(hours=7)

        make_alert(db, metric_name="cpu", severity="P2", last_seen_at=stale_time)
        ticket = make_ticket(
            db, agent_id="A", metric_name="cpu", severity="P2", meta=prior_meta,
        )

        ResolutionService.run_resolution_pass(db)
        db.refresh(ticket)

        meta = json.loads(ticket.meta)
        assert meta["env"]           == "prod"
        assert meta["region"]        == "us-east-1"
        assert meta["auto_closed"]   is True
        assert meta["closed_reason"] == "resolution_window_expired"

    def test_p4_tickets_not_touched_by_resolution(self, db):
        stale = datetime.now() - timedelta(hours=7)
        make_alert(db, metric_name="cpu", severity="P2", last_seen_at=stale)
        p4_ticket = make_ticket(db, agent_id="A", metric_name="cpu", severity="P4")

        ResolutionService.run_resolution_pass(db)
        db.refresh(p4_ticket)
        assert p4_ticket.status == "OPEN"

    def test_high_frequency_ingestion_single_alert(self, SessionFactory):
        s_alert = SessionFactory()
        for i in range(100):
            ts = SessionFactory()
            r = TicketService.create_ticket(
                ts, agent_id="A", metric_name="cpu", severity="P1",
                detector="det", meta="{}", message=f"burst {i}",
            )
            ticket = s_alert.query(Ticket).filter_by(id=r["ticket_id"]).first()
            process_ticket(s_alert, ticket)

        assert s_alert.query(Alert).filter_by(
            metric_name="cpu", severity="P1", status="OPEN"
        ).count() == 1
