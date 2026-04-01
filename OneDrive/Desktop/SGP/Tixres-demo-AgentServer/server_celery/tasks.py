from celery import group
import asyncio

from server_celery.app import app
from anomaly.zScore import ZScoreAnomaly
from debug.anomaly import get_agent_z_score_metric_mapping
from metric_rollup.rollUp import InfluxDBRollup

@app.task
def one_min_rollup():
    inf = InfluxDBRollup()
    return asyncio.run(inf.one_min_roll_up())

@app.task
def ten_min_rollup():
    inf = InfluxDBRollup()
    return asyncio.run(inf.ten_min_roll_up())

@app.task
def one_hour_rollup():
    inf = InfluxDBRollup()
    return asyncio.run(inf.one_hour_roll_up())

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

    if not agent_metric_map:
        return None

    jobs = group(
        run_zscore_for_agent.s(agent_id, metrics)
        for agent_id, metrics in agent_metric_map.items()
    )

    jobs.apply_async()