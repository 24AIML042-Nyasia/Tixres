import re
from datetime import datetime, timedelta, timezone
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from sqlalchemy import text
from server_db.connection import SessionLocal
from settings import METRIC_REGEX_PATTERN
from metric_rollup.rollUpStateService import RollupStateService
from server_utils.logger import get_logger
from influx_db.connection import InfluxDBService
from influx_db.const import (
    MEASUREMENT_1M ,
    MEASUREMENT_10M ,
    MEASUREMENT_1H ,

    TAG_AGENT_ID ,
    TAG_METRIC ,
    TAG_VERSION,
    TAG_UNIT ,

    FIELD_COUNT,
    FIELD_MIN,
    FIELD_MAX,
    FIELD_SUM,
    FIELD_AVG ,
    FIELD_BUCKET_START ,

    SOURCE_POSTGRES,
    SOURCE_1M ,
    SOURCE_10M 
)

pattern = re.compile(METRIC_REGEX_PATTERN)
logger = get_logger()


class InfluxDBRollup:
    def __init__(self):
        self.client = InfluxDBService.getClient()
        self.write_api = InfluxDBService.getWriteApiSync(self.client)
        self.query_api = InfluxDBService.getQueryApi(self.client)
        self.org = InfluxDBService.getOrg()
        self.bucket = InfluxDBService.getBucket()

    def _parse_metric_name(self, metric_name):
        match = pattern.match(metric_name)
        if not match:
            return None
        return {
            "metric": match.group("metric"),
            "version": match.group("version"),
            "unit": match.group("unit"),
        }

    def _create_point(
        self,
        measurement,
        agent_id,
        metric,
        version,
        unit,
        bucket_start,
        count,
        min_val,
        max_val,
        sum_val,
    ):
        if count == 0:
            return None

        avg = sum_val / count

        return (
            Point(measurement)
            .tag(TAG_AGENT_ID, agent_id)
            .tag(TAG_METRIC, metric)
            .tag(TAG_VERSION, version)
            .tag(TAG_UNIT, unit)
            .field(FIELD_COUNT, int(count))
            .field(FIELD_MIN, float(min_val))
            .field(FIELD_MAX, float(max_val))
            .field(FIELD_SUM, float(sum_val))
            .field(FIELD_AVG, float(avg))
            .field(FIELD_BUCKET_START, bucket_start.isoformat())
            .time(bucket_start)
        )

    def _write_points(self, points):
        if points:
            self.write_api.write(bucket=self.bucket, record=points, org=self.org)

    async def one_min_roll_up(self):
        db = SessionLocal()
        try:
            last_bucket = RollupStateService.get_last_bucket(
                db, SOURCE_POSTGRES, MEASUREMENT_1M
            )

            if last_bucket is None:
                last_bucket = datetime.now(timezone.utc) - timedelta(hours=1)

            result = db.execute(
                text(
                    """
                SELECT
                    agent_id,
                    metric_name,
                    date_trunc('minute', timestamp) AS bucket_start,
                    COUNT(*) AS count,
                    MIN(value) AS min,
                    MAX(value) AS max,
                    SUM(value) AS sum
                FROM metric_numeric
                WHERE timestamp > :last_bucket
                GROUP BY agent_id, metric_name, bucket_start
                ORDER BY bucket_start ASC
            """
                ),
                {"last_bucket": last_bucket},
            )

            rows = result.fetchall()
            if not rows:
                return

            points = []
            max_bucket = last_bucket

            for row in rows:
                parsed = self._parse_metric_name(row.metric_name)
                if not parsed:
                    continue

                bucket_start = row.bucket_start.replace(tzinfo=timezone.utc)

                point = self._create_point(
                    MEASUREMENT_1M,
                    row.agent_id,
                    parsed["metric"],
                    parsed["version"],
                    parsed["unit"],
                    bucket_start,
                    row.count,
                    row.min,
                    row.max,
                    row.sum,
                )

                if point:
                    points.append(point)

                if bucket_start > max_bucket:
                    max_bucket = bucket_start

            self._write_points(points)

            RollupStateService.update_last_bucket(
                db, SOURCE_POSTGRES, MEASUREMENT_1M, max_bucket
            )
            db.commit()

        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    async def ten_min_roll_up(self):
        db = SessionLocal()
        try:
            last_bucket = RollupStateService.get_last_bucket(
                db, SOURCE_1M, MEASUREMENT_10M
            )

            if last_bucket is None:
                last_bucket = datetime.now(timezone.utc) - timedelta(hours=2)

            start_time = last_bucket.isoformat()

            query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: time(v: "{start_time}"))
                |> filter(fn: (r) => r._measurement == "{MEASUREMENT_1M}")
                |> filter(fn: (r) =>
                    r._field == "count" or
                    r._field == "sum" or
                    r._field == "min" or
                    r._field == "max"
                )
                |> filter(fn: (r) => r._time > time(v: "{start_time}"))
            '''

            results = self.query_api.query(query, org=self.org)

            grouped = {}
            max_bucket = last_bucket

            for table in results:
                for record in table.records:
                    agent_id = record[TAG_AGENT_ID]
                    metric = record[TAG_METRIC]
                    version = record[TAG_VERSION]
                    unit = record[TAG_UNIT]
                    timestamp = record.get_time()

                    bucket_start = timestamp.replace(
                        minute=(timestamp.minute // 10) * 10,
                        second=0,
                        microsecond=0,
                    )

                    key = (agent_id, metric, version, unit, bucket_start)

                    if key not in grouped:
                        grouped[key] = {
                            "count": 0,
                            "sum": 0.0,
                            "min": float("inf"),
                            "max": float("-inf"),
                        }

                    field = record.get_field()
                    value = record.get_value()

                    if field == FIELD_COUNT:
                        grouped[key]["count"] += int(value)
                    elif field == FIELD_SUM:
                        grouped[key]["sum"] += float(value)
                    elif field == FIELD_MIN:
                        grouped[key]["min"] = min(grouped[key]["min"], float(value))
                    elif field == FIELD_MAX:
                        grouped[key]["max"] = max(grouped[key]["max"], float(value))

                    if timestamp > max_bucket:
                        max_bucket = timestamp

            points = []

            for (agent_id, metric, version, unit, bucket_start), values in grouped.items():
                point = self._create_point(
                    MEASUREMENT_10M,
                    agent_id,
                    metric,
                    version,
                    unit,
                    bucket_start,
                    values["count"],
                    values["min"],
                    values["max"],
                    values["sum"],
                )
                if point:
                    points.append(point)

            self._write_points(points)

            RollupStateService.update_last_bucket(
                db, SOURCE_1M, MEASUREMENT_10M, max_bucket
            )
            db.commit()

        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    async def one_hour_roll_up(self):
        db = SessionLocal()
        try:
            last_bucket = RollupStateService.get_last_bucket(
                db, SOURCE_10M, MEASUREMENT_1H
            )

            if last_bucket is None:
                last_bucket = datetime.now(timezone.utc) - timedelta(hours=4)

            start_time = last_bucket.isoformat()

            query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: time(v: "{start_time}"))
                |> filter(fn: (r) => r._measurement == "{MEASUREMENT_10M}")
                |> filter(fn: (r) =>
                    r._field == "count" or
                    r._field == "sum" or
                    r._field == "min" or
                    r._field == "max"
                )
                |> filter(fn: (r) => r._time > time(v: "{start_time}"))
            '''

            results = self.query_api.query(query, org=self.org)

            grouped = {}
            max_bucket = last_bucket

            for table in results:
                for record in table.records:
                    agent_id = record[TAG_AGENT_ID]
                    metric = record[TAG_METRIC]
                    version = record[TAG_VERSION]
                    unit = record[TAG_UNIT]
                    timestamp = record.get_time()

                    bucket_start = timestamp.replace(
                        minute=0,
                        second=0,
                        microsecond=0,
                    )

                    key = (agent_id, metric, version, unit, bucket_start)

                    if key not in grouped:
                        grouped[key] = {
                            "count": 0,
                            "sum": 0.0,
                            "min": float("inf"),
                            "max": float("-inf"),
                        }

                    field = record.get_field()
                    value = record.get_value()

                    if field == FIELD_COUNT:
                        grouped[key]["count"] += int(value)
                    elif field == FIELD_SUM:
                        grouped[key]["sum"] += float(value)
                    elif field == FIELD_MIN:
                        grouped[key]["min"] = min(grouped[key]["min"], float(value))
                    elif field == FIELD_MAX:
                        grouped[key]["max"] = max(grouped[key]["max"], float(value))

                    if timestamp > max_bucket:
                        max_bucket = timestamp

            points = []

            for (agent_id, metric, version, unit, bucket_start), values in grouped.items():
                point = self._create_point(
                    MEASUREMENT_1H,
                    agent_id,
                    metric,
                    version,
                    unit,
                    bucket_start,
                    values["count"],
                    values["min"],
                    values["max"],
                    values["sum"],
                )
                if point:
                    points.append(point)

            self._write_points(points)

            RollupStateService.update_last_bucket(
                db, SOURCE_10M, MEASUREMENT_1H, max_bucket
            )
            db.commit()

        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def close(self):
        self.client.close()


    def __del__(self):
        self.close()
