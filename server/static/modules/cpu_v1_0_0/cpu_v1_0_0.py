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
# CPU MODULE
# ============================================================================

class CpuModule(BaseModule):
    name = "cpu"
    version = "1.0.0"
    description = "CPU metrics including usage, load, and temperature"

    def __init__(self):
        self.functions = {
            "usage_overall": {"func": self.get_usage_overall, "dtype": float},
            "usage_per_core": {"func": self.get_usage_per_core, "dtype": "json"},
            "load_average": {"func": self.get_load_average, "dtype": "json"},
            "temperature": {"func": self.get_temperature, "dtype": float},
            "core_count": {"func": self.get_core_count, "dtype": int},
            "frequency": {"func": self.get_frequency, "dtype": "json"}
        }

    async def get_usage_overall(self):
        if psutil is None:
            return -1.0
        return psutil.cpu_percent(interval=1)

    async def get_usage_per_core(self):
        if psutil is None:
            return psutil_missing_json()
        percents = psutil.cpu_percent(interval=1, percpu=True)
        return wrap_json({i: round(p, 1) for i, p in enumerate(percents)})

    async def get_load_average(self):
        try:
            load = psutil.getloadavg()
            return wrap_json({
                "1m": round(load[0], 2),
                "5m": round(load[1], 2),
                "15m": round(load[2], 2)
            })
        except:
            return wrap_json({"1m": 0.0, "5m": 0.0, "15m": 0.0})

    async def get_temperature(self):
        try:
            temps = psutil.sensors_temperatures()
            if not temps:
                return -1.0

            for name, entries in temps.items():
                if 'coretemp' in name.lower() or 'cpu' in name.lower():
                    for entry in entries:
                        if 'package' in entry.label.lower() or 'core 0' in entry.label.lower():
                            return float(entry.current)
                    return float(entries[0].current)

            first_sensor = next(iter(temps.values()))
            return float(first_sensor[0].current) if first_sensor else -1.0
        except:
            return -1.0

    async def get_core_count(self):
        if psutil is None:
            return 0
        return psutil.cpu_count(logical=True)

    async def get_frequency(self):
        try:
            freq = psutil.cpu_freq()
            if freq:
                return wrap_json({
                    "current": round(freq.current, 1),
                    "min": round(freq.min, 1),
                    "max": round(freq.max, 1)
                })
        except:
            pass
        return wrap_json({"current": 0.0, "min": 0.0, "max": 0.0})

    def register(self):
        return self.functions


