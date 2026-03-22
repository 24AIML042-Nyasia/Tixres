from fastapi import HTTPException, Depends
import secrets
import json
from datetime import datetime

from server_auth.hmac import generate_credentials, verify_auth
from server_db.connection import SessionLocal
from server_db.models import AgentCredentials, Agent
from server_utils.models import (
    AgentRegisterRequest, AgentRegisterResponse,
    AgentLoginRequest, AgentLoginResponse,
    PingRequest
)
from server_utils.logger import get_logger
from agent_adapter.templates import get_template

logger = get_logger()

tempCache = {}

async def register_agent(request: AgentRegisterRequest):
    try:
        api_key, secret_key = generate_credentials()
        agent_id = f"agent_{secrets.token_urlsafe(16)}"
        
        db = SessionLocal()
        try:
            credentials = AgentCredentials(
                agent_id=agent_id,
                api_key=api_key,
                secret_key=secret_key
            )
            db.add(credentials)
            
            template_json = get_template()
            agent = Agent(
                agent_id=agent_id,
                agent_version=request.agent_version,
                hostname=request.hostname,
                os=request.os,
                fingerprint=request.fingerprint,
                template=template_json,
                heartbeat=datetime.now()
            )
            db.add(agent)
            
            db.commit()
            
            logger.info(f"Agent registered: {agent_id} (hostname: {request.hostname})")
            
            return AgentRegisterResponse(
                agent_id=agent_id,
                api_key=api_key,
                secret_key=secret_key,
                template = template_json,
                message="Agent registered successfully"
            )
        finally:
            db.close()
        
    except Exception as e:
        logger.error(f"Error registering agent: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

async def login_agent(request: AgentLoginRequest, agent_id: str = Depends(verify_auth)):
    try:
        db = SessionLocal()
        try:
            agent = db.query(Agent).filter(Agent.agent_id == agent_id).first()
            
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")
            
            agent.heartbeat = datetime.now()
            agent.updated_at = datetime.now()
            db.commit()
            
            agent_info = {
                "agent_id": agent.agent_id,
                "agent_version": agent.agent_version,
                "hostname": agent.hostname,
                "os": agent.os,
                "created_at": str(agent.created_at),
                "heartbeat": str(agent.heartbeat),
                "template": agent.template
            }
            
            logger.info(f"Agent logged in: {agent_id}")
            
            await run_resolver(agent_id)
            return AgentLoginResponse(
                message="Login successful",
                agent_info=agent_info
            )
        finally:
            db.close()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during login: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

async def ping_agent(request: PingRequest, agent_id: str = Depends(verify_auth)):
    try:
        db = SessionLocal()
        try:
            agent = db.query(Agent).filter(Agent.agent_id == agent_id).first()
            if agent:
                agent.heartbeat = datetime.now()
                db.commit()
                          
            logger.debug(f"Heartbeat updated for agent: {agent_id}")
            
            return {"message": "Heartbeat updated",
                    "timestamp": datetime.now().isoformat(),
                    "template" : agent.template,
                    "action" : tempCache[agent_id]
                    }
        finally:
            tempCache[agent_id] = False
            db.close()
        
    except Exception as e:
        logger.error(f"Error updating heartbeat: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ping failed: {str(e)}")

async def run_resolver(agent_id: str = Depends(verify_auth)):
    tempCache.update({agent_id : True})
