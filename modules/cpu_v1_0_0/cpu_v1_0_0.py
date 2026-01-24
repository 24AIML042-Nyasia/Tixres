# # import asyncio

# from modules.base import BaseModule

# class CpuModule(BaseModule):
#     name = "cpu"
#     version = "1.0.0"
#     description = "CPU related metrics"

#     def __init__(self):
#         self.functions = {
#             "usage": self.get_usage,
#             "cores": self.get_cores
#         }

#     async def get_usage(self):
#         return "42%"

#     async def get_cores(self):
#         return 8

#     def register(self):
#         return self.functions

# modules/cpu_v1_0_0.py
import psutil
from modules.base import BaseModule

class CpuModule(BaseModule):
    name = "cpu"
    version = "1.0.0"
    description = "CPU metrics including usage, load, and temperature"

    def __init__(self):
        self.functions = {
            "usage_overall": self.get_usage_overall,
            "usage_per_core": self.get_usage_per_core,
            "load_average": self.get_load_average,
            "temperature": self.get_temperature,
            "core_count": self.get_core_count,
            "frequency": self.get_frequency
        }

    async def get_usage_overall(self) -> float:
        """Overall CPU usage percentage"""
        return psutil.cpu_percent(interval=1)

    async def get_usage_per_core(self) -> dict:
        """Per-core CPU usage as dict {0: percent, 1: percent, ...}"""
        percents = psutil.cpu_percent(interval=1, percpu=True)
        return {i: round(p, 1) for i, p in enumerate(percents)}

    async def get_load_average(self) -> dict:
        """Load average as dict with 1m, 5m, 15m keys"""
        try:
            load = psutil.getloadavg()
            return {
                "1m": round(load[0], 2),
                "5m": round(load[1], 2),
                "15m": round(load[2], 2)
            }
        except (AttributeError, OSError):
            return {"1m": 0.0, "5m": 0.0, "15m": 0.0}

    async def get_temperature(self) -> float:
        """CPU temperature in Celsius (returns -1 if unavailable)"""
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
        except (AttributeError, IndexError, KeyError):
            return -1.0

    async def get_core_count(self) -> int:
        """Number of logical CPU cores"""
        return psutil.cpu_count(logical=True)

    async def get_frequency(self) -> dict:
        """CPU frequency in MHz as dict with current, min, max"""
        try:
            freq = psutil.cpu_freq()
            if freq:
                return {
                    "current": round(freq.current, 1),
                    "min": round(freq.min, 1),
                    "max": round(freq.max, 1)
                }
            return {"current": 0.0, "min": 0.0, "max": 0.0}
        except (AttributeError, OSError):
            return {"current": 0.0, "min": 0.0, "max": 0.0}

    def register(self):
        return self.functions


# modules/memory_v1_0_0.py
import psutil
from modules.base import BaseModule

class MemoryModule(BaseModule):
    name = "memory"
    version = "1.0.0"
    description = "RAM and swap memory metrics"

    def __init__(self):
        self.functions = {
            "ram": self.get_ram,
            "swap": self.get_swap
        }

    async def get_ram(self) -> dict:
        """RAM metrics in bytes and percentage"""
        mem = psutil.virtual_memory()
        return {
            "total": mem.total,
            "used": mem.used,
            "free": mem.available,
            "percent": mem.percent,
            "cached": getattr(mem, 'cached', 0),
            "buffers": getattr(mem, 'buffers', 0)
        }

    async def get_swap(self) -> dict:
        """Swap memory metrics in bytes and percentage"""
        swap = psutil.swap_memory()
        return {
            "total": swap.total,
            "used": swap.used,
            "free": swap.free,
            "percent": swap.percent
        }

    def register(self):
        return self.functions


# modules/disk_v1_0_0.py
import psutil
from modules.base import BaseModule

class DiskModule(BaseModule):
    name = "disk"
    version = "1.0.0"
    description = "Disk usage, I/O, and partition metrics"

    def __init__(self):
        self.functions = {
            "usage": self.get_usage,
            "io": self.get_io,
            "partitions": self.get_partitions
        }
        self._root_partition = self._get_root_partition()

    def _get_root_partition(self) -> str:
        """Get the root partition path"""
        try:
            partitions = psutil.disk_partitions()
            for part in partitions:
                if part.mountpoint in ['/', 'C:\\', 'C:/']:
                    return part.mountpoint
            return partitions[0].mountpoint if partitions else '/'
        except (IndexError, PermissionError):
            return '/'

    async def get_usage(self) -> dict:
        """Disk usage for root partition in bytes and percentage"""
        try:
            usage = psutil.disk_usage(self._root_partition)
            return {
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": usage.percent
            }
        except (PermissionError, OSError):
            return {"total": 0, "used": 0, "free": 0, "percent": 0.0}

    async def get_io(self) -> dict:
        """Disk I/O statistics"""
        try:
            io = psutil.disk_io_counters()
            return {
                "read_bytes": io.read_bytes,
                "write_bytes": io.write_bytes,
                "read_count": io.read_count,
                "write_count": io.write_count,
                "read_time_ms": io.read_time,
                "write_time_ms": io.write_time
            }
        except (AttributeError, RuntimeError):
            return {
                "read_bytes": 0,
                "write_bytes": 0,
                "read_count": 0,
                "write_count": 0,
                "read_time_ms": 0,
                "write_time_ms": 0
            }

    async def get_partitions(self) -> dict:
        """All mounted partitions with usage"""
        try:
            parts = psutil.disk_partitions()
            result = {}
            for p in parts:
                try:
                    usage = psutil.disk_usage(p.mountpoint)
                    result[p.mountpoint] = {
                        "device": p.device,
                        "fstype": p.fstype,
                        "total": usage.total,
                        "used": usage.used,
                        "free": usage.free,
                        "percent": usage.percent
                    }
                except (PermissionError, OSError):
                    continue
            return result
        except (PermissionError, OSError):
            return {}

    def register(self):
        return self.functions


# modules/system_v1_0_0.py
import psutil
import platform
from datetime import datetime
from modules.base import BaseModule

class SystemModule(BaseModule):
    name = "system"
    version = "1.0.0"
    description = "System health, uptime, and OS information"

    def __init__(self):
        self.functions = {
            "uptime": self.get_uptime,
            "info": self.get_info,
            "users": self.get_users,
            "process_count": self.get_process_count
        }

    async def get_uptime(self) -> dict:
        """System uptime information"""
        try:
            boot_time = psutil.boot_time()
            uptime_seconds = int(datetime.now().timestamp() - boot_time)
            return {
                "seconds": uptime_seconds,
                "boot_time": datetime.fromtimestamp(boot_time).isoformat()
            }
        except (OSError, ValueError):
            return {"seconds": 0, "boot_time": ""}

    async def get_info(self) -> dict:
        """Operating system information"""
        return {
            "os": platform.system(),
            "version": platform.release(),
            "hostname": platform.node(),
            "architecture": platform.machine()
        }

    async def get_users(self) -> int:
        """Number of logged-in users"""
        try:
            return len(psutil.users())
        except (OSError, RuntimeError):
            return 0

    async def get_process_count(self) -> int:
        """Total number of running processes"""
        try:
            return len(psutil.pids())
        except (OSError, RuntimeError):
            return 0

    def register(self):
        return self.functions


# modules/process_v1_0_0.py
import psutil
from modules.base import BaseModule

class ProcessModule(BaseModule):
    name = "process"
    version = "1.0.0"
    description = "Process-level monitoring metrics"

    def __init__(self):
        self.functions = {
            "top_cpu": self.get_top_cpu,
            "top_memory": self.get_top_memory,
            "zombie_count": self.get_zombie_count,
            "total_threads": self.get_total_threads
        }

    async def get_top_cpu(self) -> dict:
        """Top 5 CPU-consuming processes"""
        try:
            procs = []
            for p in psutil.process_iter(['name', 'pid', 'cpu_percent']):
                try:
                    procs.append(p.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            top = sorted(procs, key=lambda x: x.get('cpu_percent', 0), reverse=True)[:5]
            return {
                i: {
                    "name": p['name'],
                    "pid": p['pid'],
                    "cpu_percent": round(p.get('cpu_percent', 0), 1)
                }
                for i, p in enumerate(top)
            }
        except (OSError, RuntimeError):
            return {}

    async def get_top_memory(self) -> dict:
        """Top 5 memory-consuming processes"""
        try:
            procs = []
            for p in psutil.process_iter(['name', 'pid', 'memory_info']):
                try:
                    info = p.info
                    info['mem_mb'] = info['memory_info'].rss / (1024 * 1024)
                    procs.append(info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            top = sorted(procs, key=lambda x: x.get('mem_mb', 0), reverse=True)[:5]
            return {
                i: {
                    "name": p['name'],
                    "pid": p['pid'],
                    "memory_mb": round(p.get('mem_mb', 0), 1)
                }
                for i, p in enumerate(top)
            }
        except (OSError, RuntimeError):
            return {}

    async def get_zombie_count(self) -> int:
        """Number of zombie processes"""
        try:
            count = 0
            for p in psutil.process_iter(['status']):
                try:
                    if p.info['status'] == psutil.STATUS_ZOMBIE:
                        count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return count
        except (OSError, RuntimeError):
            return 0

    async def get_total_threads(self) -> int:
        """Total number of threads across all processes"""
        try:
            total = 0
            for p in psutil.process_iter(['num_threads']):
                try:
                    total += p.info.get('num_threads', 0)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return total
        except (OSError, RuntimeError):
            return 0

    def register(self):
        return self.functions


# modules/network_v1_0_0.py
import psutil
from modules.base import BaseModule

class NetworkModule(BaseModule):
    name = "network"
    version = "1.0.0"
    description = "Network usage and connection metrics"

    def __init__(self):
        self.functions = {
            "io": self.get_io,
            "connections": self.get_connections
        }

    async def get_io(self) -> dict:
        """Network I/O statistics"""
        try:
            io = psutil.net_io_counters()
            return {
                "bytes_sent": io.bytes_sent,
                "bytes_recv": io.bytes_recv,
                "packets_sent": io.packets_sent,
                "packets_recv": io.packets_recv
            }
        except (AttributeError, RuntimeError):
            return {
                "bytes_sent": 0,
                "bytes_recv": 0,
                "packets_sent": 0,
                "packets_recv": 0
            }

    async def get_connections(self) -> dict:
        """Network connection statistics"""
        try:
            conns = psutil.net_connections(kind='inet')
            established = sum(1 for c in conns if c.status == 'ESTABLISHED')
            listen = sum(1 for c in conns if c.status == 'LISTEN')
            
            return {
                "total": len(conns),
                "established": established,
                "listen": listen
            }
        except (psutil.AccessDenied, OSError):
            return {"total": 0, "established": 0, "listen": 0}

    def register(self):
        return self.functions


# modules/temperature_v1_0_0.py
import psutil
from modules.base import BaseModule

class TemperatureModule(BaseModule):
    name = "temperature"
    version = "1.0.0"
    description = "System temperature and fan metrics"

    def __init__(self):
        self.functions = {
            "sensors": self.get_sensors,
            "fans": self.get_fans,
            "battery": self.get_battery
        }

    async def get_sensors(self) -> dict:
        """Temperature sensors (returns empty dict if unavailable)"""
        try:
            temps = psutil.sensors_temperatures()
            if not temps:
                return {}
            
            result = {}
            for name, entries in temps.items():
                result[name] = [
                    {
                        "label": e.label,
                        "current": e.current,
                        "high": e.high if e.high else None,
                        "critical": e.critical if e.critical else None
                    }
                    for e in entries
                ]
            return result
        except AttributeError:
            return {}

    async def get_fans(self) -> dict:
        """Fan speeds in RPM (returns empty dict if unavailable)"""
        try:
            fans = psutil.sensors_fans()
            if not fans:
                return {}
            
            result = {}
            for name, entries in fans.items():
                result[name] = [
                    {"label": e.label, "current": e.current}
                    for e in entries
                ]
            return result
        except AttributeError:
            return {}

    async def get_battery(self) -> dict:
        """Battery information (returns empty dict if no battery)"""
        try:
            battery = psutil.sensors_battery()
            if not battery:
                return {}
            
            return {
                "percent": battery.percent,
                "plugged": battery.power_plugged,
                "time_left_seconds": battery.secsleft if battery.secsleft != psutil.POWER_TIME_UNLIMITED else -1
            }
        except (AttributeError, RuntimeError):
            return {}

    def register(self):
        return self.functions