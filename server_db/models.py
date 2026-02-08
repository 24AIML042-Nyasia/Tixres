from server_db.conncetion import get_db

async def one_min_roll_up():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO metric_numeric_1m
        SELECT
            agent_id,
            metric_name,
            datetime(strftime('%Y-%m-%d %H:%M:00', timestamp)) AS bucket_start,

            COUNT(*) AS count,
            MIN(value) AS min,
            MAX(value) AS max,
            SUM(value) AS sum,
            AVG(value) AS avg
        FROM metric_numeric
        WHERE timestamp >= (
            SELECT datetime(MAX(timestamp), '-1 minutes')
            FROM metric_numeric
        )
        GROUP BY agent_id, metric_name, bucket_start;
    """)

    conn.commit()
    conn.close()

async def ten_min_roll_up():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO metric_numeric_10m
        SELECT
            agent_id,
            metric_name,
            datetime(
                strftime('%Y-%m-%d %H:', bucket_start) ||
                printf('%02d', (strftime('%M', bucket_start) / 10) * 10) ||
                ':00'
            ) AS bucket_start,

            SUM(count) AS count,
            MIN(min) AS min,
            MAX(max) AS max,
            SUM(sum) AS sum,
            SUM(sum) / SUM(count) AS avg
        FROM metric_numeric_1m
        WHERE bucket_start >=  (
            SELECT datetime(MAX(timestamp), '-10 minutes')
            FROM metric_numeric
        )
        GROUP BY agent_id, metric_name, bucket_start;
    """)

    conn.commit()
    conn.close()

async def one_hour_roll_up():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO metric_numeric_1h
        SELECT
            agent_id,
            metric_name,
            datetime(strftime('%Y-%m-%d %H:00:00', bucket_start)) AS bucket_start,

            SUM(count) AS count,
            MIN(min) AS min,
            MAX(max) AS max,
            SUM(sum) AS sum,
            SUM(sum) / SUM(count) AS avg
        FROM metric_numeric_10m
        WHERE bucket_start >=  (
            SELECT datetime(MAX(timestamp), '-1 hour')
            FROM metric_numeric
        )
        GROUP BY agent_id, metric_name, bucket_start;
    """)

    conn.commit()
    conn.close()

def one_minutes_metric():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""SELECT * FROM metric_numeric_1m;  
    """)

    return cursor.fetchall()


def ten_minutes_metric():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""SELECT * FROM metric_numeric_10m;  
    """)

    return cursor.fetchall()


def one_hour_metric():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""SELECT * FROM metric_numeric_1h;  
    """)

    return cursor.fetchall()

def retention_policy():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM metric_numeric
        WHERE timestamp < datetime('now', '-7 days');""")

    cursor.execute("""          
        DELETE FROM metric_numeric_1m
        WHERE bucket_start < datetime('now', '-30 days');""")

    cursor.execute("""
        DELETE FROM metric_numeric_10m
        WHERE bucket_start < datetime('now', '-90 days');
    """)


