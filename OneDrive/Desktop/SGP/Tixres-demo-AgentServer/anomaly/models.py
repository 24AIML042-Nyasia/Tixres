from sqlalchemy import Column, String, Index
from server_db.connection import Base

class AnomalyState(Base):
    __tablename__ = 'anomaly_state'
    
    table_name = Column(String, nullable=False, primary_key=True)
    detector = Column(String, nullable=False, primary_key=True)
    agent_id = Column(String, nullable=False, primary_key=True)
    metric_name = Column(String, nullable=False, primary_key=True)
    last_bucket = Column(String, nullable=False)
    
    __table_args__ = (
        Index('idx_anomaly_lookup', 'table_name', 'detector', 'agent_id', 'metric_name'),
    )