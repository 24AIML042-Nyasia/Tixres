"""celery_tasks.py – Celery application + beat schedule for background jobs.

Workers
-------
Start the worker:
    celery -A celery_tasks worker --loglevel=info

Start the scheduler (beat):
    celery -A celery_tasks beat --loglevel=info

Or both together (dev):
    celery -A celery_tasks worker --beat --loglevel=info

Redis is the default broker; override with the CELERY_BROKER_URL env-var.
You can also use an in-process scheduler with the ``celery.backends.database``
backend or the ``django-celery-beat`` package if you prefer SQLite/DB beats.
"""
from __future__ import annotations

import logging
import os
from datetime import timedelta
from pathlib import Path

from celery import Celery
from celery.schedules import crontab

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────
#  App configuration
# ──────────────────────────────────────────────────────────────────
def _load_platform_config() -> dict:
    """Read the central config.json from the project root."""
    cfg_path = Path(__file__).resolve().parents[1] / "config.json"
    if cfg_path.exists():
        import json
        with cfg_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}

_pcfg = _load_platform_config()
BROKER_URL     = os.environ.get("CELERY_BROKER_URL",     _pcfg.get("celery", {}).get("broker_url",     "redis://127.0.0.1:6379/0"))
RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", _pcfg.get("celery", {}).get("result_backend", "redis://127.0.0.1:6379/1"))

app = Celery(
    "two_o",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Retry connection if broker is unavailable at startup
    broker_connection_retry_on_startup=True,
    # Beat schedule
    beat_schedule={
        # ── alert expiry: every 5 minutes ──────────────────────
        "expire-alerts": {
            "task": "celery_tasks.expire_alerts",
            "schedule": timedelta(minutes=5),
        },
        # ── incident expiry: every 10 minutes ──────────────────
        "expire-incidents": {
            "task": "celery_tasks.expire_incidents",
            "schedule": timedelta(minutes=10),
        },
        # ── metric retention: hourly ────────────────────────────
        "retention-cleanup": {
            "task": "celery_tasks.run_retention_cleanup",
            "schedule": crontab(minute=0),   # top of every hour
        },
        # ── 1-minute rollup: every minute ──────────────────────
        "rollup-1m": {
            "task": "celery_tasks.run_rollup",
            "schedule": timedelta(minutes=1),
            "args": (60, "metric_numeric_1m"),
        },
        # ── 10-minute rollup: every 10 minutes ─────────────────
        "rollup-10m": {
            "task": "celery_tasks.run_rollup",
            "schedule": timedelta(minutes=10),
            "args": (600, "metric_numeric_10m"),
        },
        # ── 1-hour rollup: every hour ───────────────────────────
        "rollup-1h": {
            "task": "celery_tasks.run_rollup",
            "schedule": crontab(minute=5),   # 5 past every hour
            "args": (3600, "metric_numeric_1h"),
        },
    },
)

# ──────────────────────────────────────────────────────────────────
#  Path injection for standalone Celery execution
# ──────────────────────────────────────────────────────────────────
import sys
import pathlib
_server_dir = pathlib.Path(__file__).resolve().parent
if str(_server_dir) not in sys.path:
    sys.path.insert(0, str(_server_dir))

# ──────────────────────────────────────────────────────────────────
#  Lazy storage / incident store factories
# ──────────────────────────────────────────────────────────────────

def _get_store():
    """Return a Storage instance."""
    from storage import get_storage  # type: ignore
    return get_storage()


def _get_incident_store():
    from incidents import IncidentStore  # type: ignore
    return IncidentStore()


# ──────────────────────────────────────────────────────────────────
#  Tasks
# ──────────────────────────────────────────────────────────────────

@app.task(name="celery_tasks.expire_alerts", bind=True, max_retries=3)
def expire_alerts(self):
    """Expire stale alerts by severity window."""
    try:
        store = _get_store()
        rules = {
            "HIGH":   2 * 3600,  # 2 h
            "MEDIUM": 3600,      # 1 h
            "LOW":    1800,      # 30 min
        }
        count = store.expire_alerts(rules)
        log.info("[celery] expire_alerts: resolved %d alerts", count)
        return {"resolved": count}
    except Exception as exc:
        log.exception("[celery] expire_alerts failed")
        raise self.retry(exc=exc, countdown=60)


@app.task(name="celery_tasks.expire_incidents", bind=True, max_retries=3)
def expire_incidents(self):
    """Auto-resolve stale open incidents."""
    try:
        store = _get_incident_store()
        count = store.expire_incidents()
        log.info("[celery] expire_incidents: resolved %d incidents", count)
        return {"resolved": count}
    except Exception as exc:
        log.exception("[celery] expire_incidents failed")
        raise self.retry(exc=exc, countdown=120)


@app.task(name="celery_tasks.run_rollup", bind=True, max_retries=3)
def run_rollup(self, bucket_seconds: int, target_table: str):
    """Trigger a numeric rollup for the given bucket size."""
    try:
        from rollups import RollupService  # type: ignore
        store = _get_store()
        rs = RollupService(store.path)
        result = rs.run_numeric_rollup(bucket_seconds=bucket_seconds, target_table=target_table)
        log.info("[celery] rollup %s: %d buckets written", target_table, result.buckets_written)
        return {"table": target_table, "buckets": result.buckets_written}
    except Exception as exc:
        log.exception("[celery] run_rollup failed for %s", target_table)
        raise self.retry(exc=exc, countdown=30)


@app.task(name="celery_tasks.run_retention_cleanup", bind=True, max_retries=3)
def run_retention_cleanup(self):
    """
    Delete raw metric rows that are older than the retention policy.

    Retention policy (template-driven via template.json):
      metric_numeric  – 7 days
      metric_json     – 3 days
      metric_log      – 1 day
    """
    try:
        import sqlite3
        from datetime import datetime, timedelta

        store = _get_store()

        # Load retention from template if available, else use defaults
        retention_days = _load_retention_policy()

        with sqlite3.connect(store.path) as conn:
            total_deleted = 0
            for table, days in retention_days.items():
                cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
                cur = conn.execute(
                    f"DELETE FROM {table} WHERE timestamp < ?;",
                    (cutoff,),
                )
                deleted = cur.rowcount
                total_deleted += deleted
                if deleted:
                    log.info("[celery] retention: deleted %d rows from %s (cutoff=%s)", deleted, table, cutoff)

        log.info("[celery] retention_cleanup: total deleted=%d", total_deleted)
        return {"deleted": total_deleted}
    except Exception as exc:
        log.exception("[celery] run_retention_cleanup failed")
        raise self.retry(exc=exc, countdown=300)


def _load_retention_policy() -> dict[str, int]:
    """
    Read retention_days from plugin_defaults.json if present, otherwise return defaults.
    """
    import json

    defaults = {
        "metric_numeric": 7,
        "metric_json": 3,
        "metric_log": 1,
    }

    try:
        config_path = Path(__file__).with_name("plugin_defaults.json")
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf-8"))
            retention = config.get("retention", {})
            for key in defaults:
                if isinstance(retention.get(key), (int, float)) and retention[key] > 0:
                    defaults[key] = int(retention[key])
    except Exception:
        pass

    return defaults
