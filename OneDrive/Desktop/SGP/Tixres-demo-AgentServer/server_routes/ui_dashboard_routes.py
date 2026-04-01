import json
from sqlalchemy.orm import Session
from sqlalchemy import desc
from server_db.models import MetricNumeric, MetricJson


def build_dashboard_payload(db: Session, agent_id: str) -> dict:
    """
    Returns latest dashboard snapshot for an agent.
    Optimized to fetch only latest per metric.
    """

    # -------- Helper functions -------- #

    def latest_numeric(metric_name: str):
        row = (
            db.query(MetricNumeric)
            .filter(
                MetricNumeric.agent_id == agent_id,
                MetricNumeric.metric_name == metric_name,
            )
            .order_by(desc(MetricNumeric.timestamp))
            .first()
        )
        return row.value if row else None

    def latest_json(metric_name: str):
        row = (
            db.query(MetricJson)
            .filter(
                MetricJson.agent_id == agent_id,
                MetricJson.metric_name == metric_name,
            )
            .order_by(desc(MetricJson.timestamp))
            .first()
        )
        if not row:
            return None
        try:
            return json.loads(row.value)
        except Exception:
            return None

    # -------- CPU -------- #

    cpu_usage = latest_numeric("cpu_v1.0.0.usage_overall")
    per_core = latest_json("cpu_v1.0.0.usage_per_core")
    cpu_load = latest_json("cpu_v1.0.0.load_average")
    cpu_freq = latest_json("cpu_v1.0.0.frequency")
    top_cpu = latest_json("process_v1.0.0.top_cpu")

    # Remove idle process if exists
    if isinstance(top_cpu, list):
        top_cpu = [
            p for p in top_cpu
            if p.get("name") != "System Idle Process"
        ]

    # -------- Memory -------- #

    memory = latest_json("memory_v1.0.0.ram")
    cached_free = latest_json("memory_v1.0.0.cached_vs_free")
    swap = latest_json("memory_v1.0.0.swap")
    top_memory = latest_json("process_v1.0.0.top_memory")

    # -------- Disk -------- #

    disk_usage = latest_json("disk_v1.0.0.usage")
    disk_io = latest_json("disk_v1.0.0.io")

    total_disk = None
    used_disk = None
    free_disk = None
    disk_percent = None

    if disk_usage:
        # Assuming single drive
        drive = list(disk_usage.values())[0]
        total_disk = drive.get("total_gb")
        used_disk = drive.get("used_gb")
        disk_percent = drive.get("percent")
        if total_disk and used_disk:
            free_disk = total_disk - used_disk

    # -------- Network -------- #

    network_io = latest_json("network_v1.0.0.io")
    network_conn = latest_json("network_v1.0.0.connections")
    network_errors = latest_json("network_v1.0.0.errors")

    total_bandwidth_mbps = None
    if network_io:
        total_bandwidth_mbps = (
            (network_io.get("upload_mb_s", 0) +
             network_io.get("download_mb_s", 0)) * 8
        )

    total_errors = 0
    if network_errors:
        total_errors = (
            network_errors.get("errors_in", 0) +
            network_errors.get("errors_out", 0)
        )

    active_connections = None
    if network_conn:
        active_connections = network_conn.get("total")

    # -------- Process Stats -------- #

    total_threads = latest_numeric("process_v1.0.0.total_threads")
    zombie_count = latest_numeric("process_v1.0.0.zombie_count")

    # -------- Final Payload -------- #

    return {
        # CPU
        "cpu_usage_percent": cpu_usage,
        "cpu_per_core": per_core,
        "cpu_load_avg": cpu_load,
        "cpu_frequency": cpu_freq,
        "top_cpu_process": top_cpu[0] if top_cpu else None,

        # Memory
        "memory_percent": memory.get("percent") if memory else None,
        "memory_used_gb": memory.get("used_gb") if memory else None,
        "memory_total_gb": memory.get("total_gb") if memory else None,
        "memory_available_gb": memory.get("available_gb") if memory else None,
        "memory_cached_gb": cached_free.get("cached_gb") if cached_free else None,
        "memory_free_gb": cached_free.get("free_gb") if cached_free else None,
        "swap_percent": swap.get("percent") if swap else None,
        "swap_used_gb": swap.get("used_gb") if swap else None,
        "swap_total_gb": swap.get("total_gb") if swap else None,
        "top_memory_process": top_memory[0] if top_memory else None,

        # Disk
        "disk_percent": disk_percent,
        "disk_total_gb": total_disk,
        "disk_used_gb": used_disk,
        "disk_free_gb": free_disk,
        "disk_read_mb_s": disk_io.get("read_mb_s") if disk_io else None,
        "disk_write_mb_s": disk_io.get("write_mb_s") if disk_io else None,

        # Network
        "network_total_mbps": total_bandwidth_mbps,
        "network_active_connections": active_connections,
        "network_total_errors": total_errors,

        # Process
        "total_threads": total_threads,
        "zombie_count": zombie_count,
    }
