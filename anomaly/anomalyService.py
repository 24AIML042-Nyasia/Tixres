from server_db.conncetion import get_db


class AnomalyService:
    @staticmethod
    def migrate_anomaly_service():
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS anomaly_state (
                table_name   TEXT NOT NULL,
                detector     TEXT NOT NULL,
                agent_id     TEXT NOT NULL,
                metric_name  TEXT NOT NULL,
                last_bucket  TEXT NOT NULL,
                PRIMARY KEY (table_name, detector, agent_id, metric_name)
            );
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_anomaly_lookup
            ON anomaly_state (table_name, detector, agent_id, metric_name);
        """)

        conn.commit()
        conn.close()

    @staticmethod
    def insertOrReplace(table, detector, agent_id, metric_name, latest_bucket):
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO anomaly_state
            (table_name, detector, agent_id, metric_name, last_bucket)
            VALUES (?, ?, ?, ?, ?);
        """,
        (table, detector, agent_id, metric_name, latest_bucket))

        conn.commit()
        conn.close()

    @staticmethod
    def selectOne(table, detector, agent_id, metric_name):
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT last_bucket
            FROM anomaly_state
            WHERE table_name = ?
            AND detector = ?
            AND agent_id = ?
            AND metric_name = ?;
        """,
        (table, detector, agent_id, metric_name))

        row = cursor.fetchone()
        conn.close()

        return row
