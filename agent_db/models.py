import json
from typing import Any, Dict, List
from agent_db.connection import execute

# New design solves Leaking SQLite Connections on Exception

def insert_metric(metric_name: str, value: Any) -> None:
    """Insert metric into the appropriate table based on value type."""

    if isinstance(value, (int, float)):
        execute(
            "INSERT INTO metric_numeric (metric_name, value) VALUES (?, ?)",
            (metric_name, float(value)),
        )

    elif isinstance(value, str):
        execute(
            "INSERT INTO metric_text (metric_name, value) VALUES (?, ?)",
            (metric_name, value),
        )

    else:
        execute(
            "INSERT INTO metric_json (metric_name, value) VALUES (?, ?)",
            (metric_name, json.dumps(value)),
        )


# ------------------------------------------------------------------


def fetch_unsent(table: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Fetch unsent metrics from a table."""

    rows = execute(
        f"""
        SELECT id, metric_name, value, timestamp
        FROM {table}
        WHERE sent = 0
        ORDER BY timestamp
        LIMIT ?
        """,
        (limit,),
        fetch="all",
    )

    return [dict(row) for row in rows] if rows else []


# ------------------------------------------------------------------


def mark_sent(table: str, ids: List[int]) -> None:
    """Mark metrics as sent."""

    if not ids:
        return

    placeholders = ",".join("?" for _ in ids)

    execute(
        f"UPDATE {table} SET sent = 1 WHERE id IN ({placeholders})",
        tuple(ids),
    )


# ------------------------------------------------------------------


def cleanup_old_metrics(days: int = 1) -> None:
    """Delete old metrics from all tables."""

    for table in ["metric_numeric", "metric_text", "metric_json"]:
        execute(
            f"""
            DELETE FROM {table}
            WHERE timestamp < datetime('now', ?)
            """,
            (f"-{days} day",),
        )