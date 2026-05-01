import asyncio
import copy
import json
import logging
import random
from pathlib import Path

from utils.execution_manager import ExecutionManager
from utils.function_registry import FunctionRegistry, load_modules
from utils.module_store import get_module_store

logging.basicConfig(level=logging.INFO, format="%(message)s")


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


async def hash_gen():
    await asyncio.sleep(0.02)
    return {"hash": hex(random.getrandbits(64))[2:].upper()}


async def main():
    registry = FunctionRegistry()
    loaded_modules = load_modules(registry)

    registry.register(
        name="core_v1.0.0.hashGen",
        fn=hash_gen,
        dtype="json",
        type="once",
    )

    store = get_module_store()
    sync = store.sync_registry(registry)

    print("Loaded modules:", [m.module_id for m in loaded_modules])
    print("DB sync:", sync)

    manager = ExecutionManager(registry)

    template_path = Path(__file__).with_name("template.json")
    template = load_json(template_path)

    print("\n== Verify + apply initial template ==")
    verification, diff = manager.apply_template(template)
    print("verify:", verification)
    print("diff:", diff)

    print("\n== Run once ==")
    manager.run_once("core_v1.0.0.hashGen")

    await asyncio.sleep(3)

    print("\n== Template update ==")
    updated = copy.deepcopy(template)
    metrics = updated.get("template", {}).get("metrics", {})
    metrics["cpu_v1.0.0.usage_overall"] = 1  # seconds (nested template)
    metrics["temperature_v1.0.0.sensors"] = 30
    metrics.pop("disk_v1.0.0.usage", None)

    verification2, diff2 = manager.apply_template(updated)
    print("verify:", verification2)
    print("diff:", diff2)

    await asyncio.sleep(3)

    print("\n== Verify broken template (missing module + function) ==")
    broken = copy.deepcopy(updated)
    broken.setdefault("template", {}).setdefault("modules", []).append("gpu_v1.0.0")
    broken.setdefault("template", {}).setdefault("metrics", {})["cpu_v1.0.0.nope"] = 5

    verification3 = manager.verify_template(broken)
    print("verify:", verification3)

    manager.stop_all()


if __name__ == "__main__":
    asyncio.run(main())

