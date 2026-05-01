from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from storage import METRIC_TS_FMT


SOURCE_NUMERIC = "metric_numeric"
ROLLUP_1M = "metric_numeric_1m"
ROLLUP_10M = "metric_numeric_10m"
ROLLUP_1H = "metric_numeric_1h"


_ALLOWED_TARGETS = {ROLLUP_1M, ROLLUP_10M, ROLLUP_1H}


def _utcnow_bucket_seed(hours: int = 24) -> str:
    return (datetime.utcnow() - timedelta(hours=hours)).strftime(METRIC_TS_FMT)


def _get_last_bucket(conn: sqlite3.Connection, source: str, target: str) -> str | None:
    row = conn.execute(
        """
        SELECT last_bucket FROM rollup_state
        WHERE source_table = ? AND target_table = ?;
        """,
        (source, target),
    ).fetchone()
    return row[0] if row else None


def _set_last_bucket(
    conn: sqlite3.Connection, source: str, target: str, last_bucket: str
) -> None:
    conn.execute(
        """
        INSERT INTO rollup_state(source_table, target_table, last_bucket, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(source_table, target_table) DO UPDATE SET
          last_bucket=excluded.last_bucket,
          updated_at=CURRENT_TIMESTAMP;
        """,
        (source, target, last_bucket),
    )


@dataclass(frozen=True)
class RollupRunResult:
    target_table: str
    buckets_written: int
    max_bucket: str | None


class RollupService:
    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)

    def run_numeric_rollup(self, *, bucket_seconds: int, target_table: str) -> RollupRunResult:
        if target_table not in _ALLOWED_TARGETS:
            raise ValueError(f"Invalid target_table: {target_table}")
        if bucket_seconds <= 0:
            raise ValueError("bucket_seconds must be positive")

        from config_loader import load_config
        config = load_config()
        db_config = config.get("database", {})
        
        use_pg = False
        pg_params = {}
        if db_config.get("engine") == "postgresql":
            use_pg = True
            print(f"[ROLLUP] PostgreSQL mode ACTIVE")
            import urllib.parse
            pg_params = {
                "host": db_config.get("host", "127.0.0.1"),
                "port": db_config.get("port", 5432),
                "database": db_config.get("name", "tixres"),
                "user": db_config.get("user"),
                "password": urllib.parse.unquote(db_config.get("password", ""))
            }

        if use_pg:
            import psycopg2
            conn = psycopg2.connect(**pg_params)
            # Fetch last bucket
            cur = conn.cursor()
            cur.execute("SELECT last_bucket FROM rollup_state WHERE source_table=%s AND target_table=%s", (SOURCE_NUMERIC, target_table))
            row = cur.fetchone()
            last_bucket = row[0] if row else _utcnow_bucket_seed()
            
            # PostgreSQL version
            sql = f"""
                SELECT
                  agent_id,
                  metric_name,
                  to_timestamp(floor(extract(epoch from timestamp) / %s) * %s) AT TIME ZONE 'UTC' AS bucket_start,
                  count(*) AS count,
                  min(value) AS min,
                  max(value) AS max,
                  sum(value) AS sum
                FROM {SOURCE_NUMERIC}
                WHERE timestamp > %s
                GROUP BY agent_id, metric_name, bucket_start
                ORDER BY bucket_start ASC;
            """
            params = (bucket_seconds, bucket_seconds, last_bucket)
        else:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            # Fetch last bucket
            row = conn.execute("SELECT last_bucket FROM rollup_state WHERE source_table=? AND target_table=?", (SOURCE_NUMERIC, target_table)).fetchone()
            last_bucket = row[0] if row else _utcnow_bucket_seed()
            
            # SQLite version
            sql = f"""
                SELECT
                  agent_id,
                  metric_name,
                  datetime(
                    CAST(CAST(strftime('%s', timestamp) AS integer) / ? AS integer) * ?,
                    'unixepoch'
                  ) AS bucket_start,
                  count(*) AS count,
                  min(value) AS min,
                  max(value) AS max,
                  sum(value) AS sum
                FROM {SOURCE_NUMERIC}
                WHERE timestamp > ?
                GROUP BY agent_id, metric_name, bucket_start
                ORDER BY bucket_start ASC;
            """
            params = (bucket_seconds, bucket_seconds, last_bucket)

        try:
            if not use_pg: conn.execute("PRAGMA foreign_keys = ON;")
            
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
            print(f"[ROLLUP] Processing {target_table}. Lookback: {last_bucket}. Found {len(rows)} buckets.")

            if not rows:
                return RollupRunResult(target_table=target_table, buckets_written=0, max_bucket=None)

            max_bucket: str | None = None
            
            # Upsert logic
            if use_pg:
                upsert_sql = f"""
                    INSERT INTO {target_table}(
                      agent_id, metric_name, bucket_start, count, min, max, sum, received_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT(agent_id, metric_name, bucket_start) DO UPDATE SET
                      count=EXCLUDED.count,
                      min=EXCLUDED.min,
                      max=EXCLUDED.max,
                      sum=EXCLUDED.sum,
                      received_at=CURRENT_TIMESTAMP;
                """
            else:
                upsert_sql = f"""
                    INSERT INTO {target_table}(
                      agent_id, metric_name, bucket_start, count, min, max, sum, received_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(agent_id, metric_name, bucket_start) DO UPDATE SET
                      count=excluded.count,
                      min=excluded.min,
                      max=excluded.max,
                      sum=excluded.sum,
                      received_at=CURRENT_TIMESTAMP;
                """

            for row in rows:
                if use_pg:
                    agent_id, metric_name, bucket_start, count, min_v, max_v, sum_v = row
                    # bucket_start is datetime in PG
                    bucket_start_str = bucket_start.strftime(METRIC_TS_FMT)
                else:
                    agent_id, metric_name, bucket_start_str, count, min_v, max_v, sum_v = row
                
                cur.execute(upsert_sql, (
                    agent_id,
                    metric_name,
                    bucket_start_str,
                    int(count),
                    float(min_v),
                    float(max_v),
                    float(sum_v),
                ))
                
                if max_bucket is None or bucket_start_str > max_bucket:
                    max_bucket = bucket_start_str

            if max_bucket is not None:
                if use_pg:
                    cur.execute("""
                        INSERT INTO rollup_state(source_table, target_table, last_bucket, updated_at)
                        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT(source_table, target_table) DO UPDATE SET
                          last_bucket=EXCLUDED.last_bucket,
                          updated_at=CURRENT_TIMESTAMP;
                    """, (SOURCE_NUMERIC, target_table, max_bucket))
                else:
                    cur.execute("""
                        INSERT INTO rollup_state(source_table, target_table, last_bucket, updated_at)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(source_table, target_table) DO UPDATE SET
                          last_bucket=excluded.last_bucket,
                          updated_at=CURRENT_TIMESTAMP;
                    """, (SOURCE_NUMERIC, target_table, max_bucket))

            conn.commit()
            return RollupRunResult(target_table=target_table, buckets_written=len(rows), max_bucket=max_bucket)
        finally:
            conn.close()

    def _dummy_run_to_keep_original_code_structure(self):
        # This is just to satisfy the tool if it needs a specific end point
        pass

    async def run_periodic(self, *, bucket_seconds: int, target_table: str) -> None:
        while True:
            now = time.time()
            next_run = (int(now) // bucket_seconds + 1) * bucket_seconds
            await asyncio.sleep(max(0.0, next_run - now))
            try:
                await asyncio.to_thread(
                    self.run_numeric_rollup,
                    bucket_seconds=bucket_seconds,
                    target_table=target_table,
                )
            except Exception:
                # Don't crash the server if rollups fail.
                continue
