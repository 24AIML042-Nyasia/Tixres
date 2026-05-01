# Tixres - Intelligent Observability & Incident Response

Tixres is a high-performance observability platform featuring:

- **Intelligent Anomaly Detection**: Statistical (z-Score/MAD) and rule-based detectors.
- **Incident Management**: Automated grouping of alerts into incidents with lifecycle tracking.
- **Metrics Explorer**: Advanced visualization of raw metrics and rollups (1m, 10m, 1h).
- **Administrative Control**: Task scheduler and alert seeder for testing and optimization.
- **Hybrid Storage**: Native support for SQLite (dev) and PostgreSQL (prod).
- **Dynamic Guidance**: Contextual resolution paths for incidents.

## Quick Start

### 1. Requirements
- Python 3.10+
- Redis (Required for Celery tasks). Recommended via Docker:
  ```powershell
  docker run -d --name tixres-redis -p 6379:6379 redis
  ```
- PostgreSQL (Optional, for production use)

### 2. Installation
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Setup Admin User
```powershell
python server/admin_cli.py create-admin --username admin --password yourpassword
```

### 4. Running the Platform

**Start the Server:**
```powershell
python server/main.py
```
- Dashboard: `http://127.0.0.1:8000/`
- WebSocket: `ws://127.0.0.1:8765/`

**Start Celery Workers (Required for rollups and expiry):**
Open two separate terminals:
```powershell
# Terminal 1: Beat (Scheduler)
.venv\Scripts\celery -A server.celery_tasks beat --loglevel=info

# Terminal 2: Worker (Executor)
.venv\Scripts\celery -A server.celery_tasks worker --loglevel=info -P solo
```

**Start the Agent:**
```powershell
python agent/run_agent.py
```

## Configuration

Tixres supports configuration via `config.json` and `.env` files. Environment variables in `.env` take priority for sensitive data like database credentials.

### Environment Variables (.env)
Copy `.env.example` to `.env` and update your credentials:
```env
DB_ENGINE=postgresql
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=Tixres
DB_USER=postgres
DB_PASSWORD=your_password
```

### config.json
General system settings like ports and Celery URLs are managed here.

## Template System

Tixres uses a template-driven approach defined in `server/template.json`. Updating this file live will hot-reload thresholds and configurations across all connected agents and detectors.