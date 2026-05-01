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
# TEMPERATURE MODULE
# ============================================================================

class TemperatureModule(BaseModule):
    name = "temperature"
    version = "1.0.0"
    description = "CPU, GPU temperature, fan speeds, and battery health"

    def __init__(self):
        self.functions = {
            "sensors": {"func": self.get_sensors, "dtype": "json"},
            "fans": {"func": self.get_fans, "dtype": "json"},
            "battery": {"func": self.get_battery, "dtype": "json"}
        }

    async def get_sensors(self):
        try:
            temps = psutil.sensors_temperatures()
            if not temps:
                return wrap_json({})

            result = {}
            for name, entries in temps.items():
                result[name] = [
                    {
                        "label": entry.label or "Unknown",
                        "current": entry.current,
                        "high": entry.high,
                        "critical": entry.critical
                    }
                    for entry in entries
                ]
            return wrap_json(result)
        except:
            return wrap_json({})

    async def get_fans(self):
        try:
            fans = psutil.sensors_fans()
            if not fans:
                return wrap_json({})

            result = {}
            for name, entries in fans.items():
                result[name] = [
                    {
                        "label": entry.label or "Unknown",
                        "current": entry.current
                    }
                    for entry in entries
                ]
            return wrap_json(result)
        except:
            return wrap_json({})

    async def get_battery(self):
        try:
            battery = psutil.sensors_battery()
            if battery is None:
                return wrap_json({"present": False})

            return wrap_json({
                "present": True,
                "percent": battery.percent,
                "power_plugged": battery.power_plugged,
                "seconds_left": battery.secsleft if battery.secsleft != psutil.POWER_TIME_UNLIMITED else -1
            })
        except:
            return wrap_json({"present": False})

    def register(self):
        return self.functions
