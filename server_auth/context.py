from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, Header, HTTPException

from server_auth.hmac import verify_signature
from server_db.connection import SessionLocal
from server_db.models import AgentCredentials
from server_utils.logger import get_logger

logger = get_logger()

Role = Literal["user", "resolver"]


@dataclass
class AuthContext:
    """Lightweight request context containing the caller's identity and role."""

    agent_id: str
    role: Role
    api_key: str


async def get_auth_context(
    x_api_key: str = Header(...),
    x_signature: str = Header(...),
    x_message: str = Header(...),
) -> AuthContext:
    """
    Validate HMAC headers and return the authenticated caller with role info.
    Falls back to 'user' when role is missing or unknown.
    """
    if not verify_signature(x_api_key, x_message, x_signature):
        raise HTTPException(status_code=401, detail="Invalid authentication")

    db = SessionLocal()
    try:
        cred = (
            db.query(AgentCredentials)
            .filter(AgentCredentials.api_key == x_api_key)
            .first()
        )
        if not cred:
            raise HTTPException(status_code=401, detail="Agent not found")

        role = (cred.role or "user").lower()
        if role not in ("user", "resolver"):
            logger.warning("Unknown role '%s' for %s, defaulting to user", role, cred.agent_id)
            role = "user"

        return AuthContext(agent_id=cred.agent_id, role=role, api_key=x_api_key)
    finally:
        db.close()


def enforce_agent_scope(requested_agent_id: str, auth: AuthContext) -> None:
    """
    Ensure that non-resolver callers can only access their own agent data.
    """
    if auth.role != "resolver" and requested_agent_id != auth.agent_id:
        raise HTTPException(
            status_code=403,
            detail="Access to other agents' data is forbidden for this role",
        )


def require_resolver(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
    """Dependency that rejects any non-resolver caller."""
    if auth.role != "resolver":
        raise HTTPException(status_code=403, detail="Resolver role required")
    return auth
