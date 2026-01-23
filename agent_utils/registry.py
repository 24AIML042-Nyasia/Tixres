MODULE_REGISTRY = {}
FUNCTION_REGISTRY = {}

def register_module(module):
    MODULE_REGISTRY[module.name + "_v" + module.version] = module

    for fname, func in module.functions.items():
        FUNCTION_REGISTRY[f"{module.name}.{fname}"] = func