import asyncio
import base64
import hashlib
import importlib
import json
import logging
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from auth.hmac import create_signature
from utils.execution_manager import ExecutionManager
from utils.function_registry import FunctionRegistry
from utils.module_manager import ModuleManager
from utils.template_engine import parse_template
from utils.ws_client import WebSocketClient, WebSocketClientError


logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


AGENT_VERSION = "1.0.0"
CREDENTIALS_PATH = Path(__file__).with_name("agent_credentials.json")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_code_fingerprint(agent_dir: Path) -> str:
    modules_dir = agent_dir / "static" / "modules"
    h = hashlib.sha256()
    for path in sorted(modules_dir.rglob("*.py")):
        rel = path.relative_to(agent_dir).as_posix()
        content = path.read_bytes()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(hashlib.sha256(content).digest())
        h.update(b"\0")
    return h.hexdigest()


def required_module_ids_from_template(template: dict | str) -> set[str]:
    parsed = parse_template(template)
    required = set(parsed.modules)
    required |= {name.rsplit(".", 1)[0] for name in parsed.metrics if "." in name}
    return required


def load_credentials() -> dict[str, str] | None:
    if not CREDENTIALS_PATH.exists():
        return None
    try:
        data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    api_key = data.get("api_key")
    secret_key = data.get("secret_key")
    agent_id = data.get("agent_id")
    if not all(isinstance(x, str) and x for x in (api_key, secret_key, agent_id)):
        return None
    return {"agent_id": agent_id, "api_key": api_key, "secret_key": secret_key}


def save_credentials(agent_id: str, api_key: str, secret_key: str) -> None:
    CREDENTIALS_PATH.write_text(
        _safe_json({"agent_id": agent_id, "api_key": api_key, "secret_key": secret_key}),
        encoding="utf-8",
    )


async def main(host: str = "127.0.0.1", port: int = 8765):
    agent_dir = Path(__file__).resolve().parent
    hostname = platform.node() or "unknown"
    os_name = f"{platform.system()} {platform.release()}".strip()

    registry = FunctionRegistry()
    modules = ModuleManager()
    manager = ExecutionManager(registry)

    code_fingerprint = compute_code_fingerprint(agent_dir)

    creds = load_credentials()

    try:
        ws = await WebSocketClient.connect(host, port, "/")
    except WebSocketClientError as exc:
        raise SystemExit(f"Failed to connect: {exc}") from exc

    send_lock = asyncio.Lock()
    incoming_events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
    request_seq = 0

    async def ws_send(obj: dict[str, Any]) -> None:
        async with send_lock:
            await ws.send_json(obj)

    async def rpc(event: str, data: dict[str, Any], timeout_s: float = 15.0) -> dict[str, Any]:
        nonlocal request_seq
        request_seq += 1
        request_id = str(request_seq)
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        pending[request_id] = fut
        await ws_send({"event": event, "data": data, "request_id": request_id})
        try:
            return await asyncio.wait_for(fut, timeout=timeout_s)
        finally:
            # Prevent leaked pending futures on timeout/cancel.
            pending.pop(request_id, None)

    async def receiver() -> None:
        while True:
            msg = await ws.recv_json()
            if msg is None:
                return
            request_id = msg.get("request_id")
            if isinstance(request_id, str):
                fut = pending.get(request_id)
                if fut is not None:
                    pending.pop(request_id, None)
                    if not fut.done():
                        fut.set_result(msg)
                # Either way, don't treat responses as broadcast events.
                continue
            await incoming_events.put(msg)

    recv_task = asyncio.create_task(receiver())

    hello = await incoming_events.get()
    log.info("server: %s", hello)

    if creds is None:
        reg = await rpc(
            "register",
            {
                "agent_version": AGENT_VERSION,
                "hostname": hostname,
                "os": os_name,
                "fingerprint": code_fingerprint,
            },
        )
        if not reg.get("ok"):
            raise SystemExit(f"register failed: {reg}")

        data = reg.get("data") or {}
        agent_id = data.get("agent_id")
        api_key = data.get("api_key")
        secret_key = data.get("secret_key")
        if not all(isinstance(x, str) and x for x in (agent_id, api_key, secret_key)):
            raise SystemExit(f"register invalid response: {reg}")

        save_credentials(agent_id, api_key, secret_key)
        creds = {"agent_id": agent_id, "api_key": api_key, "secret_key": secret_key}
        log.info("registered agent_id=%s api_key=%s", agent_id, api_key)

    message = str(int(time.time()))
    signature = create_signature(creds["api_key"], creds["secret_key"], message)

    login = await rpc(
        "login",
        {
            "api_key": creds["api_key"],
            "message": message,
            "signature": signature,
            "agent_version": AGENT_VERSION,
            "hostname": hostname,
            "os": os_name,
            "fingerprint": code_fingerprint,
        },
    )
    if not login.get("ok"):
        raise SystemExit(f"login failed: {login}")

    template = (login.get("data") or {}).get("template")
    if not isinstance(template, dict):
        raise SystemExit(f"login missing template: {login}")

    async def apply_module_bundle(files: list[dict[str, Any]]) -> int:
        wrote = 0
        for f in files:
            rel = f.get("path")
            content_b64 = f.get("content_b64")
            sha256 = f.get("sha256")
            if not isinstance(rel, str) or not isinstance(content_b64, str) or not isinstance(sha256, str):
                continue

            rel_path = Path(rel)
            if rel_path.is_absolute() or ".." in rel_path.parts:
                continue
            rel_posix = rel_path.as_posix()
            if not rel_posix.startswith("static/modules/"):
                continue

            content = base64.b64decode(content_b64.encode("ascii"))
            if hashlib.sha256(content).hexdigest() != sha256:
                continue

            dest = agent_dir / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
            wrote += 1

        if wrote:
            importlib.invalidate_caches()
        return wrote

    async def sync_to_template(new_template: dict, *, reason: str) -> bool:
        nonlocal code_fingerprint

        required = required_module_ids_from_template(new_template)

        # Load any newly required modules first (don't unload yet).
        ensure_result = modules.ensure_loaded(required_module_ids=required, registry=registry)

        if ensure_result.missing:
            dl = await rpc(
                "module_download",
                {"module_ids": ensure_result.missing},
                timeout_s=30.0,
            )
            if dl.get("ok"):
                files = (dl.get("data") or {}).get("files", [])
                if isinstance(files, list):
                    await apply_module_bundle(files)
                # Retry after download
                ensure_result = modules.ensure_loaded(required_module_ids=required, registry=registry)

        verification, _diff = manager.apply_template(new_template)
        log.info("[%s] template verify: %s", reason, verification)
        if not verification.ok:
            return False

        # After tasks are restarted, unload modules that are no longer required.
        await modules.unload_unneeded(required_module_ids=required, registry=registry)

        module_ids = sorted(modules.module_ids())
        function_names = sorted(
            name for name, entry in registry.entries() if getattr(entry, "module", None) is not None
        )

        code_fingerprint = compute_code_fingerprint(agent_dir)
        verify_payload = {
            "modules": module_ids,
            "functions": function_names,
            "fingerprint": code_fingerprint,
        }

        async def _module_verify_best_effort() -> None:
            delays = (0.0, 2.0, 5.0, 10.0)
            for attempt, delay in enumerate(delays, start=1):
                if delay:
                    await asyncio.sleep(delay)
                try:
                    await rpc("module_verify", verify_payload, timeout_s=30.0)
                    return
                except asyncio.TimeoutError:
                    log.warning(
                        "module_verify timed out (attempt %s/%s)",
                        attempt,
                        len(delays),
                    )
                except Exception as exc:
                    log.warning("module_verify failed: %s", exc)
                    return

        asyncio.create_task(_module_verify_best_effort())

        return True

    # Initial sync and start
    ok = await sync_to_template(template, reason="login")
    if not ok:
        log.error("Template invalid; agent will not start.")
        recv_task.cancel()
        await ws.close()
        return

    send_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)

    async def sender() -> None:
        while True:
            msg = await send_queue.get()
            await ws_send(msg)

    send_task = asyncio.create_task(sender())

    async def event_loop() -> None:
        while True:
            msg = await incoming_events.get()
            event = msg.get("event")
            if isinstance(event, str):
                event = event.strip().replace(" ", "_")

            if event == "template_update" and msg.get("ok") is True:
                new_template = (msg.get("data") or {}).get("template")
                if isinstance(new_template, dict):
                    await sync_to_template(new_template, reason="server_update")
            elif event == "run_once" and msg.get("ok") is True:
                payload = msg.get("data") or {}
                name = payload.get("name")
                args = payload.get("args") or {}
                if isinstance(name, str):
                    try:
                        manager.run_once(name, args=args if isinstance(args, dict) else None)
                        request_id = msg.get("request_id")
                        if isinstance(request_id, str) and request_id:
                            await ws_send(
                                {
                                    "event": "run_once",
                                    "ok": True,
                                    "data": {"queued": True, "name": name},
                                    "request_id": request_id,
                                }
                            )
                    except Exception as exc:
                        request_id = msg.get("request_id")
                        if isinstance(request_id, str) and request_id:
                            await ws_send(
                                {
                                    "event": "run_once",
                                    "ok": False,
                                    "error": str(exc),
                                    "request_id": request_id,
                                }
                            )

    evt_task = asyncio.create_task(event_loop())

    def on_run(payload: dict) -> None:
        name = payload.get("name")
        if not isinstance(name, str):
            return
        value = payload.get("result")
        if "error" in payload:
            value = {"error": str(payload.get("error"))}

        msg = {
            "event": "submit_metrics",
            "data": {
                "metrics": [
                    {
                        "name": name,
                        "value": value,
                        "timestamp": _utcnow_iso(),
                        "duration_ms": payload.get("duration_ms"),
                    }
                ]
            },
        }
        try:
            send_queue.put_nowait(msg)
        except Exception:
            pass

    manager.on("run", on_run)

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        manager.stop_all()
        send_task.cancel()
        evt_task.cancel()
        recv_task.cancel()
        await ws.close()


if __name__ == "__main__":
    asyncio.run(main())
