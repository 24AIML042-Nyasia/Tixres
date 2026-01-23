from agent_utils.registry import FUNCTION_REGISTRY , MODULE_REGISTRY

def val_modules(request : dict) -> bool:
    req_modules = request['modules']
    
    return all(module in list(MODULE_REGISTRY.keys()) for module in req_modules)

def load_metrics(request : dict) -> bool:
    return request['metrics']






