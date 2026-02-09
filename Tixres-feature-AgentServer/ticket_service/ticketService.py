from server_db.connection import get_db
from datetime import datetime

class TicketService:
    @staticmethod
    def create_ticket(
        agent_id: str,
        metric_name: str,
        severity: str,
        anomaly_type: str,
        metadata : str,
        message: str
    ):
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO tickets (
                agent_id, metric_name,
                severity, anomaly_type, metadata,
                message, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            agent_id, metric_name,
            severity, anomaly_type,metadata, message, datetime.now()
        ))

        conn.commit()
        conn.close()

    @staticmethod
    def get_Tickets(limit = 100) -> list:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM tickets LIMIT 100;
        """)

        return cursor.fetchall()

