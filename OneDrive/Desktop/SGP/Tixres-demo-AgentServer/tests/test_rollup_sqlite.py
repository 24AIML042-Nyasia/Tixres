import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import server_db.connection as conn
from server_db.connection import Base
from server_db.models import Agent, AgentCredentials, MetricNumeric
from metric_rollup.models import RollupState
from metric_rollup.rollUp import InfluxDBRollup
from influx_db.const import MEASUREMENT_1M


@pytest.fixture()
def sqlite_session(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    # Rebind global SessionLocal used inside rollup code to the sqlite engine
    conn.engine = engine
    conn.SessionLocal = Session
    import metric_rollup.rollUp as rollup_module

    rollup_module.SessionLocal = Session

    # Register all models and build schema
    import server_db.models  # noqa: F401
    import metric_rollup.models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_one_min_rollup_sqlite(monkeypatch, sqlite_session):
    # Stub Influx service to avoid external dependencies
    class DummyWriteApi:
        def __init__(self):
            self.written = None

        def write(self, bucket, record, org):
            self.written = record

    write_api = DummyWriteApi()

    monkeypatch.setattr("metric_rollup.rollUp.InfluxDBService.getClient", lambda: object())
    monkeypatch.setattr("metric_rollup.rollUp.InfluxDBService.getWriteApiSync", lambda client: write_api)
    monkeypatch.setattr("metric_rollup.rollUp.InfluxDBService.getQueryApi", lambda client: object())
    monkeypatch.setattr("metric_rollup.rollUp.InfluxDBService.getOrg", lambda: "dummy-org")
    monkeypatch.setattr("metric_rollup.rollUp.InfluxDBService.getBucket", lambda: "dummy-bucket")

    now = datetime.utcnow().replace(microsecond=0)

    # Minimal agent + credentials for FK
    cred = AgentCredentials(agent_id="agent_sqlite", api_key="k", secret_key="s")
    agent = Agent(
        agent_id="agent_sqlite",
        agent_version="1.0.0",
        hostname="host",
        os="linux",
        fingerprint="fp",
    )
    agent.credentials = cred
    sqlite_session.add_all([cred, agent])

    # Seed metric rows that match rollup regex
    sqlite_session.add_all(
        [
            MetricNumeric(
                agent_id="agent_sqlite",
                metric_name="cpu_v1.0.0.pct",
                value=10.0,
                timestamp=now - timedelta(seconds=50),
            ),
            MetricNumeric(
                agent_id="agent_sqlite",
                metric_name="cpu_v1.0.0.pct",
                value=20.0,
                timestamp=now - timedelta(seconds=40),
            ),
            MetricNumeric(
                agent_id="agent_sqlite",
                metric_name="cpu_v1.0.0.pct",
                value=30.0,
                timestamp=now - timedelta(seconds=30),
            ),
        ]
    )

    sqlite_session.add(
        RollupState(
            source_table="metric_numeric",
            target_table=MEASUREMENT_1M,
            last_bucket=now - timedelta(minutes=5),
        )
    )
    sqlite_session.commit()

    rollup = InfluxDBRollup()
    asyncio.run(rollup.one_min_roll_up())

    assert write_api.written, "rollup should emit points to Influx"
    assert len(write_api.written) == 1, "expect one aggregated 1m bucket"

    state = (
        sqlite_session.query(RollupState)
        .filter(
            RollupState.source_table == "metric_numeric",
            RollupState.target_table == MEASUREMENT_1M,
        )
        .first()
    )
    assert state and state.last_bucket, "rollup cursor should be updated"
