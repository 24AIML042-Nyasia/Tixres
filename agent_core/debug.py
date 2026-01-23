from agent_utils.registry import FUNCTION_REGISTRY, MODULE_REGISTRY



def print_registries():
    print(MODULE_REGISTRY.keys())
    print(FUNCTION_REGISTRY.keys())