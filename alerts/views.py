"""
alerts/views.py
---------------
JSON API views for the alerts app (no UI endpoints).
"""

import json

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from alerts.models import Alert
from alerts.resolution import ResolutionService


def _json_body(request):
    try:
        return json.loads(request.body), None
    except (json.JSONDecodeError, TypeError):
        return {}, JsonResponse({"error": "Invalid JSON body"}, status=400)


def _serialize_alert(a: Alert) -> dict:
    def _iso(dt):
        return dt.isoformat() if dt else None

    return {
        "id":               a.pk,
        "metric_name":      a.metric_name,
        "severity":         a.severity,
        "purpose":          a.purpose,
        "type":             a.type,
        "status":           a.status,
        "agent_ids":        json.loads(a.agent_ids or "[]"),
        "total_occurrence": a.total_occurrence,
        "first_seen_at":    _iso(a.first_seen_at),
        "last_seen_at":     _iso(a.last_seen_at),
        "cooldown_until":   _iso(a.cooldown_until),
        "created_at":       _iso(a.created_at),
        "closed_at":        _iso(a.closed_at),
        "acknowledged_at":  _iso(a.acknowledged_at),
        "acknowledged_by":  a.acknowledged_by,
    }


# ---------------------------------------------------------------------------
# GET /api/alerts/
# ---------------------------------------------------------------------------

@require_http_methods(["GET"])
def alert_list(request):
    """
    Paginated list of alerts, ordered by last_seen_at desc.

    Query params: status, severity, purpose, skip (int), limit (int ≤100)
    """
    qs = Alert.objects.all()

    if status := request.GET.get("status"):
        qs = qs.filter(status=status)
    if severity := request.GET.get("severity"):
        qs = qs.filter(severity=severity)
    if purpose := request.GET.get("purpose"):
        qs = qs.filter(purpose=purpose)

    try:
        skip  = max(int(request.GET.get("skip", 0)), 0)
        limit = min(max(int(request.GET.get("limit", 20)), 1), 100)
    except ValueError:
        skip, limit = 0, 20

    total   = qs.count()
    alerts  = list(qs.order_by("-last_seen_at")[skip : skip + limit])

    return JsonResponse({
        "total":  total,
        "items":  [_serialize_alert(a) for a in alerts],
    })


# ---------------------------------------------------------------------------
# GET /api/alerts/<alert_id>/
# ---------------------------------------------------------------------------

@require_http_methods(["GET"])
def alert_detail(request, alert_id: int):
    try:
        alert = Alert.objects.get(pk=alert_id)
    except Alert.DoesNotExist:
        return JsonResponse({"error": f"Alert {alert_id} not found"}, status=404)
    return JsonResponse(_serialize_alert(alert))


# ---------------------------------------------------------------------------
# POST /api/alerts/<alert_id>/resolve/
# ---------------------------------------------------------------------------

@csrf_exempt
@require_http_methods(["POST"])
def alert_resolve(request, alert_id: int):
    """Manually close an OPEN alert and its related tickets."""
    try:
        alert = Alert.objects.get(pk=alert_id)
    except Alert.DoesNotExist:
        return JsonResponse({"error": f"Alert {alert_id} not found"}, status=404)

    if alert.status != "OPEN":
        return JsonResponse(
            {"error": f"Alert {alert_id} is already {alert.status}"},
            status=400,
        )

    ResolutionService.resolve_alert(alert)
    return JsonResponse({"message": "Alert resolved", "resolved_id": alert_id})


# ---------------------------------------------------------------------------
# POST /api/alerts/<alert_id>/broadcast/
# ---------------------------------------------------------------------------

@csrf_exempt
@require_http_methods(["POST"])
def alert_broadcast(request, alert_id: int):
    """
    Broadcast a comment to every non-closed ticket associated with this alert.

    The alert and tickets are linked by the natural key
    (metric_name, severity, purpose).  All OPEN or ACK tickets matching that
    key receive the comment.

    Body (JSON):
        content     str   required — the message to broadcast
        visibility  str   optional — "external" (default) | "internal"

    Only resolver and admin may post internal broadcasts.
    End-user broadcasts are always coerced to "external".

    Response:
        {
          "alert_id": 1,
          "message": "Broadcast sent",
          "comment_ids": [10, 11, 12],   ← one TicketComment per matched ticket
          "ticket_count": 3
        }
    """
    try:
        alert = Alert.objects.get(pk=alert_id)
    except Alert.DoesNotExist:
        return JsonResponse({"error": f"Alert {alert_id} not found"}, status=404)

    data, err = _json_body(request)
    if err:
        return err

    content = (data.get("content") or "").strip()
    if not content:
        return JsonResponse({"error": "'content' is required"}, status=400)

    # Resolve author from JWT middleware (may be None for unauthenticated requests)
    user = getattr(request, "sso_user", None)
    from auth_core.models import Role as _Role
    can_internal = user and user.role in (_Role.RESOLVER, _Role.ADMIN)

    requested_vis = data.get("visibility", "external")
    visibility    = "internal" if (can_internal and requested_vis == "internal") else "external"

    # Find all OPEN / ACK tickets matching the alert's natural key
    from tickets.models import (
        Ticket,
        TicketComment,
        TICKET_STATUS_OPEN,
        TICKET_STATUS_ACK,
        COMMENT_VISIBILITY_EXTERNAL,
        COMMENT_VISIBILITY_INTERNAL,
    )

    tickets = Ticket.objects.filter(
        metric_name = alert.metric_name,
        severity    = alert.severity,
        purpose     = alert.purpose,
        status__in  = [TICKET_STATUS_OPEN, TICKET_STATUS_ACK],
    )

    vis_const = (
        COMMENT_VISIBILITY_INTERNAL if visibility == "internal"
        else COMMENT_VISIBILITY_EXTERNAL
    )

    comments = TicketComment.objects.bulk_create([
        TicketComment(
            ticket     = ticket,
            author     = user,
            content    = content,
            visibility = vis_const,
        )
        for ticket in tickets
    ])

    return JsonResponse({
        "alert_id":     alert_id,
        "message":      "Broadcast sent",
        "visibility":   visibility,
        "comment_ids":  [c.pk for c in comments],
        "ticket_count": len(comments),
    })
