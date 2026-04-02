import json
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from server_auth.hmac import verify_auth
from server_db.connection import get_db
from server_db.models import Agent, Purpose
from server_db.purpose import create_purpose
from SLAs.templates import DEFAULT_TEMPLATE
from server_routes import rollup_routes


router = APIRouter(prefix="/api/downstream", tags=["Downstream"])


class AgentDetail(BaseModel):
    agent_id: str
    agent_version: str
    hostname: str
    os: str
    fingerprint: Optional[str]
    created_at: str
    updated_at: str
    heartbeat: Optional[str]
    purpose: Optional[str]
    template: Optional[str]


class AgentListResponse(BaseModel):
    count: int
    agents: List[AgentDetail]


class PurposeResponse(BaseModel):
    id: int
    purpose: str
    template: str
    agent_count: int


class PurposeListResponse(BaseModel):
    count: int
    items: List[PurposeResponse]


class PurposeUpsertRequest(BaseModel):
    purpose: str
    template: Optional[Any] = None


def _serialize_template(template_value) -> str:
    if template_value is None:
        return DEFAULT_TEMPLATE
    if isinstance(template_value, str):
        return template_value
    return json.dumps(template_value)


def _serialize_agent(agent: Agent) -> AgentDetail:
    template = _serialize_template(agent.effective_template)
    return AgentDetail(
        agent_id=agent.agent_id,
        agent_version=agent.agent_version,
        hostname=agent.hostname,
        os=agent.os,
        fingerprint=agent.fingerprint,
        created_at=str(agent.created_at),
        updated_at=str(agent.updated_at),
        heartbeat=str(agent.heartbeat) if agent.heartbeat else None,
        purpose=agent.purpose.purpose if agent.purpose else None,
        template=template,
    )


def _serialize_purpose(purpose: Purpose, db: Session) -> PurposeResponse:
    template = _serialize_template(purpose.template)
    agent_count = db.query(Agent).filter(Agent.purpose_id == purpose.id).count()
    return PurposeResponse(
        id=purpose.id,
        purpose=purpose.purpose,
        template=template,
        agent_count=agent_count,
    )


@router.get("/agents", response_model=AgentListResponse)
def list_agents(
    _: str = Depends(verify_auth),
    db: Session = Depends(get_db),
):
    agents = db.query(Agent).order_by(Agent.created_at.asc()).all()
    return {"count": len(agents), "agents": [_serialize_agent(agent) for agent in agents]}


@router.get("/agents/{agent_id}", response_model=AgentDetail)
def get_agent_detail(
    agent_id: str,
    _: str = Depends(verify_auth),
    db: Session = Depends(get_db),
):
    agent = db.query(Agent).filter(Agent.agent_id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _serialize_agent(agent)


@router.get("/purposes", response_model=PurposeListResponse)
def list_purposes(
    _: str = Depends(verify_auth),
    db: Session = Depends(get_db),
):
    purposes = db.query(Purpose).order_by(Purpose.purpose.asc()).all()
    return {
        "count": len(purposes),
        "items": [_serialize_purpose(purpose, db) for purpose in purposes],
    }


@router.put("/purposes", response_model=PurposeResponse)
def upsert_purpose(
    payload: PurposeUpsertRequest,
    _: str = Depends(verify_auth),
    db: Session = Depends(get_db),
):
    purpose_row = create_purpose(payload.purpose, payload.template, db=db)
    return _serialize_purpose(purpose_row, db)


@router.get("/rollups/{agent_id}")
def downstream_rollups(
    agent_id: str,
    measurement: str = "1m",
    metric_name: Optional[str] = None,
    start_minutes: int = 240,
    _: str = Depends(verify_auth),
    db: Session = Depends(get_db),
):
    """
    Alias to the core rollups endpoint so upstream/downstream servers can consume
    rollup data even if they do not mount the original router.
    """
    return rollup_routes.get_rollup_series(
        agent_id=agent_id,
        measurement=measurement,
        metric_name=metric_name,
        start_minutes=start_minutes,
        db=db,
    )
