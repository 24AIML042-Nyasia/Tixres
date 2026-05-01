import json
import sqlite3
import psycopg2
from pathlib import Path
from datetime import datetime

def migrate():
    config_path = Path("config.json")
    if not config_path.exists():
        print("config.json not found")
        return

    with open(config_path, "r") as f:
        config = json.load(f)

    db_config = config.get("database", {})
    if db_config.get("engine") != "postgresql":
        print("PostgreSQL not configured in config.json")
        return

    sqlite_path = Path(db_config.get("sqlite_path", "server/data/agent_metrics.sqlite3"))
    if not sqlite_path.exists():
        print(f"SQLite file not found at {sqlite_path}")
        return

    print(f"Connecting to SQLite: {sqlite_path}")
    lite_conn = sqlite3.connect(sqlite_path)
    lite_conn.row_factory = sqlite3.Row

    print("Connecting to PostgreSQL...")
    try:
        pg_conn = psycopg2.connect(
            host=db_config.get("host", "127.0.0.1"),
            port=db_config.get("port", 5432),
            database=db_config.get("name", "tixres"),
            user=db_config.get("user"),
            password=db_config.get("password")
        )
    except Exception as e:
        print(f"Failed to connect to PostgreSQL: {e}")
        return

    pg_cur = pg_conn.cursor()

    # Tables in dependency order
    tables = [
        "auth_config",
        "ui_users",
        "agent_credentials",
        "agents",
        "agent_assignments",
        "guidance",
        "agent_inventory",
        "alerts",
        "incidents",
        "anomaly_state",
        "rollup_state",
        "metric_numeric",
        "metric_json",
        "metric_log",
        "metric_numeric_1m",
        "metric_numeric_10m",
        "metric_numeric_1h"
    ]

    for table in tables:
        print(f"Migrating table: {table}...", end="", flush=True)
        try:
            # Check if table exists in SQLite
            lite_cur = lite_conn.execute(f"SELECT * FROM {table}")
            rows = lite_cur.fetchall()
            if not rows:
                print(" skipped (empty)")
                continue

            # Clear PG table first (optional, but ensures fresh start)
            # pg_cur.execute(f"TRUNCATE TABLE {table} CASCADE")

            cols = rows[0].keys()
            col_names = ", ".join(cols)
            placeholders = ", ".join(["%s"] * len(cols))
            
            insert_query = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

            for row in rows:
                values = [row[c] for c in cols]
                pg_cur.execute(insert_query, values)

            pg_conn.commit()
            print(f" done ({len(rows)} rows)")
        except sqlite3.OperationalError:
            print(" skipped (not in SQLite)")
        except Exception as e:
            print(f" error: {e}")
            pg_conn.rollback()

    lite_conn.close()
    pg_conn.close()
    print("\nMigration finished successfully.")

if __name__ == "__main__":
    migrate()
