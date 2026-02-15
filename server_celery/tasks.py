from celery import group
import asyncio

from server_celery.app import app
from anomaly.zScore import ZScoreAnomaly
from debug.anomaly import get_agent_z_score_metric_mapping
from server_db.rollups import one_min_roll_up, ten_min_roll_up, one_hour_roll_up

@app.task
def one_min_rollup():
    return asyncio.run(one_min_roll_up())

@app.task
def ten_min_rollup():
    return asyncio.run(ten_min_roll_up())

@app.task
def one_hour_rollup():
    return asyncio.run(one_hour_roll_up())

@app.task(bind=True, max_retries=3)
def run_zscore_for_agent(self, agent_id: str, metrics: list):
    try:
        detector = ZScoreAnomaly(
            agent_id=agent_id,
            metrics=metrics
        )

        return detector.detect_anomaly()

    except Exception as e:
        raise self.retry(exc=e, countdown=5)
    
@app.task
def run_anomaly_cycle():

    agent_metric_map = get_agent_z_score_metric_mapping()
    # example:
    # {
    #   "agent_1": ["cpu", "memory"],
    #   "agent_2": ["disk", "network"]
    # }

    jobs = group(
        run_zscore_for_agent.s(agent_id, metrics)
        for agent_id, metrics in agent_metric_map.items()
    )

    jobs.apply_async()