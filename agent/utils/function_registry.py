from typing import Callable, Awaitable, Literal, Any

import pkgutil
import importlib
import inspect
import logging

import static.modules as modules
from static.modules.base import BaseModule


# ============================================================================
# TYPES
# ============================================================================

FnType = Literal["loop", "once"]
DType = Literal["int", "float", "json"]


# ============================================================================
# FUNCTION ENTRY
# ============================================================================

class FunctionEntry:
    def __init__(
        self,
        fn: Callable[..., Awaitable[Any]],
        type: FnType,
        dtype: DType,
        module: BaseModule | None = None
    ):
        self.fn = fn
        self.type = type
        self.dtype = dtype
        self.module = module


# ============================================================================
# FUNCTION REGISTRY
# ============================================================================

class FunctionRegistry:
    def __init__(self):
        self._fns: dict[str, FunctionEntry] = {}

    def register(
        self,
        name: str,
        fn: Callable[..., Awaitable[Any]],
        dtype: DType,
        type: FnType = "loop",
        module: BaseModule | None = None
    ):
        if not callable(fn):
            raise ValueError(f'"{name}" must be callable')

        self._fns[name] = FunctionEntry(fn, type, dtype, module)

    def get(self, name: str) -> FunctionEntry | None:
        return self._fns.get(name)

    def has(self, name: str) -> bool:
        return name in self._fns

    def entries(self):
        return self._fns.items()

    def unregister_module(self, module: BaseModule):
        """Remove all functions belonging to a module"""
        to_delete = [
            name for name, entry in self._fns.items()
            if entry.module == module
        ]
        for name in to_delete:
            del self._fns[name]


# ============================================================================
# MODULE REGISTRATION
# ============================================================================

def register_module(instance: BaseModule, registry: FunctionRegistry):
    module_name = instance.module_id

    for fname, meta in instance.register().items():
        fn = meta["func"]
        dtype = meta["dtype"]
        fn_type = meta.get("type", "loop") if isinstance(meta, dict) else "loop"
        if fn_type not in ("loop", "once"):
            fn_type = "loop"

        # normalize dtype
        if dtype in (int, float):
            dtype_name: DType = dtype.__name__  # "int" or "float"
        else:
            dtype_name = "json"

        full_name = f"{module_name}.{fname}"

        registry.register(
            name=full_name,
            fn=fn,
            dtype=dtype_name,
            type=fn_type,
            module=instance
        )


# ============================================================================
# MODULE LOADER
# ============================================================================

def _class_module_id(obj) -> str | None:
    name = getattr(obj, "name", None)
    version = getattr(obj, "version", None)
    if not isinstance(name, str) or not isinstance(version, str):
        return None
    if not name or not version:
        return None
    return f"{name}_v{version}"


def load_modules(
    registry: FunctionRegistry,
    *,
    allowed_module_ids: set[str] | None = None,
    already_loaded_module_ids: set[str] | None = None,
):
    instances: list[BaseModule] = []

    for _, module_name, _ in pkgutil.iter_modules(modules.__path__):
        try:
            module = importlib.import_module(f"{modules.__name__}.{module_name}")
        except ModuleNotFoundError as exc:
            logging.warning(
                "Skipping module %s because dependency is missing: %s",
                module_name,
                getattr(exc, "name", exc),
            )
            continue
        except Exception as exc:
            logging.warning("Skipping module %s due to import error: %s", module_name, exc)
            continue

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, BaseModule) and obj is not BaseModule:
                module_id = _class_module_id(obj)
                if module_id is None:
                    continue
                if allowed_module_ids is not None and module_id not in allowed_module_ids:
                    continue
                if already_loaded_module_ids is not None and module_id in already_loaded_module_ids:
                    continue
                instance = obj()
                register_module(instance, registry)
                instances.append(instance)

    return instances


# ============================================================================
# MODULE UNLOADER (CLEANUP)
# ============================================================================

async def unload_module(module: BaseModule, registry: FunctionRegistry):
    """Safely unload a module"""
    registry.unregister_module(module)

    # explicit cleanup (recommended)
    if hasattr(module, "cleanup") and callable(module.cleanup):
        try:
            await module.cleanup()
        except Exception as e:
            logging.warning("Cleanup failed for module %s: %s", module.name, e)


async def unload_all(modules_list: list[BaseModule], registry: FunctionRegistry):
    """Unload all modules"""
    for module in modules_list:
        await unload_module(module, registry)
