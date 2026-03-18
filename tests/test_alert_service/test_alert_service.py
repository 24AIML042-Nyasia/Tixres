"""
tests/unit/test_alert_service.py
=================================
Unit tests for the AlertService correlation engine.

Coverage
--------
✅ Good  : SINGLE creation, SINGLE→GROUP escalation, multi-agent growth
❌ Bad   : no duplicate alerts, P4 silent, agent list preservation
⚠️  Edge : repeated same-agent, empty agent_ids corruption, 1000-agent scale,
            mixed severity isolation, cooldown helpers, resolution helpers
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from freezegun import freeze_time

from tests.test_alert_service.conftest import make_ticket, make_alert
from alert_service.alert_service import (
    process_ticket,
    compute_cooldown,
    get_resolution_window,
    is_resolved,
)
from alert_service.models import Alert


# ===========================================================================
# ✅ GOOD CASES
# ===========================================================================

class TestSingleAlertCreation:
    """✅ Case 1 — First event from one agent."""

    def test_creates_single_alert_for_first_ticket(self, db):
        ticket = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2")
        alert  = process_ticket(db, ticket)

        assert alert is not None
        assert alert.type             == "SINGLE"
        assert alert.status           == "OPEN"
        assert alert.metric_name      == "cpu"
        assert alert.severity         == "P2"
        assert alert.total_occurrence == 1
        assert json.loads(alert.agent_ids) == ["A"]

    def test_exactly_one_alert_row_created(self, db):
        ticket = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2")
        process_ticket(db, ticket)
        assert db.query(Alert).filter_by(metric_name="cpu", severity="P2").count() == 1

    def test_alert_first_seen_at_and_last_seen_at_populated(self, db):
        before = datetime.now()
        ticket = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2")
        alert  = process_ticket(db, ticket)
        after  = datetime.now()

        assert alert.first_seen_at is not None
        assert alert.last_seen_at  is not None
        # last_seen_at should be within the test window
        assert before <= alert.last_seen_at <= after

    def test_cooldown_until_set_on_creation(self, db):
        ticket = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2")
        alert  = process_ticket(db, ticket)
        assert alert.cooldown_until is not None
        assert alert.cooldown_until > datetime.now()


class TestSameAgentRepeatedEvents:
    """✅ Case 2 — Same agent fires multiple times (dedup already merged ticket)."""

    def test_repeated_same_agent_stays_single(self, db):
        """Even if occurrence_count grows, type must stay SINGLE."""
        ticket = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2", occurrence_count=5)
        process_ticket(db, ticket)   # create

        ticket2 = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2", occurrence_count=3)
        alert = process_ticket(db, ticket2)  # update

        assert alert.type == "SINGLE"
        assert json.loads(alert.agent_ids) == ["A"]

    def test_total_occurrence_accumulates(self, db):
        t1 = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2", occurrence_count=3)
        process_ticket(db, t1)

        t2 = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2", occurrence_count=4)
        alert = process_ticket(db, t2)

        assert alert.total_occurrence == 7

    def test_last_seen_at_updated_on_same_agent_repeat(self, db):
        t1 = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2")
        process_ticket(db, t1)

        before_second = datetime.now()
        t2 = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2")
        alert = process_ticket(db, t2)

        assert alert.last_seen_at >= before_second


class TestGroupEscalation:
    """✅ Case 3 — Second distinct agent escalates SINGLE → GROUP."""

    def test_second_agent_escalates_to_group(self, db):
        tA = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2")
        process_ticket(db, tA)

        tB = make_ticket(db, agent_id="B", metric_name="cpu", severity="P2")
        alert = process_ticket(db, tB)

        assert alert.type == "GROUP"

    def test_both_agents_in_agent_ids_after_escalation(self, db):
        tA = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2")
        process_ticket(db, tA)

        tB = make_ticket(db, agent_id="B", metric_name="cpu", severity="P2")
        alert = process_ticket(db, tB)

        agents = set(json.loads(alert.agent_ids))
        assert {"A", "B"} == agents

    def test_only_one_alert_row_after_escalation(self, db):
        """Escalation must update the existing row, not insert a new one."""
        tA = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2")
        process_ticket(db, tA)

        tB = make_ticket(db, agent_id="B", metric_name="cpu", severity="P2")
        process_ticket(db, tB)

        assert db.query(Alert).filter_by(metric_name="cpu", severity="P2", status="OPEN").count() == 1

    def test_group_stays_group_after_third_agent(self, db):
        """Once GROUP, type must never go back to SINGLE."""
        for agent in ["A", "B", "C"]:
            t = make_ticket(db, agent_id=agent, metric_name="cpu", severity="P2")
            alert = process_ticket(db, t)

        assert alert.type == "GROUP"
        assert len(json.loads(alert.agent_ids)) == 3


class TestMultipleAgentsContinuousActivity:
    """✅ Case 4 — Many agents, one alert, no explosion."""

    def test_four_agents_produce_one_alert(self, db):
        for agent in ["A", "B", "C", "D"]:
            t = make_ticket(db, agent_id=agent, metric_name="cpu", severity="P2")
            process_ticket(db, t)

        assert db.query(Alert).filter_by(metric_name="cpu", severity="P2", status="OPEN").count() == 1

    def test_agent_ids_contain_all_four_agents(self, db):
        for agent in ["A", "B", "C", "D"]:
            t = make_ticket(db, agent_id=agent, metric_name="cpu", severity="P2")
            alert = process_ticket(db, t)

        assert set(json.loads(alert.agent_ids)) == {"A", "B", "C", "D"}


# ===========================================================================
# ❌ BAD CASES — System must NOT do these
# ===========================================================================

class TestP4Silent:
    """❌ Case: P4 must never produce an alert."""

    def test_p4_ticket_returns_none(self, db):
        ticket = make_ticket(db, agent_id="A", metric_name="disk", severity="P4")
        result = process_ticket(db, ticket)
        assert result is None

    def test_p4_ticket_creates_no_alert_row(self, db):
        ticket = make_ticket(db, agent_id="A", metric_name="disk", severity="P4")
        process_ticket(db, ticket)
        assert db.query(Alert).filter_by(metric_name="disk").count() == 0

    def test_p4_does_not_affect_existing_p2_alert(self, db):
        """A P4 event on the same metric must not touch an existing P2 alert."""
        t_p2 = make_ticket(db, agent_id="A", metric_name="disk", severity="P2")
        alert_before = process_ticket(db, t_p2)
        occ_before = alert_before.total_occurrence

        t_p4 = make_ticket(db, agent_id="B", metric_name="disk", severity="P4")
        process_ticket(db, t_p4)

        db.refresh(alert_before)
        assert alert_before.total_occurrence == occ_before


class TestNoDuplicateAlerts:
    """❌ Case: Two agents on same metric must not create two alerts."""

    def test_no_duplicate_alerts_for_same_metric_severity(self, db):
        tA = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2")
        tB = make_ticket(db, agent_id="B", metric_name="cpu", severity="P2")
        process_ticket(db, tA)
        process_ticket(db, tB)

        count = db.query(Alert).filter_by(
            metric_name="cpu", severity="P2", status="OPEN"
        ).count()
        assert count == 1


class TestAgentListPreservation:
    """❌ Case: Updating alert must never drop existing agents."""

    def test_existing_agents_preserved_when_new_agent_added(self, db):
        """[A, B] + C → [A, B, C], not [C]."""
        alert = make_alert(db, agent_ids=["A", "B"], metric_name="cpu", severity="P2")
        ticket = make_ticket(db, agent_id="C", metric_name="cpu", severity="P2")
        updated = process_ticket(db, ticket)

        agents = set(json.loads(updated.agent_ids))
        assert {"A", "B", "C"} == agents

    def test_same_agent_not_duplicated_in_list(self, db):
        """Feeding the same agent repeatedly must not bloat agent_ids."""
        tA1 = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2")
        process_ticket(db, tA1)

        tA2 = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2")
        alert = process_ticket(db, tA2)

        agents = json.loads(alert.agent_ids)
        assert agents.count("A") == 1


# ===========================================================================
# ⚠️  EDGE CASES
# ===========================================================================

class TestMixedSeveritySameMetric:
    """⚠️ Case 10 — CPU P2 and CPU P3 must produce two separate alerts."""

    def test_different_severities_create_separate_alerts(self, db):
        t2 = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2")
        t3 = make_ticket(db, agent_id="A", metric_name="cpu", severity="P3")
        process_ticket(db, t2)
        process_ticket(db, t3)

        assert db.query(Alert).filter_by(metric_name="cpu", status="OPEN").count() == 2

    def test_p2_alert_not_polluted_by_p3_occurrence(self, db):
        t2 = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2", occurrence_count=5)
        t3 = make_ticket(db, agent_id="A", metric_name="cpu", severity="P3", occurrence_count=10)
        a2 = process_ticket(db, t2)
        process_ticket(db, t3)

        db.refresh(a2)
        assert a2.total_occurrence == 5   # unchanged by P3 activity


class TestCorruptedAlertData:
    """⚠️ Case 6 — Alert with empty / corrupted agent_ids must recover."""

    def test_empty_agent_ids_recovers_with_incoming_agent(self, db):
        """alert.agent_ids = '[]' must not crash; incoming agent is added."""
        alert = make_alert(db, agent_ids=[], metric_name="cpu", severity="P2")
        ticket = make_ticket(db, agent_id="X", metric_name="cpu", severity="P2")
        updated = process_ticket(db, ticket)

        agents = json.loads(updated.agent_ids)
        assert "X" in agents

    def test_none_agent_ids_treated_as_empty(self, db):
        """agent_ids=NULL in DB must not cause AttributeError."""
        alert = make_alert(db, agent_ids=[], metric_name="cpu", severity="P2")
        alert.agent_ids = None
        db.commit()

        ticket = make_ticket(db, agent_id="Y", metric_name="cpu", severity="P2")
        # Should not raise
        updated = process_ticket(db, ticket)
        assert "Y" in json.loads(updated.agent_ids)


class TestHugeAgentExplosion:
    """⚠️ Case 7 — 1000 distinct agents → exactly ONE alert."""

    def test_thousand_agents_produce_one_alert(self, db):
        for i in range(1000):
            t = make_ticket(db, agent_id=f"agent_{i}", metric_name="cpu", severity="P2")
            process_ticket(db, t)

        assert db.query(Alert).filter_by(metric_name="cpu", severity="P2", status="OPEN").count() == 1

    def test_thousand_agents_all_in_agent_ids(self, db):
        for i in range(1000):
            t = make_ticket(db, agent_id=f"agent_{i}", metric_name="cpu", severity="P2")
            alert = process_ticket(db, t)

        agents = json.loads(alert.agent_ids)
        assert len(agents) == 1000
        assert "agent_0"   in agents
        assert "agent_999" in agents

    def test_thousand_agents_alert_is_group(self, db):
        for i in range(1000):
            t = make_ticket(db, agent_id=f"agent_{i}", metric_name="cpu", severity="P2")
            alert = process_ticket(db, t)
        assert alert.type == "GROUP"


class TestNewAlertAfterClosure:
    """✅ Case 7 — New ticket after old alert is CLOSED must create a fresh alert."""

    def test_new_ticket_after_closed_alert_creates_new_alert(self, db):
        # Pre-existing CLOSED alert
        make_alert(db, metric_name="cpu", severity="P2", status="CLOSED")

        ticket = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2")
        alert  = process_ticket(db, ticket)

        assert alert.status == "OPEN"
        # Must be a brand-new row, not the old one
        assert db.query(Alert).filter_by(metric_name="cpu", severity="P2", status="OPEN").count() == 1

    def test_new_alert_after_closure_starts_as_single(self, db):
        make_alert(db, metric_name="cpu", severity="P2", status="CLOSED")
        ticket = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2")
        alert  = process_ticket(db, ticket)
        assert alert.type == "SINGLE"


# ===========================================================================
# Helper function tests
# ===========================================================================

class TestComputeCooldown:
    def test_p1_cooldown_is_10_minutes(self):
        before = datetime.now()
        cd = compute_cooldown("P1")
        assert timedelta(minutes=9, seconds=59) < cd - before <= timedelta(minutes=10, seconds=1)

    def test_p2_cooldown_is_15_minutes(self):
        before = datetime.now()
        cd = compute_cooldown("P2")
        assert timedelta(minutes=14, seconds=59) < cd - before <= timedelta(minutes=15, seconds=1)

    def test_p3_cooldown_is_30_minutes(self):
        before = datetime.now()
        cd = compute_cooldown("P3")
        assert timedelta(minutes=29, seconds=59) < cd - before <= timedelta(minutes=30, seconds=1)

    def test_unknown_severity_defaults_to_30_minutes(self):
        before = datetime.now()
        cd = compute_cooldown("UNKNOWN")
        assert timedelta(minutes=29, seconds=59) < cd - before <= timedelta(minutes=30, seconds=1)


class TestGetResolutionWindow:
    def test_p1_window_is_2_hours(self):
        assert get_resolution_window("P1") == timedelta(hours=2)

    def test_p2_window_is_6_hours(self):
        assert get_resolution_window("P2") == timedelta(hours=6)

    def test_p3_window_is_12_hours(self):
        assert get_resolution_window("P3") == timedelta(hours=12)

    def test_p4_window_is_24_hours(self):
        assert get_resolution_window("P4") == timedelta(hours=24)

    def test_unknown_severity_defaults_to_24_hours(self):
        assert get_resolution_window("UNKNOWN") == timedelta(hours=24)


class TestIsResolved:
    def test_alert_not_resolved_when_within_window(self, db):
        # last_seen_at = 1 hour ago; P2 window = 6 hours
        alert = make_alert(
            db,
            severity="P2",
            last_seen_at=datetime.now() - timedelta(hours=1),
        )
        assert is_resolved(alert) is False

    def test_alert_resolved_when_past_window(self, db):
        # last_seen_at = 7 hours ago; P2 window = 6 hours → resolved
        alert = make_alert(
            db,
            severity="P2",
            last_seen_at=datetime.now() - timedelta(hours=7),
        )
        assert is_resolved(alert) is True

    def test_alert_not_resolved_one_second_before_boundary(self, db):
        """1 second before the P2 window expires the alert must still be OPEN.

        The exact-boundary case (now - last_seen == 6h exactly) is impossible
        to test without freezing the clock because real-clock execution always
        adds a few microseconds.  We therefore test 1 second *before* the
        window, which is deterministic and covers the same code path.
        """
        alert = make_alert(
            db,
            severity="P2",
            last_seen_at=datetime.now() - timedelta(hours=5, minutes=59, seconds=59),
        )
        assert is_resolved(alert) is False

    def test_alert_with_none_last_seen_at_is_not_resolved(self, db):
        alert = make_alert(db, severity="P2", last_seen_at=datetime.now())
        alert.last_seen_at = None
        db.commit()
        assert is_resolved(alert) is False

    def test_future_last_seen_at_clock_skew_does_not_crash(self, db):
        """⚠️ Clock skew: last_seen_at in the future must return False, not raise."""
        alert = make_alert(
            db,
            severity="P2",
            last_seen_at=datetime.now() + timedelta(hours=10),
        )
        # Should return False (not resolved), not throw
        assert is_resolved(alert) is False