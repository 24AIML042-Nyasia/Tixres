from collections import defaultdict
from sqlalchemy import text

from server_db.connection import SessionLocal
from anomaly.baseAnomaly import BaseAnomaly
from ticket_service.ticketService import TicketService
from anomaly.const import AVA_METRIC_TABLES, AVA_ATTRIBUTES
from anomaly.anomalyService import AnomalyService
from influx_db.connection import InfluxDBService


class ZScoreAnomaly(BaseAnomaly):
    detector_name = "zscore_v1"

    def __init__(
        self,
        agent_id: str,
        metrics: list,
        window: int = 30,
        measurement: str = "metric_numeric_10m",
        on: str = "avg",
    ):
        self.agent_id = agent_id
        self.metrics = metrics
        self.window = window

        self.measurement = measurement if measurement in AVA_METRIC_TABLES else "metric_numeric_10m"
        self.on = on if on in AVA_ATTRIBUTES else "avg"

        def _get_agent_metrics(self):
            if not self.metrics:
                return []

            metrics_filter = " or ".join(
                [f'r["metric"] == "{m}"' for m in self.metrics]
            )

            query = f'''
            from(bucket: "{InfluxDBService.getBucket()}")
            |> range(start: -7d)
            |> filter(fn: (r) => r["_measurement"] == "{self.measurement}")
            |> filter(fn: (r) => r["agent_id"] == "{self.agent_id}")
            |> filter(fn: (r) => {metrics_filter})
            |> filter(fn: (r) => r["_field"] == "{self.on}")
            |> sort(columns: ["_time"], desc: true)
            '''

            result = InfluxDBService.getQueryApi(
                InfluxDBService.getClient()).query(query, org=self.org)

            rows = []

            for table in result:
                for record in table.records:
                    rows.append({
                        "metric_name": record["metric"],
                        "value": record.get_value(),
                        "bucket_start": record.get_time()
                    })

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
                self.measurement,
                self.detector_name,
                self.agent_id,
                metric
            )

            if row and row[0] == latest_bucket:
                continue

            meta = self._calc_Z_score(metric_rows, metric)

            if meta:
                AnomalyService.insertOrReplace(
                    self.measurement,
                    self.detector_name,
                    self.agent_id,
                    metric,
                    str(latest_bucket),
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

        print(az)

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
            detector="zscore",
            meta=str(
                {
                    "current_value": current,
                    "baseline_value": mean,
                    "deviation": z,
                    "table" : self.measurement
                }
            ),
            message=f"Z-score anomaly detected (z={round(z, 2)})",
        )

        return {
            "metric": metric,
            "z": z,
            "severity": severity,
        }