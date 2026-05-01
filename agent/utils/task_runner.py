import asyncio
import time
from typing import Awaitable, Callable


async def loop_runner(
    name: str,
    fn: Callable[[], Awaitable],
    frequency_ms: int,
    stop_event: asyncio.Event,
    on_result: Callable,
):
    """Runs fn every frequency_ms milliseconds until stop_event is set."""
    frequency_s = frequency_ms / 1000

    while not stop_event.is_set():
        start = time.monotonic()
        try:
            result = await fn()
            on_result(
                {
                    "name": name,
                    "result": result,
                    "duration_ms": round((time.monotonic() - start) * 1000),
                }
            )
        except Exception as err:
            on_result(
                {
                    "name": name,
                    "error": err,
                    "duration_ms": round((time.monotonic() - start) * 1000),
                }
            )

        elapsed = time.monotonic() - start
        remaining = max(0.0, frequency_s - elapsed)

        # Sleep in small chunks so stop_event is checked promptly
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=remaining)
        except asyncio.TimeoutError:
            pass  # Normal - sleep finished before stop


async def one_shot_runner(
    name: str,
    fn: Callable[..., Awaitable],
    on_result: Callable,
    *,
    kwargs: dict | None = None,
):
    """Fire-and-forget: run fn once, no stop mechanism needed."""
    start = time.monotonic()
    try:
        result = await fn(**(kwargs or {}))
        on_result(
            {
                "name": name,
                "result": result,
                "duration_ms": round((time.monotonic() - start) * 1000),
            }
        )
    except Exception as err:
        on_result(
            {
                "name": name,
                "error": err,
                "duration_ms": round((time.monotonic() - start) * 1000),
            }
        )

