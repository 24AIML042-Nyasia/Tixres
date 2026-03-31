"""
dev_auth/views.py
-----------------
⚠️  DEVELOPMENT / DEMO USE ONLY ⚠️

Two endpoints:

  POST /api/dev-auth/register/
  POST /api/dev-auth/login/

Both endpoints are **blocked in production** (DEBUG=False → 403).

Design
------
* No cookies, no sessions — pure JWT.
* The issued token is signed with the same AUTH_JWT_SECRET /
  AUTH_JWT_ALGORITHM as the rest of the system, so JWTAuthMiddleware
  accepts it out of the box.
* `sub` = user_id (settable on register so you can use any stable ID).
* Token expiry defaults to 24 h (configurable via DEV_AUTH_TOKEN_TTL_HOURS).
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from auth_core.models import SSOUser, Role
from auth_core.services import AuthService
from dev_auth.models import DevCredential


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dev_only(view_func):
    """Block the view with 403 when DEBUG is False."""
    import functools
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not settings.DEBUG:
            return JsonResponse(
                {"error": "dev_auth endpoints are disabled in production (DEBUG=False)."},
                status=403,
            )
        return view_func(request, *args, **kwargs)
    return wrapper


def _json_body(request):
    try:
        return json.loads(request.body), None
    except (json.JSONDecodeError, TypeError):
        return {}, JsonResponse({"error": "Invalid JSON body"}, status=400)


def _issue_token(user: SSOUser) -> str:
    """Sign and return a JWT for this user."""
    ttl_hours = getattr(settings, "DEV_AUTH_TOKEN_TTL_HOURS", 24)
    now       = datetime.now(tz=timezone.utc)
    payload   = {
        "sub":   user.user_id,
        "email": user.email,
        "name":  user.name,
        "role":  user.role,          # non-standard claim; convenient for debugging
        "iat":   now,
        "exp":   now + timedelta(hours=ttl_hours),
    }

    audience = getattr(settings, "AUTH_JWT_AUDIENCE", None)
    issuer   = getattr(settings, "AUTH_JWT_ISSUER",   None)
    if audience:
        payload["aud"] = audience
    if issuer:
        payload["iss"] = issuer

    return jwt.encode(
        payload,
        settings.AUTH_JWT_SECRET,
        algorithm=settings.AUTH_JWT_ALGORITHM,
    )


def _serialize_user(user: SSOUser) -> dict:
    return {
        "user_id":          user.user_id,
        "email":            user.email,
        "name":             user.name,
        "role":             user.role,
        "is_active":        user.is_active,
        "allowed_agents":   user.allowed_agents,
        "allowed_purposes": user.allowed_purposes,
    }


# ---------------------------------------------------------------------------
# POST /api/dev-auth/register/
# ---------------------------------------------------------------------------

@csrf_exempt
@_dev_only
@require_http_methods(["POST"])
def register(request):
    """
    Register a new user and return a JWT.

    Body (JSON):
        email       str  required
        password    str  required
        name        str  optional
        role        str  optional  (end_user | resolver | admin)  default: end_user
        user_id     str  optional  custom stable ID; auto-generated UUID if omitted

    Returns:
        {token, expires_in, user}
    """
    data, err = _json_body(request)
    if err:
        return err

    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name     = data.get("name") or ""
    role     = data.get("role") or Role.END_USER
    user_id  = (data.get("user_id") or "").strip() or f"dev_{uuid.uuid4().hex[:12]}"

    if not email or not password:
        return JsonResponse({"error": "email and password are required"}, status=400)

    if role not in [r.value for r in Role]:
        return JsonResponse({"error": f"Unknown role '{role}'"}, status=400)

    # Guard: email must be unique
    if SSOUser.objects.filter(email=email).exists():
        return JsonResponse({"error": f"Email '{email}' is already registered"}, status=409)

    # Create SSOUser + DevCredential atomically
    user = SSOUser.objects.create(
        user_id = user_id,
        email   = email,
        name    = name,
        role    = role,
    )

    cred = DevCredential(user=user)
    cred.set_password(password)
    cred.save()

    # Automatically create ResolverProfile for resolvers so skill_set is ready
    if role == Role.RESOLVER:
        from auth_core.models import ResolverProfile
        ResolverProfile.objects.create(user=user)

    token    = _issue_token(user)
    ttl      = getattr(settings, "DEV_AUTH_TOKEN_TTL_HOURS", 24)

    return JsonResponse(
        {
            "token":      token,
            "expires_in": ttl * 3600,
            "user":       _serialize_user(user),
        },
        status=201,
    )


# ---------------------------------------------------------------------------
# POST /api/dev-auth/login/
# ---------------------------------------------------------------------------

@csrf_exempt
@_dev_only
@require_http_methods(["POST"])
def login(request):
    """
    Verify credentials and return a fresh JWT.

    Body (JSON):
        email     str  required
        password  str  required

    Returns:
        {token, expires_in, user}
    """
    data, err = _json_body(request)
    if err:
        return err

    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return JsonResponse({"error": "email and password are required"}, status=400)

    try:
        user = SSOUser.objects.select_related("dev_credential").get(email=email)
    except SSOUser.DoesNotExist:
        return JsonResponse({"error": "Invalid credentials"}, status=401)

    if not user.is_active:
        return JsonResponse({"error": "Account is inactive"}, status=403)

    cred: DevCredential | None = getattr(user, "dev_credential", None)
    if cred is None or not cred.verify_password(password):
        return JsonResponse({"error": "Invalid credentials"}, status=401)

    token = _issue_token(user)
    ttl   = getattr(settings, "DEV_AUTH_TOKEN_TTL_HOURS", 24)

    return JsonResponse(
        {
            "token":      token,
            "expires_in": ttl * 3600,
            "user":       _serialize_user(user),
        }
    )


# ---------------------------------------------------------------------------
# POST /api/dev-auth/token/
# ---------------------------------------------------------------------------

@csrf_exempt
@_dev_only
@require_http_methods(["POST"])
def issue_token(request):
    """
    ⚠️ Passwordless token mint — for scripting and automated tests ONLY.

    Accepts any user_id that already exists in SSOUser and issues a JWT
    without checking credentials. Useful for writing quick curl tests.

    Body (JSON):
        user_id   str  required
    """
    data, err = _json_body(request)
    if err:
        return err

    user_id = (data.get("user_id") or "").strip()
    if not user_id:
        return JsonResponse({"error": "user_id is required"}, status=400)

    try:
        user = AuthService.get_user(user_id)
    except Exception:
        return JsonResponse({"error": f"User '{user_id}' not found"}, status=404)

    if not user.is_active:
        return JsonResponse({"error": "Account is inactive"}, status=403)

    token = _issue_token(user)
    ttl   = getattr(settings, "DEV_AUTH_TOKEN_TTL_HOURS", 24)
    return JsonResponse({"token": token, "expires_in": ttl * 3600})
