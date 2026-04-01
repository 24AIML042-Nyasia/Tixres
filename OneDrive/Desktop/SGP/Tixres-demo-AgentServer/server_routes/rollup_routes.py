import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from server_db.connection import get_db
from server_db.models import MetricNumeric
from influx_db.const import MEASUREMENT_1M, MEASUREMENT_10M, MEASUREMENT_1H
from settings import METRIC_REGEX_PATTERN

try:
    from influx_db.connection import InfluxDBService  # type: ignore
except Exception:  # pragma: no cover - optional dep
    InfluxDBService = None  # type: ignore


router = APIRouter(prefix="/api/rollups", tags=["Rollups"])

_MEASUREMENT_MAP = {
    "1m": (MEASUREMENT_1M, 1),
    "10m": (MEASUREMENT_10M, 10),
    "1h": (MEASUREMENT_1H, 60),
}

_METRIC_PATTERN = re.compile(METRIC_REGEX_PATTERN)


def _parse_measurement(measurement: str):
    normalized = measurement.lower()
    if normalized not in _MEASUREMENT_MAP:
        raise HTTPException(status_code=400, detail="measurement must be one of 1m, 10m, 1h")
    return _MEASUREMENT_MAP[normalized]


def _parse_metric(metric_name: Optional[str]):
    if not metric_name:
        return None
    match = _METRIC_PATTERN.match(metric_name)
    if not match:
        raise HTTPException(status_code=400, detail="metric_name must match METRIC_REGEX_PATTERN")
    return {
        "metric": match.group("metric"),
        "version": match.group("version"),
        "unit": match.group("unit"),
    }


def _bucket_start(ts: datetime, bucket_minutes: int) -> datetime:
    ts = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    trimmed = ts.replace(second=0, microsecond=0)
    if bucket_minutes == 10:
        return trimmed - timedelta(minutes=trimmed.minute % 10)
    if bucket_minutes == 60:
        return trimmed.replace(minute=0)
    return trimmed


def _query_influx_rollups(
    agent_id: str,
    measurement_name: str,
    bucket_minutes: int,
    metric_filters: Optional[dict],
    start_dt: datetime,
):
    if InfluxDBService is None:
        return None
    try:
        bucket = InfluxDBService.getBucket()
        org = InfluxDBService.getOrg()
        if not bucket or not org:
            return None

        client = InfluxDBService.getClient()
        query_api = InfluxDBService.getQueryApi(client)

        metric_clause = ""
        if metric_filters:
            metric_clause = (
                f'|> filter(fn: (r) => r.metric == "{metric_filters["metric"]}" '
                f'and r.version == "{metric_filters["version"]}" '
                f'and r.unit == "{metric_filters["unit"]}")'
            )

        query = f"""
        from(bucket: "{bucket}")
            |> range(start: time(v: "{start_dt.isoformat()}"))
            |> filter(fn: (r) => r._measurement == "{measurement_name}")
            |> filter(fn: (r) => r.agent_id == "{agent_id}")
            {metric_clause}
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
            |> keep(columns: ["_time","count","min","max","sum","avg","bucket_start","metric","version","unit","agent_id"])
            |> sort(columns: ["_time"])
        """
        result = query_api.query(query, org=org)

        points = []
        for table in result:
            for record in table.records:
                values = record.values
                bucket_start = record.get_time()
                points.append(
                    {
                        "bucket_start": bucket_start.isoformat() if bucket_start else values.get("bucket_start"),
                        "count": values.get("count"),
                        "min": values.get("min"),
                        "max": values.get("max"),
                        "sum": values.get("sum"),
                        "avg": values.get("avg"),
                        "metric": values.get("metric"),
                        "version": values.get("version"),
                        "unit": values.get("unit"),
                        "source": "influx",
                    }
                )

        client.close()
        return points
    except Exception:
        return None


def _query_sql_rollups(
    db: Session,
    agent_id: str,
    bucket_minutes: int,
    metric_name: Optional[str],
    start_dt: datetime,
):
    # SQLite stores naive timestamps — strip tz before comparing
    from sqlalchemy import inspect as sa_inspect
    dialect = db.bind.dialect.name if db.bind else ""
    if dialect == "sqlite" and start_dt.tzinfo is not None:
        start_dt = start_dt.replace(tzinfo=None)

    query = db.query(MetricNumeric).filter(MetricNumeric.agent_id == agent_id)
    if metric_name:
        query = query.filter(MetricNumeric.metric_name == metric_name)
    if start_dt:
        query = query.filter(MetricNumeric.timestamp >= start_dt)

    rows = query.all()
    buckets = {}
    for row in rows:
        ts = row.timestamp if row.timestamp.tzinfo else row.timestamp.replace(tzinfo=timezone.utc)
        bucket = _bucket_start(ts, bucket_minutes)
        stats = buckets.setdefault(
            bucket, {"count": 0, "sum": 0.0, "min": float("inf"), "max": float("-inf")}
        )
        stats["count"] += 1
        stats["sum"] += float(row.value)
        stats["min"] = min(stats["min"], float(row.value))
        stats["max"] = max(stats["max"], float(row.value))

    points = []
    for bucket, stats in sorted(buckets.items()):
        if stats["count"] == 0:
            continue
        points.append(
            {
                "bucket_start": bucket.isoformat(),
                "count": stats["count"],
                "min": stats["min"],
                "max": stats["max"],
                "sum": stats["sum"],
                "avg": stats["sum"] / stats["count"],
                "metric": metric_name,
                "source": "sqlite",
            }
        )
    return points


@router.get("/{agent_id}")
def get_rollup_series(
    agent_id: str,
    measurement: str = Query("1m", description="One of 1m,10m,1h"),
    metric_name: Optional[str] = Query(None, description="Filter to a specific metric_name"),
    start_minutes: int = Query(240, ge=1, le=4320, description="Lookback window in minutes"),
    db: Session = Depends(get_db),
):
    """
    Fetch rollup data for an agent from Influx if configured, otherwise aggregate from metric_numeric.
    """
    measurement_name, bucket_minutes = _parse_measurement(measurement)
    metric_filters = _parse_metric(metric_name)
    start_dt = datetime.now(timezone.utc) - timedelta(minutes=start_minutes)

    points = _query_influx_rollups(agent_id, measurement_name, bucket_minutes, metric_filters, start_dt)
    source = "influx" if points is not None else "sqlite"

    if points is None:
        points = _query_sql_rollups(db, agent_id, bucket_minutes, metric_name, start_dt)

    return {
        "agent_id": agent_id,
        "measurement": measurement,
        "metric_name": metric_name,
        "start": start_dt.isoformat(),
        "points": points,
        "source": source,
    }
