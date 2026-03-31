"""
tickets/views.py
----------------
JSON API views for the tickets app (no UI endpoints).
"""

import json

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from tickets.services import TicketService
from alerts.services import process_ticket


def _json_body(request) -> tuple[dict, JsonResponse | None]:
    """Parse JSON request body; return (data, None) or ({}, error_response)."""
    try:
        data = json.loads(request.body)
        return data, None
    except (json.JSONDecodeError, TypeError):
        return {}, JsonResponse({"error": "Invalid JSON body"}, status=400)


# ---------------------------------------------------------------------------
# GET /api/tickets/<agent_id>/latest/
# ---------------------------------------------------------------------------

@require_http_methods(["GET"])
def ticket_list(request, agent_id: str):
    """
    Return the most recent tickets for an agent.

    Query params:
      - limit   (int, 1-100, default 100)
      - include_p4 (bool, default false)
    """
    try:
        limit = min(max(int(request.GET.get("limit", 100)), 1), 100)
    except ValueError:
        limit = 100
    include_p4 = request.GET.get("include_p4", "false").lower() == "true"

    tickets = TicketService.get_tickets(agent_id, limit=limit, include_p4=include_p4)

    # Serialize datetime fields
    def _serialize(t: dict) -> dict:
        for k in ("first_occurred_at", "last_occurred_at", "created_at", "acknowledged_at"):
            if t.get(k) is not None:
                t[k] = t[k].isoformat()
        return t

    return JsonResponse({
        "agent_id": agent_id,
        "count":    len(tickets),
        "tickets":  [_serialize(t) for t in tickets],
    })


# ---------------------------------------------------------------------------
# POST /api/tickets/create/
# ---------------------------------------------------------------------------

@csrf_exempt
@require_http_methods(["POST"])
def ticket_create(request):
    """
    Create or merge a ticket.

    Required body fields: agent_id, metric_name, severity, detector, meta, message
    Optional: purpose, dedup (bool), dedup_window_minutes (int)
    """
    data, err = _json_body(request)
    if err:
        return err

    required = ["agent_id", "metric_name", "severity", "detector", "message"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return JsonResponse({"error": f"Missing required fields: {missing}"}, status=400)

    result = TicketService.create_ticket(
        agent_id             = data["agent_id"],
        metric_name          = data["metric_name"],
        severity             = data["severity"],
        detector             = data["detector"],
        meta                 = data.get("meta", "{}"),
        message              = data["message"],
        dedup                = data.get("dedup", True),
        dedup_window_minutes = data.get("dedup_window_minutes"),
        purpose              = data.get("purpose"),
    )

    ticket = result.pop("ticket")

    # Forward non-P4 tickets to AlertService
    if not result["is_p4"]:
        process_ticket(ticket)

    return JsonResponse(result, status=201 if result["created"] else 200)


# ---------------------------------------------------------------------------
# POST /api/tickets/<ticket_id>/acknowledge/
# ---------------------------------------------------------------------------

@csrf_exempt
@require_http_methods(["POST"])
def ticket_acknowledge(request, ticket_id: int):
    """
    Acknowledge an OPEN ticket.

    Required body field: acked_by (str)
    """
    data, err = _json_body(request)
    if err:
        return err

    acked_by = data.get("acked_by") or data.get("acknowledged_by")
    if not acked_by:
        return JsonResponse({"error": "Missing 'acked_by' field"}, status=400)

    try:
        changed = TicketService.acknowledge_ticket(ticket_id, acked_by)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=404)

    return JsonResponse({"ticket_id": ticket_id, "acknowledged": changed})
