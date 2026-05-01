import asyncio
import logging
from typing import Callable

from .function_registry import FunctionRegistry
from .task_runner import loop_runner, one_shot_runner
from .template_engine import (
    TemplateDiff,
    TemplateEngine,
    TemplateVerificationResult,
    verify_template,
)

log = logging.getLogger(__name__)


class ExecutionManager:
    def __init__(self, registry: FunctionRegistry):
        self._registry = registry
        self._template = TemplateEngine()
        # name -> (asyncio.Task, asyncio.Event)
        self._tasks: dict[str, tuple[asyncio.Task, asyncio.Event]] = {}
        self._listeners: dict[str, list[Callable]] = {}

        # Wire template changes -> lifecycle management
        self._template.on_change(self._handle_diff)

    def verify_template(self, raw: str | dict) -> TemplateVerificationResult:
        return verify_template(raw, self._registry)

    def apply_template(
        self, raw: str | dict
    ) -> tuple[TemplateVerificationResult, TemplateDiff | None]:
        """Parse + validate template; only restart tasks that actually changed."""
        verification = self.verify_template(raw)
        if not verification.ok:
            self._emit("template_invalid", verification)
            return verification, None

        diff = self._template.apply(raw, self._registry)
        return verification, diff

    def run_once(self, name: str, *, args: dict | None = None) -> None:
        """Fire a one-shot function immediately, regardless of template."""
        entry = self._registry.get(name)
        if not entry:
            raise ValueError(f'Unknown function: "{name}"')
        asyncio.create_task(one_shot_runner(name, entry.fn, self._on_result, kwargs=args))

    def stop_all(self) -> None:
        for name in list(self._tasks):
            self._stop_task(name)
        self._emit("stop_all", {})

    def on(self, event: str, fn: Callable) -> None:
        """Subscribe to events: 'run', 'start', 'stop', 'template_change', 'stop_all'."""
        self._listeners.setdefault(event, []).append(fn)

    def _handle_diff(self, diff: TemplateDiff) -> None:
        for name in diff.removed:
            self._stop_task(name)
        for name, freq in diff.added:
            self._start_loop(name, freq)
        for name, freq in diff.updated:
            self._stop_task(name)
            self._start_loop(name, freq)
        self._emit("template_change", diff)

    def _start_loop(self, name: str, freq: int) -> None:
        entry = self._registry.get(name)
        if not entry or entry.type != "loop":
            return

        stop_event = asyncio.Event()
        task = asyncio.create_task(loop_runner(name, entry.fn, freq, stop_event, self._on_result))
        task.add_done_callback(lambda _: self._tasks.pop(name, None))
        self._tasks[name] = (task, stop_event)
        self._emit("start", {"name": name, "freq": freq})
        log.info("[START] %s every %sms", name, freq)

    def _stop_task(self, name: str) -> None:
        if name not in self._tasks:
            return
        _, stop_event = self._tasks.pop(name)
        stop_event.set()  # signals loop_runner to exit cleanly
        self._emit("stop", {"name": name})
        log.info("[STOP]  %s", name)

    def _on_result(self, payload: dict) -> None:
        if "error" in payload:
            log.error("[ERR]  %s: %s", payload.get("name"), payload.get("error"))
        else:
            log.info(
                "[RUN]  %s -> %s (%sms)",
                payload.get("name"),
                payload.get("result"),
                payload.get("duration_ms"),
            )
        self._emit("run", payload)

    def _emit(self, event: str, payload) -> None:
        for fn in self._listeners.get(event, []):
            fn(payload)

