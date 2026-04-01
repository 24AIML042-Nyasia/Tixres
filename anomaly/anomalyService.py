from sqlalchemy import text
from server_db.connection import SessionLocal
from anomaly.models import AnomalyState

class AnomalyService:    
    @staticmethod
    def insertOrReplace(table, detector, agent_id, metric_name, latest_bucket):
        db = SessionLocal()
        try:
            existing = db.query(AnomalyState).filter(
                AnomalyState.table_name == table,
                AnomalyState.detector == detector,
                AnomalyState.agent_id == agent_id,
                AnomalyState.metric_name == metric_name
            ).first()
            
            if existing:
                existing.last_bucket = latest_bucket
            else:
                new_state = AnomalyState(
                    table_name=table,
                    detector=detector,
                    agent_id=agent_id,
                    metric_name=metric_name,
                    last_bucket=latest_bucket
                )
                db.add(new_state)
            
            db.commit()
        finally:
            db.close()
    
    @staticmethod
    def selectOne(table, detector, agent_id, metric_name):
        db = SessionLocal()
        try:
            state = db.query(AnomalyState).filter(
                AnomalyState.table_name == table,
                AnomalyState.detector == detector,
                AnomalyState.agent_id == agent_id,
                AnomalyState.metric_name == metric_name
            ).first()
            
            if state:
                return (state.last_bucket,)
            return None
        finally:
            db.close()