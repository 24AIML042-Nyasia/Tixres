from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Literal
import sqlite3
from datetime import datetime

app = FastAPI(title="System Metrics API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database configuration
DATABASE_PATH = "app.db" 

class MetricRequest(BaseModel):
    type: Literal["numeric", "json"]
    metrics: List[str]  # List of metric names, use ["all"] to get all metrics
    limit: Optional[int] = 100  # Limit number of records returned
    start_time: Optional[str] = None  # ISO format datetime
    end_time: Optional[str] = None  # ISO format datetime

class MetricResponse(BaseModel):
    success: bool
    data: List[dict]
    count: int
    metric_type: str

def get_db_connection():
    """Create database connection"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.post("/api/metrics", response_model=MetricResponse)
async def fetch_metrics(request: MetricRequest):
    """
    Fetch metrics from either metric_numeric or metric_json table
    
    Parameters:
    - type: "numeric" or "json" to specify table
    - metrics: List of metric names or ["all"] for all metrics
    - limit: Maximum number of records to return (default: 100)
    - start_time: Filter metrics after this timestamp (ISO format)
    - end_time: Filter metrics before this timestamp (ISO format)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Determine table name
        table_name = "metric_numeric" if request.type == "numeric" else "metric_json"
        
        # Build query
        query = f"SELECT * FROM {table_name} WHERE 1=1"
        params = []
        
        # Filter by metric names
        if "all" not in request.metrics:
            placeholders = ','.join(['?' for _ in request.metrics])
            query += f" AND metric_name IN ({placeholders})"
            params.extend(request.metrics)
        
        # Filter by time range
        if request.start_time:
            query += " AND timestamp >= ?"
            params.append(request.start_time)
        
        if request.end_time:
            query += " AND timestamp <= ?"
            params.append(request.end_time)
        
        # Order by timestamp descending and apply limit
        query += f" ORDER BY timestamp DESC LIMIT ?"
        params.append(request.limit)
        
        # Execute query
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        # Convert to list of dictionaries
        data = [dict(row) for row in rows]
        
        conn.close()
        
        return MetricResponse(
            success=True,
            data=data,
            count=len(data),
            metric_type=request.type
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/metrics/available")
async def get_available_metrics():
    """
    Get list of available metrics from both tables
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get unique metric names from numeric table
        cursor.execute("SELECT DISTINCT metric_name FROM metric_numeric ORDER BY metric_name")
        numeric_metrics = [row[0] for row in cursor.fetchall()]
        
        # Get unique metric names from json table
        cursor.execute("SELECT DISTINCT metric_name FROM metric_json ORDER BY metric_name")
        json_metrics = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        
        return {
            "success": True,
            "numeric_metrics": numeric_metrics,
            "json_metrics": json_metrics
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/metrics/latest")
async def get_latest_metrics(metric_type: Literal["numeric", "json"] = "numeric"):
    """
    Get the latest value for each unique metric
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        table_name = "metric_numeric" if metric_type == "numeric" else "metric_json"
        
        query = f"""
            SELECT m1.*
            FROM {table_name} m1
            INNER JOIN (
                SELECT metric_name, MAX(timestamp) as max_timestamp
                FROM {table_name}
                GROUP BY metric_name
            ) m2 ON m1.metric_name = m2.metric_name AND m1.timestamp = m2.max_timestamp
            ORDER BY m1.metric_name
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        data = [dict(row) for row in rows]
        
        conn.close()
        
        return {
            "success": True,
            "data": data,
            "count": len(data),
            "metric_type": metric_type
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    return {
        "message": "System Metrics API",
        "endpoints": {
            "POST /api/metrics": "Fetch metrics with filters",
            "GET /api/metrics/available": "Get available metric names",
            "GET /api/metrics/latest": "Get latest values for all metrics"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)