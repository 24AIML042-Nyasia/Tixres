"""
auth_core/views.py
------------------
Auth management endpoints.

GET   /api/auth/me/                    Any authenticated user — own profile.
GET   /api/auth/users/                 Admin — list users with filters.
GET   /api/auth/users/<user_id>/       Admin — detail.
PATCH /api/auth/users/<user_id>/       Admin — update role / attributes / skills.
POST  /api/auth/users/<user_id>/skills/add/     Admin — add one resolver skill.
POST  /api/auth/users/<user_id>/skills/remove/  Admin — remove one resolver skill.
"""

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from auth_core.decorators import require_auth, require_role
from auth_core.models import Role, SSOUser, ResolverProfile
from auth_core.services import AuthService, UserNotFoundError


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

def _serialize_user(user: SSOUser) -> dict:
    profile: ResolverProfile | None = user.resolver_profile
    return {
        "user_id":          user.user_id,
        "email":            user.email,
        "name":             user.name,
        "role":             user.role,
        "is_active":        user.is_active,
        "allowed_agents":   user.allowed_agents,
        "allowed_purposes": user.allowed_purposes,
        "skill_set":        profile.skill_set if profile else None,
        "created_at":       user.created_at.isoformat(),
        "updated_at":       user.updated_at.isoformat(),
    }


def _json_body(request) -> tuple[dict, JsonResponse | None]:
    try:
        return json.loads(request.body), None
    except (json.JSONDecodeError, TypeError):
        return {}, JsonResponse({"error": "Invalid JSON body"}, status=400)


# ---------------------------------------------------------------------------
# GET /api/auth/me/
# ---------------------------------------------------------------------------

@require_auth
@require_http_methods(["GET"])
def me(request):
    """Return the authenticated user's own profile."""
    return JsonResponse(_serialize_user(request.sso_user))


# ---------------------------------------------------------------------------
# GET/POST /api/auth/users/
# ---------------------------------------------------------------------------

@csrf_exempt
@require_auth
@require_role(Role.ADMIN)
@require_http_methods(["GET"])
def user_list(request):
    """List all users (admin only). Supports ?role=&is_active=&skip=&limit= filters."""
    role      = request.GET.get("role")
    is_active_str = request.GET.get("is_active")
    is_active = None
    if is_active_str is not None:
        is_active = is_active_str.lower() == "true"

    try:
        skip  = max(int(request.GET.get("skip",  0)), 0)
        limit = min(max(int(request.GET.get("limit", 50)), 1), 200)
    except ValueError:
        skip, limit = 0, 50

    total, users = AuthService.list_users(
        role=role, is_active=is_active, skip=skip, limit=limit
    )
    return JsonResponse({"total": total, "items": [_serialize_user(u) for u in users]})


# ---------------------------------------------------------------------------
# GET/PATCH /api/auth/users/<user_id>/
# ---------------------------------------------------------------------------

@csrf_exempt
@require_auth
@require_http_methods(["GET", "PATCH"])
def user_detail(request, user_id: str):
    """
    GET  — anyone authenticated (returns 403 for non-admin looking up others).
    PATCH — admin only (update role, allowed_agents, allowed_purposes, is_active).
    """
    # Non-admins can only fetch their own record
    if request.method == "GET":
        if not request.sso_user.is_admin and user_id != request.sso_user.user_id:
            return JsonResponse({"error": "Forbidden"}, status=403)
        try:
            user = AuthService.get_user(user_id)
        except UserNotFoundError as exc:
            return JsonResponse({"error": str(exc)}, status=404)
        return JsonResponse(_serialize_user(user))

    # PATCH — admin only
    if not request.sso_user.is_admin:
        return JsonResponse({"error": "Admin role required"}, status=403)

    data, err = _json_body(request)
    if err:
        return err

    try:
        user = AuthService.get_user(user_id)
    except UserNotFoundError as exc:
        return JsonResponse({"error": str(exc)}, status=404)

    # Apply each patchable field if present in the body
    if "role" in data:
        try:
            user = AuthService.set_role(user_id, data["role"])
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=400)

    if "is_active" in data:
        user = AuthService.set_active(user_id, bool(data["is_active"]))

    allowed_agents   = data.get("allowed_agents")
    allowed_purposes = data.get("allowed_purposes")
    if allowed_agents is not None or allowed_purposes is not None:
        user = AuthService.set_attributes(
            user_id,
            allowed_agents   = allowed_agents,
            allowed_purposes = allowed_purposes,
        )

    if "skill_set" in data:
        try:
            AuthService.set_resolver_skills(user_id, data["skill_set"])
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)

    # Refresh to return fully up-to-date record
    user = AuthService.get_user(user_id)
    return JsonResponse(_serialize_user(user))


# ---------------------------------------------------------------------------
# POST /api/auth/users/<user_id>/skills/add/
# POST /api/auth/users/<user_id>/skills/remove/
# ---------------------------------------------------------------------------

@csrf_exempt
@require_auth
@require_role(Role.ADMIN)
@require_http_methods(["POST"])
def skill_add(request, user_id: str):
    """Add a single skill to a resolver. Body: {"skill": "cpu"}"""
    data, err = _json_body(request)
    if err:
        return err
    skill = data.get("skill", "").strip()
    if not skill:
        return JsonResponse({"error": "'skill' field required"}, status=400)
    try:
        profile = AuthService.add_resolver_skill(user_id, skill)
    except (UserNotFoundError, ValueError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse({"user_id": user_id, "skill_set": profile.skill_set})


@csrf_exempt
@require_auth
@require_role(Role.ADMIN)
@require_http_methods(["POST"])
def skill_remove(request, user_id: str):
    """Remove a single skill from a resolver. Body: {"skill": "cpu"}"""
    data, err = _json_body(request)
    if err:
        return err
    skill = data.get("skill", "").strip()
    if not skill:
        return JsonResponse({"error": "'skill' field required"}, status=400)
    try:
        profile = AuthService.remove_resolver_skill(user_id, skill)
    except UserNotFoundError as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    return JsonResponse({"user_id": user_id, "skill_set": profile.skill_set if profile else []})
