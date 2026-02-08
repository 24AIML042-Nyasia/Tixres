from server_db.migration import migrate
from server_db.test import print_rollup_rows
from server_db.models import one_min_roll_up,one_hour_roll_up,ten_min_roll_up
from server_db.conncetion import get_db
import asyncio



conn = get_db()
cursor = conn.cursor()


cursor.execute('SELECT * FROM metric_numeric')

for row in cursor.fetchall():
    print(dict(row))

# async def fn():
#     await one_min_roll_up()
#     await one_hour_roll_up()
#     await ten_min_roll_up()
    
#     await asyncio.sleep(60)

# asyncio.run(fn())
# # migrate()




asyncio.run(one_min_roll_up())
asyncio.run(one_hour_roll_up())
asyncio.run(ten_min_roll_up())

print_rollup_rows()