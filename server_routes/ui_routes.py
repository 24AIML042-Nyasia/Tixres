from fastapi import HTTPException, Query
from typing import Optional, List, Literal
from sqlalchemy import text, func
import json

from server_db.connection import SessionLocal
from server_db.models import Agent, MetricNumeric, MetricJson
from server_utils.models import AgentInfo
from server_utils.logger import get_logger

logger = get_logger()

async def get_agents(active_only: bool = Query(False)):
    try:
        db = SessionLocal()
        try:
            query = db.query(Agent)
            
            if active_only:
                query = query.filter(
                    Agent.heartbeat >= text("NOW() - INTERVAL '5 minutes'")
                )
            
            agents = query.order_by(Agent.created_at.desc()).all()
            
            return [
                AgentInfo(
                    agent_id=agent.agent_id,
                    agent_version=agent.agent_version,
                    hostname=agent.hostname,
                    os=agent.os,
                    created_at=str(agent.created_at),
                    updated_at=str(agent.updated_at),
                    heartbeat=str(agent.heartbeat) if agent.heartbeat else None,
                    fingerprint=agent.fingerprint,
                    template=agent.template
                )
                for agent in agents
            ]
        finally:
            db.close()
        
    except Exception as e:
        logger.error(f"Error fetching agents: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch agents: {str(e)}")

async def get_agent_details(agent_id: str):
    try:
        db = SessionLocal()
        try:
            agent = db.query(Agent).filter(Agent.agent_id == agent_id).first()
            
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")
            
            numeric_count = db.query(func.count(MetricNumeric.id)).filter(
                MetricNumeric.agent_id == agent_id
            ).scalar()
            
            json_count = db.query(func.count(MetricJson.id)).filter(
                MetricJson.agent_id == agent_id
            ).scalar()
            
            latest_numeric = db.query(MetricNumeric).filter(
                MetricNumeric.agent_id == agent_id
            ).order_by(MetricNumeric.timestamp.desc()).limit(10).all()
            
            latest_json = db.query(MetricJson).filter(
                MetricJson.agent_id == agent_id
            ).order_by(MetricJson.timestamp.desc()).limit(10).all()
            
            return {
                "agent": {
                    "agent_id": agent.agent_id,
                    "agent_version": agent.agent_version,
                    "hostname": agent.hostname,
                    "os": agent.os,
                    "created_at": str(agent.created_at),
                    "updated_at": str(agent.updated_at),
                    "heartbeat": str(agent.heartbeat) if agent.heartbeat else None,
                    "fingerprint": agent.fingerprint,
                    "template": agent.template
                },
                "metrics_count": {
                    "numeric": numeric_count,
                    "json": json_count,
                    "total": numeric_count + json_count
                },
                "latest_metrics": {
                    "numeric": [
                        {
                            "metric_name": m.metric_name,
                            "value": m.value,
                            "timestamp": str(m.timestamp)
                        }
                        for m in latest_numeric
                    ],
                    "json": [
                        {
                            "metric_name": m.metric_name,
                            "value": m.value,
                            "timestamp": str(m.timestamp)
                        }
                        for m in latest_json
                    ]
                }
            }
        finally:
            db.close()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching agent details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch agent details: {str(e)}")

async def get_metrics_summary():
    try:
        db = SessionLocal()
        try:
            total_agents = db.query(func.count(Agent.agent_id)).scalar()
            
            active_agents = db.query(func.count(Agent.agent_id)).filter(
                Agent.heartbeat >= text("NOW() - INTERVAL '5 minutes'")
            ).scalar()
            
            numeric_metrics = db.query(func.count(MetricNumeric.id)).scalar()
            json_metrics = db.query(func.count(MetricJson.id)).scalar()
            
            numeric_last_hour = db.query(func.count(MetricNumeric.id)).filter(
                MetricNumeric.timestamp >= text("NOW() - INTERVAL '1 hour'")
            ).scalar()
            
            json_last_hour = db.query(func.count(MetricJson.id)).filter(
                MetricJson.timestamp >= text("NOW() - INTERVAL '1 hour'")
            ).scalar()
            
            try:
                result = db.execute(text("""
                    SELECT metric_name, COUNT(*) as count
                    FROM (
                        SELECT metric_name FROM metric_numeric
                        UNION ALL
                        SELECT metric_name FROM metric_json
                    ) AS combined
                    GROUP BY metric_name
                    ORDER BY count DESC
                    LIMIT 10
                """))
                top_metrics = [{"metric_name": row[0], "count": row[1]} for row in result]
            except Exception as e:
                logger.error(f"Error fetching top metrics: {str(e)}")
                top_metrics = []
            
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
        finally:
            db.close()
        
    except Exception as e:
        logger.error(f"Error fetching summary: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch summary: {str(e)}")

async def get_metrics(
    metric_type: Literal["numeric", "json"],
    agent_id: Optional[str] = None,
    metric_name: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = Query(100, le=1000)
):
    try:
        if metric_type not in ['numeric', 'json']:
            raise HTTPException(status_code=400, detail="Invalid metric type")
        
        db = SessionLocal()
        try:
            if metric_type == 'numeric':
                query = db.query(MetricNumeric)
                
                if agent_id:
                    query = query.filter(MetricNumeric.agent_id == agent_id)
                if metric_name:
                    query = query.filter(MetricNumeric.metric_name == metric_name)
                if start_time:
                    query = query.filter(MetricNumeric.timestamp >= start_time)
                if end_time:
                    query = query.filter(MetricNumeric.timestamp <= end_time)
                
                results = query.order_by(MetricNumeric.timestamp.desc()).limit(limit).all()
                
                metrics = [
                    {
                        "id": m.id,
                        "agent_id": m.agent_id,
                        "metric_name": m.metric_name,
                        "value": m.value,
                        "timestamp": str(m.timestamp),
                        "received_at": str(m.received_at)
                    }
                    for m in results
                ]
            else:
                query = db.query(MetricJson)
                
                if agent_id:
                    query = query.filter(MetricJson.agent_id == agent_id)
                if metric_name:
                    query = query.filter(MetricJson.metric_name == metric_name)
                if start_time:
                    query = query.filter(MetricJson.timestamp >= start_time)
                if end_time:
                    query = query.filter(MetricJson.timestamp <= end_time)
                
                results = query.order_by(MetricJson.timestamp.desc()).limit(limit).all()
                
                metrics = []
                for m in results:
                    try:
                        value = json.loads(m.value)
                    except:
                        value = m.value
                    
                    metrics.append({
                        "id": m.id,
                        "agent_id": m.agent_id,
                        "metric_name": m.metric_name,
                        "value": value,
                        "timestamp": str(m.timestamp),
                        "received_at": str(m.received_at)
                    })
            
            return {
                "metric_type": metric_type,
                "count": len(metrics),
                "metrics": metrics
            }
        finally:
            db.close()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch metrics: {str(e)}")
