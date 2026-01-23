import pkgutil
import importlib
import inspect

import modules
from modules.base import BaseModule
from .registry import register_module


def load_modules():
    for _, module_name, _ in pkgutil.iter_modules(modules.__path__):
        # print(f"{modules.__name__}.{module_name}")
        module = importlib.import_module(f"{modules.__name__}.{module_name}")

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, BaseModule) and obj is not BaseModule:
                register_module(obj())




