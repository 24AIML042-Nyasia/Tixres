# Upstream Server Integration Guide

This server can act as the upstream source of agent inventory, purpose-template mappings, and rollup data for downstream services.

## Authentication (HMAC)
- Every request must carry headers: `x-api-key`, `x-signature`, `x-message`.
- Signature formula: `HMAC_SHA256(secret_key, "{api_key}:{message}")`.
- The `message` can be any string (often a timestamp); the same value must be used when computing the signature and sending the request.
- Downstream servers can apply their own role checks; this upstream only verifies the HMAC signature.

## Core Endpoints
- `POST /api/agent/register` — register an agent; accepts optional `purpose` and `template` to seed the purpose-template mapping.
- `POST /api/agent/login` — refresh heartbeat and return agent info.
- `POST /api/agent/ping` — lightweight heartbeat.
- `POST /api/metrics/submit` — ingest metrics batch.
- `GET /api/rollups/{agent_id}` — rollup data (InfluxDB if configured, otherwise SQLite aggregation).

## Register a Server (dedicated credential)
- `POST /api/server/register` → returns `server_id`, `api_key`, `secret_key`, `role: "server"`.
- Use these keys for downstream-to-upstream calls; keep them separate from agent credentials.

## Server auth endpoints (for downstream servers)
- `POST /api/server/login`
  - Headers: HMAC (`x-api-key`, `x-message`, `x-signature`)
  - Body: `{"server_id": "<id returned at register>"}`
  - Response: message, server_id, role, authenticated_at
- `POST /api/server/ping`
  - Headers: HMAC
  - Body: `{"server_id": "<id>"}` 
  - Response: message, server_id, timestamp

## Downstream Catalog Endpoints
- `GET /api/downstream/agents` — list agents with details (purpose, effective template, heartbeat, metadata).
- `GET /api/downstream/agents/{agent_id}` — single agent detail.
- `GET /api/downstream/purposes` — list purposes with their default templates and agent counts.
- `PUT /api/downstream/purposes` — upsert a purpose + template mapping:
  ```json
  { "purpose": "general", "template": { "modules": ["cpu_v1.0.0"], "metrics": {} } }
  ```
- `GET /api/downstream/rollups/{agent_id}?measurement=1m&start_minutes=240&metric_name=cpu_v1.0.0.usage_overall` — alias to the rollups endpoint for consumers that only mount downstream routes.

## Template–Purpose Behavior
- Each purpose stores a default template; agents inherit it unless they provide an explicit template at registration.
- On startup the server ensures the `general` purpose exists and backfills any agent missing a purpose to `general`.
- Registering an agent with `{ purpose, template }` will create (or update) the purpose with that template so downstream consumers can reuse it.

## Minimal cURL Example (resolver)
```bash
BASE=http://localhost:8000
API_KEY=resolver-demo-key
SECRET=resolver-demo-secret
MSG=$(date -Iseconds)
SIG=$(python - <<'PY'
import hmac, hashlib, os, sys
api=os.environ["API_KEY"]; secret=os.environ["SECRET"]; msg=os.environ["MSG"]
print(hmac.new(secret.encode(), f"{api}:{msg}".encode(), hashlib.sha256).hexdigest())
PY
)
curl -s "${BASE}/api/downstream/agents" \
  -H "x-api-key: ${API_KEY}" \
  -H "x-signature: ${SIG}" \
  -H "x-message: ${MSG}"
```

## Quick HMAC Client Snippet (Python)
```python
import hmac, hashlib, requests, datetime

api_key = "your-api-key"
secret = "your-secret"
message = datetime.datetime.utcnow().isoformat()
signature = hmac.new(secret.encode(), f"{api_key}:{message}".encode(), hashlib.sha256).hexdigest()

resp = requests.get(
    "http://localhost:8000/api/downstream/agents",
    headers={
        "x-api-key": api_key,
        "x-message": message,
        "x-signature": signature,
    },
    timeout=10,
)
print(resp.status_code, resp.json())
```

### Server login/ping payloads (reference)
- Login body: `{"server_id": "server_xxx"}`
- Ping body: `{"server_id": "server_xxx"}`

## Notes
- Rollups automatically fall back to SQL aggregation when InfluxDB is not available.
- Downstream endpoints are read-friendly and safe for other services to consume; they do not return API secrets.
