from server_db.connection import SessionLocal
from server_db.models import MetricJson , MetricNumeric

db = SessionLocal()

for r in db.query(MetricJson).all():
    print((r.to_dict()))

# for r in db.query(MetricNumeric).all():
#     print(r.to_dict())