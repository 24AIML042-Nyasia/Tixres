"""
guidance/crud.py
----------------
Low-level database operations for the Guidance model.
The (metric_name, priority, purpose) tuple is the natural key — there is exactly one
record per combination. All writes go through upsert_guidance.
"""

from typing import Optional
from sqlalchemy.orm import Session

from guidance.models import Guidance, Priority
from guidance.schemas import GuidanceUpsert, GuidanceUpdate


# --------------------------------------------------------------------------- #
#  Internal helpers                                                            #
# --------------------------------------------------------------------------- #

def _get_by_natural_key(db: Session, metric_name: str, priority: Priority, purpose: str) -> Optional[Guidance]:
    priority_value = priority.value if isinstance(priority, Priority) else priority
    return (
        db.query(Guidance)
        .filter(
            Guidance.metric_name == metric_name,
            Guidance.priority == priority_value,
            Guidance.purpose == purpose,
        )
        .first()
    )


# --------------------------------------------------------------------------- #
#  UPSERT  (create or update by natural key)                                  #
# --------------------------------------------------------------------------- #

def upsert_guidance(db: Session, payload: GuidanceUpsert) -> tuple[Guidance, bool]:
    """
    Insert a new record if (metric_name, priority, purpose) does not exist,
    otherwise update the mutable fields.

    Returns (record, created) where `created` is True on insert, False on update.
    """
    record = _get_by_natural_key(db, payload.metric_name, payload.priority, payload.purpose)

    if record is None:
        record = Guidance(
            metric_name=payload.metric_name,
            purpose=payload.purpose,
            priority=payload.priority,
            resolution_steps=payload.resolution_steps,
            resolver_notes=payload.resolver_notes,
            resolution_meta=payload.resolution_meta or {},
        )
        db.add(record)
        created = True
    else:
        record.priority = payload.priority
        record.resolution_steps = payload.resolution_steps
        record.resolver_notes = payload.resolver_notes
        record.resolution_meta = payload.resolution_meta or {}
        created = False

    db.commit()
    db.refresh(record)
    return record, created


# --------------------------------------------------------------------------- #
#  READ                                                                        #
# --------------------------------------------------------------------------- #

def get_guidance_by_id(db: Session, guidance_id: int) -> Optional[Guidance]:
    return db.get(Guidance, guidance_id)


def get_guidance_by_natural_key(
    db: Session, metric_name: str, priority: Priority, purpose: str = "general"
) -> Optional[Guidance]:
    return _get_by_natural_key(db, metric_name, priority, purpose)


def get_all_guidance(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 20,
    priority: Optional[Priority] = None,
    metric_name: Optional[str] = None,
    purpose: Optional[str] = None,
) -> tuple[int, list[Guidance]]:
    """Return (total_count, page). Supports optional filters."""
    query = db.query(Guidance)

    if priority:
        priority_value = priority.value if isinstance(priority, Priority) else priority
        query = query.filter(Guidance.priority == priority_value)
    if metric_name:
        query = query.filter(Guidance.metric_name.ilike(f"%{metric_name}%"))
    if purpose:
        query = query.filter(Guidance.purpose == purpose)

    total: int = query.count()
    records = (
        query.order_by(Guidance.last_updated.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return total, records


# --------------------------------------------------------------------------- #
#  UPDATE  (patch mutable fields only, lookup by PK)                          #
# --------------------------------------------------------------------------- #

def update_guidance_by_id(
    db: Session, guidance_id: int, payload: GuidanceUpdate
) -> Optional[Guidance]:
    """
    Partial update of the three mutable fields by primary key.
    Only fields explicitly set in the payload are applied (PATCH semantics).
    Returns None when the record does not exist.
    """
    record = db.get(Guidance, guidance_id)
    if record is None:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(record, field, value)

    db.commit()
    db.refresh(record)
    return record


# --------------------------------------------------------------------------- #
#  DELETE                                                                      #
# --------------------------------------------------------------------------- #

def delete_guidance_by_id(db: Session, guidance_id: int) -> bool:
    record = db.get(Guidance, guidance_id)
    if record is None:
        return False
    db.delete(record)
    db.commit()
    return True


def delete_guidance_by_natural_key(
    db: Session, metric_name: str, priority: Priority, purpose: str = "general"
) -> bool:
    record = _get_by_natural_key(db, metric_name, priority, purpose)
    if record is None:
        return False
    db.delete(record)
    db.commit()
    return True
