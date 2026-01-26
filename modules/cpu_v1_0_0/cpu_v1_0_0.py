import psutil
import platform
import time
from modules.base import BaseModule


# ============================================================================
# CPU MODULE
# ============================================================================

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


# ============================================================================
# MEMORY MODULE
# ============================================================================

class MemoryModule(BaseModule):
    name = "memory"
    version = "1.0.0"
    description = "Memory (RAM and Swap) metrics"

    def __init__(self):
        self.functions = {
            "ram": self.get_ram,
            "swap": self.get_swap,
            "cached_vs_free": self.get_cached_vs_free
        }

    async def get_ram(self) -> dict:
        """RAM usage metrics"""
        mem = psutil.virtual_memory()
        return {
            "percent": round(mem.percent, 1),
            "used_gb": round(mem.used / (1024**3), 2),
            "total_gb": round(mem.total / (1024**3), 2),
            "available_gb": round(mem.available / (1024**3), 2)
        }

    async def get_swap(self) -> dict:
        """Swap usage metrics"""
        swap = psutil.swap_memory()
        return {
            "percent": round(swap.percent, 1),
            "used_gb": round(swap.used / (1024**3), 2),
            "total_gb": round(swap.total / (1024**3), 2)
        }

    async def get_cached_vs_free(self) -> dict:
        """Cached vs Free memory breakdown"""
        mem = psutil.virtual_memory()
        return {
            "cached_gb": round(getattr(mem, 'cached', 0) / (1024**3), 2),
            "free_gb": round(mem.free / (1024**3), 2),
            "buffers_gb": round(getattr(mem, 'buffers', 0) / (1024**3), 2)
        }

    def register(self):
        return self.functions


# ============================================================================
# DISK MODULE
# ============================================================================

class DiskModule(BaseModule):
    name = "disk"
    version = "1.0.0"
    description = "Disk usage, I/O, and partition metrics"

    def __init__(self):
        self.functions = {
            "usage": self.get_usage,
            "io": self.get_io,
            "partitions": self.get_partitions,
            "io_wait": self.get_io_wait
        }
        self._last_io = None

    async def get_usage(self) -> dict:
        """Disk usage per main partition"""
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
        
        return usage_data

    async def get_io(self) -> dict:
        """Disk read/write speeds in MB/s"""
        io_current = psutil.disk_io_counters()
        
        if self._last_io is None:
            self._last_io = io_current
            return {"read_mb_s": 0.0, "write_mb_s": 0.0}
        
        read_bytes = io_current.read_bytes - self._last_io.read_bytes
        write_bytes = io_current.write_bytes - self._last_io.write_bytes
        
        self._last_io = io_current
        
        return {
            "read_mb_s": round(read_bytes / (1024**2), 2),
            "write_mb_s": round(write_bytes / (1024**2), 2)
        }

    async def get_partitions(self) -> list:
        """List of disk partitions"""
        partitions = psutil.disk_partitions()
        return [
            {
                "device": p.device,
                "mountpoint": p.mountpoint,
                "fstype": p.fstype,
                "opts": p.opts
            }
            for p in partitions
        ]

    async def get_io_wait(self) -> float:
        """I/O wait time percentage (Linux only)"""
        try:
            with open('/proc/stat', 'r') as f:
                for line in f:
                    if line.startswith('cpu '):
                        fields = line.split()
                        iowait = int(fields[5])
                        total = sum(int(x) for x in fields[1:])
                        return round((iowait / total) * 100, 2) if total > 0 else 0.0
        except (FileNotFoundError, IndexError, ValueError):
            return -1.0
        return -1.0

    def register(self):
        return self.functions


# ============================================================================
# NETWORK MODULE
# ============================================================================

class NetworkModule(BaseModule):
    name = "network"
    version = "1.0.0"
    description = "Network I/O, connections, and error metrics"

    def __init__(self):
        self.functions = {
            "io": self.get_io,
            "connections": self.get_connections,
            "errors": self.get_errors
        }
        self._last_net = None

    async def get_io(self) -> dict:
        """Network upload/download speeds in MB/s"""
        net_current = psutil.net_io_counters()
        
        if self._last_net is None:
            self._last_net = net_current
            return {"upload_mb_s": 0.0, "download_mb_s": 0.0}
        
        sent_bytes = net_current.bytes_sent - self._last_net.bytes_sent
        recv_bytes = net_current.bytes_recv - self._last_net.bytes_recv
        
        self._last_net = net_current
        
        return {
            "upload_mb_s": round(sent_bytes / (1024**2), 2),
            "download_mb_s": round(recv_bytes / (1024**2), 2)
        }

    async def get_connections(self) -> dict:
        """Active network connections count by status"""
        connections = psutil.net_connections(kind='inet')
        status_counts = {}
        
        for conn in connections:
            status = conn.status if conn.status else 'UNKNOWN'
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "total": len(connections),
            "by_status": status_counts
        }

    async def get_errors(self) -> dict:
        """Packet errors and drops"""
        net = psutil.net_io_counters()
        return {
            "errors_in": net.errin,
            "errors_out": net.errout,
            "drops_in": net.dropin,
            "drops_out": net.dropout
        }

    def register(self):
        return self.functions


# ============================================================================
# SYSTEM MODULE
# ============================================================================

class SystemModule(BaseModule):
    name = "system"
    version = "1.0.0"
    description = "System health, uptime, and information"

    def __init__(self):
        self.functions = {
            "uptime": self.get_uptime,
            "info": self.get_info,
            "users": self.get_users,
            "process_count": self.get_process_count
        }

    async def get_uptime(self) -> dict:
        """System uptime in seconds and formatted"""
        boot_time = psutil.boot_time()
        uptime_seconds = int(time.time() - boot_time)
        
        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60
        
        return {
            "seconds": uptime_seconds,
            "formatted": f"{days}d {hours}h {minutes}m"
        }

    async def get_info(self) -> dict:
        """OS and kernel version information"""
        uname = platform.uname()
        return {
            "system": uname.system,
            "release": uname.release,
            "version": uname.version,
            "machine": uname.machine,
            "processor": uname.processor or "Unknown"
        }

    async def get_users(self) -> list:
        """Currently logged in users"""
        users = psutil.users()
        return [
            {
                "name": u.name,
                "terminal": u.terminal,
                "host": u.host,
                "started": u.started
            }
            for u in users
        ]

    async def get_process_count(self) -> int:
        """Total number of running processes"""
        return len(psutil.pids())

    def register(self):
        return self.functions


# ============================================================================
# PROCESS MODULE
# ============================================================================

class ProcessModule(BaseModule):
    name = "process"
    version = "1.0.0"
    description = "Top processes by CPU and memory usage"

    def __init__(self):
        self.functions = {
            "top_cpu": self.get_top_cpu,
            "top_memory": self.get_top_memory,
            "zombie_count": self.get_zombie_count,
            "total_threads": self.get_total_threads
        }

    async def get_top_cpu(self, count: int = 5) -> list:
        """Top N processes by CPU usage"""
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
            try:
                processes.append({
                    "pid": proc.info['pid'],
                    "name": proc.info['name'],
                    "cpu_percent": proc.info['cpu_percent']
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        processes.sort(key=lambda x: x['cpu_percent'] or 0, reverse=True)
        return processes[:count]

    async def get_top_memory(self, count: int = 5) -> list:
        """Top N processes by memory usage"""
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
            try:
                processes.append({
                    "pid": proc.info['pid'],
                    "name": proc.info['name'],
                    "memory_percent": round(proc.info['memory_percent'], 2)
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        processes.sort(key=lambda x: x['memory_percent'] or 0, reverse=True)
        return processes[:count]

    async def get_zombie_count(self) -> int:
        """Count of zombie processes"""
        count = 0
        for proc in psutil.process_iter(['status']):
            try:
                if proc.info['status'] == psutil.STATUS_ZOMBIE:
                    count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return count

    async def get_total_threads(self) -> int:
        """Total thread count across all processes"""
        total = 0
        for proc in psutil.process_iter(['num_threads']):
            try:
                total += proc.info['num_threads'] or 0
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return total

    def register(self):
        return self.functions


# ============================================================================
# TEMPERATURE MODULE
# ============================================================================

class TemperatureModule(BaseModule):
    name = "temperature"
    version = "1.0.0"
    description = "CPU, GPU temperature, fan speeds, and battery health"

    def __init__(self):
        self.functions = {
            "sensors": self.get_sensors,
            "fans": self.get_fans,
            "battery": self.get_battery
        }

    async def get_sensors(self) -> dict:
        """All temperature sensors (CPU, GPU, etc.)"""
        try:
            temps = psutil.sensors_temperatures()
            if not temps:
                return {}
            
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
            return result
        except AttributeError:
            return {}

    async def get_fans(self) -> dict:
        """Fan speeds in RPM"""
        try:
            fans = psutil.sensors_fans()
            if not fans:
                return {}
            
            result = {}
            for name, entries in fans.items():
                result[name] = [
                    {
                        "label": entry.label or "Unknown",
                        "current": entry.current
                    }
                    for entry in entries
                ]
            return result
        except AttributeError:
            return {}

    async def get_battery(self) -> dict:
        """Battery health and status"""
        try:
            battery = psutil.sensors_battery()
            if battery is None:
                return {"present": False}
            
            return {
                "present": True,
                "percent": battery.percent,
                "power_plugged": battery.power_plugged,
                "seconds_left": battery.secsleft if battery.secsleft != psutil.POWER_TIME_UNLIMITED else -1
            }
        except AttributeError:
            return {"present": False}

    def register(self):
        return self.functions