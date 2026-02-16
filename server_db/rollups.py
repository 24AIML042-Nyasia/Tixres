from sqlalchemy import text
from server_db.connection import SessionLocal

def retention_policy():
    db = SessionLocal()
    try:
        db.execute(text("""
            DELETE FROM metric_numeric
            WHERE timestamp < NOW() - INTERVAL '7 days'
        """))
        
        db.execute(text("""          
            DELETE FROM metric_numeric_1m
            WHERE bucket_start < NOW() - INTERVAL '30 days'
        """))
        
        db.execute(text("""
            DELETE FROM metric_numeric_10m
            WHERE bucket_start < NOW() - INTERVAL '90 days'
        """))
        
        db.commit()
    finally:
        db.close()