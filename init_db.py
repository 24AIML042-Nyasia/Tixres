#!/usr/bin/env python3
"""
Initialize the metrics server database
Run this before starting the server if you encounter database errors
"""

import sqlite3
import sys

DB_PATH = "metrics_server.db"

def init_database():
    """Initialize database with all required tables"""
    print(f"Initializing database: {DB_PATH}")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Agent credentials table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_credentials (
            agent_id TEXT PRIMARY KEY,
            api_key TEXT UNIQUE NOT NULL,
            secret_key TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    """)
    print("✓ Created agent_credentials table")
    
    # Agent table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            agent_id TEXT PRIMARY KEY,
            agent_version TEXT NOT NULL,
            hostname TEXT NOT NULL,
            os TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            template TEXT,
            heartbeat TIMESTAMP,
            fingerprint TEXT,
            FOREIGN KEY (agent_id) REFERENCES agent_credentials(agent_id)
        )
    """)
    print("✓ Created agents table")
    
    # Numeric metrics table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metric_numeric (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            value REAL NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
        )
    """)
    print("✓ Created metric_numeric table")
    
    # JSON metrics table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metric_json (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            value TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
        )
    """)
    print("✓ Created metric_json table")
    
    # Create indexes for better query performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_metric_numeric_agent ON metric_numeric(agent_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_metric_numeric_timestamp ON metric_numeric(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_metric_numeric_name ON metric_numeric(metric_name)")
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_metric_json_agent ON metric_json(agent_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_metric_json_timestamp ON metric_json(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_metric_json_name ON metric_json(metric_name)")
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_agents_heartbeat ON agents(heartbeat)")
    
    print("✓ Created indexes")
    
    conn.commit()
    
    # Verify tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]
    
    print(f"\nDatabase initialized successfully!")
    print(f"Tables: {', '.join(tables)}")
    
    # Show counts
    cursor.execute("SELECT COUNT(*) FROM agents")
    agents_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM metric_numeric")
    numeric_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM metric_json")
    json_count = cursor.fetchone()[0]
    
    print(f"\nCurrent data:")
    print(f"  Agents: {agents_count}")
    print(f"  Numeric metrics: {numeric_count}")
    print(f"  JSON metrics: {json_count}")
    
    conn.close()
    return True

if __name__ == "__main__":
    try:
        init_database()
        print("\n✓ Database ready to use!")
        print("  You can now start the server: python server.py")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error initializing database: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)