from sqlalchemy import Column, String, DateTime, func
from server_db.connection import Base

class RollupState(Base):
    __tablename__ = "rollup_state"

    source_table = Column(String, primary_key=True)
    target_table = Column(String, primary_key=True)

    last_bucket = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )
