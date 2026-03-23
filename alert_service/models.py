"""
Alert ORM model.

An Alert represents a correlated, deduplicated view of one or more Tickets
sharing the same (metric_name, severity) key. It tracks lifecycle from OPEN
through CLOSED, accumulates agent IDs, and controls notification cooldowns.
"""

from sqlalchemy import Column, String, Integer, TIMESTAMP, Text, text
from sqlalchemy import UniqueConstraint
from datetime import datetime
from server_db.connection import Base


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # --- Identity key: (metric_name, severity) ---
    metric_name = Column(String, nullable=False, index=True)
    severity    = Column(String, nullable=False, index=True)
    purpose     = Column(String, nullable=False, default="general", server_default=text("'general'"), index=True)

    # --- Classification ---
    # "SINGLE"  → only one agent has fired this alert
    # "GROUP"   → two or more agents have fired it (escalated)
    type   = Column(String, default="SINGLE")       # SINGLE | GROUP
    status = Column(String, default="OPEN")         # OPEN   | CLOSED

    # JSON-encoded list of agent_ids that contributed, e.g. '["agent_1","agent_2"]'
    agent_ids = Column(Text, default="[]")

    # Running total of occurrences across all contributing tickets
    total_occurrence = Column(Integer, default=0)

    # Timestamps
    first_seen_at  = Column(TIMESTAMP, nullable=True)
    last_seen_at   = Column(TIMESTAMP, nullable=True)

    # When the notification cooldown expires; no new pages/alerts should fire before this
    cooldown_until = Column(TIMESTAMP, nullable=True)

    created_at = Column(
        TIMESTAMP,
        default=datetime.now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    closed_at = Column(TIMESTAMP, nullable=True)

    __table_args__ = (
        UniqueConstraint("metric_name", "severity", "purpose", "status", name="uq_alert_metric_severity_purpose_status"),
    )
