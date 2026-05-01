import asyncio
import json
import logging
import random
from pathlib import Path

from utils.execution_manager import ExecutionManager
from utils.function_registry import FunctionRegistry, load_modules
from utils.ws_client import WebSocketClient

logging.basicConfig(level=logging.INFO, format="%(message)s")


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


async def main():
    ws = await WebSocketClient.connect("127.0.0.1", 8765, "/")
    hello = await ws.recv_json()
    print("server:", hello)

    async def drain():
        while True:
            msg = await ws.recv_json()
            if msg is None:
                return

    name = f"agent-{random.randint(1000, 9999)}"
    password = "pass1234"

    await ws.send_json({"event": "register", "data": {"name": name, "password": password}})
    reg = await ws.recv_json()
    print("register:", reg)
    api_key = reg["data"]["credential"]["api_key"]

    await ws.send_json({"event": "login", "data": {"api_key": api_key, "password": password}})
    login = await ws.recv_json()
    print("login:", login)

    registry = FunctionRegistry()
    load_modules(registry)
    manager = ExecutionManager(registry)

    template = load_json(Path(__file__).with_name("template.json"))

    await ws.send_json({"event": "template_update", "data": {"template": template}})
    tmpl_resp = await ws.recv_json()
    print("template_update:", tmpl_resp)

    drain_task = asyncio.create_task(drain())

    manager.on(
        "run",
        lambda payload: asyncio.create_task(
            ws.send_json(
                {
                    "event": "submit_metrics",
                    "data": {
                        "metrics": [
                            {
                                "name": payload.get("name"),
                                "value": payload.get("result")
                                if "error" not in payload
                                else {"error": str(payload.get("error"))},
                            }
                        ]
                    },
                }
            )
        ),
    )

    verification, _diff = manager.apply_template(template)
    print("local template verify:", verification)

    await asyncio.sleep(6)
    manager.stop_all()
    drain_task.cancel()
    await ws.close()


if __name__ == "__main__":
    asyncio.run(main())
