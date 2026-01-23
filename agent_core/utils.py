from agent_utils.registry import FUNCTION_REGISTRY , MODULE_REGISTRY

def val_modules(request : dict) -> bool:
    req_modules = request['modules']

    # print(list(MODULE_REGISTRY.keys()))
    # print(req_modules)
    
    return all(module in list(MODULE_REGISTRY.keys()) for module in req_modules)


def run(task_name):
    if task_name not in FUNCTION_REGISTRY:
        return "UNAVAILABLE"
    return str(FUNCTION_REGISTRY[task_name]())




