from sqlalchemy import Column, String, Integer, Float, TIMESTAMP, Text, ForeignKey, Index, JSON, text
from sqlalchemy.orm import relationship
from datetime import datetime
from server_db.connection import Base
from server_db.const import DEFAULT_TEMPLATE

class Purpose(Base):
    __tablename__ = 'purposes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    purpose = Column(String, unique=True, nullable=False, default='general', server_default=text("'general'"))
    template = Column(JSON, default=dict, server_default=text(DEFAULT_TEMPLATE))
    created_at = Column(TIMESTAMP, default=datetime.now, server_default=text('CURRENT_TIMESTAMP'))

    agents = relationship("Agent", back_populates="purpose")

class AgentCredentials(Base):
    __tablename__ = 'agent_credentials'
    
    agent_id = Column(String, primary_key=True)
    api_key = Column(String, unique=True, nullable=False)
    secret_key = Column(String, nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.now, server_default=text('CURRENT_TIMESTAMP'))
    is_active = Column(Integer, default=1)
    
    agent = relationship("Agent", back_populates="credentials", uselist=False)

class Agent(Base):
    __tablename__ = 'agents'
    
    agent_id = Column(String, ForeignKey('agent_credentials.agent_id'), primary_key=True)
    agent_version = Column(String, nullable=False)
    hostname = Column(String, nullable=False)
    os = Column(String, nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.now, server_default=text('CURRENT_TIMESTAMP'))
    updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now, server_default=text('CURRENT_TIMESTAMP'))
    template = Column(Text, nullable=True)
    heartbeat = Column(TIMESTAMP)
    fingerprint = Column(String)
    purpose_id = Column(Integer, ForeignKey('purposes.id', ondelete="SET NULL"), nullable=True)
    
    credentials = relationship("AgentCredentials", back_populates="agent")
    numeric_metrics = relationship("MetricNumeric", back_populates="agent")
    json_metrics = relationship("MetricJson", back_populates="agent")
    purpose = relationship("Purpose", back_populates="agents")

    @property
    def effective_template(self):
        if self.template:
            return self.template
        if self.purpose:
            return self.purpose.template
        return DEFAULT_TEMPLATE

class MetricNumeric(Base):
    __tablename__ = 'metric_numeric'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String, ForeignKey('agents.agent_id'), nullable=False)
    metric_name = Column(String, nullable=False)
    value = Column(Float, nullable=False)
    timestamp = Column(TIMESTAMP, nullable=False)
    received_at = Column(TIMESTAMP, default=datetime.now, server_default=text('CURRENT_TIMESTAMP'))
    
    agent = relationship("Agent", back_populates="numeric_metrics")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
    
    __table_args__ = (
        Index('idx_metric_raw_time', 'timestamp'),
    )

class MetricJson(Base):
    __tablename__ = 'metric_json'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String, ForeignKey('agents.agent_id'), nullable=False)
    metric_name = Column(String, nullable=False)
    value = Column(Text, nullable=False)
    timestamp = Column(TIMESTAMP, nullable=False)
    received_at = Column(TIMESTAMP, default=datetime.now, server_default=text('CURRENT_TIMESTAMP'))
    
    agent = relationship("Agent", back_populates="json_metrics")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
    
    __table_args__ = (
        Index('idx_metric_json_time', 'timestamp'),
    )
    
