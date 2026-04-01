from fastapi import HTTPException, Depends
import json
from datetime import datetime

from server_auth.hmac import verify_auth
from server_db.connection import SessionLocal
from server_db.models import MetricNumeric, MetricJson, Agent
from server_utils.models import MetricBatchRequest
from server_utils.logger import get_logger

logger = get_logger()

async def submit_metrics(request: MetricBatchRequest, agent_id: str = Depends(verify_auth)):
    try:
        if request.agent_id != agent_id:
            raise HTTPException(status_code=403, detail="Agent ID mismatch")
        
        db = SessionLocal()
        try:
            numeric_count = 0
            json_count = 0
            
            for metric in request.metrics:
                if isinstance(metric.value, (int, float)):
                    numeric_metric = MetricNumeric(
                        agent_id=agent_id,
                        metric_name=metric.metric_name,
                        value=float(metric.value),
                        timestamp=datetime.fromisoformat(metric.timestamp.replace('Z', '+00:00'))
                    )
                    db.add(numeric_metric)
                    numeric_count += 1
                else:
                    value_str = json.dumps(metric.value) if not isinstance(metric.value, str) else metric.value
                    json_metric = MetricJson(
                        agent_id=agent_id,
                        metric_name=metric.metric_name,
                        value=value_str,
                        timestamp=datetime.fromisoformat(metric.timestamp.replace('Z', '+00:00'))
                    )
                    db.add(json_metric)
                    json_count += 1
            
            agent = db.query(Agent).filter(Agent.agent_id == agent_id).first()
            if agent:
                agent.heartbeat = datetime.now()
            
            db.commit()
            
            logger.info(f"Metrics received from {agent_id}: {numeric_count} numeric, {json_count} JSON")
            
            return {
                "message": "Metrics stored successfully",
                "count": len(request.metrics),
                "numeric": numeric_count,
                "json": json_count
            }
        finally:
            db.close()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error storing metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to store metrics: {str(e)}")
