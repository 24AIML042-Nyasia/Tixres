"""
guidance/guidance_service.py
----------------------------
Service layer for the Guidance feature.

Key invariant enforced here:
  - (metric_name, priority, purpose) is the natural unique key.
  - There is exactly ONE record per tuple — upsert handles create/update
    transparently.
  - Direct updates are restricted to the three mutable payload fields:
    resolution_steps, resolver_notes, resolution_meta.
"""

from typing import Optional, List
from sqlalchemy.orm import Session

from guidance.models import Priority
from guidance.schemas import (
    GuidanceListResponse,
    GuidanceResponse,
    GuidanceUpdate,
    GuidanceUpsert,
)
import guidance.crud as crud


# --------------------------------------------------------------------------- #
#  Custom exceptions                                                           #
# --------------------------------------------------------------------------- #

class GuidanceNotFoundError(Exception):
    def __init__(self, identifier: str):
        super().__init__(f"Guidance record not found: {identifier}")


# --------------------------------------------------------------------------- #
#  Service                                                                     #
# --------------------------------------------------------------------------- #

class GuidanceService:
    """
    Aggregates all guidance-related operations.

    Usage:
        service = GuidanceService(db)
        response, created = service.upsert(payload)
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    #  Upsert  — the primary write path                                   #
    # ------------------------------------------------------------------ #

    def upsert(self, payload: GuidanceUpsert) -> tuple[GuidanceResponse, bool]:
        """
        Create or update the guidance record for (metric_name, priority, purpose).

        Returns (GuidanceResponse, created: bool).
        created=True  → new record was inserted.
        created=False → existing record was updated.

        The natural key (metric_name, priority, purpose) is immutable once created;
        only resolution_steps, resolver_notes, and resolution_meta are written on update.
        """
        record, created = crud.upsert_guidance(self.db, payload)
        return GuidanceResponse.model_validate(record), created

    # ------------------------------------------------------------------ #
    #  Read                                                               #
    # ------------------------------------------------------------------ #

    def get_by_id(self, guidance_id: int) -> GuidanceResponse:
        record = crud.get_guidance_by_id(self.db, guidance_id)
        if record is None:
            raise GuidanceNotFoundError(f"id={guidance_id}")
        return GuidanceResponse.model_validate(record)

    def get_by_natural_key(self, metric_name: str, priority: Priority, purpose: str = "general") -> GuidanceResponse:
        record = crud.get_guidance_by_natural_key(self.db, metric_name, priority, purpose)
        if record is None:
            raise GuidanceNotFoundError(f"metric='{metric_name}', priority='{priority}', purpose='{purpose}'")
        return GuidanceResponse.model_validate(record)

    def list(
        self,
        *,
        skip: int = 0,
        limit: int = 20,
        priority: Optional[Priority] = None,
        metric_name: Optional[str] = None,
        purpose: Optional[str] = None,
    ) -> GuidanceListResponse:
        """Paginated list with optional filters on priority, metric_name, purpose."""
        total, records = crud.get_all_guidance(
            self.db,
            skip=skip,
            limit=limit,
            priority=priority,
            metric_name=metric_name,
            purpose=purpose,
        )
        return GuidanceListResponse(
            total=total,
            items=[GuidanceResponse.model_validate(r) for r in records],
        )

    # ------------------------------------------------------------------ #
    #  Update  — patch mutable fields only, by PK                         #
    # ------------------------------------------------------------------ #

    def update_by_id(self, guidance_id: int, payload: GuidanceUpdate) -> GuidanceResponse:
        """
        Patch resolution_steps / resolver_notes / resolution_meta by primary key.
        Only fields that are explicitly set in the payload are applied.
        """
        record = crud.update_guidance_by_id(self.db, guidance_id, payload)
        if record is None:
            raise GuidanceNotFoundError(f"id={guidance_id}")
        return GuidanceResponse.model_validate(record)

    def update_by_natural_key(
        self, metric_name: str, priority: Priority, payload: GuidanceUpdate, purpose: str = "general"
    ) -> GuidanceResponse:
        """
        Patch mutable fields by the natural key (metric_name, priority, purpose).
        Convenience wrapper — prefer upsert() when the full payload is available.
        """
        record = crud.get_guidance_by_natural_key(self.db, metric_name, priority, purpose)
        if record is None:
            raise GuidanceNotFoundError(f"metric='{metric_name}', priority='{priority}', purpose='{purpose}'")
        updated = crud.update_guidance_by_id(self.db, record.id, payload)
        return GuidanceResponse.model_validate(updated)

    # ------------------------------------------------------------------ #
    #  Delete                                                             #
    # ------------------------------------------------------------------ #

    def delete_by_id(self, guidance_id: int) -> dict:
        if not crud.delete_guidance_by_id(self.db, guidance_id):
            raise GuidanceNotFoundError(f"id={guidance_id}")
        return {"deleted": True, "id": guidance_id}

    def delete_by_natural_key(self, metric_name: str, priority: Priority, purpose: str = "general") -> dict:
        if not crud.delete_guidance_by_natural_key(self.db, metric_name, priority, purpose):
            raise GuidanceNotFoundError(f"metric='{metric_name}', priority='{priority}', purpose='{purpose}'")
        return {"deleted": True, "metric_name": metric_name, "priority": priority, "purpose": purpose}

    # ------------------------------------------------------------------ #
    #  Helpers / aggregates                                               #
    # ------------------------------------------------------------------ #

    def get_resolution_steps(self, metric_name: str, priority: Priority, purpose: str = "general") -> List[dict]:
        """
        Return only the resolution_steps for a (metric_name, priority, purpose) tuple.
        Lightweight lookup during active incident triage.
        """
        record = crud.get_guidance_by_natural_key(self.db, metric_name, priority, purpose)
        if record is None:
            raise GuidanceNotFoundError(f"metric='{metric_name}', priority='{priority}', purpose='{purpose}'")
        return record.resolution_steps or []

    def summarize_by_priority(self) -> dict[str, int]:
        """
        Count of guidance records per priority level.
        Example: {"P1": 3, "P2": 7, "P3": 12, "P4": 20}
        """
        _, all_records = crud.get_all_guidance(self.db, skip=0, limit=10_000)
        summary: dict[str, int] = {p.value: 0 for p in Priority}
        for record in all_records:
            summary[record.priority.value] += 1
        return summary
