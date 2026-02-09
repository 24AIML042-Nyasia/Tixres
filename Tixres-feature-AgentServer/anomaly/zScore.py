from server_db.connection import get_db
from anomaly.baseAnomaly import BaseAnomaly
from ticket_service.ticketService import TicketService
from anomaly.const import AVA_METRIC_TABLES , AVA_ATTRIBUTES
from anomaly.anomalyService import AnomalyService

class ZScoreAnomaly(BaseAnomaly):
    detector_name = 'zscore_v1'

    def __init__(self, agent_id: str, metric: str, window: int = 30, table : str = 'metric_numeric_10m', on : str = 'avg'):
        self.agent_id = agent_id
        self.metric = metric
        self.window = window

        if table in AVA_METRIC_TABLES:
            self.table = table
        else :
            self.table = 'metric_numeric_10m'

        if on in AVA_ATTRIBUTES:
            self.on = on
        else:
            self.on = 'avg'

    def detect_anomaly(self):
        conn = get_db()
        cursor = conn.cursor()

        query = f"""
            SELECT {self.on}, bucket_start
            FROM {self.table}
            WHERE agent_id = ?
            AND metric_name = ?
            ORDER BY bucket_start DESC
            LIMIT ?
        """

        cursor.execute(query, (self.agent_id, self.metric, self.window))

        rows = cursor.fetchall()

        if len(rows) < 10:
            return None

        latest_bucket = rows[0]["bucket_start"]

        row = AnomalyService.selectOne(self.table, self.detector_name)

        if row and row[0] == latest_bucket:
            return None
        
        meta = self._calc_Z_score(rows)

        AnomalyService.insertOrReplace(self.table, self.detector_name, latest_bucket)

        conn.close()

        return meta
        
    def _calc_Z_score(self, rows):
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
