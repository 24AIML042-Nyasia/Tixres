from datetime import datetime
from fastapi import Depends, FastAPI, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from server_auth.hmac import verify_auth
from server_auth.resolver import (
    ensure_default_resolver_credentials,
    ensure_role_column_exists,
)
from server_db.connection import get_db, SessionLocal, Base, engine
from server_db.models import Agent
from server_db.purpose import backfill_agent_purposes, create_purpose
from server_db.rollups import retention_policy
from server_routes.downstream_routes import router as downstream_router
from server_routes.agent_routes import login_agent, ping_agent, register_agent
from server_routes.metrics_routes import submit_metrics
from server_routes.rollup_routes import router as rollup_router
from server_routes.server_routes import router as server_router
from server_routes.ui_dashboard_routes import build_dashboard_payload
from server_utils.logger import get_logger
from server_utils.models import (
    AgentLoginRequest,
    AgentLoginResponse,
    AgentRegisterRequest,
    AgentRegisterResponse,
    MetricBatchRequest,
    PingRequest,
)


app = FastAPI(title="IT Metrics Storage System", version="1.0.0")

# CORS middleware for UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = get_logger()


@app.post("/api/agent/register", response_model=AgentRegisterResponse)
async def register_agent_endpoint(request: AgentRegisterRequest):
    return await register_agent(request)


@app.post("/api/agent/login", response_model=AgentLoginResponse)
async def login_agent_endpoint(
    request: AgentLoginRequest, agent_id: str = Depends(verify_auth)
):
    return await login_agent(request, agent_id)


@app.post("/api/agent/ping")
async def ping_agent_endpoint(
    request: PingRequest, agent_id: str = Depends(verify_auth)
):
    return await ping_agent(request, agent_id)


@app.post("/api/metrics/submit")
async def submit_metrics_endpoint(
    request: MetricBatchRequest, agent_id: str = Depends(verify_auth)
):
    return await submit_metrics(request, agent_id)


@app.get("/api/dashboard/{agent_id}")
def get_dashboard(
    agent_id: str,
    db: Session = Depends(get_db),
):
    return build_dashboard_payload(db, agent_id)






@app.get("/api/resolver/agents")
def list_agents_for_resolver(
    db: Session = Depends(get_db),
):
    agent_rows = db.query(Agent.agent_id).order_by(Agent.created_at.asc()).all()
    ids = [row[0] for row in agent_rows]
    return {"count": len(ids), "agents": ids}

app.include_router(rollup_router)
app.include_router(downstream_router)
app.include_router(server_router)


shared_sqlite_conn = None


@app.on_event("startup")
async def startup_event():
    # Ensure tables exist for in-memory sqlite used in tests.
    # Import all ORM models so they are registered on Base.metadata.
    import server_db.models  # noqa: F401
    import anomaly.models  # noqa: F401

    global shared_sqlite_conn
    bind = engine
    # If running against in-memory SQLite, force a single shared connection so tables persist.
    if bind.dialect.name == "sqlite" and (bind.url.database in (None, "", ":memory:")):
        if shared_sqlite_conn is None:
            shared_sqlite_conn = bind.connect()
            SessionLocal.configure(bind=shared_sqlite_conn)
        bind_to_use = shared_sqlite_conn
    else:
        bind_to_use = bind

    db = SessionLocal()
    try:
        Base.metadata.create_all(bind=bind_to_use)
    finally:
        db.close()

    # Backfill schema + seed a demo resolver credential for RBAC flows.
    ensure_role_column_exists(bind_to_use)
    ensure_default_resolver_credentials()
    # Ensure default purpose exists and agents without a purpose are assigned.
    db_session = SessionLocal()
    try:
        create_purpose("general", db=db_session)
        backfill_agent_purposes(db=db_session)
    finally:
        db_session.close()

    retention_policy()

    logger.info("Server started successfully")


@app.get("/")
async def root():
    return {
        "service": "IT Metrics Storage System",
        "version": "1.0.0",
        "status": "running",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
