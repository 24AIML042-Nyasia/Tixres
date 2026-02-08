from server_db.conncetion import get_db
from anomaly.baseAnomaly import BaseAnomaly
from ticket_service.ticketService import TicketService

class ZScoreAnomaly(BaseAnomaly):
    def __init__(self, agent_id: str, metric: str, window: int = 30):
        self.agent_id = agent_id
        self.metric = metric
        self.window = window

    def detect_anomaly(self):
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT value
            FROM metric_numeric
            WHERE agent_id = ? AND metric_name = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (self.agent_id, self.metric, self.window))

        rows = cursor.fetchall()

        for row in rows:
            print(dict(row))
            
        conn.close()

        if len(rows) < 10:
            return None

        values = [r[0] for r in rows]
        current = values[0]
        history = values[1:]

        mean = sum(history) / len(history)
        variance = sum((x - mean) ** 2 for x in history) / (len(history) - 1)
        std = variance ** 0.5

        if std == 0:
            return None

        z = (current - mean) / std
        az = abs(z)

        severity = None
        if az >= 4:
            severity = "P2"
        elif az >= 3:
            severity = "P3"
        elif az >= 2:
            severity = "P3"
        elif az >= 1.5:
            severity = "P4"

        if not severity:
            return None

        TicketService.create_ticket(
            agent_id=self.agent_id,
            metric_name=self.metric,
            severity=severity,
            anomaly_type="zscore",
            metadata= str({
                'current_value':current,
                'baseline_value':mean,
                'deviation':z}),
            message=f"Z-score anomaly detected (z={round(z,2)})"
        )

        return {
            "z": z,
            "severity": severity
        }
