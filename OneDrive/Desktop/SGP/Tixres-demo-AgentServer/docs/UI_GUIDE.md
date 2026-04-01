# Tixres UI Developer Guide

> **Demo mode** — no authentication headers are needed for any UI-facing endpoint.
> Auth (HMAC) is only required for agent-side calls (login, ping, metrics submit).

---

## Base URL

```
http://localhost:8000
```

Use the `baseUrl` as a constant across all fetches. The interactive OpenAPI docs are available at `http://localhost:8000/docs`.

---

## Role-Based Endpoint Summary

| Role | Entry point | Sees own data only? | Includes alerts? | Guidance on tickets? |
|------|-------------|---------------------|------------------|----------------------|
| **User** | `GET /api/user/{agent_id}` | ✅ Yes | ❌ No | ✅ Yes |
| **Resolver** | `GET /api/resolver/{agent_id}` | ❌ No (all agents) | ✅ Yes | ✅ Yes |

---

## 1. User View — `GET /api/user/{agent_id}`

**Who calls this:** A standard user/agent owner.  
**Auth:** None required.

### Request
```
GET /api/user/agent_abc123
```

### Response Shape
```json
{
  "agent_id": "agent_abc123",
  "role": "user",
  "dashboard": {
    "cpu_usage_percent": 37.5,
    "cpu_per_core": [10.0, 20.0, 45.0, 62.0],
    "cpu_load_avg": {"1m": 1.2, "5m": 1.0, "15m": 0.8},
    "cpu_frequency": {"current_mhz": 2400},
    "top_cpu_process": {"name": "python", "pid": 4321, "percent": 42.1},
    "memory_percent": 53.1,
    "memory_used_gb": 8.5,
    "memory_total_gb": 16.0,
    "memory_available_gb": 7.5,
    "memory_cached_gb": 2.1,
    "memory_free_gb": 1.3,
    "swap_percent": 10.0,
    "swap_used_gb": 0.5,
    "swap_total_gb": 4.0,
    "top_memory_process": {"name": "chrome", "pid": 1234, "percent": 15.2},
    "disk_percent": 50.0,
    "disk_total_gb": 500.0,
    "disk_used_gb": 250.0,
    "disk_free_gb": 250.0,
    "disk_read_mb_s": 1.2,
    "disk_write_mb_s": 0.4,
    "network_total_mbps": 40.0,
    "network_active_connections": 42,
    "network_total_errors": 3,
    "total_threads": 512,
    "zombie_count": 0
  },
  "tickets": [
    {
      "id": 1,
      "agent_id": "agent_abc123",
      "metric_name": "cpu_v1.0.0.usage_overall",
      "severity": "P1",
      "purpose": "general",
      "status": "OPEN",
      "detectors": ["anomaly_z_score"],
      "meta": "{}",
      "message": "CPU usage sustained above 90% for 5 minutes",
      "occurrence_count": 3,
      "first_occurred_at": "2026-03-26T05:00:00",
      "last_occurred_at": "2026-03-26T06:00:00",
      "created_at": "2026-03-26T05:00:00",
      "acknowledged_at": null,
      "acknowledged_by": null,
      "guidance": {
        "id": 7,
        "metric_name": "cpu_v1.0.0.usage_overall",
        "purpose": "general",
        "priority": "P1",
        "resolution_steps": [
          {"step": 1, "action": "Identify CPU-heavy processes via top/htop"},
          {"step": 2, "action": "Restart the offending service if safe to do so"}
        ],
        "resolver_notes": "Escalate if above 95% for more than 10 minutes",
        "resolution_meta": {"tags": ["infra", "cpu"], "sla_minutes": 30},
        "last_updated": "2026-03-25T10:00:00"
      }
    },
    {
      "id": 2,
      "metric_name": "memory_v1.0.0.ram",
      "severity": "P2",
      "purpose": "general",
      "status": "OPEN",
      "guidance": null
    }
  ],
  "rollups": [],
  "alerts": []
}
```

### Key Notes
- `dashboard.*` values are `null` if the agent has not submitted that metric yet.
- `tickets` is capped at the **10 most recent** open tickets (P4 excluded).
- `tickets[].guidance` is `null` when no guidance record has been created for the ticket's `(metric_name, severity, purpose)` combination.
- `alerts` is always an empty array for the user role.
- `rollups` is reserved for future use; always `[]`.

### Recommended UI Pattern
```js
const snap = await fetch(`/api/user/${agentId}`).then(r => r.json());

// Dashboard widgets
renderCPU(snap.dashboard.cpu_usage_percent);
renderMemory(snap.dashboard.memory_percent);

// Ticket list with inline guidance
snap.tickets.forEach(ticket => {
  const steps = ticket.guidance?.resolution_steps ?? [];
  renderTicketCard(ticket, steps);
});
```

---

## 2. Resolver View — `GET /api/resolver/{agent_id}`

**Who calls this:** Ops / on-call resolver.  
**Auth:** None required.  
**Scope:** Can query **any** agent_id, not just their own.

### Enumerate all agents first
```
GET /api/resolver/agents
→ { "count": 5, "agents": ["agent_abc123", "agent_xyz456", ...] }
```

### Request
```
GET /api/resolver/agent_abc123
```

### Additional field vs. User View: `alerts`
`alerts` contains all Open/Closed alerts associated with this `agent_id`:
```json
"alerts": [
  {
    "id": 5,
    "metric_name": "cpu_v1.0.0.usage_overall",
    "severity": "P1",
    "purpose": "general",
    "type": "SINGLE",
    "status": "OPEN",
    "agent_ids": "[\"agent_abc123\"]",
    "total_occurrence": 5,
    "first_seen_at": "2026-03-26T04:00:00",
    "last_seen_at": "2026-03-26T06:10:00",
    "cooldown_until": null,
    "created_at": "2026-03-26T04:00:00",
    "closed_at": null,
    "acknowledged_at": null,
    "acknowledged_by": null
  }
]
```

`tickets` has the same guidance-enriched shape as the user endpoint.

### Recommended UI Pattern
```js
// Step 1: List all agents
const { agents } = await fetch('/api/resolver/agents').then(r => r.json());

// Step 2: Load snapshot for selected agent
const snap = await fetch(`/api/resolver/${selectedAgentId}`).then(r => r.json());

// Render enriched ticket list
snap.tickets.forEach(ticket => {
  const guidance = ticket.guidance;
  renderResolverTicket(ticket, guidance);
});

// Render alerts
snap.alerts.forEach(alert => renderAlertBadge(alert));
```

---

## 3. Raw Endpoints (building blocks)

These endpoints are available if you need lower-level access:

| Endpoint | Purpose |
|----------|---------|
| `GET /api/dashboard/{agent_id}` | Dashboard metrics snapshot only (no tickets, no guidance) |
| `GET /api/tickets/{agent_id}/latest?limit=N` | Raw tickets, **no** guidance enrichment |
| `GET /api/rollups/{agent_id}?measurement=1m&start_minutes=240` | Aggregated time-series rollup data |
| `GET /api/alerts` | All alerts with optional status/severity filters |
| `GET /api/guidance/by-key?metric_name=X&priority=P1&purpose=general` | Fetch guidance manually by natural key |

---

## 4. Writing Guidance Records

Before guidance appears on tickets, a resolver or admin must create it:

```
PUT /api/guidance
Content-Type: application/json

{
  "metric_name": "cpu_v1.0.0.usage_overall",
  "priority": "P1",
  "purpose": "general",
  "resolution_steps": [
    {"step": 1, "action": "Identify CPU-heavy processes via top/htop"},
    {"step": 2, "action": "Restart the offending service if safe to do so"}
  ],
  "resolver_notes": "Escalate if above 95% for more than 10 minutes",
  "resolution_meta": {"tags": ["infra"], "sla_minutes": 30}
}
```

The natural key is `(metric_name, priority, purpose)`. Re-sending the same key performs an **upsert** (update).

---

## 5. Acknowledging Tickets & Alerts (Resolvers)

When a resolver starts investigating an issue, they should ACK the ticket or alert.

**Acking a Ticket**
```
PATCH /api/tickets/{ticket_id}/ack
Content-Type: application/json

{
  "acked_by": "Ops-Alice"
}
```

**Acking an Alert**
```
PATCH /api/alerts/{alert_id}/ack
Content-Type: application/json

{
  "acked_by": "Ops-Alice"
}
```

**Why ACK?**
1. It visually changes the signal for other resolvers (status becomes `"ACK"` instead of `"OPEN"`).
2. The `acknowledged_at` timestamp is populated.
3. **Important:** It protects the item from being auto-closed by the background `ResolutionService`. If the metric suddenly normalizes on the agent side, the `ACK` ticket/alert stays open so the resolver doesn't lose their context or investigation trail. The resolver must resolve/close it manually.

---

## 6. Ticket Severity → Guidance Priority Mapping

| Ticket `severity` | Guidance `priority` |
|-------------------|---------------------|
| `P1` | `P1` |
| `P2` | `P2` |
| `P3` | `P3` |
| `P4` | `P4` (never shown in normal ticket views) |

The enrichment helper matches on `severity` directly as the guidance `priority`.

---

## 7. Tests to Run After Changes

```powershell
# Run the full integration test suite (covers user, resolver, dashboard, tickets, guidance, alerts)
cd c:\Users\krishiv\Desktop\Projects\26-01-22-Tixres\demo-server
.venv\Scripts\python -m pytest tests/test_integration.py -v

# Guidance unit tests
.venv\Scripts\python -m pytest tests/guidance/ -v

# Alert service tests
.venv\Scripts\python -m pytest tests/test_alert_service/ -v

# Ticket deduplication tests
.venv\Scripts\python -m pytest tests/ticket_service_dedup/ -v
```

> **If you change `_enrich_tickets_with_guidance`** → run `tests/test_integration.py` and `tests/guidance/`.  
> **If you change alert/resolution logic** → run `tests/test_alert_service/`.  
> **If you change ticket dedup logic** → run `tests/ticket_service_dedup/`.

---

## 7. Interactive API Explorer

With the server running, visit:

```
http://localhost:8000/docs        ← Swagger UI (try all endpoints)
http://localhost:8000/redoc       ← ReDoc (clean reference)
http://localhost:8000/demo/api-test ← Browser smoke-test with HMAC signing
```
