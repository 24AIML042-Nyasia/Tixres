# Tickets

Agent-level issue records created by anomaly detectors or other ingest pipelines. Tickets deduplicate noisy events and feed Alerts.

## Data Model (`ticket_service/models.py`)
- `id` int PK
- `agent_id` (str), `metric_name` (str)
- `severity` (P1-P4)
- `purpose` (str, default `general`; auto-resolved from agent when not provided)
- `status` (`OPEN|CLOSED`, default OPEN)
- `detectors` (JSON string list) - for example `["zscore"]`
- `meta` (JSON string) - detector payload / audit trail
- `message` (text)
- `occurrence_count` (int, starts at 1)
- `first_occurred_at`, `last_occurred_at`, `created_at`

## Deduplication Rules (`TicketService.create_ticket`)
- Window: 60 minutes by default (`DEDUP_WINDOW_MINUTES`); override via `dedup_window_minutes`.
- Duplicate match key: `agent_id`, `metric_name`, `severity`, `purpose`, and `status=OPEN`.
- Merge behaviour (for non-P4 tickets only):
  - `detectors` -> union + sorted
  - `occurrence_count` -> +1
  - `last_occurred_at` -> now
  - `message` -> replaced with latest
- P4 tickets bypass dedup entirely; every P4 insert is its own row and is never forwarded to AlertService.

## Retrieval API
- `GET /api/tickets/{agent_id}/latest?limit=5` - returns `{agent_id, count, tickets[]}` ordered by `last_occurred_at` desc. `limit` 1-100. (Currently unauthenticated; secure behind auth in production.)
- Each ticket in the response includes parsed `detectors` list and raw `meta` string.

## Interaction with Alerts
- After creation, non-P4 tickets should be passed to `AlertService.process_ticket(db, ticket)` by a worker to group them into alerts (see `alert_service/alert_service.py`).
- Manual alert resolution (`POST /api/alerts/{id}/resolve`) closes related OPEN tickets (same metric, severity, purpose) and appends an audit trail into `meta`.

## Example Creation (inside code)
```python
from server_db.connection import SessionLocal
from ticket_service.ticketService import TicketService

TicketService.create_ticket(
    db=SessionLocal(),
    agent_id="agent_123",
    metric_name="cpu_v1.0.0.pct",
    severity="P2",
    detector="zscore",
    meta='{"current":92.1,"baseline":55.3}',
    message="CPU usage anomaly (z=3.1)",
)
```
