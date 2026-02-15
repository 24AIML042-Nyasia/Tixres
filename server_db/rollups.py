from sqlalchemy import text
from server_db.connection import SessionLocal

async def one_min_roll_up():
    db = SessionLocal()
    try:
        db.execute(text("""
            INSERT INTO metric_numeric_1m (agent_id, metric_name, bucket_start, count, min, max, sum, avg)
            SELECT
                agent_id,
                metric_name,
                date_trunc('minute', timestamp) AS bucket_start,
                COUNT(*) AS count,
                MIN(value) AS min,
                MAX(value) AS max,
                SUM(value) AS sum,
                AVG(value) AS avg
            FROM metric_numeric
            WHERE timestamp >= (
                SELECT MAX(timestamp) - INTERVAL '1 minute'
                FROM metric_numeric
            )
            GROUP BY agent_id, metric_name, bucket_start
            ON CONFLICT (agent_id, metric_name, bucket_start) 
            DO UPDATE SET
                count = EXCLUDED.count,
                min = EXCLUDED.min,
                max = EXCLUDED.max,
                sum = EXCLUDED.sum,
                avg = EXCLUDED.avg
        """))
        db.commit()
    finally:
        db.close()

async def ten_min_roll_up():
    db = SessionLocal()
    try:
        db.execute(text("""
            INSERT INTO metric_numeric_10m (agent_id, metric_name, bucket_start, count, min, max, sum, avg)
            SELECT
                agent_id,
                metric_name,
                date_trunc('minute', bucket_start) - 
                    (EXTRACT(MINUTE FROM bucket_start)::int % 10) * INTERVAL '1 minute' AS bucket_start,
                SUM(count) AS count,
                MIN(min) AS min,
                MAX(max) AS max,
                SUM(sum) AS sum,
                SUM(sum) / SUM(count) AS avg
            FROM metric_numeric_1m
            WHERE bucket_start >= (
                SELECT MAX(timestamp) - INTERVAL '10 minutes'
                FROM metric_numeric
            )
            GROUP BY agent_id, metric_name, 
                date_trunc('minute', bucket_start) - 
                    (EXTRACT(MINUTE FROM bucket_start)::int % 10) * INTERVAL '1 minute'
            ON CONFLICT (agent_id, metric_name, bucket_start) 
            DO UPDATE SET
                count = EXCLUDED.count,
                min = EXCLUDED.min,
                max = EXCLUDED.max,
                sum = EXCLUDED.sum,
                avg = EXCLUDED.avg
        """))
        db.commit()
    finally:
        db.close()

async def one_hour_roll_up():
    db = SessionLocal()
    try:
        db.execute(text("""
            INSERT INTO metric_numeric_1h (agent_id, metric_name, bucket_start, count, min, max, sum, avg)
            SELECT
                agent_id,
                metric_name,
                date_trunc('hour', bucket_start) AS bucket_start,
                SUM(count) AS count,
                MIN(min) AS min,
                MAX(max) AS max,
                SUM(sum) AS sum,
                SUM(sum) / SUM(count) AS avg
            FROM metric_numeric_10m
            WHERE bucket_start >= (
                SELECT MAX(timestamp) - INTERVAL '1 hour'
                FROM metric_numeric
            )
            GROUP BY agent_id, metric_name, date_trunc('hour', bucket_start)
            ON CONFLICT (agent_id, metric_name, bucket_start) 
            DO UPDATE SET
                count = EXCLUDED.count,
                min = EXCLUDED.min,
                max = EXCLUDED.max,
                sum = EXCLUDED.sum,
                avg = EXCLUDED.avg
        """))
        db.commit()
    finally:
        db.close()

def one_minutes_metric():
    db = SessionLocal()
    try:
        result = db.execute(text("SELECT * FROM metric_numeric_1m"))
        return result.fetchall()
    finally:
        db.close()

def ten_minutes_metric():
    db = SessionLocal()
    try:
        result = db.execute(text("SELECT * FROM metric_numeric_10m"))
        return result.fetchall()
    finally:
        db.close()

def one_hour_metric():
    db = SessionLocal()
    try:
        result = db.execute(text("SELECT * FROM metric_numeric_1h"))
        return result.fetchall()
    finally:
        db.close()

def retention_policy():
    db = SessionLocal()
    try:
        db.execute(text("""
            DELETE FROM metric_numeric
            WHERE timestamp < NOW() - INTERVAL '7 days'
        """))
        
        db.execute(text("""          
            DELETE FROM metric_numeric_1m
            WHERE bucket_start < NOW() - INTERVAL '30 days'
        """))
        
        db.execute(text("""
            DELETE FROM metric_numeric_10m
            WHERE bucket_start < NOW() - INTERVAL '90 days'
        """))
        
        db.commit()
    finally:
        db.close()