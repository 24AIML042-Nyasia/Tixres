# Tixres IT Metrics Server

## Quickstart (SQLite by default)
```
pip install -r requirements.txt
python -m server_db.demo_seed          # load demo agents/metrics/tickets
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```
Base URL: http://localhost:8000  
Auth for protected routes: HMAC headers (`x-api-key`, `x-message`, `x-signature`).

## Tests
- Core FastAPI + SQLite: `pytest tests/test_integration.py`
- Rollup (SQLite, mocked Influx): `pytest tests/test_rollup_sqlite.py`
- Postgres + Influx E2E (services + env required):  
  `pytest -m "postgres and influx" tests/test_postgres_influx_e2e.py`

## Rollups
- Raw metrics in `metric_numeric` (Postgres or SQLite) aggregate to Influx `metric_numeric_1m`.
- Metric names must match `metric_v<version>.<unit>` (e.g., `cpu_v1.0.0.pct`).

## Celery workers (if you use them)
```
python -m celery -A server_celery.app worker --pool=solo --loglevel=info
python -m celery -A server_celery.app beat --loglevel=info
```

## Full Endpoint Reference
See `docs/ENDPOINTS.md` for curl-ready examples, auth details, demo data notes, and guidance/alerts API shapes.
