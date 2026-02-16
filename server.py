from fastapi import Depends, Query
from typing import Optional, Literal
from datetime import datetime
import asyncio

from server_db.rollups import  retention_policy
from server_utils.fastapi import app
from server_utils.logger import get_logger
from server_utils.models import (
    AgentRegisterRequest, AgentRegisterResponse,
    AgentLoginRequest, AgentLoginResponse,
    PingRequest, MetricBatchRequest, AgentInfo
)
from server_auth.hmac import verify_auth

from server_routes.agent_routes import register_agent, login_agent, ping_agent
from server_routes.metrics_routes import submit_metrics
from server_routes.ui_routes import (
    get_agents, get_agent_details, 
    get_metrics_summary, get_metrics
)

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

@app.get("/api/ui/agents", response_model=list[AgentInfo])
async def get_agents_endpoint(active_only: bool = Query(False)):
    return await get_agents(active_only)

@app.get("/api/ui/agent/{agent_id}")
async def get_agent_details_endpoint(agent_id: str):
    return await get_agent_details(agent_id)

@app.get("/api/ui/metrics/summary")
async def get_metrics_summary_endpoint():
    return await get_metrics_summary()

@app.get("/api/metrics/{metric_type}")
async def get_metrics_endpoint(
    metric_type: Literal["numeric", "json"],
    agent_id: Optional[str] = None,
    metric_name: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = Query(100, le=1000)
):
    return await get_metrics(metric_type, agent_id, metric_name, start_time, end_time, limit)


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