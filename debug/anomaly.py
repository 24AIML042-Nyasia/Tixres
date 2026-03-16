from datetime import datetime, timedelta
from server_db.connection import get_db
import random

def get_agent_z_score_metric_mapping() -> dict :
    return {
        "agent_Pmx0GZGOc4z2-F1rw9V3nw" : ['process_v1.0.0.zombie_count ',
                                           'system_v1.0.0.process_count', 
                                           'process_v1.0.0.total_threads' ,
                                           'cpu_v1.0.0.usage_overall',
                                           'cpu_usage_v1_percent']
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
