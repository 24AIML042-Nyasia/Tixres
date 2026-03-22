from fastapi import Depends, Query
from typing import Optional, Literal
from datetime import datetime
from sqlalchemy.orm import Session

from server_db.rollups import  retention_policy
from server_db.connection import get_db

from server_utils.fastapi import app
from server_utils.logger import get_logger
from server_utils.models import (
    AgentRegisterRequest, AgentRegisterResponse,
    AgentLoginRequest, AgentLoginResponse,
    PingRequest, MetricBatchRequest
)
from server_auth.hmac import verify_auth

from ticket_service.ticketService import TicketService

from server_routes.agent_routes import register_agent, login_agent, ping_agent, run_resolver
from server_routes.metrics_routes import submit_metrics

from server_routes.ui_dashboard_routes import build_dashboard_payload

logger = get_logger()

@app.post("/api/agent/register", response_model=AgentRegisterResponse)
async def register_agent_endpoint(request: AgentRegisterRequest):
    return await register_agent(request)

@app.post("/api/agent/login", response_model=AgentLoginResponse)
async def login_agent_endpoint(request: AgentLoginRequest, agent_id: str = Depends(verify_auth)):
    return await login_agent(request, agent_id)

@app.post("/api/agent/ping")
async def ping_agent_endpoint(request: PingRequest, agent_id: str = Depends(verify_auth)):
    return await ping_agent(request, agent_id)

@app.post("/api/metrics/submit")
async def submit_metrics_endpoint(request: MetricBatchRequest, agent_id: str = Depends(verify_auth)):
    return await submit_metrics(request, agent_id)

@app.get("/api/dashboard/{agent_id}")
def get_dashboard(agent_id: str, db: Session = Depends(get_db)):
    return build_dashboard_payload(db, agent_id)

@app.get("/api/tickets/{agent_id}/latest")
def get_latest_tickets_endpoint(
    agent_id: str,
    limit: int = Query(default=5, ge=1, le=100),
):
    try:
        result = TicketService.get_Tickets(agent_id,limit)
    
        return {
            "agent_id": agent_id,
            "count": len(result),
            "tickets": result,
        }
    except Exception as e:
        logger.error(f"Failed to fetch tickets for agent {agent_id}: {e}")
        raise



@app.on_event("startup")
async def startup_event():
    retention_policy()
    
    logger.info("Server started successfully")

@app.get("/")
async def root():
    return {
        "service": "IT Metrics Storage System",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)