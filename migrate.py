from server_db.migration import run_migrations
from server_db.connection import engine
from server_db.models import MetricNumeric10m, MetricNumeric1h, MetricNumeric1m
# run_migrations()

# MetricNumeric1m.__table__.drop(engine)
# MetricNumeric10m.__table__.drop(engine)
# MetricNumeric1h.__table__.drop(engine)