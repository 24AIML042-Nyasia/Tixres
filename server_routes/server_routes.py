import secrets
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from server_auth.hmac import generate_credentials, verify_auth
from server_db.connection import SessionLocal
from server_db.models import AgentCredentials
from server_utils.logger import get_logger


logger = get_logger()
router = APIRouter(prefix="/api/server", tags=["Server"])


class ServerRegisterResponse(BaseModel):
    server_id: str
    api_key: str
    secret_key: str
    role: str
    message: str


class ServerLoginRequest(BaseModel):
    server_id: str


class ServerLoginResponse(BaseModel):
    message: str
    server_id: str
    role: str
    authenticated_at: str


class ServerPingRequest(BaseModel):
    server_id: str


class ServerPingResponse(BaseModel):
    message: str
    server_id: str
    timestamp: str


def _require_server(agent_id: str = Depends(verify_auth)) -> AgentCredentials:
    db = SessionLocal()
    try:
        cred = db.query(AgentCredentials).filter(AgentCredentials.agent_id == agent_id).first()
        if not cred or cred.role != "server":
            raise HTTPException(status_code=403, detail="Server credential required")
        return cred
    finally:
        db.close()


@router.post("/register", response_model=ServerRegisterResponse)
def register_server():
    """
    Issue a dedicated HMAC credential for a downstream/upstream server.
    Uses role='server' to keep it separate from agents/resolvers.
    """
    try:
        api_key, secret_key = generate_credentials()
        server_id = f"server_{secrets.token_urlsafe(12)}"

        db = SessionLocal()
        try:
            cred = AgentCredentials(
                agent_id=server_id,
                api_key=api_key,
                secret_key=secret_key,
                role="server",
            )
            db.add(cred)
            db.commit()
            logger.info("Server registered: %s", server_id)
            return ServerRegisterResponse(
                server_id=server_id,
                api_key=api_key,
                secret_key=secret_key,
                role="server",
                message="Server registered successfully",
            )
        finally:
            db.close()
    except Exception as e:
        logger.error("Error registering server: %s", e)
        raise HTTPException(status_code=500, detail="Server registration failed")


@router.post("/login", response_model=ServerLoginResponse)
def server_login(payload: ServerLoginRequest, cred: AgentCredentials = Depends(_require_server)):
    if payload.server_id != cred.agent_id:
        raise HTTPException(status_code=403, detail="server_id mismatch")
    now = datetime.utcnow().isoformat()
    logger.info("Server login: %s", cred.agent_id)
    return ServerLoginResponse(
        message="Server login successful",
        server_id=cred.agent_id,
        role=cred.role,
        authenticated_at=now,
    )


@router.post("/ping", response_model=ServerPingResponse)
def server_ping(payload: ServerPingRequest, cred: AgentCredentials = Depends(_require_server)):
    if payload.server_id != cred.agent_id:
        raise HTTPException(status_code=403, detail="server_id mismatch")
    ts = datetime.utcnow().isoformat()
    logger.debug("Server ping: %s", cred.agent_id)
    return ServerPingResponse(
        message="pong",
        server_id=cred.agent_id,
        timestamp=ts,
    )
