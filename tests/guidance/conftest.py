"""
tests/conftest.py
──────────────────
Shared fixtures for the guidance test suite.
Uses an in-memory SQLite database so no external DB is needed.
"""

import sys
import os

# Make the guidance package importable when running pytest from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "guidance"))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from guidance.models import Base, Priority
from guidance.schemas import GuidanceUpsert
from guidance.GuidanceService import GuidanceService


# --------------------------------------------------------------------------- #
#  DB engine — one fresh in-memory SQLite DB per test session                 #
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="session")
def engine():
    _engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(_engine)
    yield _engine
    _engine.dispose()


@pytest.fixture()
def db(engine) -> Session:
    """
    Yields a DB session that is rolled back after each test,
    keeping tests fully isolated without recreating the schema.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def service(db: Session) -> GuidanceService:
    return GuidanceService(db)


# --------------------------------------------------------------------------- #
#  Reusable payload factories                                                  #
# --------------------------------------------------------------------------- #

def make_upsert(
    metric_name: str = "cpu_usage",
    severity: str = "high",
    priority: Priority = Priority.P2,
    resolution_steps: list | None = None,
    resolver_notes: str | None = "Check top/htop",
    resolution_meta: dict | None = None,
) -> GuidanceUpsert:
    return GuidanceUpsert(
        metric_name=metric_name,
        severity=severity,
        priority=priority,
        resolution_steps=resolution_steps if resolution_steps is not None else [{"step": 1, "action": "Restart service"}],
        resolver_notes=resolver_notes,
        resolution_meta=resolution_meta or {"sla_minutes": 30, "tags": ["infra"]},
    )
