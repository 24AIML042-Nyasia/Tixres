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


# ============================================================================
# NETWORK MODULE
# ============================================================================

class NetworkModule(BaseModule):
    name = "network"
    version = "1.0.0"
    description = "Network I/O, connections, and error metrics"

    def __init__(self):
        self.functions = {
            "io": {"func": self.get_io, "dtype": "json"},
            "connections": {"func": self.get_connections, "dtype": "json"},
            "connections_detail": {"func": self.get_connections_detail, "dtype": "json"},
            "errors": {"func": self.get_errors, "dtype": "json"}
        }
        self._last_net = None
        self._last_net_ts = None

    async def get_io(self):
        if psutil is None:
            return psutil_missing_json()
        net_current = psutil.net_io_counters()

        if self._last_net is None:
            self._last_net = net_current
            self._last_net_ts = time.time()
            return wrap_json({"upload_mb_s": 0.0, "download_mb_s": 0.0})

        now = time.time()
        dt = now - (self._last_net_ts or now)
        if dt <= 0:
            dt = 1.0

        sent_bytes = net_current.bytes_sent - self._last_net.bytes_sent
        recv_bytes = net_current.bytes_recv - self._last_net.bytes_recv

        self._last_net = net_current
        self._last_net_ts = now

        return wrap_json({
            "upload_mb_s": round((sent_bytes / (1024**2)) / dt, 2),
            "download_mb_s": round((recv_bytes / (1024**2)) / dt, 2),
            "total_sent_bytes": int(net_current.bytes_sent),
            "total_recv_bytes": int(net_current.bytes_recv),
        })

    async def get_connections(self):
        if psutil is None:
            return psutil_missing_json()
        connections = psutil.net_connections(kind='inet')
        status_counts = {}

        for conn in connections:
            status = conn.status if conn.status else 'UNKNOWN'
            status_counts[status] = status_counts.get(status, 0) + 1

        return wrap_json({
            "total": len(connections),
            "by_status": status_counts
        })

    async def get_connections_detail(self, count: int = 10):
        if psutil is None:
            return psutil_missing_json()

        items: list[dict] = []
        try:
            connections = psutil.net_connections(kind="inet")
        except Exception:
            return wrap_json([])

        for conn in connections:
            try:
                pid = getattr(conn, "pid", None)
                status = getattr(conn, "status", None) or "UNKNOWN"
                laddr = getattr(conn, "laddr", None)
                raddr = getattr(conn, "raddr", None)
                local = (
                    f"{getattr(laddr, 'ip', '')}:{getattr(laddr, 'port', '')}"
                    if laddr
                    else ""
                )
                remote = (
                    f"{getattr(raddr, 'ip', '')}:{getattr(raddr, 'port', '')}"
                    if raddr
                    else ""
                )

                proc_name = None
                if pid:
                    try:
                        proc_name = psutil.Process(pid).name()
                    except Exception:
                        proc_name = None

                items.append(
                    {
                        "pid": pid,
                        "proc": proc_name,
                        "local": local,
                        "remote": remote,
                        "status": status,
                    }
                )
            except Exception:
                continue

        # Prefer established connections first, then listeners, then the rest.
        def _rank(item: dict) -> tuple[int, str]:
            st = str(item.get("status") or "")
            if st == "ESTABLISHED":
                return (0, st)
            if st == "LISTEN":
                return (1, st)
            return (2, st)

        items.sort(key=_rank)
        return wrap_json(items[: max(1, int(count))])

    async def get_errors(self):
        if psutil is None:
            return psutil_missing_json()
        net = psutil.net_io_counters()
        return wrap_json({
            "errors_in": net.errin,
            "errors_out": net.errout,
            "drops_in": net.dropin,
            "drops_out": net.dropout
        })

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


# ============================================================================
# PROCESS MODULE
# ============================================================================

class ProcessModule(BaseModule):
    name = "process"
    version = "1.0.0"
    description = "Top processes by CPU and memory usage"

    def __init__(self):
        self.functions = {
            "top": {"func": self.get_top, "dtype": "json"},
            "top_cpu": {"func": self.get_top_cpu, "dtype": "json"},
            "top_memory": {"func": self.get_top_memory, "dtype": "json"},
            "zombie_count": {"func": self.get_zombie_count, "dtype": int},
            "total_threads": {"func": self.get_total_threads, "dtype": int},
            "kill": {"func": self.kill_process, "dtype": "json", "type": "once"},
        }

    async def get_top(self, count: int = 15):
        if psutil is None:
            return psutil_missing_json()

        processes = []
        for proc in psutil.process_iter(["pid", "name", "status"]):
            try:
                cpu_pct = proc.cpu_percent(interval=None)
                mem_mb = None
                try:
                    mem_mb = round(proc.memory_info().rss / (1024**2))
                except Exception:
                    mem_mb = None
                processes.append(
                    {
                        "pid": proc.info.get("pid"),
                        "name": proc.info.get("name"),
                        "cpu_percent": float(cpu_pct) if cpu_pct is not None else 0.0,
                        "mem_mb": mem_mb,
                        "status": proc.info.get("status"),
                    }
                )
            except Exception:
                continue

        processes.sort(key=lambda x: x.get("cpu_percent") or 0.0, reverse=True)
        return wrap_json(processes[: max(1, int(count))])

    async def get_top_cpu(self, count: int = 5):
        if psutil is None:
            return psutil_missing_json()
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
            try:
                processes.append({
                    "pid": proc.info['pid'],
                    "name": proc.info['name'],
                    "cpu_percent": proc.info['cpu_percent']
                })
            except:
                continue

        processes.sort(key=lambda x: x['cpu_percent'] or 0, reverse=True)
        return wrap_json(processes[:count])

    async def get_top_memory(self, count: int = 5):
        if psutil is None:
            return psutil_missing_json()
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
            try:
                processes.append({
                    "pid": proc.info['pid'],
                    "name": proc.info['name'],
                    "memory_percent": round(proc.info['memory_percent'], 2)
                })
            except:
                continue

        processes.sort(key=lambda x: x['memory_percent'] or 0, reverse=True)
        return wrap_json(processes[:count])

    async def get_zombie_count(self):
        if psutil is None:
            return 0
        count = 0
        for proc in psutil.process_iter(['status']):
            try:
                if proc.info['status'] == psutil.STATUS_ZOMBIE:
                    count += 1
            except:
                continue
        return count

    async def get_total_threads(self):
        if psutil is None:
            return 0
        total = 0
        for proc in psutil.process_iter(['num_threads']):
            try:
                total += proc.info['num_threads'] or 0
            except:
                continue
        return total

    async def kill_process(self, pid: int, name: str | None = None):
        if psutil is None:
            return psutil_missing_json()

        try:
            pid_int = int(pid)
        except Exception:
            return wrap_json({"ok": False, "error": "invalid_pid", "pid": pid})

        if pid_int <= 0:
            return wrap_json({"ok": False, "error": "invalid_pid", "pid": pid_int})
        if pid_int == os.getpid():
            return wrap_json({"ok": False, "error": "refuse_self_kill", "pid": pid_int})

        try:
            proc = psutil.Process(pid_int)
        except psutil.NoSuchProcess:
            return wrap_json({"ok": False, "error": "no_such_process", "pid": pid_int})
        except Exception as exc:
            return wrap_json({"ok": False, "error": str(exc), "pid": pid_int})

        actual_name = None
        try:
            actual_name = proc.name()
        except Exception:
            actual_name = None

        if name and actual_name and str(name).lower() != str(actual_name).lower():
            return wrap_json(
                {
                    "ok": False,
                    "error": "name_mismatch",
                    "pid": pid_int,
                    "expected": name,
                    "actual": actual_name,
                }
            )

        try:
            proc.terminate()
            try:
                proc.wait(timeout=2)
                return wrap_json({"ok": True, "pid": pid_int, "name": actual_name, "action": "terminate"})
            except Exception:
                proc.kill()
                proc.wait(timeout=2)
                return wrap_json({"ok": True, "pid": pid_int, "name": actual_name, "action": "kill"})
        except psutil.AccessDenied:
            return wrap_json({"ok": False, "error": "access_denied", "pid": pid_int, "name": actual_name})
        except psutil.NoSuchProcess:
            return wrap_json({"ok": False, "error": "no_such_process", "pid": pid_int, "name": actual_name})
        except Exception as exc:
            return wrap_json({"ok": False, "error": str(exc), "pid": pid_int, "name": actual_name})

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
