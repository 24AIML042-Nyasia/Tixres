from sqlalchemy import Column, String, Integer, TIMESTAMP, Text,  text
from datetime import datetime
from server_db.connection import Base

class Ticket(Base):
    __tablename__ = 'tickets'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String, nullable=False)
    metric_name = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    status = Column(String, default='OPEN')
    anomaly_type = Column(String, nullable=False)
    meta = Column(Text)
    message = Column(Text)
    created_at = Column(TIMESTAMP, default=datetime.now, server_default=text('CURRENT_TIMESTAMP'))