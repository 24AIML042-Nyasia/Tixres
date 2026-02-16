from server_db.connection import SessionLocal
from server_db.models import MetricJson , MetricNumeric

db = SessionLocal()

from sqlalchemy import func, and_

# Subquery: get latest timestamp per metric_name
subq = (
    db.query(
        MetricNumeric.metric_name,
        func.max(MetricNumeric.timestamp).label("max_ts")
    )
    .group_by(MetricNumeric.metric_name)
    .subquery()
)

# Join back to get full rows
rows = (
    db.query(MetricNumeric)
    .join(
        subq,
        and_(
            MetricNumeric.metric_name == subq.c.metric_name,
            MetricNumeric.timestamp == subq.c.max_ts
        )
    )
    .all()
)

for r in rows:
    print(r.to_dict())


# for r in db.query(MetricNumeric).all():
#     print(r.to_dict())