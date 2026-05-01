from __future__ import annotations

from datetime import datetime

SQLALCHEMY_AVAILABLE = False

try:
    from sqlalchemy import (  # type: ignore
        Column,
        Float,
        ForeignKey,
        Index,
        Integer,
        String,
        Text,
        TIMESTAMP,
        text,
        UniqueConstraint,
    )
    from sqlalchemy.orm import declarative_base, relationship  # type: ignore

    SQLALCHEMY_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    declarative_base = None  # type: ignore
    Column = None  # type: ignore
    Float = None  # type: ignore
    ForeignKey = None  # type: ignore
    Index = None  # type: ignore
    Integer = None  # type: ignore
    String = None  # type: ignore
    Text = None  # type: ignore
    TIMESTAMP = None  # type: ignore
    text = None  # type: ignore
    relationship = None  # type: ignore


Base = declarative_base() if SQLALCHEMY_AVAILABLE else object  # type: ignore


if SQLALCHEMY_AVAILABLE:  # pragma: no cover

    class AgentCredentials(Base):
        __tablename__ = "agent_credentials"

        agent_id = Column(String, primary_key=True)
        api_key = Column(String, unique=True, nullable=False)
        secret_key = Column(String, nullable=False)
        role = Column(
            String, nullable=False, default="user", server_default=text("'user'")
        )
        created_at = Column(
            TIMESTAMP, default=datetime.now, server_default=text("CURRENT_TIMESTAMP")
        )
        is_active = Column(Integer, default=1)

        agent = relationship("Agent", back_populates="credentials", uselist=False)

    class Agent(Base):
        __tablename__ = "agents"

        agent_id = Column(
            String, ForeignKey("agent_credentials.agent_id"), primary_key=True
        )
        agent_version = Column(String, nullable=False)
        hostname = Column(String, nullable=False)
        os = Column(String, nullable=False)
        created_at = Column(
            TIMESTAMP, default=datetime.now, server_default=text("CURRENT_TIMESTAMP")
        )
        updated_at = Column(
            TIMESTAMP,
            default=datetime.now,
            onupdate=datetime.now,
            server_default=text("CURRENT_TIMESTAMP"),
        )
        template = Column(Text, nullable=True)
        plugin = Column(String, nullable=True)
        heartbeat = Column(TIMESTAMP)
        fingerprint = Column(String)

        credentials = relationship("AgentCredentials", back_populates="agent")
        numeric_metrics = relationship("MetricNumeric", back_populates="agent")
        json_metrics = relationship("MetricJson", back_populates="agent")
        log_metrics = relationship("MetricLog", back_populates="agent")

    class Guidance(Base):
        __tablename__ = "guidance"

        id = Column(Integer, primary_key=True, autoincrement=True)
        anomaly_type = Column(String, unique=True, nullable=False)
        title = Column(String, nullable=False)
        description = Column(Text)
        steps = Column(Text)  # JSON array
        priority = Column(String, nullable=False)
        created_at = Column(TIMESTAMP, default=datetime.now, server_default=text("CURRENT_TIMESTAMP"))
        updated_at = Column(TIMESTAMP, default=datetime.now, onupdate=datetime.now, server_default=text("CURRENT_TIMESTAMP"))

    class MetricNumeric(Base):
        __tablename__ = "metric_numeric"

        id = Column(Integer, primary_key=True, autoincrement=True)
        agent_id = Column(String, ForeignKey("agents.agent_id"), nullable=False)
        metric_name = Column(String, nullable=False)
        value = Column(Float, nullable=False)
        timestamp = Column(TIMESTAMP, nullable=False)
        received_at = Column(
            TIMESTAMP, default=datetime.now, server_default=text("CURRENT_TIMESTAMP")
        )

        agent = relationship("Agent", back_populates="numeric_metrics")

        __table_args__ = (Index("idx_metric_raw_time", "timestamp"),)

    class MetricJson(Base):
        __tablename__ = "metric_json"

        id = Column(Integer, primary_key=True, autoincrement=True)
        agent_id = Column(String, ForeignKey("agents.agent_id"), nullable=False)
        metric_name = Column(String, nullable=False)
        value = Column(Text, nullable=False)
        timestamp = Column(TIMESTAMP, nullable=False)
        received_at = Column(
            TIMESTAMP, default=datetime.now, server_default=text("CURRENT_TIMESTAMP")
        )

        agent = relationship("Agent", back_populates="json_metrics")

        __table_args__ = (Index("idx_metric_json_time", "timestamp"),)

    class MetricLog(Base):
        __tablename__ = "metric_log"

        id = Column(Integer, primary_key=True, autoincrement=True)
        agent_id = Column(String, ForeignKey("agents.agent_id"), nullable=False)
        metric_name = Column(String, nullable=False)
        value = Column(Text, nullable=False)
        timestamp = Column(TIMESTAMP, nullable=False)
        received_at = Column(
            TIMESTAMP, default=datetime.now, server_default=text("CURRENT_TIMESTAMP")
        )

        agent = relationship("Agent", back_populates="log_metrics")

        __table_args__ = (Index("idx_metric_log_time", "timestamp"),)

    class AgentInventory(Base):
        __tablename__ = "agent_inventory"

        agent_id = Column(String, ForeignKey("agents.agent_id"), primary_key=True)
        fingerprint = Column(String)
        modules_json = Column(Text)
        functions_json = Column(Text)
        updated_at = Column(TIMESTAMP, default=datetime.now, server_default=text("CURRENT_TIMESTAMP"))

    class RollupState(Base):
        __tablename__ = "rollup_state"

        source_table = Column(String, primary_key=True)
        target_table = Column(String, primary_key=True)
        last_bucket = Column(TIMESTAMP, nullable=False)
        updated_at = Column(TIMESTAMP, default=datetime.now, server_default=text("CURRENT_TIMESTAMP"))

    class Alert(Base):
        __tablename__ = "alerts"

        id = Column(Integer, primary_key=True, autoincrement=True)
        agent_id = Column(String, ForeignKey("agents.agent_id"), nullable=False)
        service = Column(String, nullable=False)
        anomaly_type = Column(String, nullable=False)
        severity = Column(String, nullable=False)
        fingerprint = Column(String, nullable=False)
        first_seen = Column(TIMESTAMP, nullable=False)
        last_seen = Column(TIMESTAMP, nullable=False)
        count = Column(Integer, default=1)
        plugin = Column(String)
        is_resolved = Column(Integer, default=0)
        resolved_at = Column(TIMESTAMP)

        __table_args__ = (
            Index("idx_alerts_fingerprint", "fingerprint"),
            Index("idx_alerts_agent_id", "agent_id"),
        )

    class AnomalyState(Base):
        __tablename__ = "anomaly_state"

        agent_id = Column(String, ForeignKey("agents.agent_id"), primary_key=True)
        detector_id = Column(String, primary_key=True)
        state_json = Column(Text)
        updated_at = Column(TIMESTAMP, default=datetime.now, server_default=text("CURRENT_TIMESTAMP"))

    class AuthConfig(Base):
        __tablename__ = "auth_config"
        key = Column(String, primary_key=True)
        value = Column(Text, nullable=False)

    class UiUser(Base):
        __tablename__ = "ui_users"
        username = Column(String, primary_key=True)
        pw_hash = Column(String, nullable=False)
        role = Column(String, nullable=False, default="user", server_default=text("'user'"))
        created_at = Column(TIMESTAMP, default=datetime.now, server_default=text("CURRENT_TIMESTAMP"))
        is_active = Column(Integer, default=1)

    class AgentAssignment(Base):
        __tablename__ = "agent_assignments"
        username = Column(String, primary_key=True)
        hostname = Column(String, primary_key=True)
        assigned_at = Column(TIMESTAMP, default=datetime.now, server_default=text("CURRENT_TIMESTAMP"))

    class Incident(Base):
        __tablename__ = "incidents"
        id = Column(Integer, primary_key=True, autoincrement=True)
        incident_key = Column(String, unique=True, nullable=False)
        host_id = Column(String, nullable=False)
        service = Column(String, nullable=False)
        plugin = Column(String, nullable=False)
        anomaly_type = Column(String, nullable=False)
        severity = Column(String, nullable=False)
        time_bucket = Column(String, nullable=False)
        status = Column(String, nullable=False, default="open", server_default=text("'open'"))
        alert_count = Column(Integer, nullable=False, default=1)
        first_seen = Column(TIMESTAMP, nullable=False)
        last_seen = Column(TIMESTAMP, nullable=False)
        resolved_at = Column(TIMESTAMP)
        alert_ids = Column(Text, nullable=False, default="[]", server_default=text("'[]'"))

        __table_args__ = (
            Index("idx_incidents_key", "incident_key"),
            Index("idx_incidents_status", "status"),
            Index("idx_incidents_host", "host_id"),
        )

    # Generic Rollup Model (we will use this to create the 1m, 10m, 1h tables)
    class MetricRollup1m(Base):
        __tablename__ = "metric_numeric_1m"
        id = Column(Integer, primary_key=True, autoincrement=True)
        agent_id = Column(String, ForeignKey("agents.agent_id"), nullable=False)
        metric_name = Column(String, nullable=False)
        bucket_start = Column(TIMESTAMP, nullable=False)
        count = Column(Integer, nullable=False)
        min = Column(Float, nullable=False)
        max = Column(Float, nullable=False)
        sum = Column(Float, nullable=False)
        received_at = Column(TIMESTAMP, default=datetime.now, server_default=text("CURRENT_TIMESTAMP"))
        __table_args__ = (
            Index("idx_metric_numeric_1m_time", "bucket_start"),
            UniqueConstraint("agent_id", "metric_name", "bucket_start", name="uq_metric_numeric_1m")
        )

    class MetricRollup10m(Base):
        __tablename__ = "metric_numeric_10m"
        id = Column(Integer, primary_key=True, autoincrement=True)
        agent_id = Column(String, ForeignKey("agents.agent_id"), nullable=False)
        metric_name = Column(String, nullable=False)
        bucket_start = Column(TIMESTAMP, nullable=False)
        count = Column(Integer, nullable=False)
        min = Column(Float, nullable=False)
        max = Column(Float, nullable=False)
        sum = Column(Float, nullable=False)
        received_at = Column(TIMESTAMP, default=datetime.now, server_default=text("CURRENT_TIMESTAMP"))
        __table_args__ = (
            Index("idx_metric_numeric_10m_time", "bucket_start"),
            UniqueConstraint("agent_id", "metric_name", "bucket_start", name="uq_metric_numeric_10m")
        )

    class MetricRollup1h(Base):
        __tablename__ = "metric_numeric_1h"
        id = Column(Integer, primary_key=True, autoincrement=True)
        agent_id = Column(String, ForeignKey("agents.agent_id"), nullable=False)
        metric_name = Column(String, nullable=False)
        bucket_start = Column(TIMESTAMP, nullable=False)
        count = Column(Integer, nullable=False)
        min = Column(Float, nullable=False)
        max = Column(Float, nullable=False)
        sum = Column(Float, nullable=False)
        received_at = Column(TIMESTAMP, default=datetime.now, server_default=text("CURRENT_TIMESTAMP"))
        __table_args__ = (
            Index("idx_metric_numeric_1h_time", "bucket_start"),
            UniqueConstraint("agent_id", "metric_name", "bucket_start", name="uq_metric_numeric_1h")
        )


