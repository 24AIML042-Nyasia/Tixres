# Alerts

How metric tickets are correlated into alerts and how to operate them via API.

## What an Alert Represents
- Correlated view of one or more tickets sharing `(metric_name, severity, purpose)`.
- Types: `SINGLE` (one agent) -> escalates to `GROUP` when a second agent joins.
- Status: `OPEN` or `CLOSED`.
- P4 tickets never create alerts (filtered upstream).

## Model Fields (`alert_service/models.py`)
- `id` int PK
- `metric_name`, `severity` (P1-P4), `purpose` (default `general`)
- `type` (`SINGLE|GROUP`), `status` (`OPEN|CLOSED`)
- `agent_ids` JSON string of contributing agents (sorted, unique)
- `total_occurrence` running count across tickets
- `first_seen_at`, `last_seen_at`
- `cooldown_until` - notification throttle boundary
- `created_at`, `closed_at`
- Uniqueness: one OPEN alert per `(metric_name, severity, purpose)` via `uq_alert_metric_severity_purpose_status`.

## Lifecycle (AlertService)
1) Ticket arrives (non-P4).  
2) Find OPEN alert by key; create `SINGLE` if none.  
3) Merge ticket: union agent_ids, bump `total_occurrence`, refresh `last_seen_at`. Escalate to `GROUP` when >=2 agents.  
4) Cooldown set on creation only: P1=10m, P2=15m, P3+=30m.  
5) ResolutionService periodically auto-closes alerts silent past window: P1=2h, P2=6h, P3=12h, P4=24h (for completeness). Closing an alert also closes matching OPEN tickets.

## API (all under `/api/alerts`)
- `GET /api/alerts?status=&severity=&purpose=&skip=&limit=` - paginated list ordered by `last_seen_at` desc. Filters are optional; `limit` <=100.
- `GET /api/alerts/{alert_id}` - fetch one; 404 if missing.
- `POST /api/alerts/{alert_id}/resolve` - manual close. Validates alert is OPEN, then closes alert + related tickets via `ResolutionService`. Response: `{"message","resolved_id"}`.

## Example: List Open P1/P2
```bash
curl "http://localhost:8000/api/alerts?status=OPEN&severity=P1&severity=P2&limit=10"
```
(Severity filter expects a single value; issue two calls if you need multiple severities.)

## Operational Tips
- Because cooldown is not reset on merges, notification throttling must be handled externally using `cooldown_until`.
- Auto-resolution depends on a periodic call to `ResolutionService.run_resolution_pass(db)` (e.g., a Celery beat every 60s).
- Use `purpose` to isolate tenants; alerts never merge across purposes.
