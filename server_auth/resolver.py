"""
Helper utilities for the built-in resolver (admin) role.

This keeps the RBAC bootstrap logic in one place so both the app and tests
can rely on a predictable default resolver credential.
"""

import os
from typing import Optional

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from server_db.connection import SessionLocal, engine
from server_db.models import AgentCredentials
from server_utils.logger import get_logger

logger = get_logger()

# Defaults can be overridden via environment for demos.
DEFAULT_RESOLVER_AGENT_ID = os.getenv("RESOLVER_AGENT_ID", "resolver_admin")
DEFAULT_RESOLVER_API_KEY = os.getenv("RESOLVER_API_KEY", "resolver-demo-key")
DEFAULT_RESOLVER_SECRET_KEY = os.getenv("RESOLVER_SECRET_KEY", "resolver-demo-secret")


def ensure_role_column_exists(bind=None) -> None:
    """
    Add `role` column to agent_credentials if a legacy database is missing it.
    Safe to run repeatedly; a no-op when the column already exists.
    """
    inspect_target = bind or engine
    inspector = inspect(inspect_target)
    try:
        columns = [col["name"] for col in inspector.get_columns("agent_credentials")]
    except Exception:
        # Table might not exist yet; let create_all handle it later.
        return

    if "role" in columns:
        return

    logger.info("Adding missing 'role' column to agent_credentials")
    if isinstance(inspect_target, Engine):
        conn = inspect_target.connect()
        close_conn = True
    else:
        conn = inspect_target
        close_conn = False

    try:
        with conn.begin():
            conn.execute(
                text(
                    "ALTER TABLE agent_credentials "
                    "ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'"
                )
            )
    finally:
        if close_conn:
            conn.close()


def ensure_default_resolver_credentials() -> AgentCredentials:
    """
    Create a demo resolver credential when none exists.
    Returns the existing resolver when one is already present.
    """
    db = SessionLocal()
    try:
        existing: Optional[AgentCredentials] = (
            db.query(AgentCredentials)
            .filter(AgentCredentials.role == "resolver")
            .first()
        )
        if existing:
            return existing

        cred = AgentCredentials(
            agent_id=DEFAULT_RESOLVER_AGENT_ID,
            api_key=DEFAULT_RESOLVER_API_KEY,
            secret_key=DEFAULT_RESOLVER_SECRET_KEY,
            role="resolver",
        )
        db.add(cred)
        db.commit()
        db.refresh(cred)
        logger.info("Created default resolver credentials (%s)", cred.agent_id)
        return cred
    finally:
        db.close()
