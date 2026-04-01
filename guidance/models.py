from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Enum as SAEnum, UniqueConstraint, text
from server_db.connection import Base
from sqlalchemy.sql import func
import enum
from typing import List


class Priority(str, enum.Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class Guidance(Base):
    __tablename__ = "guidance"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    metric_name = Column(String(255), nullable=False, index=True)
    purpose = Column(String(100), nullable=False, default="general", server_default=text("'general'"), index=True)
    priority = Column(SAEnum(Priority), nullable=False, default=Priority.P4)
    resolution_steps = Column(JSON, nullable=False, default=List)   # [{"step": 1, "action": "..."}]
    resolver_notes = Column(Text, nullable=True)
    resolution_meta = Column(JSON, nullable=True, default=dict)     # {"tags": [], "sla_minutes": 60}
    last_updated = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("metric_name", "priority", "purpose", name="uq_guidance_metric_priority_purpose"),
    )

    def __repr__(self):
        return (
            f"<Guidance id={self.id} metric='{self.metric_name}' "
            f"priority='{self.priority}' purpose='{self.purpose}'>"
        )
