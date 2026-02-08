"""
IT Metrics Storage System - FastAPI Server
Handles agent registration, authentication, and metrics collection
"""
from fastapi import FastAPI, HTTPException, Header, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any , Literal
from datetime import datetime, timedelta
import sqlite3
import hmac
import hashlib
import secrets
import json
import logging
import asyncio
from server_db.models import one_min_roll_up, ten_min_roll_up, one_hour_roll_up, retention_policy


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="IT Metrics Storage System", version="1.0.0")

# CORS middleware for UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database configuration
DB_PATH = "metrics_server.db"

# ============================================================================
# DATABASE SETUP
# ============================================================================

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """Initialize database with all required tables"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Agent credentials table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_credentials (
            agent_id TEXT PRIMARY KEY,
            api_key TEXT UNIQUE NOT NULL,
            secret_key TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    """)
    
    # Agent table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            agent_id TEXT PRIMARY KEY,
            agent_version TEXT NOT NULL,
            hostname TEXT NOT NULL,
            os TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            template TEXT,
            heartbeat TIMESTAMP,
            fingerprint TEXT,
            FOREIGN KEY (agent_id) REFERENCES agent_credentials(agent_id)
        )
    """)
    
    # Numeric metrics table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metric_numeric (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            value REAL NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
        )
    """)
    
    # JSON metrics table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metric_json (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            value TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
        )
    """)
    
    # Create indexes for better query performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_metric_numeric_agent ON metric_numeric(agent_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_metric_numeric_timestamp ON metric_numeric(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_metric_numeric_name ON metric_numeric(metric_name)")
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_metric_json_agent ON metric_json(agent_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_metric_json_timestamp ON metric_json(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_metric_json_name ON metric_json(metric_name)")
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_agents_heartbeat ON agents(heartbeat)")
    
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")

# ============================================================================
# MODELS
# ============================================================================

class AgentRegisterRequest(BaseModel):
    agent_version: str
    hostname: str
    os: str
    fingerprint: str
    template: Optional[Dict[str, Any]] = None

class AgentRegisterResponse(BaseModel):
    agent_id: str
    api_key: str
    secret_key: str
    message: str

class AgentLoginRequest(BaseModel):
    agent_id: str

class AgentLoginResponse(BaseModel):
    message: str
    agent_info: Dict[str, Any]

class PingRequest(BaseModel):
    agent_id: str

class MetricData(BaseModel):
    metric_name: str
    value: Any
    timestamp: str

class MetricBatchRequest(BaseModel):
    agent_id: str
    metrics: List[MetricData]

class AgentInfo(BaseModel):
    agent_id: str
    agent_version: str
    hostname: str
    os: str
    created_at: str
    updated_at: str
    heartbeat: Optional[str]
    fingerprint: str
    template: Optional[str]

# ============================================================================
# HMAC AUTHENTICATION
# ============================================================================

def generate_credentials():
    """Generate API key and secret key for agent"""
    api_key = secrets.token_urlsafe(32)
    secret_key = secrets.token_urlsafe(64)
    return api_key, secret_key

def create_signature(api_key: str, secret_key: str, message: str) -> str:
    """Create HMAC signature"""
    signature = hmac.new(
        secret_key.encode('utf-8'),
        f"{api_key}:{message}".encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature

def verify_signature(api_key: str, message: str, signature: str) -> bool:
    """Verify HMAC signature"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT secret_key, is_active FROM agent_credentials WHERE api_key = ?",
        (api_key,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        logger.warning(f"API key not found: {api_key}")
        return False
    
    if not row['is_active']:
        logger.warning(f"Inactive agent attempted authentication: {api_key}")
        return False
    
    secret_key = row['secret_key']
    expected_signature = create_signature(api_key, secret_key, message)
    
    return hmac.compare_digest(signature, expected_signature)

async def verify_auth(
    x_api_key: str = Header(...),
    x_signature: str = Header(...),
    x_message: str = Header(...)
):
    """Dependency for verifying HMAC authentication"""
    if not verify_signature(x_api_key, x_message, x_signature):
        raise HTTPException(status_code=401, detail="Invalid authentication")
    
    # Get agent_id from api_key
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT agent_id FROM agent_credentials WHERE api_key = ?", (x_api_key,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=401, detail="Agent not found")
    
    return row['agent_id']

# ============================================================================
# AGENT MANAGEMENT ENDPOINTS
# ============================================================================

@app.post("/api/agent/register", response_model=AgentRegisterResponse)
async def register_agent(request: AgentRegisterRequest):
    """Register a new agent and generate credentials"""
    try:
        # Generate credentials
        api_key, secret_key = generate_credentials()
        agent_id = f"agent_{secrets.token_urlsafe(16)}"
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Insert credentials
        cursor.execute(
            """
            INSERT INTO agent_credentials (agent_id, api_key, secret_key)
            VALUES (?, ?, ?)
            """,
            (agent_id, api_key, secret_key)
        )
        
        # Insert agent info
        template_json = json.dumps(request.template) if request.template else None
        cursor.execute(
            """
            INSERT INTO agents (agent_id, agent_version, hostname, os, fingerprint, template, heartbeat)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (agent_id, request.agent_version, request.hostname, request.os, 
             request.fingerprint, template_json)
        )
        
        conn.commit()
        conn.close()
        
        logger.info(f"Agent registered: {agent_id} (hostname: {request.hostname})")
        
        return AgentRegisterResponse(
            agent_id=agent_id,
            api_key=api_key,
            secret_key=secret_key,
            message="Agent registered successfully"
        )
        
    except Exception as e:
        logger.error(f"Error registering agent: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

@app.post("/api/agent/login", response_model=AgentLoginResponse)
async def login_agent(request: AgentLoginRequest, agent_id: str = Depends(verify_auth)):
    """Agent login - verify credentials and return agent info"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Update heartbeat
        cursor.execute(
            "UPDATE agents SET heartbeat = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE agent_id = ?",
            (agent_id,)
        )
        
        # Get agent info
        cursor.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,))
        row = cursor.fetchone()
        
        conn.commit()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        agent_info = {
            "agent_id": row['agent_id'],
            "agent_version": row['agent_version'],
            "hostname": row['hostname'],
            "os": row['os'],
            "created_at": row['created_at'],
            "heartbeat": row['heartbeat']
        }
        
        logger.info(f"Agent logged in: {agent_id}")
        
        return AgentLoginResponse(
            message="Login successful",
            agent_info=agent_info
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during login: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@app.post("/api/agent/ping")
async def ping_agent(request: PingRequest, agent_id: str = Depends(verify_auth)):
    """Update agent heartbeat"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute(
            "UPDATE agents SET heartbeat = CURRENT_TIMESTAMP WHERE agent_id = ?",
            (agent_id,)
        )
        
        conn.commit()
        conn.close()
        
        logger.debug(f"Heartbeat updated for agent: {agent_id}")
        
        return {"message": "Heartbeat updated", "timestamp": datetime.now().isoformat()}
        
    except Exception as e:
        logger.error(f"Error updating heartbeat: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ping failed: {str(e)}")

# ============================================================================
# METRICS ENDPOINTS
# ============================================================================

@app.post("/api/metrics/submit")
async def submit_metrics(request: MetricBatchRequest, agent_id: str = Depends(verify_auth)):
    """Submit batch of metrics from agent"""
    try:
        if request.agent_id != agent_id:
            raise HTTPException(status_code=403, detail="Agent ID mismatch")
        
        conn = get_db()
        cursor = conn.cursor()
        
        numeric_count = 0
        json_count = 0
        
        for metric in request.metrics:
            # Determine if metric is numeric or JSON
            if isinstance(metric.value, (int, float)):
                # Numeric metric
                cursor.execute(
                    """
                    INSERT INTO metric_numeric (agent_id, metric_name, value, timestamp)
                    VALUES (?, ?, ?, ?)
                    """,
                    (agent_id, metric.metric_name, float(metric.value), metric.timestamp)
                )
                numeric_count += 1
            else:
                # JSON metric (convert to string if not already)
                value_str = json.dumps(metric.value) if not isinstance(metric.value, str) else metric.value
                cursor.execute(
                    """
                    INSERT INTO metric_json (agent_id, metric_name, value, timestamp)
                    VALUES (?, ?, ?, ?)
                    """,
                    (agent_id, metric.metric_name, value_str, metric.timestamp)
                )
                json_count += 1
        
        # Update agent heartbeat
        cursor.execute(
            "UPDATE agents SET heartbeat = CURRENT_TIMESTAMP WHERE agent_id = ?",
            (agent_id,)
        )
        
        conn.commit()
        conn.close()
        
        logger.info(f"Metrics received from {agent_id}: {numeric_count} numeric, {json_count} JSON")
        
        return {
            "message": "Metrics stored successfully",
            "count": len(request.metrics),
            "numeric": numeric_count,
            "json": json_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error storing metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to store metrics: {str(e)}")

# ============================================================================
# UI/DASHBOARD ENDPOINTS
# ============================================================================

@app.get("/api/ui/agents", response_model=List[AgentInfo])
async def get_agents(active_only: bool = Query(False)):
    """Get list of all agents for UI"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        query = "SELECT * FROM agents"
        if active_only:
            # Agents active in last 5 minutes
            query += " WHERE heartbeat > datetime('now', '-5 minutes')"
        query += " ORDER BY created_at DESC"
        
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()
        
        agents = []
        for row in rows:
            agents.append(AgentInfo(
                agent_id=row['agent_id'],
                agent_version=row['agent_version'],
                hostname=row['hostname'],
                os=row['os'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                heartbeat=row['heartbeat'],
                fingerprint=row['fingerprint'],
                template=row['template']
            ))
        
        return agents
        
    except Exception as e:
        logger.error(f"Error fetching agents: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch agents: {str(e)}")

@app.get("/api/ui/agent/{agent_id}")
async def get_agent_details(agent_id: str):
    """Get detailed information about a specific agent"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        # Get metric counts
        cursor.execute(
            "SELECT COUNT(*) as count FROM metric_numeric WHERE agent_id = ?",
            (agent_id,)
        )
        numeric_count = cursor.fetchone()['count']
        
        cursor.execute(
            "SELECT COUNT(*) as count FROM metric_json WHERE agent_id = ?",
            (agent_id,)
        )
        json_count = cursor.fetchone()['count']
        
        # Get latest metrics
        cursor.execute(
            """
            SELECT metric_name, value, timestamp
            FROM metric_numeric
            WHERE agent_id = ?
            ORDER BY timestamp DESC
            LIMIT 10
            """,
            (agent_id,)
        )
        latest_numeric = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute(
            """
            SELECT metric_name, value, timestamp
            FROM metric_json
            WHERE agent_id = ?
            ORDER BY timestamp DESC
            LIMIT 10
            """,
            (agent_id,)
        )
        latest_json = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        return {
            "agent": dict(row),
            "metrics_count": {
                "numeric": numeric_count,
                "json": json_count,
                "total": numeric_count + json_count
            },
            "latest_metrics": {
                "numeric": latest_numeric,
                "json": latest_json
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching agent details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch agent details: {str(e)}")

@app.get("/api/ui/metrics/summary")
async def get_metrics_summary():
    """Get overall metrics summary"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Total agents
        cursor.execute("SELECT COUNT(*) as count FROM agents")
        total_agents = cursor.fetchone()['count']
        
        # Active agents (heartbeat in last 5 minutes)
        cursor.execute(
            "SELECT COUNT(*) as count FROM agents WHERE heartbeat > datetime('now', '-5 minutes')"
        )
        active_agents = cursor.fetchone()['count']
        
        # Total metrics
        cursor.execute("SELECT COUNT(*) as count FROM metric_numeric")
        numeric_metrics = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM metric_json")
        json_metrics = cursor.fetchone()['count']
        
        # Metrics in last hour
        cursor.execute(
            "SELECT COUNT(*) as count FROM metric_numeric WHERE timestamp > datetime('now', '-1 hour')"
        )
        numeric_last_hour = cursor.fetchone()['count']
        
        cursor.execute(
            "SELECT COUNT(*) as count FROM metric_json WHERE timestamp > datetime('now', '-1 hour')"
        )
        json_last_hour = cursor.fetchone()['count']
        
        # Top metric names - FIXED QUERY
        # SQLite doesn't require alias for subquery in FROM clause, but adding it doesn't hurt
        try:
            cursor.execute(
                """
                SELECT metric_name, COUNT(*) as count
                FROM (
                    SELECT metric_name FROM metric_numeric
                    UNION ALL
                    SELECT metric_name FROM metric_json
                )
                GROUP BY metric_name
                ORDER BY count DESC
                LIMIT 10
                """
            )
            top_metrics = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error fetching top metrics: {str(e)}")
            # Fallback: get top metrics from each table separately
            top_metrics = []
        
        conn.close()
        
        return {
            "agents": {
                "total": total_agents,
                "active": active_agents,
                "inactive": total_agents - active_agents
            },
            "metrics": {
                "total": numeric_metrics + json_metrics,
                "numeric": numeric_metrics,
                "json": json_metrics,
                "last_hour": numeric_last_hour + json_last_hour
            },
            "top_metrics": top_metrics
        }
        
    except Exception as e:
        logger.error(f"Error fetching summary: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch summary: {str(e)}")


@app.get("/api/metrics/{metric_type}")
async def get_metrics(
    metric_type: Literal["numeric", "json"],
    agent_id: Optional[str] = None,
    metric_name: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = Query(100, le=1000)
):
    """Get metrics with filtering options"""
    try:
        if metric_type not in ['numeric', 'json']:
            raise HTTPException(status_code=400, detail="Invalid metric type")
        
        table = f"metric_{metric_type}"
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Build query
        query = f"SELECT * FROM {table} WHERE 1=1"
        params = []
        
        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id)
        
        if metric_name:
            query += " AND metric_name = ?"
            params.append(metric_name)
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        metrics = [dict(row) for row in rows]
        
        # Parse JSON values if metric_type is json
        if metric_type == 'json':
            for metric in metrics:
                try:
                    metric['value'] = json.loads(metric['value'])
                except:
                    pass  # Keep as string if parse fails
        
        return {
            "metric_type": metric_type,
            "count": len(metrics),
            "metrics": metrics
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch metrics: {str(e)}")


# ============================================================================
# STARTUP
# ============================================================================
async def one_roll_up():
    while True:
        await asyncio.sleep(60)
        await one_min_roll_up()
    
async def ten_roll_up():
    while True:
        await asyncio.sleep(600)
        await ten_min_roll_up()

async def one_h_roll_up():
    while True:
        await asyncio.sleep(60*60)
        await one_hour_roll_up()

@app.on_event("startup")
async def startup_event():

    retention_policy()

    asyncio.create_task(one_roll_up())
    asyncio.create_task(ten_roll_up())
    asyncio.create_task(one_h_roll_up())
    
    logger.info("Server started successfully")

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "IT Metrics Storage System",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)