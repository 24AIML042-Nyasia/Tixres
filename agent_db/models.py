import json

from agent_db.connection import get_connection

# conn = get_connection()
# cursor = conn.cursor()

def insert_metric(metric_name: str, value):
    conn = get_connection()

    if isinstance(value, (int, float)):
        conn.execute(
            "INSERT INTO metric_numeric (metric_name, value) VALUES (?, ?)",
            (metric_name, float(value))
        )

    elif isinstance(value, str):
        conn.execute(
            "INSERT INTO metric_text (metric_name, value) VALUES (?, ?)",
            (metric_name, value)
        )

    else:
        # dict, list, custom object → JSON
        conn.execute(
            "INSERT INTO metric_json (metric_name, value) VALUES (?, ?)",
            (metric_name, json.dumps(value))
        )

    conn.commit()
    conn.close()

def fetch_unsent(table: str, limit: int = 100):
    conn = get_connection()
    cursor = conn.execute(
        f"""
        SELECT id, metric_name, value, timestamp
        FROM {table}
        WHERE sent = 0
        ORDER BY timestamp
        LIMIT ?
        """,
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def mark_sent(table: str, ids: list[int]):
    if not ids:
        return

    conn = get_connection()
    placeholders = ",".join("?" for _ in ids)
    conn.execute(
        f"UPDATE {table} SET sent = 1 WHERE id IN ({placeholders})",
        ids
    )
    conn.commit()
    conn.close()


def cleanup_old_metrics(days: int = 1):
    conn = get_connection()

    for table in ["metric_numeric", "metric_text", "metric_json"]:
        conn.execute(
            f"""
            DELETE FROM {table}
            WHERE timestamp < datetime('now', ?)
            """,
            (f"-{days} day",)
        )

    conn.commit()
    conn.close()
