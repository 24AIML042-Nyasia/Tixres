from datetime import datetime, timedelta
from server_db.conncetion import get_db
import random

def insert_zscore_10m_cpu_data():
    conn = get_db()
    cursor = conn.cursor()

    query = """
        INSERT OR REPLACE INTO metric_numeric_10m
        (agent_id, metric_name, bucket_start, count, min, max, sum, avg)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """

    agent_id = "agent_TrxsBcR6m-O97zHx48Om7Q"
    metric_name = "cpu_v1.0.0.usage_overall"

    now = datetime.now().replace(second=0, microsecond=0)
    rows = []

    # 27 NORMAL buckets (avg ≈ 15)
    for i in range(27):
        avg = round(random.uniform(14.8, 15.2), 2)
        count = 10
        rows.append((
            agent_id,
            metric_name,
            (now - timedelta(minutes=(30 - i) * 10)).strftime("%Y-%m-%d %H:%M:00"),
            count,
            avg - 0.5,
            avg + 0.5,
            avg * count,
            avg
        ))

    # Mild anomaly (Z ≈ 2–3)
    rows.append((
        agent_id,
        metric_name,
        (now - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:00"),
        10,
        25.0,
        26.0,
        255.0,
        25.5
    ))

    # 🔥 EXTREME anomaly (Z >> 4)
    rows.append((
        agent_id,
        metric_name,
        now.strftime("%Y-%m-%d %H:%M:00"),
        10,
        450.0,
        520.0,
        4900.0,
        490.0
    ))

    cursor.executemany(query, rows)
    conn.commit()
    conn.close()

def get_agent_z_score_metric_mapping() -> dict :
    return {
        "agent_TrxsBcR6m-O97zHx48Om7Q" : ["cpu_v1.0.0.usage_overall"]
    }



# from datetime import datetime, timedelta
# from server_db.conncetion import get_db
# import random

# def insert_zscore_cpu_data():
#     conn = get_db()
#     cursor = conn.cursor()

#     query = """
#         INSERT INTO metric_numeric (agent_id, metric_name, value, timestamp)
#         VALUES (?, ?, ?, ?)
#     """

#     agent_id = "agent_TrxsBcR6m-O97zHx48Om7Q"
#     metric_name = "cpu_v1.0.0.usage_overall"

#     now = datetime.now()
#     rows = []

#     # 27 normal points (mean ~15)
#     for i in range(27):
#         rows.append((
#             agent_id,
#             metric_name,
#             round(random.uniform(14.5, 15.5), 2),
#             (now - timedelta(minutes=30 - i)).strftime("%Y-%m-%d %H:%M:%S")
#         ))

#     # anomalies
#     rows.append((agent_id, metric_name, 4.1,  (now - timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S")))
#     rows.append((agent_id, metric_name, 52.3, (now - timedelta(minutes=11)).strftime("%Y-%m-%d %H:%M:%S")))
#     rows.append((agent_id, metric_name, 480.7, (now).strftime("%Y-%m-%d %H:%M:%S")))

#     cursor.executemany(query, rows)

#     conn.commit()
