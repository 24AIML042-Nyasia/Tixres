from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from server_db.connection import SessionLocal


def retention_policy():
    """
    Trim old metrics for whichever backend is active.
    SQLite (used in tests) does not support `NOW()` or `INTERVAL`, so we
    use its `datetime('now', '-7 days')` helper. Postgres keeps the original
    clause.
    """
    db = SessionLocal()
    try:
        dialect = db.bind.dialect.name if db.bind else ""
        if dialect == "sqlite":
            delete_sql = text(
                """
                DELETE FROM metric_numeric
                WHERE timestamp < datetime('now', '-7 days')
                """
            )
        else:
            delete_sql = text(
                """
                DELETE FROM metric_numeric
                WHERE timestamp < NOW() - INTERVAL '7 days'
                """
            )

        try:
            db.execute(delete_sql)
            db.commit()
        except OperationalError:
            # During tests the in-memory SQLite DB may not have tables yet.
            db.rollback()
    finally:
        db.close()