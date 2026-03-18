"""
tests/unit/test_resolution_service.py
=======================================
Unit tests for ResolutionService.

Coverage
--------
✅ Good  : alert closed, tickets closed, meta updated
❌ Bad   : wrong-severity ticket not closed, alert stays open while active
⚠️  Edge : corrupted meta survives, already-closed alert ignored,
            resolution boundary, late-arriving agent resets timer
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from tests.test_alert_service.conftest import make_ticket, make_alert
from alert_service.resolution_service import ResolutionService
from alert_service.models import Alert
from ticket_service.models import Ticket


# ===========================================================================
# ✅ GOOD CASES
# ===========================================================================

class TestResolveAlert:
    """Core resolve_alert() behaviour."""

    def test_alert_status_set_to_closed(self, db):
        alert = make_alert(db, metric_name="cpu", severity="P2")
        ResolutionService.resolve_alert(db, alert)
        db.refresh(alert)
        assert alert.status == "CLOSED"

    def test_alert_closed_at_populated(self, db):
        before = datetime.now()
        alert  = make_alert(db, metric_name="cpu", severity="P2")
        ResolutionService.resolve_alert(db, alert)
        db.refresh(alert)
        after = datetime.now()

        assert alert.closed_at is not None
        assert before <= alert.closed_at <= after

    def test_matching_open_tickets_are_closed(self, db):
        alert = make_alert(db, metric_name="cpu", severity="P2")
        make_ticket(db, agent_id="A", metric_name="cpu", severity="P2", status="OPEN")
        make_ticket(db, agent_id="B", metric_name="cpu", severity="P2", status="OPEN")

        ResolutionService.resolve_alert(db, alert)

        open_count = db.query(Ticket).filter_by(
            metric_name="cpu", severity="P2", status="OPEN"
        ).count()
        assert open_count == 0

    def test_all_matching_tickets_get_auto_closed_meta(self, db):
        alert = make_alert(db, metric_name="cpu", severity="P2")
        make_ticket(db, agent_id="A", metric_name="cpu", severity="P2")
        make_ticket(db, agent_id="B", metric_name="cpu", severity="P2")

        ResolutionService.resolve_alert(db, alert)

        for ticket in db.query(Ticket).filter_by(metric_name="cpu", severity="P2").all():
            meta = json.loads(ticket.meta)
            assert meta["auto_closed"]   is True
            assert meta["closed_reason"] == "resolution_window_expired"
            assert "closed_at" in meta

    def test_existing_meta_keys_preserved_on_closure(self, db):
        """Closure must merge into meta, not overwrite it."""
        existing_meta = json.dumps({"custom_key": "custom_value", "source": "prometheus"})
        alert  = make_alert(db, metric_name="cpu", severity="P2")
        ticket = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2", meta=existing_meta)

        ResolutionService.resolve_alert(db, alert)

        db.refresh(ticket)
        meta = json.loads(ticket.meta)
        assert meta["custom_key"]    == "custom_value"
        assert meta["source"]        == "prometheus"
        assert meta["auto_closed"]   is True


# ===========================================================================
# ❌ BAD CASES — Must NOT happen
# ===========================================================================

class TestSeverityIsolation:
    """❌ Case 3 — Closing a P2 alert must NOT touch P1 tickets on the same metric."""

    def test_different_severity_tickets_not_closed(self, db):
        p2_alert  = make_alert(db, metric_name="cpu", severity="P2")
        p1_ticket = make_ticket(db, agent_id="A", metric_name="cpu", severity="P1", status="OPEN")
        p2_ticket = make_ticket(db, agent_id="B", metric_name="cpu", severity="P2", status="OPEN")

        ResolutionService.resolve_alert(db, p2_alert)

        db.refresh(p1_ticket)
        db.refresh(p2_ticket)

        assert p1_ticket.status == "OPEN"    # ← must remain untouched
        assert p2_ticket.status == "CLOSED"

    def test_different_metric_tickets_not_closed(self, db):
        """Closing cpu/P2 must not affect memory/P2."""
        cpu_alert    = make_alert(db, metric_name="cpu",    severity="P2")
        cpu_ticket   = make_ticket(db, agent_id="A", metric_name="cpu",    severity="P2")
        mem_ticket   = make_ticket(db, agent_id="A", metric_name="memory", severity="P2")

        ResolutionService.resolve_alert(db, cpu_alert)

        db.refresh(mem_ticket)
        assert mem_ticket.status == "OPEN"

    def test_already_closed_tickets_not_re_closed(self, db):
        """Tickets already CLOSED before resolution must stay CLOSED (no re-write)."""
        alert  = make_alert(db, metric_name="cpu", severity="P2")
        ticket = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2", status="CLOSED")
        original_meta = ticket.meta

        ResolutionService.resolve_alert(db, alert)

        db.refresh(ticket)
        # Already-closed ticket must not have been mutated
        assert ticket.meta == original_meta


# ===========================================================================
# ⚠️  EDGE CASES
# ===========================================================================

class TestMetaCorruption:
    """⚠️ Case 5 — Invalid JSON in meta must not crash ResolutionService."""

    def test_invalid_json_meta_fallback_to_empty_dict(self, db):
        alert  = make_alert(db, metric_name="cpu", severity="P2")
        ticket = make_ticket(
            db, agent_id="A", metric_name="cpu", severity="P2",
            meta="NOT_VALID_JSON{{{{",
        )

        # Must not raise
        ResolutionService.resolve_alert(db, alert)

        db.refresh(ticket)
        meta = json.loads(ticket.meta)
        assert meta["auto_closed"] is True

    def test_null_meta_handled_gracefully(self, db):
        """meta=NULL in DB must be treated as {} and closure keys added."""
        alert  = make_alert(db, metric_name="cpu", severity="P2")
        ticket = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2", meta=None)

        ResolutionService.resolve_alert(db, alert)

        db.refresh(ticket)
        meta = json.loads(ticket.meta)
        assert meta["auto_closed"] is True


class TestRunResolutionPass:
    """run_resolution_pass() batch behaviour."""

    def test_stale_alert_is_resolved_in_pass(self, db):
        stale_time = datetime.now() - timedelta(hours=7)  # P2 window = 6h
        alert = make_alert(db, severity="P2", last_seen_at=stale_time)

        resolved_ids = ResolutionService.run_resolution_pass(db)

        assert alert.id in resolved_ids
        db.refresh(alert)
        assert alert.status == "CLOSED"

    def test_active_alert_not_resolved_in_pass(self, db):
        fresh_time = datetime.now() - timedelta(hours=1)  # P2 window = 6h
        alert = make_alert(db, severity="P2", last_seen_at=fresh_time)

        resolved_ids = ResolutionService.run_resolution_pass(db)

        assert alert.id not in resolved_ids
        db.refresh(alert)
        assert alert.status == "OPEN"

    def test_already_closed_alert_not_in_pass(self, db):
        stale_time = datetime.now() - timedelta(hours=10)
        alert = make_alert(db, severity="P2", last_seen_at=stale_time, status="CLOSED")

        resolved_ids = ResolutionService.run_resolution_pass(db)

        assert alert.id not in resolved_ids

    def test_multiple_stale_alerts_all_resolved(self, db):
        stale = datetime.now() - timedelta(hours=25)
        a1 = make_alert(db, metric_name="cpu",    severity="P1", last_seen_at=stale)
        a2 = make_alert(db, metric_name="memory", severity="P2", last_seen_at=stale)
        a3 = make_alert(db, metric_name="disk",   severity="P3", last_seen_at=stale)

        resolved_ids = ResolutionService.run_resolution_pass(db)

        assert {a1.id, a2.id, a3.id}.issubset(set(resolved_ids))

    def test_returns_empty_list_when_nothing_to_resolve(self, db):
        fresh = datetime.now()
        make_alert(db, severity="P2", last_seen_at=fresh)

        resolved_ids = ResolutionService.run_resolution_pass(db)
        assert resolved_ids == []


class TestResolutionWindowBoundary:
    """⚠️ Case 3 — Activity just before expiry must keep alert open."""

    def test_new_activity_resets_resolution_timer(self, db):
        """
        Alert fires at T=0, almost resolves at T=5h59m, new ticket at T=5h59m
        → last_seen_at updated → alert must remain OPEN after 6h from T=0.
        """
        from alert_service.alert_service import process_ticket

        # Pre-seed alert with last_seen_at just inside P2 window
        five_hours_ago = datetime.now() - timedelta(hours=5, minutes=59)
        alert = make_alert(db, severity="P2", metric_name="cpu", last_seen_at=five_hours_ago)

        # New ticket arrives now — updates last_seen_at to ~now
        ticket = make_ticket(db, agent_id="A", metric_name="cpu", severity="P2")
        process_ticket(db, ticket)

        # Now run resolution pass — should NOT close the alert
        resolved_ids = ResolutionService.run_resolution_pass(db)

        db.refresh(alert)
        assert alert.id not in resolved_ids
        assert alert.status == "OPEN"

    def test_late_agent_after_near_resolution_keeps_alert_open(self, db):
        """⚠️ Case 4 — Late new agent just before expiry resets last_seen_at.

        Pre-seed an alert that already has agent A (type=SINGLE).
        A new ticket from agent B arrives → _update_alert adds B,
        escalates to GROUP, and refreshes last_seen_at so the alert
        is no longer past its resolution window.
        """
        from alert_service.alert_service import process_ticket

        just_inside = datetime.now() - timedelta(hours=5, minutes=59)
        # Pre-seed alert with A already registered (SINGLE)
        alert = make_alert(
            db, severity="P2", metric_name="cpu",
            type="SINGLE", agent_ids=["A"], last_seen_at=just_inside,
        )

        # Late ticket from brand-new agent B
        late_ticket = make_ticket(db, agent_id="B", metric_name="cpu", severity="P2")
        process_ticket(db, late_ticket)

        # last_seen_at is now ~now, so the P2 6h window has NOT been exceeded
        resolved_ids = ResolutionService.run_resolution_pass(db)

        db.refresh(alert)
        assert alert.id not in resolved_ids
        assert alert.status == "OPEN"
        assert alert.type   == "GROUP"
        assert "B" in json.loads(alert.agent_ids)
