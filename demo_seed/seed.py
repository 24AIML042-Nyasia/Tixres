"""
Demo seeding helpers for local development and demos.

Run:
    python -m demo_seed [--skip-influx]

What it does
------------
* Creates 6 demo agents with credentials and purposes.
* Inserts rich metrics across CPU (per-core/load/frequency), memory (ram/swap/cached),
  disk (usage + IO), process, network (IO/connections/errors), and temperature.
* Seeds tickets, alerts, guidance, and anomaly state that exercise the
  alert + guidance UI flows.
* Writes rollup cursors and, when Influx credentials are present, pushes
  synthetic 1m/10m/1h rollup points to the configured bucket.

The seeding is idempotent for the demo agent ids; rerunning will wipe and
recreate only the demo rows.
"""

from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Tuple, Dict, Any

from sqlalchemy import delete, text

from server_db.connection import Base, SessionLocal, engine
from SLAs.templates import DEFAULT_TEMPLATE
from server_db.models import Agent, AgentCredentials, MetricJson, MetricNumeric, Purpose
from ticket_service.models import Ticket
from alert_service.models import Alert
from guidance.models import Guidance, Priority
from anomaly.models import AnomalyState
from metric_rollup.models import RollupState
from influx_db.const import (
    MEASUREMENT_1M,
    MEASUREMENT_10M,
    MEASUREMENT_1H,
    TAG_AGENT_ID,
    TAG_METRIC,
    TAG_VERSION,
    TAG_UNIT,
    FIELD_COUNT,
    FIELD_MIN,
    FIELD_MAX,
    FIELD_SUM,
    FIELD_AVG,
    FIELD_BUCKET_START,
    SOURCE_POSTGRES,
    SOURCE_1M,
    SOURCE_10M,
)
from settings import METRIC_REGEX_PATTERN

try:
    from influxdb_client import Point  # type: ignore
    from influx_db.connection import InfluxDBService
except Exception:  # pragma: no cover - optional dep
    Point = None
    InfluxDBService = None  # type: ignore


AGENT_FIXTURES = [
    {"agent_id": "agent_demo_web", "hostname": "demo-web", "version": "1.0.1", "os": "linux", "purpose": "general"},
    {"agent_id": "agent_demo_db", "hostname": "demo-db", "version": "1.1.0", "os": "linux", "purpose": "data"},
    {"agent_id": "agent_demo_cache", "hostname": "demo-cache", "version": "1.0.3", "os": "linux", "purpose": "observability"},
    {"agent_id": "agent_demo_search", "hostname": "demo-search", "version": "1.2.0", "os": "linux", "purpose": "general"},
    {"agent_id": "agent_demo_queue", "hostname": "demo-queue", "version": "1.0.0", "os": "linux", "purpose": "general"},
    {"agent_id": "agent_demo_edge", "hostname": "demo-edge", "version": "1.0.2", "os": "linux", "purpose": "edge"},
]

DEMO_AGENT_IDS = [a["agent_id"] for a in AGENT_FIXTURES]

DEMO_GUIDANCE_METRICS = [
    "cpu_v1.0.0.usage_overall",
    "disk_v1.0.0.usage",
    "memory_v1.0.0.ram",
    "network_v1.0.0.errors",
]

_METRIC_PATTERN = re.compile(METRIC_REGEX_PATTERN)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _ensure_alert_ack_columns(db):
    """
    Backfill ack columns on SQLite demo DBs that were created before the fields
    existed. Keeps existing data and avoids a destructive drop/create.
    """
    dialect = db.bind.dialect.name if db.bind else ""
    if dialect != "sqlite":
        return

    rows = db.execute(text("PRAGMA table_info(alerts)")).fetchall()
    cols = {row[1] for row in rows}
    altered = False

    if "acknowledged_at" not in cols:
        db.execute(text("ALTER TABLE alerts ADD COLUMN acknowledged_at TIMESTAMP"))
        altered = True
    if "acknowledged_by" not in cols:
        db.execute(text("ALTER TABLE alerts ADD COLUMN acknowledged_by VARCHAR"))
        altered = True

    if altered:
        db.commit()


def _ensure_ticket_ack_columns(db):
    """
    Backfill ack columns on SQLite demo DBs for tickets (acknowledged_at/by).
    """
    dialect = db.bind.dialect.name if db.bind else ""
    if dialect != "sqlite":
        return

    rows = db.execute(text("PRAGMA table_info(tickets)")).fetchall()
    cols = {row[1] for row in rows}
    altered = False

    if "acknowledged_at" not in cols:
        db.execute(text("ALTER TABLE tickets ADD COLUMN acknowledged_at TIMESTAMP"))
        altered = True
    if "acknowledged_by" not in cols:
        db.execute(text("ALTER TABLE tickets ADD COLUMN acknowledged_by VARCHAR"))
        altered = True

    if altered:
        db.commit()


def _purge_demo_rows(db):
    db.execute(delete(MetricNumeric).where(MetricNumeric.agent_id.in_(DEMO_AGENT_IDS)))
    db.execute(delete(MetricJson).where(MetricJson.agent_id.in_(DEMO_AGENT_IDS)))
    db.execute(delete(Ticket).where(Ticket.agent_id.in_(DEMO_AGENT_IDS)))
    db.execute(delete(Alert).where(Alert.agent_ids.contains("agent_demo_")))
    db.execute(delete(Guidance).where(Guidance.metric_name.in_(DEMO_GUIDANCE_METRICS)))
    db.execute(delete(AnomalyState).where(AnomalyState.agent_id.in_(DEMO_AGENT_IDS)))
    db.execute(
        delete(RollupState).where(
            RollupState.target_table.in_([MEASUREMENT_1M, MEASUREMENT_10M, MEASUREMENT_1H])
        )
    )
    db.execute(delete(Agent).where(Agent.agent_id.in_(DEMO_AGENT_IDS)))
    db.execute(delete(AgentCredentials).where(AgentCredentials.agent_id.in_(DEMO_AGENT_IDS)))
    db.commit()


def _get_or_create_purpose(db, name: str, template: str) -> Purpose:
    existing = db.query(Purpose).filter(Purpose.purpose == name).first()
    if existing:
        return existing
    row = Purpose(purpose=name, template=template)
    db.add(row)
    db.flush()
    return row


def _seed_purposes(db) -> dict[str, Purpose]:
    return {
        "general": _get_or_create_purpose(db, "general", DEFAULT_TEMPLATE),
        "observability": _get_or_create_purpose(
            db,
            "observability",
            json.dumps({"modules": ["cpu_v1.0.0", "memory_v1.0.0"], "metrics": {"cpu_v1.0.0.usage_overall": 5}}),
        ),
        "data": _get_or_create_purpose(
            db, "data", json.dumps({"modules": ["disk_v1.0.0"], "metrics": {"disk_v1.0.0.usage": 10}})
        ),
        "edge": _get_or_create_purpose(db, "edge", DEFAULT_TEMPLATE),
    }


def _seed_agents(db, purposes: dict[str, Purpose], now: datetime) -> list[Agent]:
    rows: list[Agent] = []
    for fixture in AGENT_FIXTURES:
        agent_id = fixture["agent_id"]
        hostname = fixture["hostname"]
        version = fixture["version"]
        os_name = fixture["os"]
        purpose_key = fixture["purpose"]
        cred = AgentCredentials(
            agent_id=agent_id,
            api_key=f"{agent_id}-key",
            secret_key=f"{agent_id}-secret",
        )
        agent = Agent(
            agent_id=agent_id,
            agent_version=version,
            hostname=hostname,
            os=os_name,
            fingerprint=f"fp-{hostname}",
            purpose_id=purposes[purpose_key].id,
            heartbeat=now,
            template=None,
        )
        agent.credentials = cred
        db.add(cred)
        db.add(agent)
        rows.append(agent)
    return rows


def _series(
    agent_id: str,
    metric_name: str,
    values: Iterable[float],
    start_minutes_ago: int,
    step_seconds: int,
    now: datetime,
) -> list[MetricNumeric]:
    base = now - timedelta(minutes=start_minutes_ago)
    return [
        MetricNumeric(
            agent_id=agent_id,
            metric_name=metric_name,
            value=float(val),
            timestamp=base + timedelta(seconds=idx * step_seconds),
        )
        for idx, val in enumerate(values)
    ]


def _seed_metrics(db, now: datetime) -> Tuple[List[MetricNumeric], List[MetricJson]]:
    numeric_rows: list[MetricNumeric] = []
    json_rows: list[MetricJson] = []

    numeric_fixtures = [
        # agent_demo_web — cpu, 30 min window, 15s steps → ~4 readings/bucket
        ("agent_demo_web", "cpu_v1.0.0.usage_overall",
         [42.2,43.1,44.0,45.5,47.0,48.5,50.2,52.8,55.1,58.3,
          62.0,65.4,68.9,72.1,74.8,76.0,77.2,78.5,80.1,81.6,
          83.3,82.0,80.5,78.2,75.6,72.0,68.4,65.1,61.8,58.0], 30, 15),
        ("agent_demo_web", "process_v1.0.0.total_threads",
         [205,206,208,210,212,215,218,220,222,224,223,221,220], 13, 60),
        ("agent_demo_web", "process_v1.0.0.zombie_count",
         [1,1,0,0,1,0,0,1,0,0], 10, 90),

        # agent_demo_db
        ("agent_demo_db", "cpu_v1.0.0.usage_overall",
         [23.0,24.5,26.0,27.8,29.0,31.2,33.5,36.0,38.8,41.5,
          44.0,46.5,48.9,50.2,51.0,50.5,49.2,47.5,45.0,42.8,
          40.5,39.2,37.8,36.0,34.5,33.0,31.5,30.0,28.8,27.5], 30, 15),
        ("agent_demo_db", "process_v1.0.0.total_threads",
         [180,181,182,183,184,185,186,185,184,183,182,181,180], 13, 60),
        ("agent_demo_db", "process_v1.0.0.zombie_count",
         [0,0,0,1,0,0,0,1,0,0], 12, 90),

        # agent_demo_cache
        ("agent_demo_cache", "cpu_v1.0.0.usage_overall",
         [18.5,19.2,20.0,21.5,23.0,24.8,26.5,28.2,30.0,31.8,
          33.5,35.0,36.8,37.5,38.0,37.2,36.0,34.5,33.0,31.5,
          30.0,29.0,28.2,27.5,26.8,26.0,25.5,25.0,24.5,24.0], 30, 15),
        ("agent_demo_cache", "process_v1.0.0.total_threads",
         [150,151,152,154,156,158,160,159,158,156,154,152,150], 13, 60),

        # agent_demo_search
        ("agent_demo_search", "cpu_v1.0.0.usage_overall",
         [32.0,33.5,35.2,37.0,39.5,41.0,43.5,46.0,49.2,52.5,
          55.0,57.8,60.2,63.0,65.5,67.0,68.5,70.0,71.5,73.5,
          72.0,70.5,68.0,65.5,63.0,61.0,59.5,58.0,56.5,55.0], 30, 15),
        ("agent_demo_search", "network_v1.0.0.errors",
         [1,0,0,2,1,0,1,0,2,1,0,0,1,0,0,2,1,0,0,1], 20, 45),

        # agent_demo_queue
        ("agent_demo_queue", "cpu_v1.0.0.usage_overall",
         [28.0,29.5,31.0,33.0,35.0,37.5,40.0,42.5,45.0,47.5,
          50.0,52.5,54.8,56.5,57.0,56.0,54.5,52.0,50.0,48.0,
          46.0,44.5,43.0,41.5,40.0,39.0,38.0,37.0,36.5,36.0], 30, 15),
        ("agent_demo_queue", "system_v1.0.0.process_count",
         [120,121,122,123,124,125,126,127,128,127,126,125,124,123], 13, 60),

        # agent_demo_edge
        ("agent_demo_edge", "cpu_v1.0.0.usage_overall",
         [19.0,20.5,22.0,23.5,25.0,26.5,28.0,29.5,31.0,32.0,
          33.0,32.5,31.5,30.5,29.5,29.0,28.5,28.0,27.5,27.0,
          26.5,26.0,25.5,25.0,24.5,24.0,23.5,23.0,22.5,22.0], 30, 15),
    ]

    for agent_id, metric, values, mins, step in numeric_fixtures:
        numeric_rows.extend(_series(agent_id, metric, values, mins, step, now))

    json_fixtures = [
        # agent_demo_web
        (
            "agent_demo_web",
            "cpu_v1.0.0.usage_per_core",
            [44.0, 52.5, 61.0, 72.5],
            3,
        ),
        (
            "agent_demo_web",
            "cpu_v1.0.0.load_average",
            {"1m": 1.7, "5m": 1.3, "15m": 1.1},
            3,
        ),
        (
            "agent_demo_web",
            "cpu_v1.0.0.frequency",
            {"current_mhz": 3050, "min_mhz": 2200, "max_mhz": 3600},
            3,
        ),
        (
            "agent_demo_web",
            "memory_v1.0.0.ram",
            {"total_gb": 32, "used_gb": 22, "percent": 68.5, "available_gb": 10},
            3,
        ),
        (
            "agent_demo_web",
            "memory_v1.0.0.cached_vs_free",
            {"cached_gb": 6.5, "free_gb": 3.5},
            3,
        ),
        (
            "agent_demo_web",
            "memory_v1.0.0.swap",
            {"total_gb": 4, "used_gb": 0.5, "percent": 12.5},
            3,
        ),
        (
            "agent_demo_web",
            "process_v1.0.0.top_memory",
            [
                {"name": "gunicorn", "pct": 18.0},
                {"name": "nginx", "pct": 6.0},
            ],
            2,
        ),
        (
            "agent_demo_web",
            "disk_v1.0.0.usage",
            {"root": {"total_gb": 512, "used_gb": 410, "percent": 80.1}},
            3,
        ),
        (
            "agent_demo_web",
            "disk_v1.0.0.io",
            {"read_mb_s": 12.4, "write_mb_s": 8.2},
            3,
        ),
        (
            "agent_demo_web",
            "network_v1.0.0.io",
            {"upload_mb_s": 18.5, "download_mb_s": 64.2},
            2,
        ),
        (
            "agent_demo_web",
            "network_v1.0.0.connections",
            {"total": 410, "established": 396, "time_wait": 14},
            2,
        ),
        (
            "agent_demo_web",
            "network_v1.0.0.errors",
            {"errors_in": 1, "errors_out": 0},
            2,
        ),

        # agent_demo_db
        (
            "agent_demo_db",
            "cpu_v1.0.0.usage_per_core",
            [18.0, 22.0, 20.5, 19.0],
            4,
        ),
        (
            "agent_demo_db",
            "cpu_v1.0.0.load_average",
            {"1m": 0.9, "5m": 0.8, "15m": 0.7},
            4,
        ),
        (
            "agent_demo_db",
            "cpu_v1.0.0.frequency",
            {"current_mhz": 2500, "min_mhz": 2200, "max_mhz": 3200},
            4,
        ),
        (
            "agent_demo_db",
            "memory_v1.0.0.ram",
            {"total_gb": 96, "used_gb": 71, "percent": 73.9, "available_gb": 25},
            4,
        ),
        (
            "agent_demo_db",
            "memory_v1.0.0.cached_vs_free",
            {"cached_gb": 40.0, "free_gb": 18.0},
            4,
        ),
        (
            "agent_demo_db",
            "memory_v1.0.0.swap",
            {"total_gb": 32, "used_gb": 4, "percent": 12.5},
            4,
        ),
        (
            "agent_demo_db",
            "process_v1.0.0.top_memory",
            [
                {"name": "postgres", "pct": 35.0},
                {"name": "backup", "pct": 5.0},
            ],
            3,
        ),
        (
            "agent_demo_db",
            "disk_v1.0.0.usage",
            {"data": {"total_gb": 1536, "used_gb": 1280, "percent": 83.3}},
            4,
        ),
        (
            "agent_demo_db",
            "disk_v1.0.0.io",
            {"read_mb_s": 140.0, "write_mb_s": 95.0},
            3,
        ),
        (
            "agent_demo_db",
            "network_v1.0.0.io",
            {"upload_mb_s": 22.5, "download_mb_s": 48.9},
            3,
        ),
        (
            "agent_demo_db",
            "network_v1.0.0.connections",
            {"total": 220, "established": 210, "time_wait": 10},
            3,
        ),
        (
            "agent_demo_db",
            "network_v1.0.0.errors",
            {"errors_in": 0, "errors_out": 1},
            3,
        ),

        # agent_demo_cache
        (
            "agent_demo_cache",
            "cpu_v1.0.0.usage_per_core",
            [15.0, 18.5, 21.0, 19.0],
            2,
        ),
        (
            "agent_demo_cache",
            "cpu_v1.0.0.load_average",
            {"1m": 0.7, "5m": 0.6, "15m": 0.5},
            2,
        ),
        (
            "agent_demo_cache",
            "cpu_v1.0.0.frequency",
            {"current_mhz": 2400, "min_mhz": 2000, "max_mhz": 2800},
            2,
        ),
        (
            "agent_demo_cache",
            "memory_v1.0.0.ram",
            {"total_gb": 24, "used_gb": 17, "percent": 70.8, "available_gb": 7},
            2,
        ),
        (
            "agent_demo_cache",
            "memory_v1.0.0.cached_vs_free",
            {"cached_gb": 5.0, "free_gb": 3.0},
            2,
        ),
        (
            "agent_demo_cache",
            "memory_v1.0.0.swap",
            {"total_gb": 8, "used_gb": 1.0, "percent": 12.5},
            2,
        ),
        (
            "agent_demo_cache",
            "process_v1.0.0.top_memory",
            [
                {"name": "redis-server", "pct": 28.0},
                {"name": "systemd", "pct": 4.0},
            ],
            2,
        ),
        (
            "agent_demo_cache",
            "disk_v1.0.0.usage",
            {"cache": {"total_gb": 256, "used_gb": 180, "percent": 70.3}},
            2,
        ),
        (
            "agent_demo_cache",
            "disk_v1.0.0.io",
            {"read_mb_s": 32.0, "write_mb_s": 18.0},
            2,
        ),
        (
            "agent_demo_cache",
            "network_v1.0.0.io",
            {"upload_mb_s": 8.1, "download_mb_s": 26.7},
            2,
        ),
        (
            "agent_demo_cache",
            "network_v1.0.0.connections",
            {"total": 150, "established": 145, "time_wait": 5},
            2,
        ),

        # agent_demo_search
        (
            "agent_demo_search",
            "cpu_v1.0.0.usage_per_core",
            [28.0, 30.5, 32.0, 34.0],
            3,
        ),
        (
            "agent_demo_search",
            "cpu_v1.0.0.load_average",
            {"1m": 1.2, "5m": 1.0, "15m": 0.9},
            3,
        ),
        (
            "agent_demo_search",
            "cpu_v1.0.0.frequency",
            {"current_mhz": 2900, "min_mhz": 2400, "max_mhz": 3400},
            3,
        ),
        (
            "agent_demo_search",
            "memory_v1.0.0.ram",
            {"total_gb": 48, "used_gb": 36, "percent": 75.0, "available_gb": 12},
            3,
        ),
        (
            "agent_demo_search",
            "memory_v1.0.0.cached_vs_free",
            {"cached_gb": 9.0, "free_gb": 6.0},
            3,
        ),
        (
            "agent_demo_search",
            "memory_v1.0.0.swap",
            {"total_gb": 12, "used_gb": 1.5, "percent": 12.5},
            3,
        ),
        (
            "agent_demo_search",
            "process_v1.0.0.top_cpu",
            [
                {"name": "searchd", "pct": 41.0},
                {"name": "nginx", "pct": 9.0},
            ],
            1,
        ),
        (
            "agent_demo_search",
            "process_v1.0.0.top_memory",
            [
                {"name": "searchd", "pct": 35.0},
                {"name": "vector-cache", "pct": 7.5},
            ],
            1,
        ),
        (
            "agent_demo_search",
            "disk_v1.0.0.usage",
            {"root": {"total_gb": 768, "used_gb": 520, "percent": 67.7}},
            3,
        ),
        (
            "agent_demo_search",
            "disk_v1.0.0.io",
            {"read_mb_s": 88.0, "write_mb_s": 60.0},
            3,
        ),
        (
            "agent_demo_search",
            "network_v1.0.0.io",
            {"upload_mb_s": 30.0, "download_mb_s": 80.5},
            3,
        ),
        (
            "agent_demo_search",
            "network_v1.0.0.connections",
            {"total": 480, "established": 460, "time_wait": 20},
            3,
        ),
        (
            "agent_demo_search",
            "network_v1.0.0.errors",
            {"errors_in": 2, "errors_out": 1},
            2,
        ),

        # agent_demo_queue
        (
            "agent_demo_queue",
            "cpu_v1.0.0.usage_per_core",
            [22.0, 24.0, 26.0, 25.0],
            2,
        ),
        (
            "agent_demo_queue",
            "cpu_v1.0.0.load_average",
            {"1m": 1.0, "5m": 0.9, "15m": 0.8},
            2,
        ),
        (
            "agent_demo_queue",
            "cpu_v1.0.0.frequency",
            {"current_mhz": 2650, "min_mhz": 2200, "max_mhz": 3100},
            2,
        ),
        (
            "agent_demo_queue",
            "memory_v1.0.0.ram",
            {"total_gb": 16, "used_gb": 9, "percent": 56.2, "available_gb": 7},
            2,
        ),
        (
            "agent_demo_queue",
            "memory_v1.0.0.cached_vs_free",
            {"cached_gb": 3.0, "free_gb": 2.5},
            2,
        ),
        (
            "agent_demo_queue",
            "memory_v1.0.0.swap",
            {"total_gb": 8, "used_gb": 0.8, "percent": 10.0},
            2,
        ),
        (
            "agent_demo_queue",
            "process_v1.0.0.top_memory",
            [
                {"name": "worker-main", "pct": 14.0},
                {"name": "consumer", "pct": 8.5},
            ],
            2,
        ),
        (
            "agent_demo_queue",
            "network_v1.0.0.io",
            {"upload_mb_s": 6.5, "download_mb_s": 18.0},
            2,
        ),
        (
            "agent_demo_queue",
            "network_v1.0.0.connections",
            {"total": 340, "established": 332, "time_wait": 8},
            2,
        ),
        (
            "agent_demo_queue",
            "network_v1.0.0.errors",
            {"errors_in": 1, "errors_out": 1},
            2,
        ),

        # agent_demo_edge
        (
            "agent_demo_edge",
            "cpu_v1.0.0.usage_per_core",
            [12.0, 14.0, 15.5, 16.0],
            2,
        ),
        (
            "agent_demo_edge",
            "cpu_v1.0.0.load_average",
            {"1m": 0.5, "5m": 0.4, "15m": 0.3},
            2,
        ),
        (
            "agent_demo_edge",
            "cpu_v1.0.0.frequency",
            {"current_mhz": 2150, "min_mhz": 1800, "max_mhz": 2600},
            2,
        ),
        (
            "agent_demo_edge",
            "memory_v1.0.0.ram",
            {"total_gb": 8, "used_gb": 5.5, "percent": 68.8, "available_gb": 2.5},
            2,
        ),
        (
            "agent_demo_edge",
            "memory_v1.0.0.cached_vs_free",
            {"cached_gb": 1.5, "free_gb": 0.8},
            2,
        ),
        (
            "agent_demo_edge",
            "memory_v1.0.0.swap",
            {"total_gb": 2, "used_gb": 0.2, "percent": 10.0},
            2,
        ),
        (
            "agent_demo_edge",
            "process_v1.0.0.top_memory",
            [
                {"name": "envoy", "pct": 16.0},
                {"name": "edge-proxy", "pct": 9.0},
            ],
            2,
        ),
        (
            "agent_demo_edge",
            "disk_v1.0.0.usage",
            {"root": {"total_gb": 128, "used_gb": 82, "percent": 64.1}},
            3,
        ),
        (
            "agent_demo_edge",
            "disk_v1.0.0.io",
            {"read_mb_s": 14.0, "write_mb_s": 6.5},
            3,
        ),
        (
            "agent_demo_edge",
            "network_v1.0.0.io",
            {"upload_mb_s": 12.0, "download_mb_s": 34.0},
            2,
        ),
        (
            "agent_demo_edge",
            "network_v1.0.0.errors",
            {"errors_in": 4, "errors_out": 2},
            1,
        ),
        (
            "agent_demo_edge",
            "temperature_v1.0.0.battery",
            {"celsius": 48.5},
            1,
        ),
    ]

    for agent_id, metric, payload, minutes_ago in json_fixtures:
        json_rows.append(
            MetricJson(
                agent_id=agent_id,
                metric_name=metric,
                value=json.dumps(payload),
                timestamp=now - timedelta(minutes=minutes_ago),
            )
        )

    db.add_all(numeric_rows + json_rows)
    return numeric_rows, json_rows


def _seed_guidance(db):
    entries = [
        Guidance(
            metric_name="cpu_v1.0.0.usage_overall",
            priority=Priority.P1,
            purpose="general",
            resolution_steps=[
                {"step": 1, "action": "Check top CPU processes (htop) and identify spikes."},
                {"step": 2, "action": "Scale out the service tier or restart noisy pods."},
                {"step": 3, "action": "Enable autoscaling if disabled."},
            ],
            resolver_notes="Trigger autoscaling after confirming traffic pattern.",
        ),
        Guidance(
            metric_name="disk_v1.0.0.usage",
            priority=Priority.P2,
            purpose="data",
            resolution_steps=[
                {"step": 1, "action": "List largest DB tables and indexes."},
                {"step": 2, "action": "Purge partitions older than 30 days."},
                {"step": 3, "action": "Plan storage expansion if utilization exceeds 85%."},
            ],
            resolver_notes="Coordinate with DBAs before moving filesystems.",
        ),
        Guidance(
            metric_name="memory_v1.0.0.ram",
            priority=Priority.P2,
            purpose="observability",
            resolution_steps=[
                {"step": 1, "action": "Identify leak suspects using pmap or memray sample."},
                {"step": 2, "action": "Restart cache pods with high RSS and tighten limits."},
            ],
            resolver_notes="Ensure hit ratio stays above 90% post-restart.",
        ),
        Guidance(
            metric_name="network_v1.0.0.errors",
            priority=Priority.P2,
            purpose="general",
            resolution_steps=[
                {"step": 1, "action": "Inspect interface error counters (ethtool -S)."},
                {"step": 2, "action": "Swap cable or move to healthy NIC if errors persist."},
            ],
            resolver_notes="Capture packet drops before remediation for RCA.",
        ),
    ]
    db.add_all(entries)
    return entries


def _seed_tickets_and_alerts(db, now: datetime):
    metrics_pool = [
        "cpu_v1.0.0.usage_overall",
        "disk_v1.0.0.usage",
        "memory_v1.0.0.ram",
        "network_v1.0.0.errors",
        "process_v1.0.0.total_threads",
        "system_v1.0.0.process_count",
    ]
    severities = ["P1", "P2", "P3"]
    detectors = {
        "cpu_v1.0.0.usage_overall": "threshold_cpu",
        "disk_v1.0.0.usage": "disk_usage",
        "memory_v1.0.0.ram": "memory_leak",
        "network_v1.0.0.errors": "nic_errors",
        "process_v1.0.0.total_threads": "thread_leak",
        "system_v1.0.0.process_count": "proc_growth",
    }

    tickets: list[Ticket] = []
    idx = 0
    for agent in AGENT_FIXTURES:
        for metric in metrics_pool:
            severity = severities[idx % len(severities)]
            purpose = agent["purpose"]
            tickets.append(
                Ticket(
                    agent_id=agent["agent_id"],
                    metric_name=metric,
                    severity=severity,
                    purpose=purpose,
                    status="OPEN",
                    detectors=json.dumps([detectors.get(metric, "generic_detector")]),
                    meta=json.dumps({"sample": True, "idx": idx}),
                    message=f"{metric} issue detected on {agent['hostname']}",
                    occurrence_count=(idx % 5) + 1,
                    first_occurred_at=now - timedelta(minutes=30 + idx),
                    last_occurred_at=now - timedelta(minutes=5 + (idx % 4)),
                )
            )
            idx += 1
            if len(tickets) >= 50:
                break
        if len(tickets) >= 50:
            break
    db.add_all(tickets)

    alerts = [
        Alert(
            metric_name="cpu_v1.0.0.usage_overall",
            severity="P1",
            purpose="general",
            status="OPEN",
            type="GROUP",
            agent_ids=json.dumps(["agent_demo_web", "agent_demo_search", "agent_demo_queue"]),
            total_occurrence=15,
            first_seen_at=now - timedelta(minutes=40),
            last_seen_at=now - timedelta(minutes=2),
        ),
        Alert(
            metric_name="disk_v1.0.0.usage",
            severity="P2",
            purpose="data",
            status="OPEN",
            type="SINGLE",
            agent_ids=json.dumps(["agent_demo_db"]),
            total_occurrence=6,
            first_seen_at=now - timedelta(minutes=35),
            last_seen_at=now - timedelta(minutes=4),
        ),
        Alert(
            metric_name="network_v1.0.0.errors",
            severity="P2",
            purpose="general",
            status="OPEN",
            type="GROUP",
            agent_ids=json.dumps(["agent_demo_edge", "agent_demo_search"]),
            total_occurrence=8,
            first_seen_at=now - timedelta(minutes=45),
            last_seen_at=now - timedelta(minutes=6),
        ),
    ]
    db.add_all(alerts)

    anomaly = AnomalyState(
        table_name="metric_numeric",
        detector="zscore",
        agent_id="agent_demo_web",
        metric_name="cpu_v1.0.0.usage_overall",
        last_bucket="demo-bucket",
    )
    db.add(anomaly)

    return tickets, alerts, anomaly


def _bucket_start(ts: datetime, bucket_minutes: int) -> datetime:
    trimmed = ts.replace(second=0, microsecond=0)
    if bucket_minutes == 10:
        return trimmed - timedelta(minutes=trimmed.minute % 10)
    if bucket_minutes == 60:
        return trimmed.replace(minute=0)
    return trimmed


def _aggregate_numeric(numeric_rows: List[MetricNumeric], bucket_minutes: int):
    grouped: Dict[Tuple[str, str, datetime], Dict[str, Any]] = {}
    for row in numeric_rows:
        bucket = _bucket_start(row.timestamp if row.timestamp.tzinfo else row.timestamp.replace(tzinfo=timezone.utc), bucket_minutes)
        key = (row.agent_id, row.metric_name, bucket)
        stats = grouped.setdefault(
            key, {"count": 0, "sum": 0.0, "min": math.inf, "max": -math.inf}
        )
        stats["count"] += 1
        stats["sum"] += float(row.value)
        stats["min"] = min(stats["min"], float(row.value))
        stats["max"] = max(stats["max"], float(row.value))
    return grouped


def _seed_rollup_state(db, last_1m: datetime, last_10m: datetime, last_1h: datetime):
    db.add_all(
        [
            RollupState(source_table=SOURCE_POSTGRES, target_table=MEASUREMENT_1M, last_bucket=last_1m),
            RollupState(source_table=SOURCE_1M, target_table=MEASUREMENT_10M, last_bucket=last_10m),
            RollupState(source_table=SOURCE_10M, target_table=MEASUREMENT_1H, last_bucket=last_1h),
        ]
    )


def _seed_influx_rollups(numeric_rows: List[MetricNumeric]):
    if Point is None or InfluxDBService is None:
        return {"written": 0, "skipped_reason": "influx client not installed"}

    try:
        client = InfluxDBService.getClient()
        write_api = InfluxDBService.getWriteApiSync(client)
        bucket = InfluxDBService.getBucket()
        org = InfluxDBService.getOrg()
        if not bucket or not org:
            return {"written": 0, "skipped_reason": "INFLUX_BUCKET/ORG not set"}
    except Exception as exc:  # pragma: no cover - external service
        return {"written": 0, "skipped_reason": f"Influx init failed: {exc}"}

    total_points = 0
    points_written = {"1m": 0, "10m": 0, "1h": 0}
    for measurement, bucket_minutes in [
        (MEASUREMENT_1M, 1),
        (MEASUREMENT_10M, 10),
        (MEASUREMENT_1H, 60),
    ]:
        grouped = _aggregate_numeric(numeric_rows, bucket_minutes)
        points: list[Any] = []
        for (agent_id, metric_name, bucket_start), stats in grouped.items():
            match = _METRIC_PATTERN.match(metric_name)
            if not match:
                continue
            metric = match.group("metric")
            version = match.group("version")
            unit = match.group("unit")
            if stats["count"] == 0:
                continue
            avg = stats["sum"] / stats["count"]
            points.append(
                Point(measurement)
                .tag(TAG_AGENT_ID, agent_id)
                .tag(TAG_METRIC, metric)
                .tag(TAG_VERSION, version)
                .tag(TAG_UNIT, unit)
                .field(FIELD_COUNT, int(stats["count"]))
                .field(FIELD_MIN, float(stats["min"]))
                .field(FIELD_MAX, float(stats["max"]))
                .field(FIELD_SUM, float(stats["sum"]))
                .field(FIELD_AVG, float(avg))
                .field(FIELD_BUCKET_START, bucket_start.isoformat())
                .time(bucket_start)
            )
        if points:
            write_api.write(bucket=bucket, record=points, org=org)
            total_points += len(points)
            key = "1m" if bucket_minutes == 1 else "10m" if bucket_minutes == 10 else "1h"
            points_written[key] = len(points)

    try:
        client.close()
    except Exception:
        pass

    return {"written": total_points, "per_measurement": points_written, "skipped_reason": None}


def seed_demo_data(skip_influx: bool = False) -> dict:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    now = _now()
    try:
        _ensure_alert_ack_columns(db)
        _ensure_ticket_ack_columns(db)
        _purge_demo_rows(db)
        purposes = _seed_purposes(db)
        agents = _seed_agents(db, purposes, now)
        numeric_rows, json_rows = _seed_metrics(db, now)
        tickets, alerts, anomaly = _seed_tickets_and_alerts(db, now)
        guidance_rows = _seed_guidance(db)

        # Rollup cursors set to the freshest bucket we generated
        last_1m = _bucket_start(max(r.timestamp for r in numeric_rows), 1)
        last_10m = _bucket_start(max(r.timestamp for r in numeric_rows), 10)
        last_1h = _bucket_start(max(r.timestamp for r in numeric_rows), 60)
        _seed_rollup_state(db, last_1m, last_10m, last_1h)

        db.commit()

        influx_result = {"written": 0, "skipped_reason": "skip_influx flag"} if skip_influx else _seed_influx_rollups(numeric_rows)

        return {
            "agents": len(agents),
            "numeric_metrics": len(numeric_rows),
            "json_metrics": len(json_rows),
            "tickets": len(tickets),
            "alerts": len(alerts),
            "guidance": len(guidance_rows),
            "anomalies": 1,
            "rollup_state": {"1m": last_1m.isoformat(), "10m": last_10m.isoformat(), "1h": last_1h.isoformat()},
            "influx": influx_result,
        }
    finally:
        db.close()


def main():
    skip_influx = os.getenv("SKIP_INFLUX", "false").lower() in ("1", "true", "yes", "y")
    summary = seed_demo_data(skip_influx=skip_influx)
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
