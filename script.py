import asyncio

from agent_core.agent import startup
from agent_core.execute import gather
from agent_db.models import fetch_unsent
# from agent_db.migrations import migrate

# migrate()

# startup()

# asyncio.run(gather())

rows = fetch_unsent("metric_numeric")

for row in rows:
    print(dict(row))

