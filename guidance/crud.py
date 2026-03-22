"""
guidance/crud.py
────────────────
Low-level database operations for the Guidance model.
The (metric_name, severity) pair is the natural key — there is exactly one
record per combination. All writes go through upsert_guidance.
"""

from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from guidance.models import Guidance, Priority
from guidance.schemas import GuidanceUpsert, GuidanceUpdate


# --------------------------------------------------------------------------- #
#  Internal helpers                                                            #
# --------------------------------------------------------------------------- #

def _get_by_natural_key(db: Session, metric_name: str, severity: str) -> Optional[Guidance]:
    stmt = select(Guidance).where(
        Guidance.metric_name == metric_name,
        Guidance.severity == severity,
    )
    return db.scalars(stmt).first()


# --------------------------------------------------------------------------- #
#  UPSERT  (create or update by natural key)                                  #
# --------------------------------------------------------------------------- #

def upsert_guidance(db: Session, payload: GuidanceUpsert) -> tuple[Guidance, bool]:
    """
    Insert a new record if (metric_name, severity) does not exist,
    otherwise update the mutable fields.

    Returns (record, created) where `created` is True on insert, False on update.
    """
    record = _get_by_natural_key(db, payload.metric_name, payload.severity)

    if record is None:
        record = Guidance(
            metric_name=payload.metric_name,
            severity=payload.severity,
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
    db: Session, metric_name: str, severity: str
) -> Optional[Guidance]:
    return _get_by_natural_key(db, metric_name, severity)


def get_all_guidance(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 20,
    priority: Optional[Priority] = None,
    metric_name: Optional[str] = None,
    severity: Optional[str] = None,
) -> tuple[int, list[Guidance]]:
    """Return (total_count, page). Supports optional filters."""
    query = select(Guidance)

    if priority:
        query = query.where(Guidance.priority == priority)
    if metric_name:
        query = query.where(Guidance.metric_name.ilike(f"%{metric_name}%"))
    if severity:
        query = query.where(Guidance.severity.ilike(f"%{severity}%"))

    total: int = db.scalar(select(func.count()).select_from(query.subquery()))  # type: ignore[arg-type]
    records = db.scalars(
        query.order_by(Guidance.last_updated.desc()).offset(skip).limit(limit)
    ).all()

    return total, list(records)


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
    db: Session, metric_name: str, severity: str
) -> bool:
    record = _get_by_natural_key(db, metric_name, severity)
    if record is None:
        return False
    db.delete(record)
    db.commit()
    return True
