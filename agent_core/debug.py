from agent_utils.registry import FUNCTION_REGISTRY, MODULE_REGISTRY

request = {'modules' : ['cpu'],
            'metrics' : {
                'cpu_v1.0.0.usage' : 5,
                'cpu_v1.0.0.cores' : 10
                       }
                       }

def print_registries():
    print(MODULE_REGISTRY.keys())
    print(FUNCTION_REGISTRY.keys())