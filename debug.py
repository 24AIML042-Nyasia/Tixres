import asyncio
from datetime import datetime, timedelta
from server_db.connection import SessionLocal
from metric_rollup.rollUp import InfluxDBRollup
from server_db.models import MetricNumeric
from metric_rollup.rollUpStateService import RollupStateService
from server_db.models import MetricNumeric, Agent, AgentCredentials
from datetime import timezone
import os
from dotenv import load_dotenv

load_dotenv('env.env')


INFLUX_URL = os.getenv('INFLUX_URL')
INFLUX_TOKEN = os.getenv('INFLUX_TOKEN')
INFLUX_ORG = os.getenv('INFLUX_ORG')
INFLUX_BUCKET = os.getenv('INFLUX_BUCKET')

async def test_one_min_rollup():
    db = SessionLocal()

    db.query(MetricNumeric).delete()
    db.query(Agent).delete()
    db.query(AgentCredentials).delete()
    db.commit()

    creds = AgentCredentials(
        agent_id="agent_1",
        api_key="test_key",
        secret_key="test_secret",
        is_active=1,
    )

    agent = Agent(
        agent_id="agent_1",
        agent_version="1.0",
        hostname="localhost",
        os="linux",
    )

    metric = MetricNumeric(
        agent_id="agent_1",
        metric_name="cpu_usage_v1_percent",
        value=50.0,
        timestamp=datetime.now(timezone.utc),
    )

    db.add(creds)
    db.add(agent)
    db.add(metric)
    db.commit()

    rollup = InfluxDBRollup(
        INFLUX_URL,
        INFLUX_TOKEN,
        INFLUX_ORG,
        INFLUX_BUCKET,
    )

    await rollup.one_min_roll_up()

    state = RollupStateService.get_last_bucket(
        db,
        "metric_numeric",
        "metric_numeric_1m",
    )

    assert state is not None
    print("✅ Rollup successful, state:", state)

    db.close()


if __name__ == "__main__":
    asyncio.run(test_one_min_rollup())
