import structlog
import logging

logging.basicConfig(level=logging.INFO)

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)

def get_logger(name : str = 'Agent'):
    return structlog.get_logger(name)

