import asyncio

from agent_core.agent import startup
from agent_core.execute import gather


startup()

asyncio.run(gather())

