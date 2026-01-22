import pkgutil
import importlib
import inspect
import modules
from modules.base import BaseMetric

metrics = []

for _, module_name, _ in pkgutil.iter_modules(modules.__path__):
    module = importlib.import_module(f"{modules.__name__}.{module_name}")

    for _, obj in inspect.getmembers(module, inspect.isclass):
        if issubclass(obj, BaseMetric) and obj is not BaseMetric:
            metrics.append(obj())

for m in metrics:
    print(m.collect())