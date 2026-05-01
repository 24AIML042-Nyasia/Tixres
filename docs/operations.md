# Operations Guide

## Running the Server
To start the main metric server:
```bash
python server/main.py
```

## Running Background Tasks (Celery)
The system uses Celery for background tasks such as metric rollups, data retention, and alert/incident expiry.

### Prerequisites
- **Redis**: Required as the message broker. The easiest way is via Docker:
  ```bash
  docker run -d --name tixres-redis -p 6379:6379 redis
  ```
- **Python Dependencies**: Ensure `celery` and `redis` are installed.

### Starting Workers
On Windows, you MUST run beat and worker separately, and the worker requires the `-P solo` pool flag:

**Terminal 1 (Beat):**
```bash
.venv\Scripts\celery -A server.celery_tasks beat --loglevel=info
```

**Terminal 2 (Worker):**
```bash
.venv\Scripts\celery -A server.celery_tasks worker --loglevel=info -P solo
```

## Maintenance
- **Database**: 
  - **SQLite**: Located at `server/data/agent_metrics.sqlite3`.
  - **PostgreSQL**: Managed via the configuration in `config.json`. Use standard PostgreSQL backup tools (e.g., `pg_dump`).
- **Retention**: Old metrics are automatically deleted by the `run_retention_cleanup` Celery task based on policies in `template.json`.

## Administrative Tools
- **Task Scheduler**: Adjust task frequencies live via the **Admin Panel** in the UI.
- **Alert Seeder**: Inject synthetic alerts for pipeline testing via the **Admin Panel**.
- **Metrics Explorer**: Query raw and rollup tables directly via the **Metrics** page to verify data integrity.
