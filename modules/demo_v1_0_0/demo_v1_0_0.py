"""
Synthetic demo versions of all metrics modules.

These generate realistic-looking data without touching host resources.
Metric names are prefixed with `demo_` to avoid clashing with real modules.
"""

import math
import random
import time
from datetime import datetime, timedelta

from modules.base import BaseModule


# Shared helpers ------------------------------------------------------------- #
_rng = random.Random(2026)
_start = time.time()


def _osc(base: float, amp: float, period_s: float) -> float:
    """Smooth oscillation with light noise."""
    t = time.time() - _start
    wave = math.sin((t % period_s) / period_s * 2 * math.pi)
    noise = _rng.uniform(-0.6, 0.6)
    return base + amp * wave + noise


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


# CPU ----------------------------------------------------------------------- #
class DemoCpuModule(BaseModule):
    name = "demo_cpu"
    version = "1.0.0"
    description = "Demo CPU metrics"

    def __init__(self):
        self.functions = {
            "usage_overall": self.get_usage_overall,
            "usage_per_core": self.get_usage_per_core,
            "load_average": self.get_load_average,
            "temperature": self.get_temperature,
            "core_count": self.get_core_count,
            "frequency": self.get_frequency,
        }

    async def get_usage_overall(self) -> float:
        return round(_clamp(_osc(48, 28, 90), 0, 100), 2)

    async def get_usage_per_core(self) -> dict:
        cores = 4
        base = _clamp(_osc(45, 20, 70), 5, 95)
        return {i: round(_clamp(base + _rng.uniform(-10, 10), 0, 100), 1) for i in range(cores)}

    async def get_load_average(self) -> dict:
        one = _clamp(_osc(1.2, 0.6, 80), 0, 4)
        return {"1m": round(one, 2), "5m": round(one * 0.8, 2), "15m": round(one * 0.6, 2)}

    async def get_temperature(self) -> float:
        return round(_clamp(_osc(58, 12, 120), 35, 85), 1)

    async def get_core_count(self) -> int:
        return 8

    async def get_frequency(self) -> dict:
        cur = _clamp(_osc(2800, 350, 110), 1800, 3800)
        return {"current": round(cur, 1), "min": 1800.0, "max": 3800.0}

    def register(self):
        return self.functions


# Memory -------------------------------------------------------------------- #
class DemoMemoryModule(BaseModule):
    name = "demo_memory"
    version = "1.0.0"
    description = "Demo memory metrics"

    def __init__(self):
        self.functions = {
            "ram": self.get_ram,
            "swap": self.get_swap,
            "cached_vs_free": self.get_cached_vs_free,
        }

    async def get_ram(self) -> dict:
        total = 32.0
        used = _clamp(_osc(20, 4, 140), 10, 30)
        return {"percent": round((used / total) * 100, 1), "used_gb": round(used, 2), "total_gb": total, "available_gb": round(total - used, 2)}

    async def get_swap(self) -> dict:
        total = 4.0
        used = _clamp(_osc(0.9, 0.5, 190), 0, 3.5)
        return {"percent": round((used / total) * 100, 1), "used_gb": round(used, 2), "total_gb": total}

    async def get_cached_vs_free(self) -> dict:
        cached = _clamp(_osc(6, 1.8, 160), 2, 10)
        free = _clamp(_osc(8, 2.5, 130), 3, 14)
        buffers = _clamp(_osc(1.5, 0.7, 90), 0.3, 3)
        return {"cached_gb": round(cached, 2), "free_gb": round(free, 2), "buffers_gb": round(buffers, 2)}

    def register(self):
        return self.functions


# Disk ---------------------------------------------------------------------- #
class DemoDiskModule(BaseModule):
    name = "demo_disk"
    version = "1.0.0"
    description = "Demo disk metrics"

    def __init__(self):
        self.functions = {
            "usage": self.get_usage,
            "io": self.get_io,
            "partitions": self.get_partitions,
            "io_wait": self.get_io_wait,
        }
        self._last_ts = time.time()
        self._last_read = 0
        self._last_write = 0

    async def get_usage(self) -> dict:
        return {
            "/": {"percent": 61.2, "used_gb": 380.4, "total_gb": 622.1},
            "/data": {"percent": 47.5, "used_gb": 720.3, "total_gb": 1517.8},
        }

    async def get_io(self) -> dict:
        now = time.time()
        delta = max(now - self._last_ts, 1)
        read = _clamp(_osc(45, 20, 40), 5, 120)
        write = _clamp(_osc(38, 18, 50), 5, 110)
        self._last_ts = now
        self._last_read += read * delta
        self._last_write += write * delta
        return {"read_mb_s": round(read, 2), "write_mb_s": round(write, 2)}

    async def get_partitions(self) -> list:
        return [
            {"device": "/dev/sda1", "mountpoint": "/", "fstype": "ext4", "opts": "rw,relatime"},
            {"device": "/dev/sdb1", "mountpoint": "/data", "fstype": "ext4", "opts": "rw,relatime"},
        ]

    async def get_io_wait(self) -> float:
        return round(_clamp(_osc(1.8, 1.2, 70), 0, 10), 2)

    def register(self):
        return self.functions


# Network ------------------------------------------------------------------- #
class DemoNetworkModule(BaseModule):
    name = "demo_network"
    version = "1.0.0"
    description = "Demo network metrics"

    def __init__(self):
        self.functions = {
            "io": self.get_io,
            "connections": self.get_connections,
            "errors": self.get_errors,
        }
        self._last_ts = datetime.utcnow()

    async def get_io(self) -> dict:
        up = _clamp(_osc(12, 6, 35), 1, 40)
        down = _clamp(_osc(18, 9, 30), 2, 60)
        return {"upload_mb_s": round(up, 2), "download_mb_s": round(down, 2)}

    async def get_connections(self) -> dict:
        states = ["ESTABLISHED", "TIME_WAIT", "CLOSE_WAIT", "LISTEN"]
        counts = {s: _rng.randint(2, 40) for s in states}
        total = sum(counts.values())
        return {"total": total, "by_status": counts}

    async def get_errors(self) -> dict:
        return {"errors_in": _rng.randint(0, 4), "errors_out": _rng.randint(0, 3), "drops_in": _rng.randint(0, 2), "drops_out": _rng.randint(0, 2)}

    def register(self):
        return self.functions


# System -------------------------------------------------------------------- #
class DemoSystemModule(BaseModule):
    name = "demo_system"
    version = "1.0.0"
    description = "Demo system metrics"

    def __init__(self):
        self.functions = {
            "uptime": self.get_uptime,
            "info": self.get_info,
            "users": self.get_users,
            "process_count": self.get_process_count,
        }
        self._boot = datetime.utcnow() - timedelta(hours=72, minutes=13)

    async def get_uptime(self) -> dict:
        seconds = int((datetime.utcnow() - self._boot).total_seconds())
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        return {"seconds": seconds, "formatted": f"{days}d {hours}h {minutes}m"}

    async def get_info(self) -> dict:
        return {"system": "DemoOS", "release": "1.0", "version": "demo-build-2026.03", "machine": "x86_64", "processor": "DemoChip"}

    async def get_users(self) -> list:
        return [{"name": "alice", "terminal": "pts/0", "host": "10.0.0.5", "started": int(time.time()) - 3600}]

    async def get_process_count(self) -> int:
        return 184

    def register(self):
        return self.functions


# Process ------------------------------------------------------------------- #
class DemoProcessModule(BaseModule):
    name = "demo_process"
    version = "1.0.0"
    description = "Demo process metrics"

    def __init__(self):
        self.functions = {
            "top_cpu": self.get_top_cpu,
            "top_memory": self.get_top_memory,
            "zombie_count": self.get_zombie_count,
            "total_threads": self.get_total_threads,
        }

    async def get_top_cpu(self, count: int = 5) -> list:
        return [
            {"pid": 120 + i, "name": f"svc_{i}", "cpu_percent": round(_clamp(_osc(18 - i * 2, 6, 45 + i * 5), 0, 90), 1)}
            for i in range(count)
        ]

    async def get_top_memory(self, count: int = 5) -> list:
        return [
            {"pid": 220 + i, "name": f"worker_{i}", "memory_percent": round(_clamp(_osc(3.5 - i * 0.4, 1.2, 60 + i * 7), 0, 20), 2)}
            for i in range(count)
        ]

    async def get_zombie_count(self) -> int:
        return _rng.randint(0, 1)

    async def get_total_threads(self) -> int:
        return 820

    def register(self):
        return self.functions


# Temperature --------------------------------------------------------------- #
class DemoTemperatureModule(BaseModule):
    name = "demo_temperature"
    version = "1.0.0"
    description = "Demo temperature and fans"

    def __init__(self):
        self.functions = {
            "sensors": self.get_sensors,
            "fans": self.get_fans,
            "battery": self.get_battery,
        }

    async def get_sensors(self) -> dict:
        cpu = round(_clamp(_osc(57, 11, 100), 35, 85), 1)
        gpu = round(_clamp(_osc(63, 10, 95), 40, 90), 1)
        return {"coretemp": [{"label": "Package id 0", "current": cpu, "high": 90.0, "critical": 100.0}], "gpu": [{"label": "GPU 0", "current": gpu, "high": 92.0, "critical": 100.0}]}

    async def get_fans(self) -> dict:
        return {"fan1": [{"label": "CPU Fan", "current": _rng.randint(900, 1400)}], "fan2": [{"label": "Chassis", "current": _rng.randint(700, 1200)}]}

    async def get_battery(self) -> dict:
        percent = round(_clamp(_osc(86, 8, 180), 30, 100), 1)
        secs_left = int(percent / 100 * 3 * 3600)
        return {"present": True, "percent": percent, "power_plugged": percent > 95, "seconds_left": secs_left}

    def register(self):
        return self.functions

