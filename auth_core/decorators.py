"""
auth_core/decorators.py
------------------------
View decorators for authentication and authorization.

All decorators work with `request.sso_user` set by JWTAuthMiddleware.

Available decorators
--------------------
@require_auth
    Must be authenticated (any role).  Returns 401 if not.

@require_role(*roles)
    Must be authenticated AND have one of the listed roles.
    Accepts role strings ("admin", "resolver", "end_user") or Role enum values.
    Returns 401 if unauthenticated, 403 if wrong role.

@require_agent_access(agent_id_getter)
    Checks ABAC allowed_agents constraint.
    Admin always passes.  End-users and resolvers pass only when:
      - allowed_agents is empty (unrestricted), OR
      - the resolved agent_id is in allowed_agents.
    Returns 403 on failure.

@require_purpose_access(purpose_getter)
    Same semantics as require_agent_access but for allowed_purposes.

@require_skill(metric_getter)
    Resolver-only skill check.  Admin always passes.
    Resolver passes only when their ResolverProfile.matches_metric() is True.
    End-users always fail (they cannot perform skill-gated actions).
    Returns 403 on failure.

Getter callables
----------------
agent_id_getter  : (request, *args, **kwargs) -> str
purpose_getter   : (request, *args, **kwargs) -> str
metric_getter    : (request, *args, **kwargs) -> str

Typical usage
-------------
@csrf_exempt
@require_auth
@require_role("resolver", "admin")
@require_skill(lambda request, ticket_id: _get_ticket_metric(ticket_id))
def ticket_acknowledge(request, ticket_id):
    ...
"""

from __future__ import annotations

import functools
import json
import logging

from django.http import JsonResponse

from auth_core.models import Role, SSOUser

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_403(message: str) -> JsonResponse:
    return JsonResponse({"error": message}, status=403)


def _json_401(message: str = "Authentication required") -> JsonResponse:
    response = JsonResponse({"error": message}, status=401)
    response["WWW-Authenticate"] = 'Bearer realm="api"'
    return response


# ---------------------------------------------------------------------------
# @require_auth
# ---------------------------------------------------------------------------

def require_auth(view_func):
    """Block unauthenticated access (returns 401)."""
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.sso_user is None:
            return _json_401()
        return view_func(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# @require_role(*roles)
# ---------------------------------------------------------------------------

def require_role(*roles: str):
    """
    Ensure the authenticated user holds one of the listed roles.

    Usage::

        @require_role("admin", "resolver")
        def my_view(request): ...
    """
    allowed = {r.value if hasattr(r, "value") else r for r in roles}

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user: SSOUser | None = request.sso_user
            if user is None:
                return _json_401()
            if user.role not in allowed:
                return _json_403(
                    f"Role '{user.role}' is not permitted to perform this action. "
                    f"Required: {sorted(allowed)}"
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# @require_agent_access(agent_id_getter)
# ---------------------------------------------------------------------------

def require_agent_access(agent_id_getter):
    """
    ABAC check: the user must be allowed to access the given agent.

    Admin bypasses this check.
    For end_user / resolver: allowed_agents must be empty (= unrestricted)
    OR must contain the resolved agent_id.

    Args:
        agent_id_getter: callable(request, *args, **kwargs) → str
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user: SSOUser | None = request.sso_user
            if user is None:
                return _json_401()

            if not user.is_admin:
                try:
                    agent_id = agent_id_getter(request, *args, **kwargs)
                except Exception:
                    logger.exception("agent_id_getter raised an exception")
                    return _json_403("Could not resolve agent context for access check.")

                if user.allowed_agents and agent_id not in user.allowed_agents:
                    return _json_403(f"Access to agent '{agent_id}' is not permitted.")

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# @require_purpose_access(purpose_getter)
# ---------------------------------------------------------------------------

def require_purpose_access(purpose_getter):
    """
    ABAC check: the user must be allowed to access the given purpose.

    Admin bypasses. Empty allowed_purposes = unrestricted.

    Args:
        purpose_getter: callable(request, *args, **kwargs) → str
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user: SSOUser | None = request.sso_user
            if user is None:
                return _json_401()

            if not user.is_admin:
                try:
                    purpose = purpose_getter(request, *args, **kwargs)
                except Exception:
                    logger.exception("purpose_getter raised an exception")
                    return _json_403("Could not resolve purpose context for access check.")

                if user.allowed_purposes and purpose not in user.allowed_purposes:
                    return _json_403(f"Access to purpose '{purpose}' is not permitted.")

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# @require_skill(metric_getter)
# ---------------------------------------------------------------------------

def require_skill(metric_getter):
    """
    Skill-based ABAC check for resolvers.

    * Admin  → always passes.
    * Resolver → passes only when ResolverProfile.matches_metric(metric_name) is True.
    * Anything else → 403 (end_user has no skills by definition).

    Args:
        metric_getter: callable(request, *args, **kwargs) → str
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user: SSOUser | None = request.sso_user
            if user is None:
                return _json_401()

            if user.is_admin:
                return view_func(request, *args, **kwargs)

            if not user.is_resolver:
                return _json_403("Skill-gated actions require the resolver role.")

            try:
                metric_name = metric_getter(request, *args, **kwargs)
            except Exception:
                logger.exception("metric_getter raised an exception")
                return _json_403("Could not resolve metric context for skill check.")

            profile = user.resolver_profile
            if profile is None or not profile.matches_metric(metric_name):
                return _json_403(
                    f"Resolver does not have a skill matching metric '{metric_name}'."
                )

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
