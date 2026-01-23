import asyncio

from agent_utils.registry import FUNCTION_REGISTRY
from agent_core.utils import load_metrics
from agent_core.debug import request


REQUIRED_FUNCTIONS = load_metrics(request)

async def runner(fn, interval):
    while True:
        try:
            val = await fn()

            print(val)
        except Exception as e:
            print(f"Error in {fn.__name__}: {e}")
        await asyncio.sleep(interval)

async def gather():
    running = [
        asyncio.create_task(runner(get_fun(fn), interval))
        for fn, interval in REQUIRED_FUNCTIONS.items()
    ]
    await asyncio.gather(*running)


def get_fun(fun_name):
    return FUNCTION_REGISTRY[fun_name]

def run(task_name):
    if task_name not in FUNCTION_REGISTRY:
        return "UNAVAILABLE"
    return str(FUNCTION_REGISTRY[task_name]())