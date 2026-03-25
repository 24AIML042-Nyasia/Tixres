# Rollups

How raw numeric metrics are aggregated into longer windows and written to InfluxDB.

## Pipeline Overview (`metric_rollup/rollUp.py`)
- Source rows: SQL table `metric_numeric` (Postgres recommended; SQLite supported only in tests).
- Naming rule: metric names must match `^(?P<metric>[a-zA-Z]+)_v(?P<version>\\d+\\.\\d+\\.\\d+)\\.(?P<unit>[a-zA-Z_]+)$` (from `settings.METRIC_REGEX_PATTERN`). Non-matching metrics are skipped.
- Stages and targets:
  - `one_min_roll_up` (async): `metric_numeric` -> Influx measurement `metric_numeric_1m`.
  - `ten_min_roll_up` (async): Influx `metric_numeric_1m` -> `metric_numeric_10m`.
  - `one_hour_roll_up` (async): Influx `metric_numeric_10m` -> `metric_numeric_1h`.
- Tags on emitted points: `agent_id`, `metric`, `version`, `unit`.
- Fields on emitted points: `count`, `min`, `max`, `sum`, `avg`, `bucket_start`.

## Cursor Tracking
- Table `rollup_state` (model in `metric_rollup/models.py`) stores `(source_table, target_table, last_bucket, updated_at)`.
- `RollupStateService` reads the last processed bucket and updates it after each batch, preventing re-processing.
- `last_bucket` is normalised to naive datetimes to avoid dialect-specific TZ issues.

## Execution Notes
- Postgres-specific SQL (`date_trunc`) is used in `one_min_roll_up`; running that job against SQLite will fail outside the test harness. Use Postgres in production.
- Influx connection expects env vars `INFLUX_URL`, `INFLUX_TOKEN`, `INFLUX_ORG`, `INFLUX_BUCKET` (see `influx_db/connection.py`). Tests monkeypatch these to dummy values.
- Cool start defaults:
  - If no cursor exists, `one_min_roll_up` starts at now - 1h; `ten_min_roll_up` at now - 2h; `one_hour_roll_up` at now - 4h.
- Jobs are async coroutines; schedule them in your worker/beat (e.g., Celery) or call directly:
```python
from metric_rollup.rollUp import InfluxDBRollup
import asyncio

rollup = InfluxDBRollup()
asyncio.run(rollup.one_min_roll_up())
asyncio.run(rollup.ten_min_roll_up())
asyncio.run(rollup.one_hour_roll_up())
```

## Retention
- Raw `metric_numeric` rows are trimmed to 7 days on app startup via `server_db/rollups.retention_policy()`.
