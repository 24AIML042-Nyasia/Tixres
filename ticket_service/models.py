from sqlalchemy import Column, String, Integer, TIMESTAMP, Text, text
from datetime import datetime
from server_db.connection import Base

class Ticket(Base):
    __tablename__ = 'tickets'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String, nullable=False)
    metric_name = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    status = Column(String, default='OPEN')
    detectors = Column(Text)          # JSON array e.g. ["detector_a", "detector_b"]
    meta = Column(Text)
    message = Column(Text)
    occurrence_count = Column(Integer, default=1, nullable=False)
    first_occurred_at = Column(TIMESTAMP, default=datetime.now, server_default=text('CURRENT_TIMESTAMP'))
    last_occurred_at = Column(TIMESTAMP, default=datetime.now, server_default=text('CURRENT_TIMESTAMP'))
    created_at = Column(TIMESTAMP, default=datetime.now, server_default=text('CURRENT_TIMESTAMP'))