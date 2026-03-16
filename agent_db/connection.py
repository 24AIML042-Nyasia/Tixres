import sqlite3
from typing import Optional
from settings import AGENT_DB_PATH

def get_connection():
    conn = sqlite3.connect(AGENT_DB_PATH)
    conn.row_factory = sqlite3.Row 
    return conn

def execute(
    query: str,
    params: tuple = (),
    *,
    fetch: Optional[str] = None
):
    """
    Execute a SQL query safely using a context manager.

    Args:
        query: SQL query string
        params: parameters for SQL placeholders
        fetch:
            None      → no results
            "one"     → fetchone()
            "all"     → fetchall()

    Returns:
        query results if fetch is specified
    """
    with get_connection() as conn:
        cursor = conn.execute(query, params)

        if fetch == "one":
            return cursor.fetchone()

        if fetch == "all":
            return cursor.fetchall()

        return None