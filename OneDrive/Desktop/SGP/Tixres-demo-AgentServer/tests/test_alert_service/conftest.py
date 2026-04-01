"""
conftest.py
===========
Shared pytest fixtures for the alert correlation test suite.

Isolation strategy
------------------
``TicketService.create_ticket`` calls ``db.close()`` in its ``finally`` block.
A session-scoped engine with rollback-based isolation therefore does NOT work —
the close() detaches all ORM objects and the rollback never sees the data.

Instead we use a **function-scoped engine** backed by a named SQLite file.
Each test:
  1. Drops the existing schema.
  2. Recreates it (``create_all``).
  3. Opens a fresh session, runs, then cleans up.

This guarantees full row-level isolation regardless of whether the code under
test closes sessions internally.

Install test dependencies:
    pip install pytest sqlalchemy
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from server_db.connection import Base
from alert_service.models import Alert   # noqa: F401 — registers table metadata
from ticket_service.models import Ticket  # noqa: F401


# ---------------------------------------------------------------------------
# Per-test engine — fresh schema for every single test
# ---------------------------------------------------------------------------

@pytest.fixture
def engine():
    """
    Function-scoped engine.  Uses a named file so concurrent-test fixtures
    (which open their own sessions/threads) can share the same physical DB
    within one test, while still getting a clean slate per test.
    """
    _engine = create_engine(
        "sqlite:///./pytest_test.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.drop_all(_engine)
    Base.metadata.create_all(_engine)
    yield _engine
    Base.metadata.drop_all(_engine)
    _engine.dispose()


@pytest.fixture
def SessionFactory(engine):
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


# ---------------------------------------------------------------------------
# Per-test session
# ---------------------------------------------------------------------------

@pytest.fixture
def db(SessionFactory):
    """
    One open session per test.

    Because TicketService.create_ticket() calls db.close() in its finally
    block, we simply open a fresh session here.  If the service already
    closed it, the extra close() in our teardown is a no-op.
    """
    session = SessionFactory()
    yield session
    try:
        session.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Helper factories — insert rows directly, bypassing service dedup logic
# ---------------------------------------------------------------------------

def make_ticket(
    db,
    agent_id:          str      = "agent_A",
    metric_name:       str      = "cpu_usage",
    severity:          str      = "P2",
    purpose:           str      = "general",
    status:            str      = "OPEN",
    occurrence_count:  int      = 1,
    detectors:         list     = None,
    meta:              str      = "{}",
    message:           str      = "test message",
    first_occurred_at: datetime = None,
    last_occurred_at:  datetime = None,
    commit:            bool     = True,
) -> Ticket:
    """
    Insert a Ticket directly, bypassing TicketService dedup logic.
    Use this when you need precise control over DB state before calling
    AlertService or ResolutionService directly.
    """
    now = datetime.now()
    t = Ticket(
        agent_id          = agent_id,
        metric_name       = metric_name,
        severity          = severity,
        status            = status,
        detectors         = json.dumps(detectors or ["detector_x"]),
        meta              = meta,
        message           = message,
        occurrence_count  = occurrence_count,
        first_occurred_at = first_occurred_at or now,
        last_occurred_at  = last_occurred_at  or now,
        purpose           = purpose,
        created_at        = now,
    )
    db.add(t)
    if commit:
        db.commit()
        db.refresh(t)
    return t


def make_alert(
    db,
    metric_name:      str      = "cpu_usage",
    severity:         str      = "P2",
    purpose:          str      = "general",
    type:             str      = "SINGLE",
    status:           str      = "OPEN",
    agent_ids:        list     = None,
    total_occurrence: int      = 1,
    last_seen_at:     datetime = None,
    first_seen_at:    datetime = None,
    commit:           bool     = True,
) -> Alert:
    """Insert an Alert directly, useful for pre-seeding resolution tests."""
    now = datetime.now()
    a = Alert(
        metric_name      = metric_name,
        severity         = severity,
        purpose          = purpose,
        type             = type,
        status           = status,
        agent_ids        = json.dumps(agent_ids or ["agent_A"]),
        total_occurrence = total_occurrence,
        first_seen_at    = first_seen_at or now,
        last_seen_at     = last_seen_at  or now,
        created_at       = now,
    )
    db.add(a)
    if commit:
        db.commit()
        db.refresh(a)
    return a


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def make_ticket(
    db,
    agent_id:    str   = "agent_A",
    metric_name: str   = "cpu_usage",
    severity:    str   = "P2",
    status:      str   = "OPEN",
    occurrence_count: int = 1,
    detectors:   list  = None,
    meta:        str   = "{}",
    message:     str   = "test message",
    first_occurred_at: datetime = None,
    last_occurred_at:  datetime = None,
    commit: bool = True,
) -> Ticket:
    """
    Insert a Ticket directly into the DB, bypassing TicketService dedup logic.
    Use this in tests that need to control the exact DB state before calling
    AlertService or ResolutionService.
    """
    now = datetime.now()
    t = Ticket(
        agent_id          = agent_id,
        metric_name       = metric_name,
        severity          = severity,
        status            = status,
        detectors         = json.dumps(detectors or ["detector_x"]),
        meta              = meta,
        message           = message,
        occurrence_count  = occurrence_count,
        first_occurred_at = first_occurred_at or now,
        last_occurred_at  = last_occurred_at  or now,
        created_at        = now,
    )
    db.add(t)
    if commit:
        db.commit()
        db.refresh(t)
    return t


def make_alert(
    db,
    metric_name:      str      = "cpu_usage",
    severity:         str      = "P2",
    type:             str      = "SINGLE",
    status:           str      = "OPEN",
    agent_ids:        list     = None,
    total_occurrence: int      = 1,
    last_seen_at:     datetime = None,
    first_seen_at:    datetime = None,
    commit: bool = True,
) -> Alert:
    """
    Insert an Alert directly into the DB.
    Useful for pre-seeding state in resolution / update tests.
    """
    now = datetime.now()
    a = Alert(
        metric_name      = metric_name,
        severity         = severity,
        type             = type,
        status           = status,
        agent_ids        = json.dumps(agent_ids or ["agent_A"]),
        total_occurrence = total_occurrence,
        first_seen_at    = first_seen_at or now,
        last_seen_at     = last_seen_at  or now,
        created_at       = now,
    )
    db.add(a)
    if commit:
        db.commit()
        db.refresh(a)
    return a
