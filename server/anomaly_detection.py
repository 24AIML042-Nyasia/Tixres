"""anomaly_detection.py – Template-driven anomaly detection with incident mapping.

Each alert fired by this detector is immediately forwarded to the IncidentStore
where it is grouped into an incident bucket via:

    incident_key = SHA-256( host_id | service | plugin | time_bucket )

Detector configuration is read from the template loaded in storage so that
operators can tune thresholds and enable/disable detectors without a redeploy.
"""
from __future__ import annotations

import hashlib
import json
import logging
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from storage import SqliteStorage, METRIC_TS_FMT
from incidents import IncidentStore

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Default detector configuration (overridable via template.json)
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_DETECTOR_CONFIG: dict[str, Any] = {
    # Statistical detector thresholds
    "stat_z_high": 5.0,
    "stat_z_medium": 3.0,
    "stat_z_low": 2.0,
    "stat_mad_high": 5.0,
    "stat_mad_medium": 3.0,
    "stat_mad_low": 2.0,
    "stat_min_history": 5,
    "stat_history_limit": 20,

    # Rule: CPU temperature
    "cpu_temp_high_c": 85.0,
    "cpu_temp_medium_c": 75.0,

    # Rule: RAM usage %
    "ram_high_pct": 90.0,

    # Rule: disk usage %
    "disk_high_pct": 90.0,

    # Rule: disk response time ms
    "disk_latency_ms": 100.0,

    # Rule: CPU jump (low → high)
    "cpu_jump_low_pct": 30.0,
    "cpu_jump_high_pct": 90.0,

    # Rule: CPU sustained %
    "cpu_sustained_pct": 85.0,
    "cpu_sustained_secs": 120,

    # Rule: RAM continuous increase secs
    "ram_increase_secs": 600,

    # Rule: network spike multiplier (vs. baseline)
    "net_spike_factor": 2.0,

    # Rule: disk IO spike multiplier (vs. rolling avg)
    "disk_io_spike_factor": 3.0,

    # Dedup windows per severity (seconds)
    "dedup_high_secs": 300,
    "dedup_medium_secs": 600,
    "dedup_low_secs": 900,
}


def _load_detector_config(config_path: Path | None = None) -> dict[str, Any]:
    """
    Merge DEFAULT_DETECTOR_CONFIG with overrides from plugin_defaults.json.
    """
    cfg = dict(DEFAULT_DETECTOR_CONFIG)
    path = config_path or Path(__file__).with_name("plugin_defaults.json")
    try:
        if path.exists():
            config = json.loads(path.read_text(encoding="utf-8"))
            overrides = config.get("detectors", {})
            for k, v in overrides.items():
                if k in cfg and isinstance(v, (int, float, bool)):
                    cfg[k] = v
    except Exception as exc:
        log.warning("Failed to load detector config from defaults: %s", exc)
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# AnomalyDetector
# ─────────────────────────────────────────────────────────────────────────────

class AnomalyDetector:
    def __init__(
        self,
        storage: SqliteStorage,
        incident_store: IncidentStore | None = None,
        template_path: Path | None = None,
    ):
        self.storage = storage
        self.incident_store = incident_store or IncidentStore(storage.path)
        self._cfg = _load_detector_config(template_path)

    def reload_config(self, template_path: Path | None = None) -> None:
        """Hot-reload detector thresholds from template (called by file watcher)."""
        self._cfg = _load_detector_config(template_path)
        log.info("Detector config reloaded")

    # ── fingerprint ────────────────────────────────────────────────────────
    def compute_fingerprint(self, agent_id: str, service: str, anomaly_type: str) -> str:
        payload = f"{agent_id}:{service}:{anomaly_type}"
        return hashlib.md5(payload.encode("utf-8")).hexdigest()

    # ── value extractor ────────────────────────────────────────────────────
    def _get_val(self, data: Any, key: str | None = None) -> float | None:
        """Helper to extract numeric value from possibly nested data."""
        try:
            val = data
            if isinstance(val, dict):
                if "value" in val:
                    val = val["value"]
                if key and isinstance(val, dict):
                    val = val.get(key)
            if isinstance(val, (int, float)):
                return float(val)
        except Exception:
            pass
        return None

    # ── statistical detector ───────────────────────────────────────────────
    def check_statistical(
        self, agent_id: str, metric_name: str, current_value: float, timestamp: str
    ) -> dict[str, Any] | None:
        cfg = self._cfg
        limit = int(cfg["stat_history_limit"])
        min_hist = int(cfg["stat_min_history"])

        history = self.storage.get_previous_metrics(agent_id, metric_name, limit=limit)
        if len(history) < min_hist:
            return None

        mean = statistics.mean(history)
        stdev = statistics.stdev(history) if len(history) > 1 else 0
        z_score = abs(current_value - mean) / stdev if stdev > 0 else 0

        median = statistics.median(history)
        abs_deviation = [abs(x - median) for x in history]
        mad = statistics.median(abs_deviation)
        mad_score = abs(current_value - median) / (mad * 1.4826) if mad > 0 else 0

        severity = None
        if z_score > cfg["stat_z_high"] or mad_score > cfg["stat_mad_high"]:
            severity = "HIGH"
        elif z_score > cfg["stat_z_medium"] or mad_score > cfg["stat_mad_medium"]:
            severity = "MEDIUM"
        elif z_score > cfg["stat_z_low"] or mad_score > cfg["stat_mad_low"]:
            severity = "LOW"

        if severity:
            return self._fire_alert(
                agent_id=agent_id,
                service=metric_name,
                anomaly_type="statistical_anomaly",
                severity=severity,
                timestamp=timestamp,
                plugin="stats_engine",
            )
        return None

    # ── rule-based detector ────────────────────────────────────────────────
    def check_rules(
        self, agent_id: str, metrics: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        cfg = self._cfg

        for m in metrics:
            name = m.get("name", "")
            val_raw = m.get("value")
            ts = m.get("timestamp") or datetime.utcnow().strftime(METRIC_TS_FMT)

            if "temperature" in name:
                temp = self._get_val(val_raw)
                if temp is not None:
                    if temp > cfg["cpu_temp_high_c"]:
                        found.append(self._fire_alert(agent_id, name, "cpu_temp_high", "HIGH", ts, "rule_engine"))
                    elif temp > cfg["cpu_temp_medium_c"]:
                        found.append(self._fire_alert(agent_id, name, "cpu_temp_high", "MEDIUM", ts, "rule_engine"))

            if "memory" in name and "ram" in name:
                pct = self._get_val(val_raw, "percent")
                if pct is not None and pct > cfg["ram_high_pct"]:
                    found.append(self._fire_alert(agent_id, name, "ram_usage_high", "HIGH", ts, "rule_engine"))

            if "disk" in name and "usage" in name:
                usages = val_raw if isinstance(val_raw, dict) else {}
                if "value" in usages:
                    usages = usages["value"]
                for path_key, data in usages.items():
                    pct = data.get("percent") if isinstance(data, dict) else None
                    if pct is not None and pct > cfg["disk_high_pct"]:
                        found.append(self._fire_alert(agent_id, f"{name}:{path_key}", "disk_usage_high", "HIGH", ts, "rule_engine"))

            if "disk" in name and "response_time" in name:
                latency = self._get_val(val_raw)
                if latency is not None and latency > cfg["disk_latency_ms"]:
                    found.append(self._fire_alert(agent_id, name, "disk_latency_high", "MEDIUM", ts, "rule_engine"))

            state_alerts = self._check_stateful_rules(agent_id, name, val_raw, ts)
            found.extend(state_alerts)

        return [a for a in found if a is not None]

    # ── stateful rules ─────────────────────────────────────────────────────
    def _check_stateful_rules(
        self, agent_id: str, name: str, val_raw: Any, ts: str
    ) -> list[dict[str, Any]]:
        detector_id = f"rule_{name}"
        state = self.storage.get_anomaly_state(agent_id, detector_id) or {}
        found: list[dict[str, Any]] = []
        cfg = self._cfg

        if "network" in name and "io" in name:
            up = self._get_val(val_raw, "upload_mb_s")
            dn = self._get_val(val_raw, "download_mb_s")
            if up is not None and dn is not None:
                val = up + dn
                baseline = state.get("baseline", val)
                if val > cfg["net_spike_factor"] * baseline and baseline > 0:
                    found.append(self._fire_alert(agent_id, name, "network_io_spike", "MEDIUM", ts, "rule_engine"))
                state["baseline"] = baseline * 0.95 + val * 0.05

        if "cpu" in name and "usage" in name:
            val = self._get_val(val_raw)
            if val is not None:
                last_val = state.get("last_val", val)
                if last_val < cfg["cpu_jump_low_pct"] and val > cfg["cpu_jump_high_pct"]:
                    found.append(self._fire_alert(agent_id, name, "cpu_usage_jump", "HIGH", ts, "rule_engine"))

                if val > cfg["cpu_sustained_pct"]:
                    start_ts = state.get("sustain_start")
                    if not start_ts:
                        state["sustain_start"] = ts
                    else:
                        try:
                            start_dt = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
                            current_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            if (current_dt - start_dt).total_seconds() > cfg["cpu_sustained_secs"]:
                                found.append(self._fire_alert(agent_id, name, "cpu_usage_sustained", "HIGH", ts, "rule_engine"))
                        except Exception:
                            pass
                else:
                    state["sustain_start"] = None

                state["last_val"] = val

        if "memory" in name and "ram" in name:
            val = self._get_val(val_raw, "percent")
            if val is not None:
                last_val = state.get("last_val", val)
                start_ts = state.get("increase_start")
                if val > last_val:
                    if not start_ts:
                        state["increase_start"] = ts
                    else:
                        try:
                            start_dt = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
                            current_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            if (current_dt - start_dt).total_seconds() > cfg["ram_increase_secs"]:
                                found.append(self._fire_alert(agent_id, name, "ram_continuous_increase", "MEDIUM", ts, "rule_engine"))
                        except Exception:
                            pass
                else:
                    state["increase_start"] = None
                state["last_val"] = val

        if "disk" in name and "io" in name:
            read = self._get_val(val_raw, "read_mb_s")
            write = self._get_val(val_raw, "write_mb_s")
            if read is not None and write is not None:
                val = read + write
                avg = state.get("average", val)
                if val > cfg["disk_io_spike_factor"] * avg and avg > 0:
                    found.append(self._fire_alert(agent_id, name, "disk_io_spike", "MEDIUM", ts, "rule_engine"))
                state["average"] = avg * 0.95 + val * 0.05

        if state:
            self.storage.set_anomaly_state(agent_id, detector_id, state)
        return [a for a in found if a is not None]

    # ── alert + incident fire ──────────────────────────────────────────────
    def _fire_alert(
        self,
        agent_id: str,
        service: str,
        anomaly_type: str,
        severity: str,
        timestamp: str,
        plugin: str,
    ) -> dict[str, Any] | None:
        cfg = self._cfg
        dedup_seconds = (
            cfg["dedup_high_secs"] if severity == "HIGH"
            else cfg["dedup_medium_secs"] if severity == "MEDIUM"
            else cfg["dedup_low_secs"]
        )
        fingerprint = self.compute_fingerprint(agent_id, service, anomaly_type)

        alert = self.storage.upsert_alert(
            agent_id=agent_id,
            service=service,
            anomaly_type=anomaly_type,
            severity=severity,
            fingerprint=fingerprint,
            timestamp=timestamp,
            dedup_window_seconds=dedup_seconds,
            plugin=plugin,
        )

        # Map alert → incident
        try:
            incident = self.incident_store.upsert_incident(
                host_id=agent_id,
                service=service,
                plugin=plugin,
                anomaly_type=anomaly_type,
                severity=severity,
                alert_id=alert.get("id"),
                timestamp=timestamp,
            )
            alert["incident_id"] = incident.get("id")
            alert["incident_key"] = incident.get("incident_key")
            alert["incident_status"] = incident.get("status")
        except Exception as exc:
            log.warning("Failed to upsert incident for alert %s: %s", alert.get("id"), exc)

        # Attach extra context useful for the UI
        alert["agent_id"] = agent_id
        alert["service"] = service
        alert["anomaly_type"] = anomaly_type
        alert["plugin"] = plugin
        return alert

    # ── main entry ────────────────────────────────────────────────────────
    def process_metrics(
        self, agent_id: str, metrics: list[dict[str, Any]], config_override: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        old_cfg = self._cfg
        if config_override:
            # Merge default config with override
            new_cfg = dict(DEFAULT_DETECTOR_CONFIG)
            new_cfg.update(config_override)
            self._cfg = new_cfg
        
        try:
            found: list[dict[str, Any]] = []
            found.extend(self.check_rules(agent_id, metrics))

            for m in metrics:
                name = m.get("name", "")
                val = self._get_val(m.get("value"))
                if val is not None:
                    alert = self.check_statistical(
                        agent_id, name, val, m.get("timestamp", "")
                    )
                    if alert:
                        found.append(alert)
            return found
        finally:
            self._cfg = old_cfg

    # ── expiration (fallback: asyncio loop uses this when Celery not running)
    def run_expiration(self) -> None:
        rules = {
            "HIGH":   int(self._cfg.get("dedup_high_secs", 7200)),
            "MEDIUM": int(self._cfg.get("dedup_medium_secs", 3600)),
            "LOW":    int(self._cfg.get("dedup_low_secs", 1800)),
        }
        count = self.storage.expire_alerts(rules)
        if count > 0:
            log.info("Auto-resolved %d stale alerts", count)
        try:
            inc_count = self.incident_store.expire_incidents()
            if inc_count > 0:
                log.info("Auto-resolved %d stale incidents", inc_count)
        except Exception as exc:
            log.warning("Incident expiry error: %s", exc)
