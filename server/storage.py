from __future__ import annotations

import json
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from models import SQLALCHEMY_AVAILABLE


DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "agent_metrics.sqlite3"

METRIC_TS_FMT = "%Y-%m-%d %H:%M:%S"

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

def _utcnow_naive() -> datetime:
    return datetime.utcnow()


def _utcnow_iso() -> str:
    return _utcnow().isoformat()


def _parse_timestamp(value: Any) -> str:
    return _parse_timestamp_dt(value).strftime(METRIC_TS_FMT)


def _parse_timestamp_dt(value: Any) -> datetime:
    if value is None:
        return _utcnow_naive()

    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc).replace(tzinfo=None)

    if isinstance(value, str):
        s = value.strip()
        if not s:
            return _utcnow_naive()
        try:
            # Accept "Z" suffix
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except Exception:
            return _utcnow_naive()

    return _utcnow_naive()


@dataclass(frozen=True)
class RegisteredAgent:
    agent_id: str
    api_key: str
    secret_key: str


@dataclass(frozen=True)
class AgentRow:
    agent_id: str
    agent_version: str
    hostname: str
    os: str
    template: str | None
    plugin: str | None
    heartbeat: str | None
    fingerprint: str | None
    role: str


class SqliteStorage:
    def __init__(self, path: Path = DEFAULT_DB_PATH):
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def url(self) -> str:
        return f"sqlite:///{self._path}"

    def init_db(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_credentials (
                  agent_id   TEXT PRIMARY KEY,
                  api_key    TEXT UNIQUE NOT NULL,
                  secret_key TEXT NOT NULL,
                  role       TEXT NOT NULL DEFAULT 'user',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  is_active  INTEGER DEFAULT 1
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agents (
                  agent_id      TEXT PRIMARY KEY,
                  agent_version TEXT NOT NULL,
                  hostname      TEXT NOT NULL,
                  os            TEXT NOT NULL,
                  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  template      TEXT,
                  plugin        TEXT,
                  heartbeat     TIMESTAMP,
                  fingerprint   TEXT,
                  FOREIGN KEY(agent_id) REFERENCES agent_credentials(agent_id) ON DELETE CASCADE
                );
                """
            )
            # Migration: add 'plugin' column if missing
            cursor = conn.execute("PRAGMA table_info(agents);")
            columns = [row[1] for row in cursor.fetchall()]
            if "plugin" not in columns:
                conn.execute("ALTER TABLE agents ADD COLUMN plugin TEXT;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS guidance (
                  id           INTEGER PRIMARY KEY AUTOINCREMENT,
                  anomaly_type TEXT UNIQUE NOT NULL,
                  title        TEXT NOT NULL,
                  description  TEXT,
                  steps        TEXT, -- JSON array of strings
                  priority     TEXT NOT NULL,
                  created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS metric_numeric (
                  id          INTEGER PRIMARY KEY AUTOINCREMENT,
                  agent_id    TEXT NOT NULL,
                  metric_name TEXT NOT NULL,
                  value       REAL NOT NULL,
                  timestamp   TIMESTAMP NOT NULL,
                  received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY(agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_metric_raw_time ON metric_numeric(timestamp);"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS metric_json (
                  id          INTEGER PRIMARY KEY AUTOINCREMENT,
                  agent_id    TEXT NOT NULL,
                  metric_name TEXT NOT NULL,
                  value       TEXT NOT NULL,
                  timestamp   TIMESTAMP NOT NULL,
                  received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY(agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_metric_json_time ON metric_json(timestamp);"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS metric_log (
                  id          INTEGER PRIMARY KEY AUTOINCREMENT,
                  agent_id    TEXT NOT NULL,
                  metric_name TEXT NOT NULL,
                  value       TEXT NOT NULL,
                  timestamp   TIMESTAMP NOT NULL,
                  received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY(agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_metric_log_time ON metric_log(timestamp);"
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_inventory (
                  agent_id      TEXT PRIMARY KEY,
                  fingerprint   TEXT,
                  modules_json  TEXT,
                  functions_json TEXT,
                  updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY(agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
                );
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rollup_state (
                  source_table TEXT NOT NULL,
                  target_table TEXT NOT NULL,
                  last_bucket  TIMESTAMP NOT NULL,
                  updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  PRIMARY KEY (source_table, target_table)
                );
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                  id           INTEGER PRIMARY KEY AUTOINCREMENT,
                  agent_id     TEXT NOT NULL,
                  service      TEXT NOT NULL,
                  anomaly_type TEXT NOT NULL,
                  severity     TEXT NOT NULL,
                  fingerprint  TEXT NOT NULL,
                  first_seen   TIMESTAMP NOT NULL,
                  last_seen    TIMESTAMP NOT NULL,
                  count        INTEGER DEFAULT 1,
                  plugin       TEXT,
                  is_resolved  INTEGER DEFAULT 0,
                  resolved_at  TIMESTAMP,
                  FOREIGN KEY(agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
                );
                """
            )
            # Migration: add 'plugin' column if missing
            cursor = conn.execute("PRAGMA table_info(alerts);")
            columns = [row[1] for row in cursor.fetchall()]
            if "plugin" not in columns:
                conn.execute("ALTER TABLE alerts ADD COLUMN plugin TEXT;")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_alerts_fingerprint ON alerts(fingerprint);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_alerts_agent_id ON alerts(agent_id);"
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS anomaly_state (
                  agent_id    TEXT NOT NULL,
                  detector_id TEXT NOT NULL,
                  state_json  TEXT,
                  updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  PRIMARY KEY (agent_id, detector_id),
                  FOREIGN KEY(agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
                );
                """
            )

            for table in ("metric_numeric_1m", "metric_numeric_10m", "metric_numeric_1h"):
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                      id          INTEGER PRIMARY KEY AUTOINCREMENT,
                      agent_id    TEXT NOT NULL,
                      metric_name TEXT NOT NULL,
                      bucket_start TIMESTAMP NOT NULL,
                      count       INTEGER NOT NULL,
                      min         REAL NOT NULL,
                      max         REAL NOT NULL,
                      sum         REAL NOT NULL,
                      received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY(agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE,
                      UNIQUE(agent_id, metric_name, bucket_start)
                    );
                    """
                )
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{table}_time ON {table}(bucket_start);"
                )

    def register_agent(
        self,
        *,
        agent_version: str,
        hostname: str,
        os_name: str,
        fingerprint: str | None = None,
        role: str = "user",
    ) -> RegisteredAgent:
        self.init_db()

        if not agent_version:
            raise ValueError("agent_version is required")
        if not hostname:
            raise ValueError("hostname is required")
        if not os_name:
            raise ValueError("os is required")

        agent_id = str(uuid.uuid4())
        api_key = secrets.token_hex(16)
        secret_key = secrets.token_hex(32)

        with sqlite3.connect(self._path) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute(
                """
                INSERT INTO agent_credentials(agent_id, api_key, secret_key, role, is_active)
                VALUES (?, ?, ?, ?, 1);
                """,
                (agent_id, api_key, secret_key, role),
            )
            conn.execute(
                """
                INSERT INTO agents(agent_id, agent_version, hostname, os, fingerprint, heartbeat, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (agent_id, agent_version, hostname, os_name, fingerprint, _utcnow_iso(), _utcnow_iso()),
            )

        return RegisteredAgent(agent_id=agent_id, api_key=api_key, secret_key=secret_key)

    def get_credentials_by_api_key(self, api_key: str) -> dict[str, Any] | None:
        self.init_db()
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT agent_id, api_key, secret_key, role, is_active
                FROM agent_credentials
                WHERE api_key = ?;
                """,
                (api_key,),
            ).fetchone()
            return dict(row) if row else None

    def get_agent_row(self, agent_id: str) -> AgentRow | None:
        self.init_db()
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT
                  a.agent_id,
                  a.agent_version,
                  a.hostname,
                  a.os,
                  a.template,
                  a.plugin,
                  a.heartbeat,
                  a.fingerprint,
                  c.role
                FROM agents a
                JOIN agent_credentials c ON c.agent_id = a.agent_id
                WHERE a.agent_id = ?;
                """,
                (agent_id,),
            ).fetchone()
            if not row:
                return None
            return AgentRow(
                agent_id=row["agent_id"],
                agent_version=row["agent_version"],
                hostname=row["hostname"],
                os=row["os"],
                template=row["template"],
                plugin=row["plugin"],
                heartbeat=row["heartbeat"],
                fingerprint=row["fingerprint"],
                role=row["role"],
            )

    def list_agents(self) -> list[AgentRow]:
        self.init_db()
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT
                  a.agent_id,
                  a.agent_version,
                  a.hostname,
                  a.os,
                  a.template,
                  a.plugin,
                  a.heartbeat,
                  a.fingerprint,
                  c.role
                FROM agents a
                JOIN agent_credentials c ON c.agent_id = a.agent_id
                ORDER BY a.updated_at DESC;
                """
            ).fetchall()

            agents: list[AgentRow] = []
            for row in rows:
                agents.append(
                    AgentRow(
                        agent_id=row["agent_id"],
                        agent_version=row["agent_version"],
                        hostname=row["hostname"],
                        os=row["os"],
                        template=row["template"],
                        plugin=row["plugin"],
                        heartbeat=row["heartbeat"],
                        fingerprint=row["fingerprint"],
                        role=row["role"],
                    )
                )
            return agents

    def get_recent_metrics(self, *, agent_id: str, limit: int = 500) -> list[dict[str, Any]]:
        self.init_db()
        if limit <= 0:
            return []
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT metric_name, value, timestamp, 'float' AS dtype
                FROM metric_numeric
                WHERE agent_id = ?
                UNION ALL
                SELECT metric_name, value, timestamp, 'json' AS dtype
                FROM metric_json
                WHERE agent_id = ?
                UNION ALL
                SELECT metric_name, value, timestamp, 'log' AS dtype
                FROM metric_log
                WHERE agent_id = ?
                ORDER BY timestamp DESC
                LIMIT ?;
                """,
                (agent_id, agent_id, agent_id, int(limit)),
            ).fetchall()
            return [dict(row) for row in rows]

    def update_agent_on_login(
        self,
        *,
        agent_id: str,
        agent_version: str | None = None,
        hostname: str | None = None,
        os_name: str | None = None,
        fingerprint: str | None = None,
    ) -> None:
        self.init_db()
        heartbeat = _utcnow_iso()
        updated_at = _utcnow_iso()

        fields: list[str] = ["heartbeat = ?", "updated_at = ?"]
        values: list[Any] = [heartbeat, updated_at]

        if agent_version:
            fields.append("agent_version = ?")
            values.append(agent_version)
        if hostname:
            fields.append("hostname = ?")
            values.append(hostname)
        if os_name:
            fields.append("os = ?")
            values.append(os_name)
        if fingerprint is not None:
            fields.append("fingerprint = ?")
            values.append(fingerprint)

        values.append(agent_id)

        with sqlite3.connect(self._path) as conn:
            conn.execute(
                f"UPDATE agents SET {', '.join(fields)} WHERE agent_id = ?;",
                tuple(values),
            )

    def update_template(self, *, agent_id: str, template: dict[str, Any]) -> None:
        self.init_db()
        template_text = json.dumps(template, ensure_ascii=False)
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                "UPDATE agents SET template = ?, updated_at = ? WHERE agent_id = ?;",
                (template_text, _utcnow_iso(), agent_id),
            )

    def update_plugin(self, *, agent_id: str, plugin: str | None) -> None:
        self.init_db()
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                "UPDATE agents SET plugin = ?, updated_at = ? WHERE agent_id = ?;",
                (plugin, _utcnow_iso(), agent_id),
            )

    def get_guidance(self, anomaly_type: str) -> dict[str, Any] | None:
        self.init_db()
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM guidance WHERE anomaly_type = ?;", (anomaly_type,)
            ).fetchone()
            if not row:
                return None
            res = dict(row)
            if res.get("steps"):
                res["steps"] = json.loads(res["steps"])
            return res

    def list_guidance(self) -> list[dict[str, Any]]:
        self.init_db()
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM guidance ORDER BY anomaly_type ASC;").fetchall()
            results = []
            for r in rows:
                d = dict(r)
                if d.get("steps"):
                    d["steps"] = json.loads(d["steps"])
                results.append(d)
            return results

    def upsert_guidance(self, anomaly_type: str, title: str, description: str, steps: list[str], priority: str) -> None:
        self.init_db()
        steps_json = json.dumps(steps)
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                """
                INSERT INTO guidance(anomaly_type, title, description, steps, priority, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(anomaly_type) DO UPDATE SET
                  title=excluded.title,
                  description=excluded.description,
                  steps=excluded.steps,
                  priority=excluded.priority,
                  updated_at=CURRENT_TIMESTAMP;
                """,
                (anomaly_type, title, description, steps_json, priority),
            )

    def delete_guidance(self, anomaly_type: str) -> bool:
        self.init_db()
        with sqlite3.connect(self._path) as conn:
            cursor = conn.execute("DELETE FROM guidance WHERE anomaly_type = ?;", (anomaly_type,))
            return cursor.rowcount > 0

    def update_agent_inventory(
        self,
        *,
        agent_id: str,
        fingerprint: str | None,
        modules: list[str],
        functions: list[str],
    ) -> None:
        self.init_db()
        modules_json = json.dumps(modules, ensure_ascii=False)
        functions_json = json.dumps(functions, ensure_ascii=False)
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                """
                INSERT INTO agent_inventory(agent_id, fingerprint, modules_json, functions_json, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(agent_id) DO UPDATE SET
                  fingerprint=excluded.fingerprint,
                  modules_json=excluded.modules_json,
                  functions_json=excluded.functions_json,
                  updated_at=CURRENT_TIMESTAMP;
                """,
                (agent_id, fingerprint, modules_json, functions_json),
            )

    def get_rollup_last_bucket(self, *, source_table: str, target_table: str) -> str | None:
        self.init_db()
        with sqlite3.connect(self._path) as conn:
            row = conn.execute(
                """
                SELECT last_bucket FROM rollup_state
                WHERE source_table = ? AND target_table = ?;
                """,
                (source_table, target_table),
            ).fetchone()
            return row[0] if row else None

    def set_rollup_last_bucket(
        self, *, source_table: str, target_table: str, last_bucket: str
    ) -> None:
        self.init_db()
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                """
                INSERT INTO rollup_state(source_table, target_table, last_bucket, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(source_table, target_table) DO UPDATE SET
                  last_bucket=excluded.last_bucket,
                  updated_at=CURRENT_TIMESTAMP;
                """,
                (source_table, target_table, last_bucket),
            )

    def insert_metric_numeric(
        self, *, agent_id: str, metric_name: str, value: float, timestamp: Any
    ) -> None:
        self.init_db()
        ts = _parse_timestamp(timestamp)
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                """
                INSERT INTO metric_numeric(agent_id, metric_name, value, timestamp)
                VALUES (?, ?, ?, ?);
                """,
                (agent_id, metric_name, float(value), ts),
            )

    def insert_metric_json(
        self, *, agent_id: str, metric_name: str, value: str, timestamp: Any
    ) -> None:
        self.init_db()
        ts = _parse_timestamp(timestamp)
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                """
                INSERT INTO metric_json(agent_id, metric_name, value, timestamp)
                VALUES (?, ?, ?, ?);
                """,
                (agent_id, metric_name, value, ts),
            )

    def insert_metric_log(
        self, *, agent_id: str, metric_name: str, value: str, timestamp: Any
    ) -> None:
        self.init_db()
        ts = _parse_timestamp(timestamp)
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                """
                INSERT INTO metric_log(agent_id, metric_name, value, timestamp)
                VALUES (?, ?, ?, ?);
                """,
                (agent_id, metric_name, value, ts),
            )

    def upsert_alert(
        self,
        *,
        agent_id: str,
        service: str,
        anomaly_type: str,
        severity: str,
        fingerprint: str,
        timestamp: str,
        dedup_window_seconds: int,
        plugin: str | None = None,
    ) -> dict[str, Any]:
        self.init_db()
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            # Check for existing unresolved alert within dedup window
            window_start = (datetime.utcnow() - timedelta(seconds=dedup_window_seconds)).strftime(METRIC_TS_FMT)
            
            existing = conn.execute(
                """
                SELECT id, count, first_seen FROM alerts
                WHERE fingerprint = ? AND is_resolved = 0 AND last_seen >= ?
                ORDER BY last_seen DESC LIMIT 1;
                """,
                (fingerprint, window_start),
            ).fetchone()

            if existing:
                conn.execute(
                    """
                    UPDATE alerts SET
                      last_seen = ?,
                      count = count + 1
                    WHERE id = ?;
                    """,
                    (timestamp, existing["id"]),
                )
                return {
                    "id": existing["id"],
                    "fingerprint": fingerprint,
                    "first_seen": existing["first_seen"],
                    "last_seen": timestamp,
                    "count": existing["count"] + 1,
                    "severity": severity,
                }
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO alerts(agent_id, service, anomaly_type, severity, fingerprint, first_seen, last_seen, count, plugin)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?);
                    """,
                    (agent_id, service, anomaly_type, severity, fingerprint, timestamp, timestamp, plugin),
                )
                return {
                    "id": cursor.lastrowid,
                    "fingerprint": fingerprint,
                    "first_seen": timestamp,
                    "last_seen": timestamp,
                    "count": 1,
                    "severity": severity,
                }

    def get_anomaly_state(self, agent_id: str, detector_id: str) -> dict[str, Any] | None:
        self.init_db()
        with sqlite3.connect(self._path) as conn:
            row = conn.execute(
                "SELECT state_json FROM anomaly_state WHERE agent_id = ? AND detector_id = ?;",
                (agent_id, detector_id),
            ).fetchone()
            if row and row[0]:
                return json.loads(row[0])
            return None

    def set_anomaly_state(self, agent_id: str, detector_id: str, state: dict[str, Any]) -> None:
        self.init_db()
        state_json = json.dumps(state)
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                """
                INSERT INTO anomaly_state(agent_id, detector_id, state_json, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(agent_id, detector_id) DO UPDATE SET
                  state_json = excluded.state_json,
                  updated_at = CURRENT_TIMESTAMP;
                """,
                (agent_id, detector_id, state_json),
            )

    def expire_alerts(self, expiration_rules: dict[str, int]) -> int:
        """
        expiration_rules: maps severity (e.g., 'HIGH', 'MEDIUM') to seconds.
        """
        self.init_db()
        total_expired = 0
        with sqlite3.connect(self._path) as conn:
            for severity, seconds in expiration_rules.items():
                cutoff = (datetime.utcnow() - timedelta(seconds=seconds)).strftime(METRIC_TS_FMT)
                cursor = conn.execute(
                    """
                    UPDATE alerts SET is_resolved = 1, resolved_at = CURRENT_TIMESTAMP
                    WHERE severity = ? AND is_resolved = 0 AND last_seen < ?;
                    """,
                    (severity, cutoff),
                )
                total_expired += cursor.rowcount
        return total_expired

    def get_previous_metrics(self, agent_id: str, metric_name: str, limit: int = 20) -> list[float]:
        self.init_db()
        with sqlite3.connect(self._path) as conn:
            rows = conn.execute(
                """
                SELECT value FROM metric_numeric
                WHERE agent_id = ? AND metric_name = ?
                ORDER BY timestamp DESC
                LIMIT ?;
                """,
                (agent_id, metric_name, limit),
            ).fetchall()
            return [row[0] for row in rows]

    def resolve_alert(self, alert_id: int) -> bool:
        self.init_db()
        with sqlite3.connect(self._path) as conn:
            cur = conn.execute(
                "UPDATE alerts SET is_resolved = 1, resolved_at = CURRENT_TIMESTAMP WHERE id = ? AND is_resolved = 0;",
                (alert_id,),
            )
        return cur.rowcount > 0

    def list_alerts(
        self,
        *,
        agent_id: str | None = None,
        is_resolved: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return alerts, optionally filtered by agent and resolved state."""
        self.init_db()
        clauses: list[str] = []
        params: list[Any] = []
        if agent_id:
            clauses.append("agent_id = ?")
            params.append(agent_id)
        if is_resolved is not None:
            clauses.append("is_resolved = ?")
            params.append(int(is_resolved))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(int(limit))
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT id, agent_id, service, anomaly_type, severity,
                       fingerprint, first_seen, last_seen, count,
                       plugin, is_resolved, resolved_at
                FROM alerts
                {where}
                ORDER BY last_seen DESC
                LIMIT ?;
                """,
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def get_rollups(self, *, agent_id: str, metric_name: str, table: str = "metric_numeric_1h", limit: int = 24) -> list[dict[str, Any]]:
        self.init_db()
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT bucket_start, count, min, max, sum
                FROM {table}
                WHERE agent_id = ? AND metric_name = ?
                ORDER BY bucket_start DESC
                LIMIT ?;
                """,
                (agent_id, metric_name, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_metrics_table(
        self,
        *,
        table: str = "metric_numeric",
        agent_id: str | None = None,
        metric_name: str | None = None,
        from_ts: str | None = None,
        to_ts: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Query any metric table with optional filters. Returns rows + total count."""
        allowed_tables = {
            "metric_numeric", "metric_json", "metric_log",
            "metric_numeric_1m", "metric_numeric_10m", "metric_numeric_1h",
        }
        if table not in allowed_tables:
            raise ValueError(f"Invalid table: {table}")

        # Rollup tables have different columns
        is_rollup = table in {"metric_numeric_1m", "metric_numeric_10m", "metric_numeric_1h"}

        clauses: list[str] = []
        params: list[Any] = []

        if agent_id:
            clauses.append("agent_id = ?")
            params.append(agent_id)
        if metric_name:
            clauses.append("metric_name LIKE ?")
            params.append(f"%{metric_name}%")

        ts_col = "bucket_start" if is_rollup else "timestamp"
        if from_ts:
            clauses.append(f"{ts_col} >= ?")
            params.append(from_ts)
        if to_ts:
            clauses.append(f"{ts_col} <= ?")
            params.append(to_ts)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        self.init_db()
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            count_row = conn.execute(
                f"SELECT COUNT(*) FROM {table} {where};", params
            ).fetchone()
            total = count_row[0] if count_row else 0

            query_params = list(params) + [int(limit), int(offset)]
            rows = conn.execute(
                f"SELECT * FROM {table} {where} ORDER BY {ts_col} DESC LIMIT ? OFFSET ?;",
                query_params,
            ).fetchall()

        return {
            "table": table,
            "total": total,
            "limit": limit,
            "offset": offset,
            "rows": [dict(r) for r in rows],
        }

    def alert_summary(self) -> dict[str, Any]:
        """Return aggregate counts across all alerts."""
        self.init_db()
        with sqlite3.connect(self._path) as conn:
            row = conn.execute(
                """
                SELECT
                  COUNT(*) FILTER (WHERE is_resolved = 0)             AS open_count,
                  COUNT(*) FILTER (WHERE is_resolved = 1)             AS resolved_count,
                  COUNT(*) FILTER (WHERE severity='HIGH' AND is_resolved=0)   AS high_open,
                  COUNT(*) FILTER (WHERE severity='MEDIUM' AND is_resolved=0) AS medium_open,
                  COUNT(*) FILTER (WHERE severity='LOW' AND is_resolved=0)    AS low_open
                FROM alerts;
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


if SQLALCHEMY_AVAILABLE:  # pragma: no cover
    from sqlalchemy import create_engine, text  # type: ignore
    from sqlalchemy.orm import Session, sessionmaker  # type: ignore

    from models import (  # type: ignore
        Base,
        Agent,
        AgentCredentials,
        MetricJson,
        MetricLog,
        MetricNumeric,
        MetricRollup1m,
        MetricRollup10m,
        MetricRollup1h,
        Alert,
    )

    class SqlAlchemyStorage:
        def __init__(self, path: Path = DEFAULT_DB_PATH):
            self._path = Path(path)
            
            from config_loader import get_db_url
            connection_url = get_db_url()

            self._engine = create_engine(connection_url)
            self._SessionLocal = sessionmaker(bind=self._engine, expire_on_commit=False)
            self.init_db()

        @property
        def path(self) -> Path:
            return self._path

        @property
        def url(self) -> str:
            # Return URL but hide password
            u = str(self._engine.url)
            if ":" in u and "@" in u:
                parts = u.split("@")
                creds = parts[0].split(":")
                if len(creds) > 2:
                    return f"{creds[0]}:****@{parts[1]}"
            return u

        def init_db(self) -> None:
            Base.metadata.create_all(self._engine)
            # Migration/Maintenance: Ensure columns exist (mostly for SQLite which doesn't support complex migrations easily)
            if self._engine.name == "sqlite":
                with self._engine.connect() as conn:
                    # agents table
                    cursor = conn.execute(text("PRAGMA table_info(agents);"))
                    columns = [row[1] for row in cursor.fetchall()]
                    if "plugin" not in columns:
                        conn.execute(text("ALTER TABLE agents ADD COLUMN plugin TEXT;"))
                        conn.commit()
                    
                    # alerts table
                    cursor = conn.execute(text("PRAGMA table_info(alerts);"))
                    columns = [row[1] for row in cursor.fetchall()]
                    if "plugin" not in columns:
                        conn.execute(text("ALTER TABLE alerts ADD COLUMN plugin TEXT;"))
                        conn.commit()
                conn.commit()

        def _session(self) -> Session:
            return self._SessionLocal()

        def get_metrics_table(
            self,
            *,
            table: str = "metric_numeric",
            agent_id: str | None = None,
            metric_name: str | None = None,
            from_ts: str | None = None,
            to_ts: str | None = None,
            limit: int = 200,
            offset: int = 0,
        ) -> dict[str, Any]:
            """Query any metric table using SQLAlchemy with optional filters."""
            table_map = {
                "metric_numeric": MetricNumeric,
                "metric_json": MetricJson,
                "metric_log": MetricLog,
                "metric_numeric_1m": MetricRollup1m,
                "metric_numeric_10m": MetricRollup10m,
                "metric_numeric_1h": MetricRollup1h,
            }
            if table not in table_map:
                raise ValueError(f"Invalid table: {table}")

            model = table_map[table]
            is_rollup = table in {"metric_numeric_1m", "metric_numeric_10m", "metric_numeric_1h"}
            ts_col_name = "bucket_start" if is_rollup else "timestamp"
            ts_attr = getattr(model, ts_col_name)

            with self._session() as session:
                query = session.query(model)
                if agent_id:
                    query = query.filter(model.agent_id == agent_id)
                if metric_name:
                    query = query.filter(model.metric_name.like(f"%{metric_name}%"))
                
                # timestamps are stored as datetime objects in SQLAlchemy models usually, 
                # but models.py uses TIMESTAMP. Let's see if we need to parse them.
                if from_ts:
                    try:
                        dt_from = datetime.strptime(from_ts, METRIC_TS_FMT)
                        query = query.filter(ts_attr >= dt_from)
                    except (ValueError, TypeError):
                        pass
                if to_ts:
                    try:
                        dt_to = datetime.strptime(to_ts, METRIC_TS_FMT)
                        query = query.filter(ts_attr <= dt_to)
                    except (ValueError, TypeError):
                        pass

                total = query.count()
                rows = query.order_by(ts_attr.desc()).offset(offset).limit(limit).all()

                # Convert SQLAlchemy objects to dicts
                res_rows = []
                for r in rows:
                    d = {c.name: getattr(r, c.name) for c in r.__table__.columns}
                    # Convert datetimes to strings for JSON serializability
                    for k, v in d.items():
                        if isinstance(v, datetime):
                            d[k] = v.strftime(METRIC_TS_FMT)
                    res_rows.append(d)

            return {
                "table": table,
                "total": total,
                "limit": limit,
                "offset": offset,
                "rows": res_rows,
            }

        def register_agent(
            self,
            *,
            agent_version: str,
            hostname: str,
            os_name: str,
            fingerprint: str | None = None,
            role: str = "user",
        ) -> RegisteredAgent:
            if not agent_version:
                raise ValueError("agent_version is required")
            if not hostname:
                raise ValueError("hostname is required")
            if not os_name:
                raise ValueError("os is required")

            agent_id = str(uuid.uuid4())
            api_key = secrets.token_hex(16)
            secret_key = secrets.token_hex(32)

            with self._session() as session:
                session.add(
                    AgentCredentials(
                        agent_id=agent_id,
                        api_key=api_key,
                        secret_key=secret_key,
                        role=role,
                        is_active=1,
                    )
                )
                session.add(
                    Agent(
                        agent_id=agent_id,
                        agent_version=agent_version,
                        hostname=hostname,
                        os=os_name,
                        fingerprint=fingerprint,
                        heartbeat=_utcnow_naive(),
                    )
                )
                session.commit()

            return RegisteredAgent(agent_id=agent_id, api_key=api_key, secret_key=secret_key)

        def get_credentials_by_api_key(self, api_key: str) -> dict[str, Any] | None:
            with self._session() as session:
                cred = (
                    session.query(AgentCredentials)
                    .filter(AgentCredentials.api_key == api_key)
                    .one_or_none()
                )
                if cred is None:
                    return None
                return {
                    "agent_id": cred.agent_id,
                    "api_key": cred.api_key,
                    "secret_key": cred.secret_key,
                    "role": cred.role,
                    "is_active": cred.is_active,
                }

        def get_agent_row(self, agent_id: str) -> AgentRow | None:
            with self._session() as session:
                agent = session.get(Agent, agent_id)
                if agent is None:
                    return None
                role = agent.credentials.role if agent.credentials else "user"
                return AgentRow(
                    agent_id=agent.agent_id,
                    agent_version=agent.agent_version,
                    hostname=agent.hostname,
                    os=agent.os,
                    template=agent.template,
                    plugin=getattr(agent, 'plugin', None),
                    heartbeat=agent.heartbeat.isoformat() if agent.heartbeat else None,
                    fingerprint=agent.fingerprint,
                    role=role,
                )

        def list_agents(self) -> list[AgentRow]:
            with self._session() as session:
                agents = session.query(Agent).order_by(Agent.updated_at.desc()).all()
                rows: list[AgentRow] = []
                for agent in agents:
                    role = agent.credentials.role if agent.credentials else "user"
                    rows.append(
                        AgentRow(
                            agent_id=agent.agent_id,
                            agent_version=agent.agent_version,
                            hostname=agent.hostname,
                            os=agent.os,
                            template=agent.template,
                            plugin=getattr(agent, 'plugin', None),
                            heartbeat=agent.heartbeat.isoformat()
                            if agent.heartbeat
                            else None,
                            fingerprint=agent.fingerprint,
                            role=role,
                        )
                    )
                return rows

        def get_recent_metrics(self, *, agent_id: str, limit: int = 500) -> list[dict[str, Any]]:
            if limit <= 0:
                return []
            with self._session() as session:
                # Fetch in descending timestamp order per-table then merge; good enough for UI bootstrap.
                numeric = (
                    session.query(MetricNumeric)
                    .filter(MetricNumeric.agent_id == agent_id)
                    .order_by(MetricNumeric.timestamp.desc())
                    .limit(limit)
                    .all()
                )
                json_rows = (
                    session.query(MetricJson)
                    .filter(MetricJson.agent_id == agent_id)
                    .order_by(MetricJson.timestamp.desc())
                    .limit(limit)
                    .all()
                )
                log_rows = (
                    session.query(MetricLog)
                    .filter(MetricLog.agent_id == agent_id)
                    .order_by(MetricLog.timestamp.desc())
                    .limit(limit)
                    .all()
                )

                merged: list[dict[str, Any]] = []
                for row in numeric:
                    merged.append(
                        {
                            "metric_name": row.metric_name,
                            "value": row.value,
                            "timestamp": row.timestamp.isoformat()
                            if hasattr(row.timestamp, "isoformat")
                            else row.timestamp,
                            "dtype": "float",
                        }
                    )
                for row in json_rows:
                    merged.append(
                        {
                            "metric_name": row.metric_name,
                            "value": row.value,
                            "timestamp": row.timestamp.isoformat()
                            if hasattr(row.timestamp, "isoformat")
                            else row.timestamp,
                            "dtype": "json",
                        }
                    )
                for row in log_rows:
                    merged.append(
                        {
                            "metric_name": row.metric_name,
                            "value": row.value,
                            "timestamp": row.timestamp.isoformat()
                            if hasattr(row.timestamp, "isoformat")
                            else row.timestamp,
                            "dtype": "log",
                        }
                    )
                merged.sort(key=lambda x: str(x.get("timestamp") or ""), reverse=True)
                return merged[:limit]

        def update_agent_on_login(
            self,
            *,
            agent_id: str,
            agent_version: str | None = None,
            hostname: str | None = None,
            os_name: str | None = None,
            fingerprint: str | None = None,
        ) -> None:
            with self._session() as session:
                agent = session.get(Agent, agent_id)
                if agent is None:
                    return
                agent.heartbeat = _utcnow_naive()
                if agent_version:
                    agent.agent_version = agent_version
                if hostname:
                    agent.hostname = hostname
                if os_name:
                    agent.os = os_name
                if fingerprint is not None:
                    agent.fingerprint = fingerprint
                session.commit()

        def update_template(self, *, agent_id: str, template: dict[str, Any]) -> None:
            template_text = json.dumps(template, ensure_ascii=False)
            with self._session() as session:
                agent = session.get(Agent, agent_id)
                if agent is None:
                    return
                agent.template = template_text
                session.commit()

        def insert_metric_numeric(
            self, *, agent_id: str, metric_name: str, value: float, timestamp: Any
        ) -> None:
            with self._session() as session:
                session.add(
                    MetricNumeric(
                        agent_id=agent_id,
                        metric_name=metric_name,
                        value=float(value),
                        timestamp=_parse_timestamp_dt(timestamp),
                    )
                )
                session.commit()

        def insert_metric_json(
            self, *, agent_id: str, metric_name: str, value: str, timestamp: Any
        ) -> None:
            with self._session() as session:
                session.add(
                    MetricJson(
                        agent_id=agent_id,
                        metric_name=metric_name,
                        value=value,
                        timestamp=_parse_timestamp_dt(timestamp),
                    )
                )
                session.commit()

        def insert_metric_log(
            self, *, agent_id: str, metric_name: str, value: str, timestamp: Any
        ) -> None:
            with self._session() as session:
                session.add(
                    MetricLog(
                        agent_id=agent_id,
                        metric_name=metric_name,
                        value=value,
                        timestamp=_parse_timestamp_dt(timestamp),
                    )
                )
                session.commit()

        def update_plugin(self, *, agent_id: str, plugin: str | None) -> None:
            with self._session() as session:
                agent = session.get(Agent, agent_id)
                if agent:
                    agent.plugin = plugin
                    agent.updated_at = _utcnow_naive()
                    session.commit()

        def get_guidance(self, anomaly_type: str) -> dict[str, Any] | None:
            with self._engine.connect() as conn:
                row = conn.execute(text("SELECT * FROM guidance WHERE anomaly_type = :a"), {"a": anomaly_type}).fetchone()
                if not row: return None
                d = dict(row._mapping)
                if d.get("steps"): d["steps"] = json.loads(d["steps"])
                return d

        def list_guidance(self) -> list[dict[str, Any]]:
            with self._engine.connect() as conn:
                rows = conn.execute(text("SELECT * FROM guidance ORDER BY anomaly_type ASC")).fetchall()
                res = []
                for r in rows:
                    d = dict(r._mapping)
                    if d.get("steps"): d["steps"] = json.loads(d["steps"])
                    res.append(d)
                return res

        def upsert_guidance(self, anomaly_type: str, title: str, description: str, steps: list[str], priority: str) -> None:
            with self._engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO guidance(anomaly_type, title, description, steps, priority, updated_at)
                    VALUES (:a, :t, :d, :s, :p, CURRENT_TIMESTAMP)
                    ON CONFLICT(anomaly_type) DO UPDATE SET
                      title=excluded.title, description=excluded.description,
                      steps=excluded.steps, priority=excluded.priority, updated_at=CURRENT_TIMESTAMP
                """), {"a": anomaly_type, "t": title, "d": description, "s": json.dumps(steps), "p": priority})
                conn.commit()

        def delete_guidance(self, anomaly_type: str) -> bool:
            with self._engine.connect() as conn:
                res = conn.execute(text("DELETE FROM guidance WHERE anomaly_type = :a"), {"a": anomaly_type})
                conn.commit()
                return res.rowcount > 0

        def upsert_alert(self, **kwargs) -> dict[str, Any]:
            """Create or update an alert with SQLAlchemy ORM."""
            dedup_window = kwargs.get("dedup_window_seconds", 300)
            window_start = datetime.utcnow() - timedelta(seconds=dedup_window)
            ts = _parse_timestamp_dt(kwargs["timestamp"])

            with self._session() as session:
                existing = (
                    session.query(Alert)
                    .filter(
                        Alert.fingerprint == kwargs["fingerprint"],
                        Alert.is_resolved == 0,
                        Alert.last_seen >= window_start
                    )
                    .order_by(Alert.last_seen.desc())
                    .first()
                )
                if existing:
                    existing.last_seen = ts
                    existing.count += 1
                    session.commit()
                    return {
                        "id": existing.id,
                        "fingerprint": kwargs["fingerprint"],
                        "first_seen": existing.first_seen.strftime(METRIC_TS_FMT),
                        "last_seen": ts.strftime(METRIC_TS_FMT),
                        "count": existing.count,
                        "severity": existing.severity
                    }
                else:
                    new_alert = Alert(
                        agent_id=kwargs["agent_id"],
                        service=kwargs["service"],
                        anomaly_type=kwargs["anomaly_type"],
                        severity=kwargs["severity"],
                        fingerprint=kwargs["fingerprint"],
                        first_seen=ts,
                        last_seen=ts,
                        count=1,
                        plugin=kwargs.get("plugin")
                    )
                    session.add(new_alert)
                    session.commit()
                    return {
                        "id": new_alert.id,
                        "fingerprint": kwargs["fingerprint"],
                        "first_seen": ts.strftime(METRIC_TS_FMT),
                        "last_seen": ts.strftime(METRIC_TS_FMT),
                        "count": 1,
                        "severity": kwargs["severity"]
                    }

        def resolve_alert(self, alert_id: int) -> bool:
            with self._engine.connect() as conn:
                res = conn.execute(text("UPDATE alerts SET is_resolved = 1, resolved_at = CURRENT_TIMESTAMP WHERE id = :id AND is_resolved = 0"),
                                   {"id": alert_id})
                conn.commit()
                return res.rowcount > 0

        def list_alerts(self, **kwargs) -> list[dict[str, Any]]:
            clauses = []
            params = {}
            if kwargs.get("agent_id"):
                clauses.append("agent_id = :aid")
                params["aid"] = kwargs["agent_id"]
            if kwargs.get("is_resolved") is not None:
                clauses.append("is_resolved = :r")
                params["r"] = int(kwargs["is_resolved"])
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            params["limit"] = kwargs.get("limit", 100)
            with self._engine.connect() as conn:
                rows = conn.execute(text(f"SELECT * FROM alerts {where} ORDER BY last_seen DESC LIMIT :limit"), params).fetchall()
                return [dict(r._mapping) for r in rows]

        def alert_summary(self) -> dict[str, Any]:
            with self._engine.connect() as conn:
                row = conn.execute(text("""
                    SELECT
                      COUNT(*) FILTER (WHERE is_resolved = 0) AS open_count,
                      COUNT(*) FILTER (WHERE is_resolved = 1) AS resolved_count,
                      COUNT(*) FILTER (WHERE severity='HIGH' AND is_resolved=0) AS high_open,
                      COUNT(*) FILTER (WHERE severity='MEDIUM' AND is_resolved=0) AS medium_open,
                      COUNT(*) FILTER (WHERE severity='LOW' AND is_resolved=0) AS low_open
                    FROM alerts
                """)).fetchone()
                if row: return {"open": row[0], "resolved": row[1], "high_open": row[2], "medium_open": row[3], "low_open": row[4]}
                return {}

        def expire_alerts(self, rules: dict[str, int]) -> int:
            total = 0
            with self._engine.connect() as conn:
                for sev, secs in rules.items():
                    cutoff = (datetime.utcnow() - timedelta(seconds=secs)).strftime(METRIC_TS_FMT)
                    res = conn.execute(text("UPDATE alerts SET is_resolved = 1, resolved_at = CURRENT_TIMESTAMP WHERE severity = :s AND is_resolved = 0 AND last_seen < :c"),
                                       {"s": sev, "c": cutoff})
                    total += res.rowcount
                conn.commit()
            return total

        def get_rollups(self, *, agent_id: str, metric_name: str, table: str = "metric_numeric_1h", limit: int = 24) -> list[dict[str, Any]]:
            allowed_tables = {"metric_numeric_1m", "metric_numeric_10m", "metric_numeric_1h"}
            if table not in allowed_tables:
                raise ValueError(f"Invalid table: {table}")
            with self._engine.connect() as conn:
                rows = conn.execute(text(f"""
                    SELECT bucket_start, count, min, max, sum
                    FROM {table}
                    WHERE agent_id = :aid AND metric_name = :mn
                    ORDER BY bucket_start DESC
                    LIMIT :l
                """), {"aid": agent_id, "mn": metric_name, "l": limit}).fetchall()
                return [dict(r._mapping) for r in rows]

        def get_metrics_table(
            self,
            *,
            table: str = "metric_numeric",
            agent_id: str | None = None,
            metric_name: str | None = None,
            from_ts: str | None = None,
            to_ts: str | None = None,
            limit: int = 200,
            offset: int = 0,
        ) -> dict[str, Any]:
            allowed_tables = {
                "metric_numeric", "metric_json", "metric_log",
                "metric_numeric_1m", "metric_numeric_10m", "metric_numeric_1h",
            }
            if table not in allowed_tables:
                raise ValueError(f"Invalid table: {table}")

            clauses = []
            params = {}
            if agent_id:
                clauses.append("agent_id = :aid")
                params["aid"] = agent_id
            if metric_name:
                clauses.append("metric_name LIKE :mn")
                params["mn"] = f"%{metric_name}%"
            
            ts_col = "bucket_start" if table.startswith("metric_numeric_") else "timestamp"
            if from_ts:
                clauses.append(f"{ts_col} >= :f")
                params["f"] = from_ts
            if to_ts:
                clauses.append(f"{ts_col} <= :t")
                params["t"] = to_ts

            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            
            with self._engine.connect() as conn:
                count_res = conn.execute(text(f"SELECT COUNT(*) FROM {table} {where}"), params).fetchone()
                total = count_res[0] if count_res else 0
                
                rows = conn.execute(text(f"""
                    SELECT * FROM {table} {where} 
                    ORDER BY {ts_col} DESC 
                    LIMIT :limit OFFSET :offset
                """), {**params, "limit": limit, "offset": offset}).fetchall()
                
                rows_dict = []
                for r in rows:
                    d = dict(r._mapping)
                    # Convert datetimes to strings for JSON
                    for k, v in d.items():
                        if isinstance(v, datetime):
                            d[k] = v.strftime(METRIC_TS_FMT)
                    rows_dict.append(d)
                
                return {
                    "table": table,
                    "total": total,
                    "rows": rows_dict,
                    "limit": limit,
                    "offset": offset
                }

        def update_agent_inventory(self, **kwargs) -> None:
            with self._engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO agent_inventory(agent_id, fingerprint, modules_json, functions_json, updated_at)
                    VALUES (:aid, :f, :m, :funcs, CURRENT_TIMESTAMP)
                    ON CONFLICT(agent_id) DO UPDATE SET
                      fingerprint=excluded.fingerprint, modules_json=excluded.modules_json,
                      functions_json=excluded.functions_json, updated_at=CURRENT_TIMESTAMP
                """), {"aid": kwargs["agent_id"], "f": kwargs["fingerprint"], 
                       "m": json.dumps(kwargs["modules"]), "funcs": json.dumps(kwargs["functions"])})
                conn.commit()

        def get_previous_metrics(self, agent_id: str, metric_name: str, limit: int = 20) -> list[float]:
            with self._session() as session:
                rows = session.query(MetricNumeric).filter(MetricNumeric.agent_id == agent_id, MetricNumeric.metric_name == metric_name).order_by(MetricNumeric.timestamp.desc()).limit(limit).all()
                return [r.value for r in rows]
        
        def set_anomaly_state(self, agent_id: str, detector_id: str, state: dict[str, Any]) -> None:
            with self._engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO anomaly_state(agent_id, detector_id, state_json, updated_at)
                    VALUES (:aid, :did, :s, CURRENT_TIMESTAMP)
                    ON CONFLICT(agent_id, detector_id) DO UPDATE SET
                      state_json = excluded.state_json, updated_at = CURRENT_TIMESTAMP
                """), {"aid": agent_id, "did": detector_id, "s": json.dumps(state)})
                conn.commit()
        
        def get_anomaly_state(self, agent_id: str, detector_id: str) -> dict[str, Any] | None:
            with self._engine.connect() as conn:
                row = conn.execute(text("SELECT state_json FROM anomaly_state WHERE agent_id = :aid AND detector_id = :did"),
                                   {"aid": agent_id, "did": detector_id}).fetchone()
                return json.loads(row[0]) if row and row[0] else None

        def get_rollup_last_bucket(self, source_table: str, target_table: str) -> str | None:
            with self._engine.connect() as conn:
                row = conn.execute(text("SELECT last_bucket FROM rollup_state WHERE source_table = :s AND target_table = :t"),
                                   {"s": source_table, "t": target_table}).fetchone()
                return row[0] if row else None

        def set_rollup_last_bucket(self, source_table: str, target_table: str, last_bucket: str) -> None:
            with self._engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO rollup_state(source_table, target_table, last_bucket, updated_at)
                    VALUES (:s, :t, :l, CURRENT_TIMESTAMP)
                    ON CONFLICT(source_table, target_table) DO UPDATE SET
                      last_bucket=excluded.last_bucket, updated_at=CURRENT_TIMESTAMP
                """), {"s": source_table, "t": target_table, "l": last_bucket})
                conn.commit()

        def get_rollups(self, *, agent_id: str, metric_name: str, table: str = "metric_numeric_1h", limit: int = 24) -> list[dict[str, Any]]:
            # Raw SQL for now since we don't have explicit ORM models for all rollup variants yet
            with self._engine.connect() as conn:
                res = conn.execute(
                    text(f"SELECT bucket_start, count, min, max, sum FROM {table} WHERE agent_id = :aid AND metric_name = :n ORDER BY bucket_start DESC LIMIT :l"),
                    {"aid": agent_id, "n": metric_name, "l": limit}
                ).fetchall()
                return [dict(r._mapping) for r in res]


def get_storage(path: Path = DEFAULT_DB_PATH):
    if SQLALCHEMY_AVAILABLE:  # pragma: no cover
        return SqlAlchemyStorage(path)
    return SqliteStorage(path)
