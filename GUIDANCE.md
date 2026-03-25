# Guidance (Runbook) API

Practical reference for creating and retrieving runbook guidance that helps operators resolve metric-driven incidents.

## Data Model (table `guidance`)
- `id` (int) auto PK
- `metric_name` (str, 255) - metric key this guidance targets.
- `purpose` (str, default `general`) - tenant/segment namespace; part of the natural key.
- `priority` (enum: P1|P2|P3|P4, default P4) - stored in `guidance.models.Priority`.
- `resolution_steps` (JSON array of `{step:int, action:str}`) - ordered, required.
- `resolver_notes` (text, optional) - free-form tips/escalation rules.
- `resolution_meta` (JSON, optional) - tags, SLA mins, owners, etc.
- `last_updated` (tz datetime, auto).
- Natural key: `(metric_name, priority, purpose)` enforced by `uq_guidance_metric_priority_purpose`.

## API Surface (all under `/api/guidance`, HMAC-protected)
- `PUT /api/guidance` - upsert by natural key. Body: `metric_name`, `priority`, `purpose?`, `resolution_steps`, `resolver_notes?`, `resolution_meta?`. Returns the record and HTTP 200 whether created or updated.
- `GET /api/guidance` - list with filters `skip`, `limit` (<=100), `priority`, `metric_name`, `purpose`. Returns `{total, items[]}`.
- `GET /api/guidance/summary/stats` - counts per priority.
- `GET /api/guidance/by-key` - lookup by `metric_name` + `priority|severity` + `purpose` (default `general`). 422 if priority missing; 404 if not found.
- `GET /api/guidance/{id}` - lookup by id.
- `PATCH /api/guidance/{id}` - partial update of `resolution_steps`, `resolver_notes`, `resolution_meta`.
- `DELETE /api/guidance/{id}` - hard delete.
- `GET /api/guidance/by-key/steps` - returns only `{"steps":[...]}` for lightweight agent use.

## Example Upsert
```bash
curl -X PUT http://localhost:8000/api/guidance \
  -H "Content-Type: application/json" \
  -H "x-api-key:$API_KEY" -H "x-message:login" -H "x-signature:$SIG" \
  -d '{
        "metric_name": "cpu_v1.0.0.pct",
        "priority": "P2",
        "purpose": "general",
        "resolution_steps": [
          {"step":1,"action":"Check top/htop for runaway PID"},
          {"step":2,"action":"Restart offending service if safe"}
        ],
        "resolver_notes": "Escalate to SRE if >95% for 10m",
        "resolution_meta": {"tags":["infra"],"sla_minutes":30}
      }'
```

## Usage Notes
- `priority` and `purpose` act as routing keys; use `purpose` to isolate multi-tenant runbooks.
- `severity` query param is accepted as an alias for `priority` on `/by-key` and `/by-key/steps`.
- `resolution_steps` must be a non-empty array; preserve step numbers if you expect ordered rendering in UIs.
- `GuidanceService` lives in `guidance/GuidanceService.py` and is injected via `Depends(get_db)`; reuse it for internal jobs instead of writing raw queries.
