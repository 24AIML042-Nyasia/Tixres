from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass

from static.modules.base import BaseModule

from .function_registry import FunctionRegistry, load_modules, unload_module


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncResult:
    loaded: list[str]
    unloaded: list[str]
    missing: list[str]


class ModuleManager:
    def __init__(self):
        self._instances: list[BaseModule] = []

    @property
    def instances(self) -> list[BaseModule]:
        return list(self._instances)

    def module_ids(self) -> set[str]:
        return {m.module_id for m in self._instances}

    def ensure_loaded(
        self, *, required_module_ids: set[str], registry: FunctionRegistry
    ) -> SyncResult:
        already_loaded = self.module_ids()
        to_load = required_module_ids - already_loaded

        loaded_instances: list[BaseModule] = []
        if to_load:
            importlib.invalidate_caches()
            loaded_instances = load_modules(
                registry,
                allowed_module_ids=to_load,
                already_loaded_module_ids=already_loaded,
            )
            self._instances.extend(loaded_instances)

        loaded = [m.module_id for m in loaded_instances]
        missing = sorted(required_module_ids - self.module_ids())
        return SyncResult(loaded=loaded, unloaded=[], missing=missing)

    async def unload_unneeded(
        self, *, required_module_ids: set[str], registry: FunctionRegistry
    ) -> SyncResult:
        unloaded: list[str] = []
        for instance in list(self._instances):
            if instance.module_id in required_module_ids:
                continue
            try:
                await unload_module(instance, registry)
            finally:
                self._instances.remove(instance)
                unloaded.append(instance.module_id)

        return SyncResult(loaded=[], unloaded=unloaded, missing=[])

    async def sync(
        self,
        *,
        required_module_ids: set[str],
        registry: FunctionRegistry,
        unload_first: bool = True,
    ) -> SyncResult:
        unloaded: list[str] = []
        if unload_first:
            unloaded = (await self.unload_unneeded(required_module_ids=required_module_ids, registry=registry)).unloaded

        loaded_result = self.ensure_loaded(required_module_ids=required_module_ids, registry=registry)
        missing = loaded_result.missing

        if missing:
            log.warning("Missing modules after sync: %s", missing)

        return SyncResult(loaded=loaded_result.loaded, unloaded=unloaded, missing=missing)
