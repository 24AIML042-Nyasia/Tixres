"""
auth_core/middleware.py
-----------------------
JWTAuthMiddleware

Validates every inbound request for a Bearer JWT, then attaches either an
SSOUser instance or None to `request.sso_user`.

The middleware NEVER raises an exception or returns a 401 by itself.
Individual views decide whether authentication is required using the
decorators in auth_core/decorators.py.

Token validation flow
---------------------
1. Try to read `Authorization: Bearer <token>` header.
2. Decode + verify with PyJWT using settings.AUTH_JWT_SECRET /
   settings.AUTH_JWT_ALGORITHM.
3. Extract `sub`, `email`, `name` JWT claims.
4. Upsert the SSOUser row (create on first login; update email/name on
   subsequent logins).
5. Reject inactive users (is_active=False) as if no token were present.

SSO compatibility notes
-----------------------
* Works with any provider that issues standard JWTs (Google, Okta, Auth0,
  Keycloak, Azure AD).  For asymmetric algorithms (RS256, ES256) set
  AUTH_JWT_ALGORITHM = "RS256" and AUTH_JWT_SECRET to the PEM public key.
* For JWKS-based key rotation, swap `_decode_token` for a JWKS client
  (e.g. python-jose) without touching the rest of the middleware.
* Audience and issuer validation are opt-in via AUTH_JWT_AUDIENCE /
  AUTH_JWT_ISSUER in settings (both default to None = not checked).
"""

from __future__ import annotations

import logging

import jwt
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

from auth_core.models import SSOUser

logger = logging.getLogger(__name__)


def _decode_token(token: str) -> dict | None:
    """
    Validate and decode a JWT string.

    Returns the payload dict on success, None on any failure
    (expired, bad signature, missing claims, …).
    """
    try:
        options: dict = {"require": ["sub"]}
        decode_kwargs: dict = {
            "jwt":        token,
            "key":        settings.AUTH_JWT_SECRET,
            "algorithms": [settings.AUTH_JWT_ALGORITHM],
            "options":    options,
        }

        # Optional audience / issuer validation
        audience = getattr(settings, "AUTH_JWT_AUDIENCE", None)
        issuer   = getattr(settings, "AUTH_JWT_ISSUER",   None)
        if audience:
            decode_kwargs["audience"] = audience
        if issuer:
            decode_kwargs["issuer"] = issuer

        return jwt.decode(**decode_kwargs)

    except jwt.ExpiredSignatureError:
        logger.debug("JWT expired")
    except jwt.InvalidTokenError as exc:
        logger.debug("JWT invalid: %s", exc)

    return None


def _get_bearer_token(request) -> str | None:
    """Extract the raw token string from the Authorization header."""
    auth_header: str = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip() or None
    return None


def _upsert_user(payload: dict) -> SSOUser | None:
    """
    Look up or create the SSOUser for this JWT payload.

    We treat `sub` as the stable identifier.  email and name are refreshed
    from the token on every login so they stay in sync with the SSO provider.
    """
    sub   = payload.get("sub")
    email = payload.get("email", "")
    name  = payload.get("name", "") or payload.get("given_name", "") or ""

    if not sub:
        return None

    user, created = SSOUser.objects.get_or_create(
        user_id  = sub,
        defaults = {"email": email, "name": name},
    )

    if not created and (user.email != email or user.name != name):
        # Keep local record in sync with SSO
        user.email = email
        user.name  = name
        user.save(update_fields=["email", "name", "updated_at"])

    return user if user.is_active else None


class JWTAuthMiddleware(MiddlewareMixin):
    """
    Attaches `request.sso_user` (SSOUser | None) to every request.

    Unauthenticated requests simply get sso_user=None; the @require_auth
    decorator returns 401 for views that need authentication.
    """

    def process_request(self, request):
        request.sso_user = None

        token = _get_bearer_token(request)
        if not token:
            return  # anonymous request

        payload = _decode_token(token)
        if not payload:
            return  # bad / expired token — leave sso_user=None

        try:
            request.sso_user = _upsert_user(payload)
        except Exception:
            logger.exception("Unexpected error during JWT user lookup")
