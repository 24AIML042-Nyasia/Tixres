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


