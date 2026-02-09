from server_db.connection import get_db

class AnomalyService:
    @staticmethod
    def migrate_anomaly_service():
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS anomaly_state (
                table_name   TEXT NOT NULL,
                detector     TEXT NOT NULL,
                last_bucket  TEXT NOT NULL,
                PRIMARY KEY (table_name, detector)
            );""")

        conn.commit()
        conn.close()


    @staticmethod
    def insertOrReplace(table,detector, latest_bucket):
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO anomaly_state (table_name, detector, last_bucket)
            VALUES (?, ?, ?);""",
            (table,detector, latest_bucket))

        conn.commit()
        conn.close()

    @staticmethod
    def selectOne(table, detector):
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT last_bucket
            FROM anomaly_state
            WHERE table_name = ?
            AND detector = ?;""",
            (table, detector))

        row =  cursor.fetchone()

        conn.close()

        return row
