from collections import defaultdict

from server_db.conncetion import get_db
from anomaly.baseAnomaly import BaseAnomaly
from ticket_service.ticketService import TicketService
from anomaly.const import AVA_METRIC_TABLES, AVA_ATTRIBUTES
from anomaly.anomalyService import AnomalyService


class ZScoreAnomaly(BaseAnomaly):
    detector_name = "zscore_v1"

    def __init__(
        self,
        agent_id: str,
        metrics: list,
        window: int = 30,
        table: str = "metric_numeric_10m",
        on: str = "avg",
    ):
        self.agent_id = agent_id
        self.metrics = metrics
        self.window = window

        self.table = table if table in AVA_METRIC_TABLES else "metric_numeric_10m"
        self.on = on if on in AVA_ATTRIBUTES else "avg"

    def _get_agent_metrics(self):
        if not self.metrics:
            return []

        conn = get_db()
        cursor = conn.cursor()

        placeholders = ",".join(["?"] * len(self.metrics))

        query = f"""
            SELECT metric_name, {self.on} AS value, bucket_start
            FROM {self.table}
            WHERE agent_id = ?
            AND metric_name IN ({placeholders})
            ORDER BY metric_name, bucket_start DESC
        """

        cursor.execute(query, (self.agent_id, *self.metrics))
        rows = cursor.fetchall()
        conn.close()

        return rows

    def detect_anomaly(self):

        rows = self._get_agent_metrics()

        if not rows:
            return None

        grouped = defaultdict(list)
        for row in rows:
            grouped[row["metric_name"]].append(row)

        results = []

        for metric, metric_rows in grouped.items():
            if len(metric_rows) < max(self.window, 10):
                continue

            metric_rows = metric_rows[: self.window]

            latest_bucket = metric_rows[0]["bucket_start"]

            row = AnomalyService.selectOne(
                self.table, self.detector_name
            )

            if row and row[0] == latest_bucket:
                continue

            meta = self._calc_Z_score(metric_rows, metric)

            if meta:
                AnomalyService.insertOrReplace(
                    self.table,
                    self.detector_name,
                    self.agent_id,
                    metric,
                    latest_bucket,
                )
                results.append(meta)

        return results if results else None

    def _calc_Z_score(self, rows, metric):

        values = [r["value"] for r in rows]

        current = values[0]
        history = values[1:]

        if len(history) < 2:
            return None

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
            metric_name=metric,
            severity=severity,
            anomaly_type="zscore",
            metadata=str(
                {
                    "current_value": current,
                    "baseline_value": mean,
                    "deviation": z,
                }
            ),
            message=f"Z-score anomaly detected (z={round(z, 2)})",
        )

        return {
            "metric": metric,
            "z": z,
            "severity": severity,
        }
