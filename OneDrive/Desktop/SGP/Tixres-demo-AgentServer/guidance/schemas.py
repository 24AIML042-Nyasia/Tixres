from pydantic import BaseModel, Field
from typing import Any, Optional, List
from datetime import datetime
from guidance.models import Priority


# --------------------------------------------------------------------------- #
#  Request schemas                                                             #
# --------------------------------------------------------------------------- #

class GuidanceUpsert(BaseModel):
    """
    Used for both create and update.
    metric_name + priority + purpose identify the record; the remaining fields are the
    updatable payload.
    """
    metric_name: str = Field(..., min_length=1, max_length=255, example="cpu_usage")
    purpose: str = Field(default="general", min_length=1, max_length=100, example="general")
    priority: Priority = Field(default=Priority.P4)
    resolution_steps: List[dict[str, Any]] = Field(
        default_factory=List,
        example=[{"step": 1, "action": "Identify CPU-heavy processes via top/htop"}],
    )
    resolver_notes: Optional[str] = Field(default=None, example="Escalate if > 95% for 10 min")
    resolution_meta: Optional[dict[str, Any]] = Field(
        default_factory=dict,
        example={"tags": ["infra"], "sla_minutes": 30},
    )


class GuidanceUpdate(BaseModel):
    """Partial update — only the three mutable payload fields."""
    resolution_steps: Optional[List[dict[str, Any]]] = None
    resolver_notes: Optional[str] = None
    resolution_meta: Optional[dict[str, Any]] = None


# --------------------------------------------------------------------------- #
#  Response schemas                                                            #
# --------------------------------------------------------------------------- #

class GuidanceResponse(BaseModel):
    id: int
    metric_name: str
    purpose: str
    priority: Priority
    resolution_steps: List[dict[str, Any]]
    resolver_notes: Optional[str]
    resolution_meta: Optional[dict[str, Any]]
    last_updated: datetime

    class Config:
        from_attributes = True


class GuidanceListResponse(BaseModel):
    total: int
    items: List[GuidanceResponse]
