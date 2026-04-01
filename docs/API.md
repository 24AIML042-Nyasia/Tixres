# Endpoint Guide

Detailed reference for the FastAPI server in `server_utils/fastapi.py`, focusing on each endpoint’s purpose, required payload, and return shape.

## Authentication
- **HMAC required** only for agent-sent endpoints: `/api/agent/login`, `/api/agent/ping`, and `/api/metrics/submit`.
- **No auth** for UI-facing endpoints: dashboard, tickets, rollups, resolver bundles, alerts, guidance, `/`, `/health`, `/api/agent/register`, `/demo/api-test`.
- HMAC headers (when needed):
  - `x-api-key`: API key issued at registration.
  - `x-message`: Arbitrary nonce (timestamp string recommended).
  - `x-signature`: `HMAC-SHA256(secret_key, f"{api_key}:{x-message}")`.

## Agent + Session
### POST `/api/agent/register`
- Purpose: Issue credentials and persist agent metadata.
- Auth: None.
- Body (JSON): `agent_version` (string), `hostname` (string), `os` (string), `fingerprint` (string), `template` (object, optional), `purpose` (string, default `"general"`).
- Response 200: `{agent_id, api_key, secret_key, template, purpose, message}`.
- Errors: 500 on registration failure.

### POST `/api/agent/login`
- Purpose: Refresh heartbeat and return agent info.
- Auth: HMAC (`user` or `resolver`) tied to the API key.
- Body (JSON): `agent_id` (string).
- Response 200: `{message, agent_info: {agent_id, agent_version, hostname, os, created_at, heartbeat, template, purpose}}`.
- Errors: 404 if agent not found; 500 on server errors.

### POST `/api/agent/ping`
- Purpose: Lightweight heartbeat to mark agent online.
- Auth: HMAC (`user` or `resolver`) tied to the agent.
- Body (JSON): `agent_id` (string).
- Response 200: `{message, timestamp, template, action}` where `action` is a transient flag set by `run_resolver`.
- Errors: 500 on failure.

## Metrics Ingestion
### POST `/api/metrics/submit`
- Purpose: Ingest mixed numeric/JSON metrics and refresh heartbeat.
- Auth: HMAC (`user` or `resolver`) for that agent; rejects mismatched `agent_id`.
- Body (JSON):  
  - `agent_id` (string)  
  - `metrics`: array of `{metric_name` (string), `value` (number or JSON), `timestamp` (ISO 8601; `Z` allowed)}`.
- Response 200: `{message, count, numeric, json}` summarising stored rows.
- Errors: 403 on agent mismatch; 500 on storage errors.

Example payload:
```
{
  "agent_id": "agent_123",
  "metrics": [
    {"metric_name": "cpu_v1.0.0.usage_overall", "value": 37.5, "timestamp": "2026-03-25T08:00:00Z"},
    {"metric_name": "process_v1.0.0.top_cpu", "value": [{"name": "python", "percent": 42}], "timestamp": "2026-03-25T08:00:02Z"}
  ]
}
```

## Dashboards, Tickets, and Snapshots
### GET `/api/dashboard/{agent_id}`
- Purpose: Latest per-metric snapshot for UI dashboards.
- Auth: None.
- Response 200: Object containing `cpu_usage_percent`, `cpu_per_core`, `cpu_load_avg`, `cpu_frequency`, `top_cpu_process`, memory fields (`memory_percent`, `memory_used_gb`, `memory_total_gb`, `memory_available_gb`, `memory_cached_gb`, `memory_free_gb`, `swap_percent`, `swap_used_gb`, `swap_total_gb`), disk fields (`disk_percent`, `disk_total_gb`, `disk_used_gb`, `disk_free_gb`, `disk_read_mb_s`, `disk_write_mb_s`), network fields (`network_total_mbps`, `network_active_connections`, `network_total_errors`), and process fields (`total_threads`, `zombie_count`).

### GET `/api/tickets/{agent_id}/latest`
- Purpose: Raw ticket records for an agent (P4 excluded). **No guidance enrichment** — use the user/resolver snapshots instead.
- Auth: None.
- Query: `limit` (int, 1–100, default 5).
- Response 200:
```json
{
  "agent_id": "agent_abc",
  "count": 2,
  "tickets": [
    {
      "id": 1, "agent_id": "agent_abc", "metric_name": "cpu_v1.0.0.usage_overall",
      "severity": "P1", "purpose": "general", "status": "OPEN",
      "detectors": ["anomaly_z_score"], "meta": "...", "message": "...",
      "occurrence_count": 3, "first_occurred_at": "...", "last_occurred_at": "...", "created_at": "...",
      "acknowledged_at": null, "acknowledged_by": null
    }
  ]
}
```

### PATCH `/api/tickets/{ticket_id}/ack`
- Purpose: Acknowledge an open ticket. This protects the ticket from being auto-closed if an alert resolves, and visually marks it as "under investigation".
- Auth: None.
- Body: `{"acked_by": "resolver"}` (optional, defaults to "resolver")
- Response 200: `{"message": "Ticket acknowledged", "changed": true}`

---### GET `/api/user/{agent_id}`
- Purpose: UI-friendly bundle for standard users.
- Auth: None.
- Response 200: `{agent_id, role:"user", dashboard:{...}, tickets:[...], rollups:[], alerts:[]}`.

### GET `/api/resolver/{agent_id}`
- Purpose: Resolver bundle (adds alerts).
- Auth: None.
- Response 200: `{agent_id, role:"resolver", dashboard:{...}, tickets:[...], rollups:[], alerts:[{id, metric_name, severity, purpose, type, status, agent_ids, total_occurrence, first_seen_at, last_seen_at, cooldown_until, created_at, closed_at}]}`.

### GET `/api/resolver/agents`
- Purpose: List all agent IDs for resolver selection.
- Auth: None.
- Response 200: `{count, agents:[agent_id, ...]}`.

## Rollups
### GET `/api/rollups/{agent_id}`
- Purpose: Aggregated metric rollups (InfluxDB preferred; SQLite/Postgres fallback).
- Auth: None.
- Query:
  - `measurement` = `1m` | `10m` | `1h` (default `1m`).
  - `metric_name` (optional) must match `^(?P<metric>[a-zA-Z]+)_v(?P<version>\\d+\\.\\d+\\.\\d+)\\.(?P<unit>[a-zA-Z_]+)$`.
  - `start_minutes` (int, default 240, range 1–4320).
- Response 200: `{agent_id, measurement, metric_name, start, points:[{bucket_start, count, min, max, sum, avg, metric?, version?, unit?, source}], source:"influx"|"sqlite"}`.

## Alerts
### GET `/api/alerts`
- Purpose: List alerts with optional filters.
- Auth: None.
- Query: `status` (`OPEN`|`ACK`|`CLOSED`), `severity` (e.g., `P1`), `purpose` (string), `skip` (>=0, default 0), `limit` (1–100, default 20).
- Response 200: `{total, items:[{id, metric_name, severity, purpose, type, status, agent_ids, total_occurrence, first_seen_at, last_seen_at, cooldown_until, created_at, closed_at, acknowledged_at, acknowledged_by}]}`.

### GET `/api/alerts/{alert_id}`
- Purpose: Fetch a single alert.
- Auth: None.
- Response 200: `AlertResponse` fields above; 404 if not found.

### POST `/api/alerts/{alert_id}/resolve`
- Purpose: Manually resolve an open alert and close related tickets.
- Auth: None.
- Response 200: `{message, resolved_id}`.
- Errors: 404 if missing; 400 if already closed.

### PATCH `/api/alerts/{alert_id}/ack`
- Purpose: Acknowledge an open alert, protecting it from auto-resolution and visually marking it as "under investigation".
- Auth: None.
- Body: `{"acked_by": "resolver"}` (optional, defaults to "resolver")
- Response 200: `{"message": "Alert acknowledged", "resolved_id": alert_id}`

## Guidance (no auth dependency)
### PUT `/api/guidance`
- Purpose: Upsert by natural key (`metric_name`, `priority`, `purpose`).
- Body: `GuidanceUpsert` → `metric_name` (string), `purpose` (string, default `"general"`), `priority` (`P1`-`P4`, default `P4`), `resolution_steps` (list of dicts), `resolver_notes` (string, optional), `resolution_meta` (dict, optional).
- Response 200: `GuidanceResponse` `{id, metric_name, purpose, priority, resolution_steps, resolver_notes, resolution_meta, last_updated}`.

### GET `/api/guidance`
- Purpose: Paginated list with filters.
- Query: `skip` (default 0), `limit` (1–100, default 20), `priority` (`P1`-`P4`), `metric_name` (string), `purpose` (string).
- Response 200: `{total, items:[GuidanceResponse...]}`.

### GET `/api/guidance/summary/stats`
- Purpose: Count of guidance records per priority.
- Response 200: Mapping like `{"P1": 3, "P2": 7, "P3": 12, "P4": 20}`.

### GET `/api/guidance/by-key`
- Purpose: Fetch by natural key.
- Query: `metric_name` (required), `priority` or legacy `severity` (one required), `purpose` (default `"general"`).
- Response 200: `GuidanceResponse`; 404 if not found.

### GET `/api/guidance/{guidance_id}`
- Purpose: Fetch by primary key.
- Response 200: `GuidanceResponse`; 404 if not found.

### PATCH `/api/guidance/{guidance_id}`
- Purpose: Partial update of mutable fields.
- Body: `GuidanceUpdate` → any of `resolution_steps`, `resolver_notes`, `resolution_meta`.
- Response 200: Updated `GuidanceResponse`; 404 if not found.

### DELETE `/api/guidance/{guidance_id}`
- Purpose: Delete by primary key.
- Response 200: `{deleted: true, id}`.

### GET `/api/guidance/by-key/steps`
- Purpose: Lightweight retrieval of only `resolution_steps`.
- Query: `metric_name` (required), `priority` or `severity` (one required), `purpose` (default `"general"`).
- Response 200: `{steps: [...]}`; 404 if not found.

## Utility
### GET `/`
- Purpose: Service banner.
- Response 200: `{service: "IT Metrics Storage System", version: "1.0.0", status: "running"}`.

### GET `/health`
- Purpose: Liveness check.
- Response 200: `{status: "healthy", timestamp: "<iso8601>"}`.

### GET `/demo/api-test`
- Purpose: HTML helper page to sign and call core APIs from a browser.
- Response 200: HTML document with client-side HMAC signing.
