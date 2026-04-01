from sqlalchemy.orm import Session
from metric_rollup.models import RollupState
from datetime import datetime

class RollupStateService:
    @staticmethod
    def get_last_bucket(db: Session, source: str, target: str):
        state = (
            db.query(RollupState)
            .filter(
                RollupState.source_table == source,
                RollupState.target_table == target
            )
            .first()
        )

        return state.last_bucket if state else None

    @staticmethod
    def update_last_bucket(
        db: Session,
        source: str,
        target: str,
        bucket_time: datetime
    ):
        state = (
            db.query(RollupState)
            .filter(
                RollupState.source_table == source,
                RollupState.target_table == target
            )
            .first()
        )

        if state:
            state.last_bucket = bucket_time
        else:
            state = RollupState(
                source_table=source,
                target_table=target,
                last_bucket=bucket_time
            )
            db.add(state)

        db.flush()  
