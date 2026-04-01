from datetime import datetime
from fastapi import Depends, FastAPI, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from server_auth.hmac import verify_auth
from server_auth.resolver import (
    ensure_default_resolver_credentials,
    ensure_role_column_exists,
)
from server_db.connection import get_db, SessionLocal, Base, engine
from server_db.models import Agent
from server_db.rollups import retention_policy
from server_routes.agent_routes import login_agent, ping_agent, register_agent
from server_routes.alert_routes import router as alert_router
from server_routes.guidance_routes import router as guidance_router
from server_routes.metrics_routes import submit_metrics
from server_routes.rollup_routes import router as rollup_router
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
from ticket_service.ticketService import TicketService


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


@app.get("/api/tickets/{agent_id}/latest")
def get_latest_tickets_endpoint(
    agent_id: str,
    limit: int = Query(default=5, ge=1, le=100),
):
    db = SessionLocal()
    try:
        result = TicketService.get_tickets(db, agent_id, limit)
        return {
            "agent_id": agent_id,
            "count": len(result),
            "tickets": result,
        }
    except Exception as e:
        logger.error(f"Failed to fetch tickets for agent {agent_id}: {e}")
        raise
    finally:
        db.close()


@app.get("/api/user/{agent_id}")
def get_user_snapshot(
    agent_id: str,
):
    """
    UI-friendly bundle for a regular user.
    Returns metrics dashboard + latest tickets for the given agent.
    """
    db = SessionLocal()
    try:
        dashboard = build_dashboard_payload(db, agent_id)
    finally:
        db.close()

    db = SessionLocal()
    try:
        tickets = TicketService.get_tickets(db, agent_id, limit=10)
    finally:
        db.close()

    return {
        "agent_id": agent_id,
        "role": "user",
        "dashboard": dashboard,
        "tickets": tickets,
        "rollups": [],
        "alerts": [],  # Explicitly omitted for user view
    }


@app.get("/api/resolver/{agent_id}")
def get_resolver_snapshot(
    agent_id: str,
):
    """
    UI-friendly bundle for resolver role.
    Includes alerts in addition to dashboard and tickets.
    """
    # Resolver can read any agent id; no scope check required beyond role.
    db = SessionLocal()
    try:
        dashboard = build_dashboard_payload(db, agent_id)
    finally:
        db.close()

    db = SessionLocal()
    try:
        tickets = TicketService.get_tickets(db, agent_id, limit=10)
    finally:
        db.close()

    # Alerts filtered for the requested agent_id
    alert_db = SessionLocal()
    try:
        from alert_service.models import Alert  # local import to avoid cycle

        alerts = (
            alert_db.query(Alert)
            .filter(Alert.agent_ids.contains(agent_id))
            .order_by(Alert.last_seen_at.desc())
            .all()
        )
        alerts_payload = jsonable_encoder(alerts)
    finally:
        alert_db.close()

    return {
        "agent_id": agent_id,
        "role": "resolver",
        "dashboard": dashboard,
        "tickets": tickets,
        "rollups": [],
        "alerts": alerts_payload,
    }


@app.get("/api/resolver/agents")
def list_agents_for_resolver(
    db: Session = Depends(get_db),
):
    agent_rows = db.query(Agent.agent_id).order_by(Agent.created_at.asc()).all()
    ids = [row[0] for row in agent_rows]
    return {"count": len(ids), "agents": ids}


app.include_router(alert_router)
app.include_router(guidance_router)
app.include_router(rollup_router)


shared_sqlite_conn = None


@app.on_event("startup")
async def startup_event():
    # Ensure tables exist for in-memory sqlite used in tests.
    # Import all ORM models so they are registered on Base.metadata.
    import server_db.models  # noqa: F401
    import guidance.models  # noqa: F401
    import alert_service.models  # noqa: F401
    import ticket_service.models  # noqa: F401
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


@app.get("/demo/api-test", response_class=HTMLResponse)
async def api_test_page():
    """
    Lightweight HTML page to call core APIs (dashboard, user, resolver, tickets, rollups).
    Provide agent_id, api_key, secret_key; the page computes the HMAC signature client-side.
    """
    html = """
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8" />
        <title>API Smoke Test</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            label { display: block; margin-top: 8px; }
            input, select { width: 320px; padding: 4px; }
            button { margin-top: 10px; padding: 6px 12px; }
            pre { background: #111; color: #0f0; padding: 10px; white-space: pre-wrap; }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 12px; }
            .card { border: 1px solid #ccc; padding: 10px; border-radius: 6px; }
        </style>
    </head>
    <body>
        <h2>API Smoke Test</h2>
        <p>Fill the credentials, then click "Call All". Uses HMAC headers (x-api-key, x-signature, x-message).</p>
        <label>Base URL <input id="baseUrl" value="" placeholder="defaults to current origin"></label>
        <label>Agent ID <input id="agentId" value="agent_demo_web"></label>
        <label>API Key <input id="apiKey" value=""></label>
        <label>Secret Key <input id="secretKey" value=""></label>
        <label>Message (any text) <input id="message" value=""></label>
        <label>Rollup measurement
            <select id="measurement">
                <option value="1m">1m</option>
                <option value="10m">10m</option>
                <option value="1h">1h</option>
            </select>
        </label>
        <label>Start minutes (lookback) <input id="startMinutes" type="number" min="1" max="4320" value="240"></label>
        <button onclick="callAll()">Call All</button>

        <div class="grid">
            <div class="card"><h4>/api/dashboard</h4><pre id="dashboard"></pre></div>
            <div class="card"><h4>/api/user</h4><pre id="user"></pre></div>
            <div class="card"><h4>/api/resolver</h4><pre id="resolver"></pre></div>
            <div class="card"><h4>/api/tickets</h4><pre id="tickets"></pre></div>
            <div class="card"><h4>/api/rollups</h4><pre id="rollups"></pre></div>
        </div>

        <script>
        async function sign(apiKey, secretKey, message) {
            const enc = new TextEncoder();
            const key = await crypto.subtle.importKey("raw", enc.encode(secretKey), {name:"HMAC", hash:"SHA-256"}, false, ["sign"]);
            const sigBuf = await crypto.subtle.sign("HMAC", key, enc.encode(`${apiKey}:${message}`));
            return Array.from(new Uint8Array(sigBuf)).map(b => b.toString(16).padStart(2, "0")).join("");
        }

        async function fetchEndpoint(path, targetId) {
            const base = document.getElementById("baseUrl").value || window.location.origin;
            const agentId = document.getElementById("agentId").value;
            const apiKey = document.getElementById("apiKey").value;
            const secretKey = document.getElementById("secretKey").value;
            const messageInput = document.getElementById("message").value || new Date().toISOString();
            const signature = await sign(apiKey, secretKey, messageInput);
            const url = base + path.replace("{agentId}", agentId);

            const res = await fetch(url, {
                headers: {
                    "x-api-key": apiKey,
                    "x-message": messageInput,
                    "x-signature": signature
                }
            });
            const text = await res.text();
            document.getElementById(targetId).textContent = res.status + " " + res.statusText + "\\n" + text;
        }

        async function callAll() {
            const agentId = document.getElementById("agentId").value;
            const measurement = document.getElementById("measurement").value;
            const startMinutes = document.getElementById("startMinutes").value || 240;
            fetchEndpoint(`/api/dashboard/${agentId}`, "dashboard");
            fetchEndpoint(`/api/user/${agentId}`, "user");
            fetchEndpoint(`/api/resolver/${agentId}`, "resolver");
            fetchEndpoint(`/api/tickets/${agentId}/latest`, "tickets");
            fetchEndpoint(`/api/rollups/${agentId}?measurement=${measurement}&start_minutes=${startMinutes}`, "rollups");
        }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)
