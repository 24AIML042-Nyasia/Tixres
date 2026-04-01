"""
tickets/views.py
----------------
JSON API views for the tickets app (no UI endpoints).
"""

import json
from datetime import datetime, timezone

from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from alerts.services import process_ticket
from auth_core.decorators import require_auth, require_role
from auth_core.models import Role as _Role
from auth_core.services import AuthService
from tickets.assignment import AssignmentService, AssignmentDecision
from tickets.models import (
    Ticket,
    TicketComment,
    COMMENT_VISIBILITY_EXTERNAL,
)
from tickets.services import TicketService
from attachments.services import AttachmentService, AttachmentValidationError
from attachments.models import AttachmentKind


def _json_body(request) -> tuple[dict, JsonResponse | None]:
    """Parse JSON request body; return (data, None) or ({}, error_response)."""
    try:
        data = json.loads(request.body)
        return data, None
    except (json.JSONDecodeError, TypeError):
        return {}, JsonResponse({"error": "Invalid JSON body"}, status=400)


def _render_report_form(initial: dict | None = None, errors: list[str] | None = None, ticket_id: int | None = None) -> HttpResponse:
    initial = initial or {}
    errors = errors or []
    base_style = """
    <style>
      body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f6f7fb; padding: 32px; }
      .card { max-width: 640px; margin: 0 auto; background: #fff; padding: 24px 28px; border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.06); }
      h1 { margin-top: 0; font-size: 20px; }
      label { display: block; font-weight: 600; margin: 16px 0 6px; }
      input, textarea { width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid #d7d9e0; font-size: 14px; }
      textarea { min-height: 120px; resize: vertical; }
      .hint { color: #6b7280; font-size: 12px; margin-top: 4px; }
      .error { background: #fff5f5; color: #b91c1c; padding: 10px 12px; border-radius: 8px; margin-bottom: 8px; border: 1px solid #fecdd3; }
      .success { background: #ecfdf3; color: #166534; padding: 12px 14px; border-radius: 10px; margin-bottom: 10px; border: 1px solid #bbf7d0; }
      button { background: #111827; color: #fff; border: none; padding: 12px 16px; border-radius: 10px; font-size: 14px; cursor: pointer; margin-top: 18px; }
      button:hover { background: #0b1220; }
      .flex { display: flex; gap: 12px; }
      .flex .col { flex: 1; }
    </style>
    """
    success_html = ""
    if ticket_id is not None:
        success_html = f'<div class="success">Thanks! Ticket <strong>#{ticket_id}</strong> was created with priority P0.</div>'

    errors_html = "".join(f'<div class="error">{e}</div>' for e in errors)
    html = f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <title>Report an Issue</title>
        {base_style}
      </head>
      <body>
        <div class="card">
          <h1>Report an Issue</h1>
          {success_html}
          {errors_html}
          <form method="post">
            <label for="agent_id">Agent ID *</label>
            <input id="agent_id" name="agent_id" value="{initial.get('agent_id', '')}" placeholder="agent-prod-1" required />
            <div class="hint">Purpose will be auto-fetched from this agent.</div>

            <label for="metric_name">Metric / Component *</label>
            <input id="metric_name" name="metric_name" value="{initial.get('metric_name', 'user.report')}" placeholder="user.report" required />

            <label for="message">What happened? *</label>
            <textarea id="message" name="message" placeholder="Describe the issue, expected vs actual, timestamps, links..." required>{initial.get('message', '')}</textarea>

            <div class="flex">
              <div class="col">
                <label for="reporter_name">Your name</label>
                <input id="reporter_name" name="reporter_name" value="{initial.get('reporter_name', '')}" placeholder="Ada Lovelace" />
              </div>
              <div class="col">
                <label for="reporter_email">Email</label>
                <input id="reporter_email" name="reporter_email" value="{initial.get('reporter_email', '')}" placeholder="you@example.com" />
              </div>
            </div>

            <label for="attachments">Attachment links (one per line)</label>
            <textarea id="attachments" name="attachments" placeholder="https://.../screenshot1.png\nhttps://.../har.log">{initial.get('attachments', '')}</textarea>
            <div class="hint">Paste URLs to images or files stored elsewhere; they will attach to the first comment.</div>

            <button type="submit">Submit P0 Ticket</button>
          </form>
        </div>
      </body>
    </html>
    """
    return HttpResponse(html)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def ticket_report_form(request):
    """
    Simple HTML form for user-submitted tickets (always severity P0, no dedup).
    Purpose is inferred from the agent_id via TicketService._resolve_purpose.
    """
    if request.method == "GET":
        return _render_report_form()

    data = request.POST
    initial = {
        "agent_id": data.get("agent_id", "").strip(),
        "metric_name": data.get("metric_name", "").strip(),
        "message": data.get("message", "").strip(),
        "reporter_name": data.get("reporter_name", "").strip(),
        "reporter_email": data.get("reporter_email", "").strip(),
        "attachments": data.get("attachments", "").strip(),
    }

    errors: list[str] = []
    if not initial["agent_id"]:
        errors.append("Agent ID is required.")
    if not initial["metric_name"]:
        errors.append("Metric / Component is required.")
    if not initial["message"]:
        errors.append("Message is required.")

    attachments_payload: list[dict] = []
    if initial["attachments"]:
        # allow comma or newline separated URLs
        raw_items = []
        for line in initial["attachments"].splitlines():
            raw_items.extend([p for p in line.split(",") if p.strip()])
        for idx, url in enumerate(raw_items):
            url = url.strip()
            if not url:
                continue
            attachments_payload.append(
                {
                    "kind": AttachmentKind.IMAGE,
                    "url": url,
                    "file_name": f"attachment-{idx + 1}",
                }
            )

    if errors:
        return _render_report_form(initial, errors)

    meta = {
        "reporter_name": initial["reporter_name"],
        "reporter_email": initial["reporter_email"],
        "source": "user_form",
    }

    try:
        result = TicketService.create_ticket(
            agent_id             = initial["agent_id"],
            metric_name          = initial["metric_name"] or "user.report",
            severity             = "P0",
            detector             = "user_form",
            meta                 = json.dumps(meta),
            message              = initial["message"],
            dedup                = False,
            dedup_window_minutes = None,
            purpose              = None,
        )
        ticket = result["ticket"]

        comment = TicketComment.objects.create(
            ticket     = ticket,
            author     = getattr(request, "sso_user", None),
            content    = initial["message"],
            visibility = COMMENT_VISIBILITY_EXTERNAL,
        )
        if attachments_payload:
            AttachmentService.sync_for_object(
                comment,
                attachments_payload,
                allowed_kinds=[AttachmentKind.IMAGE],
            )
    except AttachmentValidationError as exc:
        return _render_report_form(initial, [str(exc)])
    except Exception as exc:  # pragma: no cover - defensive UX
        return _render_report_form(initial, [f"Could not create ticket: {exc}"])

    return _render_report_form(
        {
            "agent_id": initial["agent_id"],
            "metric_name": initial["metric_name"],
            "attachments": initial["attachments"],
        },
        [],
        ticket_id=ticket.pk,
    )


# ---------------------------------------------------------------------------
# GET /api/tickets/<agent_id>/latest/
# ---------------------------------------------------------------------------

@require_http_methods(["GET"])
def ticket_list(request, agent_id: str):
    """
    Return the most recent tickets for an agent.

    Query params:
      - limit        (int, 1-100, default 100)
      - include_p4   (bool, default false)
      - status       (OPEN|ACK|CLOSED)
      - severity     (priority filter, e.g. P1)
      - detector     (matches detectors array)
      - start / end  (ISO8601; filters last_occurred_at range)
    """
    try:
        limit = min(max(int(request.GET.get("limit", 100)), 1), 100)
    except ValueError:
        limit = 100
    include_p4 = request.GET.get("include_p4", "false").lower() == "true"

    def _parse_ts(raw: str | None):
        if not raw:
            return None
        try:
            cleaned = raw.replace("Z", "+00:00")
            dt = datetime.fromisoformat(cleaned)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            return None

    start_ts = _parse_ts(request.GET.get("start") or request.GET.get("from") or request.GET.get("start_at"))
    end_ts   = _parse_ts(request.GET.get("end")   or request.GET.get("to")   or request.GET.get("end_at"))

    tickets = TicketService.get_tickets(
        agent_id,
        limit=limit,
        include_p4=include_p4,
        status=request.GET.get("status") or None,
        severity=request.GET.get("severity") or request.GET.get("priority") or None,
        detector=request.GET.get("detector") or None,
        start=start_ts,
        end=end_ts,
    )

    # Serialize datetime fields
    def _serialize(t: dict) -> dict:
        for k in ("first_occurred_at", "last_occurred_at", "created_at", "acknowledged_at", "assigned_at"):
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

    if result.get("assigned_at"):
        result["assigned_at"] = result["assigned_at"].isoformat()

    return JsonResponse(result, status=201 if result["created"] else 200)


# ---------------------------------------------------------------------------
@csrf_exempt
@require_auth
@require_role("resolver", "admin")
@require_http_methods(["POST"])
def ticket_assign(request, ticket_id: int):
    """
    Manually assign a ticket to a resolver.
    Body: { "assignee_id": "<resolver_id>", "reason": "optional" }
    """
    data, err = _json_body(request)
    if err:
        return err

    assignee_id = data.get("assignee_id")
    reason = data.get("reason", "").strip()
    if not assignee_id:
        return JsonResponse({"error": "'assignee_id' is required"}, status=400)

    try:
        ticket = Ticket.objects.get(pk=ticket_id)
    except Ticket.DoesNotExist:
        return JsonResponse({"error": f"Ticket {ticket_id} not found"}, status=404)

    user = request.sso_user
    if not (user.is_admin or AuthService.can_access_agent(user, ticket.agent_id)):
        return JsonResponse({"error": "Access to this agent is not permitted"}, status=403)
    if not (user.is_admin or AuthService.can_access_purpose(user, ticket.purpose)):
        return JsonResponse({"error": "Access to this purpose is not permitted"}, status=403)

    # Fetch target resolver
    try:
        assignee = AuthService.get_user(assignee_id)
    except Exception:
        return JsonResponse({"error": "Assignee not found"}, status=404)
    if assignee.role != _Role.RESOLVER:
        return JsonResponse({"error": "Assignee must be a resolver"}, status=400)
    if not assignee.is_active:
        return JsonResponse({"error": "Assignee is inactive"}, status=400)

    if not user.is_admin and not AssignmentService._is_eligible(assignee, ticket, skip_skill=False):
        return JsonResponse({"error": "Assignee fails skill or ABAC checks"}, status=403)

    now = datetime.now(tz=timezone.utc)
    ticket.assigned_to = assignee
    ticket.assigned_at = now
    ticket.assignment_strategy = "manual"
    ticket.assignment_reason = reason or "Manual assignment"
    ticket.auto_assigned = False
    ticket.save(
        update_fields=[
            "assigned_to",
            "assigned_at",
            "assignment_strategy",
            "assignment_reason",
            "auto_assigned",
        ]
    )
    AssignmentService._append_history(
        ticket,
        AssignmentDecision(
            assignee=assignee,
            strategy="manual",
            reason=ticket.assignment_reason,
            auto_assigned=False,
        ),
        now,
    )

    response = {
        "ticket_id":          ticket.pk,
        "assigned_to":        assignee.user_id,
        "assigned_to_email":  assignee.email,
        "assigned_to_name":   assignee.name,
        "assigned_at":        ticket.assigned_at.isoformat(),
        "assignment_strategy": ticket.assignment_strategy,
        "assignment_reason":   ticket.assignment_reason,
        "auto_assigned":       ticket.auto_assigned,
    }
    return JsonResponse(response)


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
