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


