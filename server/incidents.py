"""incidents.py – Alert → Incident mapping layer.

incident_key = SHA-256( host_id | service | plugin | time_bucket )

A new incident is opened (or an existing open one is updated) every time
an alert fires.  Incidents are closed automatically by the Celery expiry
tasks defined at the bottom of this module.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────
#  Time bucket helpers
# ──────────────────────────────────────────────────────────────────
BUCKET_MINUTES = 10  # each 10-minute window gets a unique bucket label
INCIDENT_TS_FMT = "%Y-%m-%d %H:%M:%S"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _time_bucket(dt: datetime | None = None, bucket_minutes: int = BUCKET_MINUTES) -> str:
    """Floor *dt* to the nearest *bucket_minutes* interval and return as string."""
    if dt is None:
        dt = _utcnow()
    total_seconds = int(dt.timestamp())
    bucket_seconds = bucket_minutes * 60
    floored = (total_seconds // bucket_seconds) * bucket_seconds
    return datetime.utcfromtimestamp(floored).strftime(INCIDENT_TS_FMT)


# ──────────────────────────────────────────────────────────────────
#  Deterministic key
# ──────────────────────────────────────────────────────────────────

def make_incident_key(
    host_id: str,
    service: str,
    plugin: str,
    time_bucket: str,
) -> str:
    """Return a hex SHA-256 that uniquely identifies an incident window."""
    raw = f"{host_id}|{service}|{plugin}|{time_bucket}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ──────────────────────────────────────────────────────────────────
#  IncidentStore – thin SQLite wrapper (mirrors SqliteStorage style)
# ──────────────────────────────────────────────────────────────────

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "agent_metrics.sqlite3"

# Severity → max open lifetime in seconds
EXPIRY_RULES: dict[str, int] = {
    "HIGH": 4 * 3600,    # 4 h
    "MEDIUM": 2 * 3600,  # 2 h
    "LOW": 3600,         # 1 h
}


try:
    from sqlalchemy import create_engine, text, Column, Integer, String, Text, TIMESTAMP, Index
    from sqlalchemy.orm import sessionmaker, Session
    from models import Incident, Base, SQLALCHEMY_AVAILABLE
except ImportError:
    SQLALCHEMY_AVAILABLE = False

class IncidentStore:
    def __init__(self, path: Path = DEFAULT_DB_PATH) -> None:
        self._path = Path(path)
        self._use_sqlalchemy = SQLALCHEMY_AVAILABLE
        self._engine = None
        self._SessionLocal = None

        if self._use_sqlalchemy:
            # Check config for postgres
            from config_loader import get_db_url
            connection_url = get_db_url()
            
            self._engine = create_engine(connection_url)
            self._SessionLocal = sessionmaker(bind=self._engine, expire_on_commit=False)

    # ── schema ───────────────────────────────────────────────────
    def init_db(self) -> None:
        if self._use_sqlalchemy and self._engine:
            Base.metadata.create_all(self._engine)
            return

        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS incidents (
                  id              INTEGER PRIMARY KEY AUTOINCREMENT,
                  incident_key    TEXT NOT NULL UNIQUE,
                  host_id         TEXT NOT NULL,
                  service         TEXT NOT NULL,
                  plugin          TEXT NOT NULL,
                  anomaly_type    TEXT NOT NULL,
                  severity        TEXT NOT NULL,
                  time_bucket     TEXT NOT NULL,
                  status          TEXT NOT NULL DEFAULT 'open',
                  alert_count     INTEGER NOT NULL DEFAULT 1,
                  first_seen      TIMESTAMP NOT NULL,
                  last_seen       TIMESTAMP NOT NULL,
                  resolved_at     TIMESTAMP,
                  alert_ids       TEXT NOT NULL DEFAULT '[]'
                );
                """
            )
            # Migration: add 'plugin' column if missing (unlikely but safe)
            cursor = conn.execute("PRAGMA table_info(incidents);")
            columns = [row[1] for row in cursor.fetchall()]
            if "plugin" not in columns:
                conn.execute("ALTER TABLE incidents ADD COLUMN plugin TEXT NOT NULL DEFAULT 'unknown';")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_incidents_key ON incidents(incident_key);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_incidents_host ON incidents(host_id);")

    # ── upsert ───────────────────────────────────────────────────
    def upsert_incident(
        self,
        *,
        host_id: str,
        service: str,
        plugin: str,
        anomaly_type: str,
        severity: str,
        alert_id: int | None,
        timestamp: str | None = None,
        bucket_minutes: int = BUCKET_MINUTES,
    ) -> dict[str, Any]:
        """Create or update the incident that owns this alert."""
        self.init_db()

        ts_dt = _utcnow()
        if timestamp:
            try:
                ts_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                pass

        bucket = _time_bucket(ts_dt, bucket_minutes)
        key = make_incident_key(host_id, service, plugin, bucket)
        now_str = ts_dt.strftime(INCIDENT_TS_FMT)

        if self._use_sqlalchemy and self._SessionLocal:
            with self._SessionLocal() as session:
                existing = session.query(Incident).filter(Incident.incident_key == key).one_or_none()
                if existing:
                    alert_ids = json.loads(existing.alert_ids or "[]")
                    if alert_id is not None and alert_id not in alert_ids:
                        alert_ids.append(alert_id)
                    
                    severity_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
                    if severity_rank.get(severity, 0) > severity_rank.get(existing.severity, 0):
                        existing.severity = severity
                    
                    existing.last_seen = ts_dt
                    existing.alert_count += 1
                    existing.alert_ids = json.dumps(alert_ids)
                    existing.status = 'open'
                    existing.resolved_at = None
                    session.commit()
                    return {
                        "id": existing.id, "incident_key": key, "host_id": host_id,
                        "service": service, "plugin": plugin, "anomaly_type": anomaly_type,
                        "severity": existing.severity, "time_bucket": bucket, "status": "open",
                        "alert_count": existing.alert_count, "first_seen": existing.first_seen.strftime(INCIDENT_TS_FMT),
                        "last_seen": now_str, "alert_ids": alert_ids
                    }
                else:
                    alert_ids = [alert_id] if alert_id is not None else []
                    new_inc = Incident(
                        incident_key=key, host_id=host_id, service=service, plugin=plugin,
                        anomaly_type=anomaly_type, severity=severity, time_bucket=bucket,
                        status='open', alert_count=1, first_seen=ts_dt, last_seen=ts_dt,
                        alert_ids=json.dumps(alert_ids)
                    )
                    session.add(new_inc)
                    session.commit()
                    return {
                        "id": new_inc.id, "incident_key": key, "host_id": host_id,
                        "service": service, "plugin": plugin, "anomaly_type": anomaly_type,
                        "severity": severity, "time_bucket": bucket, "status": "open",
                        "alert_count": 1, "first_seen": now_str, "last_seen": now_str, "alert_ids": alert_ids
                    }

        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            existing = conn.execute(
                "SELECT id, alert_ids, alert_count, first_seen, severity FROM incidents WHERE incident_key = ?;",
                (key,),
            ).fetchone()

            if existing:
                alert_ids: list = json.loads(existing["alert_ids"] or "[]")
                if alert_id is not None and alert_id not in alert_ids:
                    alert_ids.append(alert_id)

                severity_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
                final_severity = severity if severity_rank.get(severity, 0) >= severity_rank.get(existing["severity"], 0) else existing["severity"]

                conn.execute(
                    """
                    UPDATE incidents SET
                      last_seen   = ?,
                      alert_count = alert_count + 1,
                      alert_ids   = ?,
                      severity    = ?,
                      status      = 'open',
                      resolved_at = NULL
                    WHERE incident_key = ?;
                    """,
                    (now_str, json.dumps(alert_ids), final_severity, key),
                )
                return {
                    "id": existing["id"],
                    "incident_key": key,
                    "host_id": host_id,
                    "service": service,
                    "plugin": plugin,
                    "anomaly_type": anomaly_type,
                    "severity": final_severity,
                    "time_bucket": bucket,
                    "status": "open",
                    "alert_count": existing["alert_count"] + 1,
                    "first_seen": existing["first_seen"],
                    "last_seen": now_str,
                    "alert_ids": alert_ids,
                }
            else:
                alert_ids = [alert_id] if alert_id is not None else []
                cursor = conn.execute(
                    """
                    INSERT INTO incidents(
                      incident_key, host_id, service, plugin, anomaly_type,
                      severity, time_bucket, status, alert_count,
                      first_seen, last_seen, alert_ids
                    )
                    VALUES (?,?,?,?,?,?,?,'open',1,?,?,?);
                    """,
                    (key, host_id, service, plugin, anomaly_type,
                     severity, bucket, now_str, now_str, json.dumps(alert_ids)),
                )
                return {
                    "id": cursor.lastrowid,
                    "incident_key": key,
                    "host_id": host_id,
                    "service": service,
                    "plugin": plugin,
                    "anomaly_type": anomaly_type,
                    "severity": severity,
                    "time_bucket": bucket,
                    "status": "open",
                    "alert_count": 1,
                    "first_seen": now_str,
                    "last_seen": now_str,
                    "alert_ids": alert_ids,
                }

    # ── queries ──────────────────────────────────────────────────
    def list_incidents(
        self,
        *,
        status: str | None = None,
        host_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        self.init_db()
        if self._use_sqlalchemy and self._SessionLocal:
            with self._SessionLocal() as session:
                query = session.query(Incident)
                if status: query = query.filter(Incident.status == status)
                if host_id: query = query.filter(Incident.host_id == host_id)
                rows = query.order_by(Incident.last_seen.desc()).limit(limit).all()
                res = []
                for r in rows:
                    d = {c.name: getattr(r, c.name) for c in r.__table__.columns}
                    # Datetime conversion
                    for k in ["first_seen", "last_seen", "resolved_at"]:
                        if d.get(k) and isinstance(d[k], datetime):
                            d[k] = d[k].strftime(INCIDENT_TS_FMT)
                    if d.get("alert_ids"): d["alert_ids"] = json.loads(d["alert_ids"])
                    res.append(d)
                return res

        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if host_id:
            clauses.append("host_id = ?")
            params.append(host_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(int(limit))

        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT * FROM incidents
                {where}
                ORDER BY last_seen DESC
                LIMIT ?;
                """,
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def get_incident(self, incident_id: int) -> dict[str, Any] | None:
        self.init_db()
        if self._use_sqlalchemy and self._SessionLocal:
            with self._SessionLocal() as session:
                r = session.get(Incident, incident_id)
                if not r: return None
                d = {c.name: getattr(r, c.name) for c in r.__table__.columns}
                for k in ["first_seen", "last_seen", "resolved_at"]:
                    if d.get(k) and isinstance(d[k], datetime):
                        d[k] = d[k].strftime(INCIDENT_TS_FMT)
                if d.get("alert_ids"): d["alert_ids"] = json.loads(d["alert_ids"])
                return d

        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM incidents WHERE id = ?;", (incident_id,)
            ).fetchone()
        return dict(row) if row else None

    def resolve_incident(self, incident_id: int) -> bool:
        self.init_db()
        now_dt = _utcnow()
        if self._use_sqlalchemy and self._SessionLocal:
            with self._SessionLocal() as session:
                r = session.get(Incident, incident_id)
                if r and r.status == 'open':
                    r.status = 'resolved'
                    r.resolved_at = now_dt
                    session.commit()
                    return True
                return False

        now_str = now_dt.strftime(INCIDENT_TS_FMT)
        with sqlite3.connect(self._path) as conn:
            cur = conn.execute(
                "UPDATE incidents SET status='resolved', resolved_at=? WHERE id=? AND status='open';",
                (now_str, incident_id),
            )
        return cur.rowcount > 0

    # ── expiry ────────────────────────────────────────────────────
    def expire_incidents(self, expiry_rules: dict[str, int] | None = None) -> int:
        """Auto-resolve incidents whose last_seen is older than expiry window."""
        self.init_db()
        rules = expiry_rules or EXPIRY_RULES
        now_dt = _utcnow()
        total = 0
        
        if self._use_sqlalchemy and self._SessionLocal:
            with self._SessionLocal() as session:
                for severity, seconds in rules.items():
                    cutoff = now_dt - timedelta(seconds=seconds)
                    res = session.query(Incident).filter(
                        Incident.severity == severity,
                        Incident.status == 'open',
                        Incident.last_seen < cutoff
                    ).update({Incident.status: 'resolved', Incident.resolved_at: now_dt}, synchronize_session=False)
                    total += res
                session.commit()
            return total

        now_str = now_dt.strftime(INCIDENT_TS_FMT)
        with sqlite3.connect(self._path) as conn:
            for severity, seconds in rules.items():
                cutoff = (_utcnow() - timedelta(seconds=seconds)).strftime(INCIDENT_TS_FMT)
                cur = conn.execute(
                    """
                    UPDATE incidents SET status='resolved', resolved_at=?
                    WHERE severity=? AND status='open' AND last_seen < ?;
                    """,
                    (now_str, severity, cutoff),
                )
                total += cur.rowcount
        if total:
            log.info("Expired %d incidents", total)
        return total

    # ── stats ────────────────────────────────────────────────────
    def incident_summary(self) -> dict[str, Any]:
        self.init_db()
        if self._use_sqlalchemy and self._engine:
             with self._engine.connect() as conn:
                row = conn.execute(text("""
                    SELECT
                      COUNT(*) FILTER (WHERE status='open')     AS open_count,
                      COUNT(*) FILTER (WHERE status='resolved') AS resolved_count,
                      COUNT(*) FILTER (WHERE severity='HIGH' AND status='open')   AS high_open,
                      COUNT(*) FILTER (WHERE severity='MEDIUM' AND status='open') AS medium_open,
                      COUNT(*) FILTER (WHERE severity='LOW' AND status='open')    AS low_open
                    FROM incidents;
                """)).fetchone()
                if row: return {"open": row[0], "resolved": row[1], "high_open": row[2], "medium_open": row[3], "low_open": row[4]}
                return {}

        with sqlite3.connect(self._path) as conn:
            row = conn.execute(
                """
                SELECT
                  COUNT(*) FILTER (WHERE status='open')     AS open_count,
                  COUNT(*) FILTER (WHERE status='resolved') AS resolved_count,
                  COUNT(*) FILTER (WHERE severity='HIGH' AND status='open')   AS high_open,
                  COUNT(*) FILTER (WHERE severity='MEDIUM' AND status='open') AS medium_open,
                  COUNT(*) FILTER (WHERE severity='LOW' AND status='open')    AS low_open
                FROM incidents;
                """
            ).fetchone()
        if row:
            return {
                "open": row[0],
                "resolved": row[1],
                "high_open": row[2],
                "medium_open": row[3],
                "low_open": row[4],
            }
        return {}

