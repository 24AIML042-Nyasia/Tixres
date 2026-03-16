import asyncio

from agent_utils.registry import FUNCTION_REGISTRY
from agent_core.utils import load_metrics
from agent_core.debug import request
from agent_db.models import insert_metric
from settings import DEBUG


REQUIRED_FUNCTIONS = load_metrics(request)

if(DEBUG):
    met = []

async def runner(fn, interval):
    while True:
        

        try:
            val = await get_fun(fn)()

        except Exception as e:
            # print(f"Error in {fn.__name__}: {e}")
            val = {'status' : "UNAVAILABLE"}

        if(DEBUG):
            met.append(fn)
            print(get_fun(fn),val)
            
        else:
            insert_metric(fn,val)

        # print(all([m in met for m in list(REQUIRED_FUNCTIONS.keys())]))

        await asyncio.sleep(interval)

async def gather():
    running = [
        asyncio.create_task(runner(fn, interval))
        for fn, interval in REQUIRED_FUNCTIONS.items()
    ]
    await asyncio.gather(*running)


def get_fun(fun_name):
    return FUNCTION_REGISTRY[fun_name]

def run(task_name):
    if task_name not in FUNCTION_REGISTRY:
        return "UNAVAILABLE"
    return str(FUNCTION_REGISTRY[task_name]())