from server_db.migration import migrate_ticket
from server_db.test import print_rollup_rows
from server_db.models import one_min_roll_up,one_hour_roll_up,ten_min_roll_up
from server_db.conncetion import get_db
from anomaly.zScore import ZScoreAnomaly
from ticket_service.ticketService import TicketService
from debug.anomaly import insert_zscore_10m_cpu_data
from anomaly.anomalyService import AnomalyService

import asyncio

# AnomalyService.migrate_anomaly_service()

conn = get_db()
cursor = conn.cursor()

# insert_zscore_10m_cpu_data()

# cursor.execute("DROP TABLE anomaly_state;")
# conn.commit()

AnomalyService.migrate_anomaly_service()


# cursor.execute("""
# SELECT *
# FROM metric_numeric_10m
# ORDER BY bucket_start DESC
# LIMIT 30;
# """)

# for row in cursor.fetchall():
#     print(dict(row))

detecter = ZScoreAnomaly('agent_TrxsBcR6m-O97zHx48Om7Q', ['cpu_v1.0.0.usage_overall'])
detecter.detect_anomaly()

print('Tickets')

for row in TicketService.get_Tickets():
    print(dict(row))

cursor.execute("""
SELECT *
FROM anomaly_state;
""")

for row in cursor.fetchall():
    print(dict(row))

# async def fn():
#     await one_min_roll_up()
#     await one_hour_roll_up()
#     await ten_min_roll_up()
    
#     await asyncio.sleep(60)

# asyncio.run(fn())
# # migrate()




# asyncio.run(one_min_roll_up())
# asyncio.run(one_hour_roll_up())
# asyncio.run(ten_min_roll_up())

# print_rollup_rows()