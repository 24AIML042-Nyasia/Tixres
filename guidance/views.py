"""
guidance/views.py
-----------------
JSON API views for the guidance (runbook) app (no UI endpoints).
"""

import json

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from attachments.models import AttachmentKind
from attachments.services import AttachmentService, AttachmentValidationError
from guidance.models import Guidance
from guidance.services import GuidanceService, GuidanceNotFoundError


def _serialize(obj: Guidance) -> dict:
    return {
        "id":               obj.pk,
        "metric_name":      obj.metric_name,
        "purpose":          obj.purpose,
        "priority":         obj.priority,
        "resolution_steps": obj.resolution_steps or [],
        "resolver_notes":   obj.resolver_notes,
        "resolution_meta":  obj.resolution_meta,
        "attachments":      AttachmentService.serialize_many(getattr(obj, "attachments").all()),
        "last_updated":     obj.last_updated.isoformat(),
    }


def _json_body(request) -> tuple[dict, JsonResponse | None]:
    try:
        return json.loads(request.body), None
    except (json.JSONDecodeError, TypeError):
        return {}, JsonResponse({"error": "Invalid JSON body"}, status=400)


# ---------------------------------------------------------------------------
# PUT /api/guidance/  — upsert
# GET /api/guidance/  — list
# ---------------------------------------------------------------------------

@csrf_exempt
@require_http_methods(["PUT", "GET"])
def guidance_list_or_upsert(request):
    if request.method == "PUT":
        data, err = _json_body(request)
        if err:
            return err

        attachments_payload = data.get("attachments", None)
        if not data.get("metric_name"):
            return JsonResponse({"error": "metric_name is required"}, status=400)
        if not data.get("resolution_steps"):
            return JsonResponse({"error": "resolution_steps must be a non-empty array"}, status=400)

        try:
            with transaction.atomic():
                obj, created = GuidanceService.upsert(data)
                if attachments_payload is not None:
                    AttachmentService.sync_for_object(
                        obj,
                        attachments_payload,
                        allowed_kinds=[AttachmentKind.IMAGE],
                    )
        except AttachmentValidationError as exc:
            return JsonResponse({"error": str(exc)}, status=400)

        return JsonResponse(_serialize(obj), status=201 if created else 200)

    # GET — paginated list
    try:
        skip  = max(int(request.GET.get("skip", 0)), 0)
        limit = min(max(int(request.GET.get("limit", 20)), 1), 100)
    except ValueError:
        skip, limit = 0, 20

    total, records = GuidanceService.list(
        skip        = skip,
        limit       = limit,
        priority    = request.GET.get("priority") or request.GET.get("severity"),
        metric_name = request.GET.get("metric_name"),
        purpose     = request.GET.get("purpose"),
    )

    return JsonResponse({"total": total, "items": [_serialize(r) for r in records]})


# ---------------------------------------------------------------------------
# GET /api/guidance/summary/stats/
# ---------------------------------------------------------------------------

@require_http_methods(["GET"])
def guidance_stats(request):
    return JsonResponse(GuidanceService.summarize_by_priority())


# ---------------------------------------------------------------------------
# GET /api/guidance/by-key/
# GET /api/guidance/by-key/steps/
# ---------------------------------------------------------------------------

@require_http_methods(["GET"])
def guidance_by_key(request):
    """Lookup by natural key: ?metric_name=&priority=&purpose="""
    metric_name = request.GET.get("metric_name")
    priority    = request.GET.get("priority") or request.GET.get("severity")
    purpose     = request.GET.get("purpose", "general")

    if not metric_name or not priority:
        return JsonResponse(
            {"error": "metric_name and priority (or severity) are required"},
            status=422,
        )

    try:
        obj = GuidanceService.get_by_natural_key(metric_name, priority, purpose)
    except GuidanceNotFoundError as exc:
        return JsonResponse({"error": str(exc)}, status=404)

    return JsonResponse(_serialize(obj))


@require_http_methods(["GET"])
def guidance_by_key_steps(request):
    """Return only resolution_steps for lightweight agent triage."""
    metric_name = request.GET.get("metric_name")
    priority    = request.GET.get("priority") or request.GET.get("severity")
    purpose     = request.GET.get("purpose", "general")

    if not metric_name or not priority:
        return JsonResponse(
            {"error": "metric_name and priority (or severity) are required"},
            status=422,
        )

    try:
        steps = GuidanceService.get_resolution_steps(metric_name, priority, purpose)
    except GuidanceNotFoundError as exc:
        return JsonResponse({"error": str(exc)}, status=404)

    return JsonResponse({"steps": steps})


# ---------------------------------------------------------------------------
# GET  /api/guidance/<id>/
# PATCH /api/guidance/<id>/
# DELETE /api/guidance/<id>/
# ---------------------------------------------------------------------------

@csrf_exempt
@require_http_methods(["GET", "PATCH", "DELETE"])
def guidance_detail(request, pk: int):
    if request.method == "GET":
        try:
            obj = GuidanceService.get_by_id(pk)
        except GuidanceNotFoundError as exc:
            return JsonResponse({"error": str(exc)}, status=404)
        return JsonResponse(_serialize(obj))

    if request.method == "PATCH":
        data, err = _json_body(request)
        if err:
            return err
        attachments_payload = data.get("attachments", None)
        try:
            with transaction.atomic():
                obj = GuidanceService.update_by_id(pk, data)
                if attachments_payload is not None:
                    AttachmentService.sync_for_object(
                        obj,
                        attachments_payload,
                        allowed_kinds=[AttachmentKind.IMAGE],
                    )
        except GuidanceNotFoundError as exc:
            return JsonResponse({"error": str(exc)}, status=404)
        except AttachmentValidationError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        return JsonResponse(_serialize(obj))

    # DELETE
    try:
        result = GuidanceService.delete_by_id(pk)
    except GuidanceNotFoundError as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    return JsonResponse(result)
