# Auto Assignment Service

Location: `tickets/assignment.py`  
Scope: new tickets are auto-assigned to eligible resolvers; manual overrides stay intact.

## Data model additions (`tickets_ticket`)
- `assigned_to` (FK `auth_core.SSOUser`, nullable, indexed)
- `assigned_at` (datetime)
- `assignment_strategy` (char, e.g., `sticky`, `skill`, `purpose_fallback`, `oncall`, `manual`, `unassigned`)
- `assignment_reason` (text, freeform)
- `auto_assigned` (bool)
- `meta.assignment_history` (append-only JSON array) tracks every assignment decision: `{at, strategy, reason, assignee_id}`.

Migration: `0004_auto_assignment_fields`. Run `python manage.py migrate`.

## Picker algorithm (order)
1) **Sticky reuse** — reuse the most recent OPEN/ACK ticket assignee for the same `(metric_name, severity, purpose)` if their load is within `AUTO_ASSIGN_STICKY_LOAD_DELTA` (default `1`) of the current minimum load.
2) **Skill + ABAC** — eligible resolvers who pass agent/purpose access **and** metric skill; pick least-loaded (OPEN/ACK ticket count), tie-breaker: oldest `assigned_at`, then `user_id`.
3) **Purpose fallback** — if `AUTO_ASSIGN_ALLOW_PURPOSE_FALLBACK=True`, ignore skill but keep ABAC; pick least-loaded.
4) **On-call fallback** — resolver id in `AUTO_ASSIGN_ONCALL_RESOLVER_ID` if still ABAC-eligible.
5) **Unassigned** — leave blank and set `assignment_reason`.

Eligibility gates (for non-admin resolvers): active, role=resolver, `AuthService.can_access_agent`, `AuthService.can_access_purpose`, and (unless skipped) `AuthService.has_skill_for_metric`.

## Integration points
- **Auto on create**: `TicketService.create_ticket` calls `AssignmentService.assign` only for newly inserted tickets. Duplicate merges never change `assigned_to`.
- **API surface**: ticket responses now include `assigned_to`, `assigned_to_email`, `assigned_to_name`, `assigned_at`, `assignment_strategy`, `assignment_reason`, `auto_assigned`.
- **Serialization**: `assigned_at` is ISO-8601 in JSON responses.

## Manual override endpoint
- `POST /api/tickets/<ticket_id>/assign/`
  - Auth: `@require_auth` + `@require_role("resolver", "admin")`
  - Body: `{"assignee_id": "...", "reason": "optional"}`
  - Non-admins must satisfy ABAC + skill for the target ticket.
  - Records `assignment_strategy="manual"`, `auto_assigned=False`, and appends to history.

## Settings
- `AUTO_ASSIGN_ALLOW_PURPOSE_FALLBACK` (bool, default `False`)
- `AUTO_ASSIGN_ONCALL_RESOLVER_ID` (str resolver id, default `None`)
- `AUTO_ASSIGN_STICKY_LOAD_DELTA` (int, default `1`)

## Operational notes
- Assignment is transaction-light: selection runs post-insert; history is stored inside `meta`.
- Logging: decisions are logged via standard logging module in `tickets.assignment`.
- Load metric: count of OPEN/ACK tickets with `assigned_to` set.
- If no resolver is eligible, ticket stays unassigned with explicit reason for UI.

## Testing
`python manage.py test tickets`
- Covers least-loaded skill selection, sticky reuse tolerance, purpose fallback, and duplicate-merge assignment preservation.

## Future hooks
- Add cooldown between reassignments to avoid thrash.
- Expose assignment_history via API when UI needs audit visibility.
- Optional background rebalancer for long-lived queues.
