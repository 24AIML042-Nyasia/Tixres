try:
    import psutil  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    psutil = None  # type: ignore
import platform
import os
import time
from static.modules.base import BaseModule


def wrap_json(data):
    return {"value": data}


def psutil_missing_json():
    return wrap_json({"error": "psutil is not installed"})

# ============================================================================
# MEMORY MODULE
# ============================================================================

class MemoryModule(BaseModule):
    name = "memory"
    version = "1.0.0"
    description = "Memory (RAM and Swap) metrics"

    def __init__(self):
        self.functions = {
            "ram": {"func": self.get_ram, "dtype": "json"},
            "swap": {"func": self.get_swap, "dtype": "json"},
            "cached_vs_free": {"func": self.get_cached_vs_free, "dtype": "json"}
        }

    async def get_ram(self):
        if psutil is None:
            return psutil_missing_json()
        mem = psutil.virtual_memory()
        return wrap_json({
            "percent": round(mem.percent, 1),
            "used_gb": round(mem.used / (1024**3), 2),
            "total_gb": round(mem.total / (1024**3), 2),
            "available_gb": round(mem.available / (1024**3), 2)
        })

    async def get_swap(self):
        if psutil is None:
            return psutil_missing_json()
        swap = psutil.swap_memory()
        return wrap_json({
            "percent": round(swap.percent, 1),
            "used_gb": round(swap.used / (1024**3), 2),
            "total_gb": round(swap.total / (1024**3), 2)
        })

    async def get_cached_vs_free(self):
        if psutil is None:
            return psutil_missing_json()
        mem = psutil.virtual_memory()
        return wrap_json({
            "cached_gb": round(getattr(mem, 'cached', 0) / (1024**3), 2),
            "free_gb": round(mem.free / (1024**3), 2),
            "buffers_gb": round(getattr(mem, 'buffers', 0) / (1024**3), 2)
        })

    def register(self):
        return self.functions


