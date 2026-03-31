"""
workflows/views.py
------------------
Admin-only API for managing workflow statuses per purpose.

GET  /api/workflows/statuses/              list (filterable by purpose, applies_to)
POST /api/workflows/statuses/              create / upsert a status
GET  /api/workflows/statuses/<id>/         detail
PATCH /api/workflows/statuses/<id>/        update
DELETE /api/workflows/statuses/<id>/       delete
"""

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from auth_core.decorators import require_auth, require_role
from auth_core.models import Role
from workflows.models import WorkflowStatus, AppliesTo
from workflows.services import WorkflowService


def _serialize(obj: WorkflowStatus) -> dict:
    return {
        "id":                obj.pk,
        "purpose":           obj.purpose,
        "applies_to":        obj.applies_to,
        "key":               obj.key,
        "label":             obj.label,
        "color":             obj.color,
        "is_initial":        obj.is_initial,
        "is_terminal":       obj.is_terminal,
        "is_auto_resolvable": obj.is_auto_resolvable,
        "order":             obj.order,
    }


def _json_body(request):
    try:
        return json.loads(request.body), None
    except (json.JSONDecodeError, TypeError):
        return {}, JsonResponse({"error": "Invalid JSON body"}, status=400)


# ---------------------------------------------------------------------------
# GET /api/workflows/statuses/        — list
# POST /api/workflows/statuses/       — upsert
# ---------------------------------------------------------------------------

@csrf_exempt
@require_auth
@require_http_methods(["GET", "POST"])
def status_list_create(request):
    if request.method == "GET":
        qs = WorkflowStatus.objects.all()
        if purpose := request.GET.get("purpose"):
            qs = qs.filter(purpose=purpose)
        elif request.GET.get("global") == "true":
            qs = qs.filter(purpose__isnull=True)
        if applies_to := request.GET.get("applies_to"):
            qs = qs.filter(applies_to__in=[applies_to, AppliesTo.BOTH])
        return JsonResponse({
            "count": qs.count(),
            "items": [_serialize(r) for r in qs.order_by("purpose", "applies_to", "order", "key")],
        })

    # POST — admin only
    if not request.sso_user.is_admin:
        return JsonResponse({"error": "Admin role required"}, status=403)

    data, err = _json_body(request)
    if err:
        return err

    key   = (data.get("key") or "").strip().upper()
    label = (data.get("label") or "").strip()
    if not key or not label:
        return JsonResponse({"error": "'key' and 'label' are required"}, status=400)

    applies_to = data.get("applies_to", AppliesTo.BOTH)
    if applies_to not in [c[0] for c in AppliesTo.choices]:
        return JsonResponse({"error": f"Invalid applies_to '{applies_to}'"}, status=400)

    obj, created = WorkflowService.upsert_status(
        key                = key,
        label              = label,
        purpose            = data.get("purpose") or None,
        applies_to         = applies_to,
        color              = data.get("color", ""),
        is_initial         = bool(data.get("is_initial", False)),
        is_terminal        = bool(data.get("is_terminal", False)),
        is_auto_resolvable = bool(data.get("is_auto_resolvable", False)),
        order              = int(data.get("order", 0)),
    )
    return JsonResponse(_serialize(obj), status=201 if created else 200)


# ---------------------------------------------------------------------------
# GET /api/workflows/statuses/<id>/
# PATCH /api/workflows/statuses/<id>/
# DELETE /api/workflows/statuses/<id>/
# ---------------------------------------------------------------------------

@csrf_exempt
@require_auth
@require_http_methods(["GET", "PATCH", "DELETE"])
def status_detail(request, pk: int):
    try:
        obj = WorkflowStatus.objects.get(pk=pk)
    except WorkflowStatus.DoesNotExist:
        return JsonResponse({"error": f"WorkflowStatus {pk} not found"}, status=404)

    if request.method == "GET":
        return JsonResponse(_serialize(obj))

    if not request.sso_user.is_admin:
        return JsonResponse({"error": "Admin role required"}, status=403)

    if request.method == "PATCH":
        data, err = _json_body(request)
        if err:
            return err

        patchable = ["label", "color", "is_initial", "is_terminal", "is_auto_resolvable", "order"]
        updated = []
        for field in patchable:
            if field in data:
                setattr(obj, field, data[field])
                updated.append(field)

        if updated:
            obj.save(update_fields=updated)

            if "is_initial" in updated and obj.is_initial:
                # Enforce single initial per scope
                WorkflowStatus.objects.filter(
                    purpose    = obj.purpose,
                    applies_to = obj.applies_to,
                    is_initial = True,
                ).exclude(pk=obj.pk).update(is_initial=False)

        return JsonResponse(_serialize(obj))

    # DELETE
    obj.delete()
    return JsonResponse({"deleted": True, "id": pk})
