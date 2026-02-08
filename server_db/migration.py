from server_db.conncetion import get_db

def migrate_ticket():
    conn = get_db()
    cursor = conn.cursor()

    #ticket table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            agent_id TEXT NOT NULL,
            metric_name TEXT NOT NULL,

            severity TEXT NOT NULL,      -- P1, P2, P3, P4
            status TEXT DEFAULT 'OPEN',  -- OPEN, ACK, RESOLVED

            anomaly_type TEXT NOT NULL,  
            metadata TEXT,
            message TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

""")


# def migrate():
#     conn = get_db()
#     cursor =conn.cursor()

#     #1m roll up
#     cursor.execute("""
#         CREATE TABLE IF NOT EXISTS metric_numeric_1m (
#         agent_id TEXT NOT NULL,
#         metric_name TEXT NOT NULL,
#         bucket_start TIMESTAMP NOT NULL,

#         count INTEGER NOT NULL,
#         min REAL NOT NULL,
#         max REAL NOT NULL,
#         sum REAL NOT NULL,
#         avg REAL NOT NULL,

#         PRIMARY KEY (agent_id, metric_name, bucket_start),
#         FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
#         );
#     """)

#     #10m roll up
#     cursor.execute("""
#         CREATE TABLE IF NOT EXISTS metric_numeric_10m (
#         agent_id TEXT NOT NULL,
#         metric_name TEXT NOT NULL,
#         bucket_start TIMESTAMP NOT NULL,

#         count INTEGER NOT NULL,
#         min REAL NOT NULL,
#         max REAL NOT NULL,
#         sum REAL NOT NULL,
#         avg REAL NOT NULL,

#         PRIMARY KEY (agent_id, metric_name, bucket_start)
#         );
#     """)

#     #1h roll up
#     cursor.execute("""
#     CREATE TABLE IF NOT EXISTS metric_numeric_1h (
#     agent_id TEXT NOT NULL,
#     metric_name TEXT NOT NULL,
#     bucket_start TIMESTAMP NOT NULL,

#     count INTEGER NOT NULL,
#     min REAL NOT NULL,
#     max REAL NOT NULL,
#     sum REAL NOT NULL,
#     avg REAL NOT NULL,

#     PRIMARY KEY (agent_id, metric_name, bucket_start)
#     );
#     """)


#     #Indexes
#     conn.execute("""
#         CREATE INDEX IF NOT EXISTS idx_metric_raw_time
#         ON metric_numeric (timestamp);""")

#     conn.execute("""
#         CREATE INDEX IF NOT EXISTS idx_metric_1m_time
#         ON metric_numeric_1m (bucket_start);""")

#     conn.execute("""
#         CREATE INDEX IF NOT EXISTS idx_metric_10m_time
#         ON metric_numeric_10m (bucket_start);
#     """)

#     conn.commit()
#     conn.close()