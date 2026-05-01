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
# DISK MODULE
# ============================================================================

class DiskModule(BaseModule):
    name = "disk"
    version = "1.0.0"
    description = "Disk usage, I/O, and partition metrics"

    def __init__(self):
        self.functions = {
            "usage": {"func": self.get_usage, "dtype": "json"},
            "io": {"func": self.get_io, "dtype": "json"},
            "partitions": {"func": self.get_partitions, "dtype": "json"},
            "io_wait": {"func": self.get_io_wait, "dtype": float}
        }
        self._last_io = None
        self._last_io_ts = None

    async def get_usage(self):
        if psutil is None:
            return psutil_missing_json()
        partitions = psutil.disk_partitions()
        usage_data = {}

        for partition in partitions:
            if partition.fstype:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    usage_data[partition.mountpoint] = {
                        "percent": round(usage.percent, 1),
                        "used_gb": round(usage.used / (1024**3), 2),
                        "total_gb": round(usage.total / (1024**3), 2)
                    }
                except PermissionError:
                    continue

        return wrap_json(usage_data)

    async def get_io(self):
        if psutil is None:
            return psutil_missing_json()
        io_current = psutil.disk_io_counters()

        if self._last_io is None:
            self._last_io = io_current
            self._last_io_ts = time.time()
            return wrap_json({"read_mb_s": 0.0, "write_mb_s": 0.0})

        now = time.time()
        dt = now - (self._last_io_ts or now)
        if dt <= 0:
            dt = 1.0

        read_bytes = io_current.read_bytes - self._last_io.read_bytes
        write_bytes = io_current.write_bytes - self._last_io.write_bytes

        self._last_io = io_current
        self._last_io_ts = now

        return wrap_json({
            "read_mb_s": round((read_bytes / (1024**2)) / dt, 2),
            "write_mb_s": round((write_bytes / (1024**2)) / dt, 2)
        })

    async def get_partitions(self):
        if psutil is None:
            return psutil_missing_json()
        partitions = psutil.disk_partitions()
        return wrap_json([
            {
                "device": p.device,
                "mountpoint": p.mountpoint,
                "fstype": p.fstype,
                "opts": p.opts
            }
            for p in partitions
        ])

    async def get_io_wait(self):
        try:
            with open('/proc/stat', 'r') as f:
                for line in f:
                    if line.startswith('cpu '):
                        fields = line.split()
                        iowait = int(fields[5])
                        total = sum(int(x) for x in fields[1:])
                        return round((iowait / total) * 100, 2) if total > 0 else 0.0
        except:
            return -1.0
        return -1.0

    def register(self):
        return self.functions


