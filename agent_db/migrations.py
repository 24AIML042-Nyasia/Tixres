from agent_db.connection import get_connection


def migrate():
    conn = get_connection()
    cursor = conn.cursor()

    conn.execute("""
        CREATE TABLE metric_numeric (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        metric_name TEXT NOT NULL,
        value REAL NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        sent INTEGER DEFAULT 0
    );"""
    )


    conn.execute("""
        CREATE TABLE metric_text (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        metric_name TEXT NOT NULL,
        value TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        sent INTEGER DEFAULT 0
    );"""
    )


    conn.execute("""
        CREATE TABLE metric_json (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        metric_name TEXT NOT NULL,
        value TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        sent INTEGER DEFAULT 0
    );"""
    )


    conn.commit()

    conn.close()