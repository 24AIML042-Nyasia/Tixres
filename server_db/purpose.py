import json
from typing import Any, Dict, Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy import update

from server_db.connection import SessionLocal
from server_db.models import Purpose, Agent
from server_db.const import DEFAULT_TEMPLATE

TemplateType = Union[Dict[str, Any], Any]


def _normalize_template(template: Optional[TemplateType]) -> TemplateType:
    """Ensure templates default to an empty JSON object."""
    if template is None:
        return {}
    if isinstance(template, str):
        try:
            return json.loads(template)
        except json.JSONDecodeError:
            return template
    return template


def create_purpose(purpose: str = "general", template: Optional[TemplateType] = None, db: Optional[Session] = None) -> Purpose:
    """Create a purpose row (idempotent by name)."""
    session = db or SessionLocal()
    close_session = db is None
    try:
        existing = session.query(Purpose).filter(Purpose.purpose == purpose).first()
        if existing:
            return existing

        normalized = _normalize_template(template if template is not None else DEFAULT_TEMPLATE)
        template_str = json.dumps(normalized) if not isinstance(normalized, str) else normalized
        purpose_row = Purpose(purpose=purpose, template=template_str)
        session.add(purpose_row)
        session.commit()
        session.refresh(purpose_row)
        return purpose_row
    finally:
        if close_session:
            session.close()


def read_purpose(purpose_id: int, db: Optional[Session] = None) -> Optional[Purpose]:
    """Read a purpose row by id."""
    session = db or SessionLocal()
    close_session = db is None
    try:
        return session.query(Purpose).filter(Purpose.id == purpose_id).first()
    finally:
        if close_session:
            session.close()


def update_purpose_template(purpose_id: int, template: TemplateType, db: Optional[Session] = None) -> Optional[Purpose]:
    """Update only the template for a given purpose."""
    session = db or SessionLocal()
    close_session = db is None
    try:
        purpose_row = session.query(Purpose).filter(Purpose.id == purpose_id).first()
        if not purpose_row:
            return None

        normalized = _normalize_template(template)
        purpose_row.template = json.dumps(normalized) if not isinstance(normalized, str) else normalized
        session.commit()
        session.refresh(purpose_row)
        return purpose_row
    finally:
        if close_session:
            session.close()


def delete_purpose(purpose_id: int, db: Optional[Session] = None) -> bool:
    """Delete a purpose row."""
    session = db or SessionLocal()
    close_session = db is None
    try:
        purpose_row = session.query(Purpose).filter(Purpose.id == purpose_id).first()
        if not purpose_row:
            return False

        session.delete(purpose_row)
        session.commit()
        return True
    finally:
        if close_session:
            session.close()

def set_template(db: Session, template: str, agent_id: str):
    stmt = (
        update(Agent)
        .where(Agent.agent_id == agent_id)
        .values(template=_normalize_template(template))
    )

    db.execute(stmt)
    db.commit()
