from server_db.connection import engine, Base
from server_db.models import (
    AgentCredentials, Agent, MetricNumeric, MetricJson,
    MetricNumeric1m, MetricNumeric10m, MetricNumeric1h)
    
from anomaly.models import AnomalyState
from ticket_service.models import Ticket

from server_utils.logger import get_logger

logger = get_logger()

def run_migrations():
    logger.info("Starting database migrations...")
    
    Base.metadata.create_all(bind=engine)
    
    logger.info("Tables created:")
    for table in Base.metadata.sorted_tables:
        logger.info(f"  - {table.name}")
    
    logger.info("Database migrations completed successfully!")
