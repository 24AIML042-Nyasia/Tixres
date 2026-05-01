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
# SYSTEM MODULE
# ============================================================================

class SystemModule(BaseModule):
    name = "system"
    version = "1.0.0"
    description = "System health, uptime, and information"

    def __init__(self):
        self.functions = {
            "uptime": {"func": self.get_uptime, "dtype": "json"},
            "info": {"func": self.get_info, "dtype": "json"},
            "users": {"func": self.get_users, "dtype": "json"},
            "process_count": {"func": self.get_process_count, "dtype": int}
        }

    async def get_uptime(self):
        if psutil is None:
            return psutil_missing_json()
        boot_time = psutil.boot_time()
        uptime_seconds = int(time.time() - boot_time)

        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60

        return wrap_json({
            "seconds": uptime_seconds,
            "formatted": f"{days}d {hours}h {minutes}m"
        })

    async def get_info(self):
        uname = platform.uname()
        return wrap_json({
            "system": uname.system,
            "release": uname.release,
            "version": uname.version,
            "machine": uname.machine,
            "processor": uname.processor or "Unknown"
        })

    async def get_users(self):
        if psutil is None:
            return psutil_missing_json()
        users = psutil.users()
        return wrap_json([
            {
                "name": u.name,
                "terminal": u.terminal,
                "host": u.host,
                "started": u.started
            }
            for u in users
        ])

    async def get_process_count(self):
        if psutil is None:
            return 0
        return len(psutil.pids())

    def register(self):
        return self.functions


