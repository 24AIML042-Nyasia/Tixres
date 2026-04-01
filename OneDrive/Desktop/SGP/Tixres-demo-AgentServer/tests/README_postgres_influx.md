# Postgres + InfluxDB E2E tests

These tests validate the rollup pipeline from Postgres (`metric_numeric`) into InfluxDB rollup measurements.

## Prerequisites
- Running Postgres instance
- Running InfluxDB 2.x instance
- Environment variables set:
  - `DATABASE_URL` (e.g., `postgresql+psycopg2://user:pass@localhost:5432/metrics_test`)
  - `INFLUX_URL` (e.g., `http://localhost:8086`)
  - `INFLUX_TOKEN`
  - `INFLUX_ORG`
  - `INFLUX_BUCKET`
- Python deps installed: `pip install -r requirements.txt`

## What the test does
- Seeds three raw metric points into Postgres for agent `agent_pg_influx_e2e` and metric `cpu_v1.0.0_pct`.
- Clears prior rollup state and Influx measurements for that agent.
- Runs `InfluxDBRollup.one_min_roll_up()`.
- Asserts a `metric_numeric_1m` point exists in InfluxDB with expected aggregates (count/min/max/sum).

## Running
```
pytest -m "postgres and influx" tests/test_postgres_influx_e2e.py
```

If env vars are missing, the test is skipped. Use the marker filter above to avoid running it in CI that lacks Postgres/Influx.
