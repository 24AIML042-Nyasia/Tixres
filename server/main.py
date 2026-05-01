import asyncio
import base64
import hashlib
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from hmac_auth import verify_signature, verify_timestamp
from storage import get_storage
from ws_protocol import WebSocket, WebSocketError, handshake
from rollups import ROLLUP_10M, ROLLUP_1H, ROLLUP_1M, RollupService
from http_static import handle_static_http
from anomaly_detection import AnomalyDetector
from incidents import IncidentStore
from idp import TixresIdP


log = logging.getLogger(__name__)


def _add_agent_import_path() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    agent_dir = repo_root / "agent"
    sys.path.insert(0, str(agent_dir))
    return repo_root


def _safe_json(obj: Any) -> str:
    from datetime import datetime
    def handler(v):
        if isinstance(v, datetime):
            return v.strftime("%Y-%m-%d %H:%M:%S")
        return str(v)
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=handler)


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@dataclass
class Connection:
    ws: WebSocket
    send_lock: asyncio.Lock
    agent_id: str
    hostname: str
    role: str


@dataclass
class UiConnection:
    ws: WebSocket
    send_lock: asyncio.Lock
    username: str | None = None
    role: str = "user"


class MetricServer:
    def __init__(
        self,
        store,
        registry,
        default_template: dict,
        module_repo_root: Path,
        *,
        template_path: Path | None = None,
    ):
        self._store = store
        self._registry = registry
        self._default_template = default_template
        self._module_repo_root = Path(module_repo_root)
        self._template_path = Path(template_path) if template_path is not None else None
        self._connections: dict[int, Connection] = {}
        self._ui_connections: dict[int, UiConnection] = {}
        self._incident_store = IncidentStore(self._store.path)
        self._incident_store.init_db()
        self._detector = AnomalyDetector(self._store, self._incident_store, self._template_path)
        self._idp = TixresIdP(self._store.path)
        self._plugin_defaults_path = Path(__file__).parent / "plugin_defaults.json"

    def _get_plugin_path(self, plugin_name: str) -> Path:
        return Path(__file__).parent / "plugins" / f"{plugin_name}.json"

    def _load_plugin_config(self, plugin_name: str | None) -> dict[str, Any]:
        if not plugin_name:
            plugin_name = "standard_monitoring"
            
        path = self._get_plugin_path(plugin_name)
        if not path.exists():
            path = self._get_plugin_path("standard_monitoring")
        
        try:
            plugin_data = _load_json(path)
        except Exception:
            plugin_data = self._default_template.get("template", {})

        defaults = {}
        if self._plugin_defaults_path.exists():
            try:
                defaults = _load_json(self._plugin_defaults_path)
            except Exception:
                pass
        
        result = {
            "modules": plugin_data.get("modules", []),
            "metrics": plugin_data.get("metrics", {}),
            "detectors": plugin_data.get("detectors", {}),
            "retention": plugin_data.get("retention") or defaults.get("retention", {}),
            "rollups": plugin_data.get("rollups") or defaults.get("rollups", {}),
        }
        return {"template": result}

    async def broadcast_ui(self, payload: dict[str, Any]) -> None:
        text = _safe_json(payload)
        for conn in list(self._ui_connections.values()):
            try:
                async with conn.send_lock:
                    await conn.ws.send_text(text)
            except Exception:
                continue

    async def broadcast_ui_event(self, event: str, data: dict[str, Any]) -> None:
        await self.broadcast_ui({"event": event, "ok": True, "data": data})

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        conn_id = id(writer)
        authenticated_agent_id: str | None = None
        is_ui = False
        send_lock = asyncio.Lock()

        try:
            await handshake(reader, writer)
            ws = WebSocket(reader, writer)

            await ws.send_json({"event": "hello", "ok": True, "data": {"server": "two_o"}})

            while True:
                msg = await ws.recv_json()
                if msg is None:
                    return

                event = msg.get("event")
                if isinstance(event, str):
                    event = event.strip().replace(" ", "_")
                data = msg.get("data") or {}
                request_id = msg.get("request_id")

                try:
                    if event == "register":
                        agent_version = str(data.get("agent_version", "")).strip()
                        hostname = str(data.get("hostname", "")).strip()
                        os_name = str(data.get("os", "")).strip()
                        fingerprint = data.get("fingerprint")

                        created = self._store.register_agent(
                            agent_version=agent_version,
                            hostname=hostname,
                            os_name=os_name,
                            fingerprint=str(fingerprint) if fingerprint is not None else None,
                            role="user",
                        )
                        resp = {
                            "event": "register",
                            "ok": True,
                            "data": asdict(created),
                        }

                    elif event == "login":
                        api_key = str(data.get("api_key", "")).strip()
                        message = str(data.get("message", "")).strip()
                        signature = str(data.get("signature", "")).strip()

                        creds = self._store.get_credentials_by_api_key(api_key)
                        if not creds or int(creds.get("is_active") or 0) != 1:
                            raise ValueError("invalid credentials")

                        secret_key = str(creds["secret_key"])
                        if not verify_timestamp(message):
                            raise ValueError("invalid message timestamp")
                        if not verify_signature(api_key, secret_key, message, signature):
                            raise ValueError("invalid signature")

                        agent_id = str(creds["agent_id"])
                        authenticated_agent_id = agent_id

                        agent_version = data.get("agent_version")
                        hostname = data.get("hostname")
                        os_name = data.get("os")
                        fingerprint = data.get("fingerprint")

                        self._store.update_agent_on_login(
                            agent_id=agent_id,
                            agent_version=str(agent_version).strip()
                            if isinstance(agent_version, str)
                            else None,
                            hostname=str(hostname).strip() if isinstance(hostname, str) else None,
                            os_name=str(os_name).strip() if isinstance(os_name, str) else None,
                            fingerprint=str(fingerprint) if fingerprint is not None else None,
                        )

                        agent_row = self._store.get_agent_row(agent_id)
                        if not agent_row:
                            raise ValueError("agent not found")

                        template_obj: dict
                        if agent_row.template:
                            try:
                                template_obj = json.loads(agent_row.template)
                            except Exception:
                                template_obj = self._load_plugin_config(agent_row.plugin)
                        else:
                            template_obj = self._load_plugin_config(agent_row.plugin)

                        self._connections[conn_id] = Connection(
                            ws=ws,
                            send_lock=send_lock,
                            agent_id=agent_id,
                            hostname=agent_row.hostname,
                            role=agent_row.role,
                        )

                        resp = {
                            "event": "login",
                            "ok": True,
                            "data": {
                                "agent": asdict(agent_row),
                                "template": template_obj,
                            },
                        }

                        await self.broadcast_ui_event(
                            "agent_connected",
                            {"agent_id": agent_row.agent_id, "hostname": agent_row.hostname},
                        )

                    elif event == "template_update":
                        if not authenticated_agent_id:
                            raise ValueError("not logged in")
                        template = data.get("template")
                        if not isinstance(template, (dict, str)):
                            raise ValueError("template must be an object or JSON string")

                        from utils.template_engine import verify_template  # type: ignore

                        verification = verify_template(template, self._registry)
                        if not verification.ok:
                            resp = {
                                "event": "template_update",
                                "ok": False,
                                "data": asdict(verification),
                            }
                        else:
                            template_obj = (
                                json.loads(template) if isinstance(template, str) else template
                            )
                            self._store.update_template(
                                agent_id=authenticated_agent_id, template=template_obj
                            )
                            resp = {
                                "event": "template_update",
                                "ok": True,
                                "data": {"verification": asdict(verification)},
                            }

                    elif event == "module_verify":
                        if not authenticated_agent_id:
                            raise ValueError("not logged in")

                        modules = data.get("modules", [])
                        functions = data.get("functions", [])
                        fingerprint = data.get("fingerprint")

                        if not isinstance(modules, list) or not isinstance(functions, list):
                            raise ValueError("modules/functions must be lists")

                        resp = {
                            "event": "module_verify",
                            "ok": True,
                            "data": {"modules": len(modules), "functions": len(functions)},
                        }

                        # Do DB writes in the background so this RPC never blocks the event loop.
                        def _sync_update() -> None:
                            fp = str(fingerprint) if fingerprint is not None else None
                            ms = [str(m) for m in modules if isinstance(m, str)]
                            fs = [str(f) for f in functions if isinstance(f, str)]
                            try:
                                self._store.update_agent_on_login(
                                    agent_id=authenticated_agent_id, fingerprint=fp
                                )
                                if hasattr(self._store, "update_agent_inventory"):
                                    self._store.update_agent_inventory(
                                        agent_id=authenticated_agent_id,
                                        fingerprint=fp,
                                        modules=ms,
                                        functions=fs,
                                    )
                                agent_row = self._store.get_agent_row(authenticated_agent_id)
                                agent_label = (
                                    agent_row.hostname if agent_row else authenticated_agent_id
                                )
                                log.info(
                                    "module_verify agent=%s modules=%s functions=%s",
                                    agent_label,
                                    len(ms),
                                    len(fs),
                                )
                            except Exception:
                                return

                        asyncio.create_task(asyncio.to_thread(_sync_update))

                    elif event == "module_download":
                        if not authenticated_agent_id:
                            raise ValueError("not logged in")

                        requested = data.get("module_ids") or data.get("modules") or []
                        if isinstance(requested, str):
                            requested = [requested]
                        if not isinstance(requested, list):
                            raise ValueError("module_ids must be a list[str]")

                        # Return only the requested module files from the server's module repository.
                        repo_files: list[dict[str, Any]] = []
                        base_dir = self._module_repo_root.parent.parent  # .../server

                        for module_id in requested:
                            if not isinstance(module_id, str):
                                continue
                            
                            # Map module_id (e.g. cpu_v1.0.0) to folder name (e.g. cpu_v1_0_0)
                            folder_name = module_id.replace(".", "_")
                            module_dir = self._module_repo_root / folder_name
                            
                            if not module_dir.exists() or not module_dir.is_dir():
                                log.warning("Module download requested for non-existent module: %s (folder: %s)", module_id, folder_name)
                                continue

                            for path in sorted(module_dir.rglob("*.py")):
                                try:
                                    # We want the path relative to the repository 'base' so the agent
                                    # can reconstruct the 'static/modules/...' structure.
                                    # Since base_dir is .../server, rel will be 'static/modules/...'
                                    rel = path.relative_to(base_dir).as_posix()
                                except Exception:
                                    continue

                                content = path.read_bytes()
                                repo_files.append(
                                    {
                                        "path": rel,
                                        "sha256": hashlib.sha256(content).hexdigest(),
                                        "content_b64": base64.b64encode(content).decode("ascii"),
                                    }
                                )

                        resp = {
                            "event": "module_download",
                            "ok": True,
                            "data": {
                                "requested": [str(x) for x in requested if isinstance(x, str)],
                                "files": repo_files,
                            },
                        }

                    elif event == "submit_metrics":
                        if not authenticated_agent_id:
                            raise ValueError("not logged in")

                        self._store.update_agent_on_login(agent_id=authenticated_agent_id)

                        metrics = data.get("metrics")
                        if metrics is None:
                            metrics = [data]
                        if not isinstance(metrics, list):
                            raise ValueError("metrics must be a list")

                        agent_row = self._store.get_agent_row(authenticated_agent_id)
                        agent_label = (
                            agent_row.hostname if agent_row else authenticated_agent_id
                        )

                        # Process anomalies using the agent's specific plugin detector config
                        plugin_cfg = self._load_plugin_config(agent_row.plugin if agent_row else None)
                        detector_cfg = plugin_cfg.get("template", {}).get("detectors", {})
                        found_alerts = self._detector.process_metrics(authenticated_agent_id, metrics, detector_cfg)
                        
                        for alert in found_alerts:
                            await self.broadcast_ui({
                                "event": "alert",
                                "ok": True,
                                "data": alert
                            })

                        for item in metrics:
                            if not isinstance(item, dict):
                                continue
                            name = item.get("name")
                            value = item.get("value")
                            timestamp = item.get("timestamp")

                            entry = (
                                self._registry.get(name) if isinstance(name, str) else None
                            )
                            dtype = (
                                entry.dtype if entry else (item.get("dtype") or "unknown")
                            )

                            print(
                                f"[METRIC] agent={agent_label} name={name} dtype={dtype} value={value}"
                            )

                            if not isinstance(name, str) or not name:
                                continue
                            
                            try:
                                if dtype in ("int", "float") and isinstance(
                                    value, (int, float)
                                ):
                                    self._store.insert_metric_numeric(
                                        agent_id=authenticated_agent_id,
                                        metric_name=name,
                                        value=float(value),
                                        timestamp=timestamp,
                                    )
                                elif dtype == "json":
                                    value_text = (
                                        value
                                        if isinstance(value, str)
                                        else json.dumps(value, ensure_ascii=False)
                                    )
                                    self._store.insert_metric_json(
                                        agent_id=authenticated_agent_id,
                                        metric_name=name,
                                        value=value_text,
                                        timestamp=timestamp,
                                    )
                                    # Optimization: extract percent for numeric rollups if it's a known dict
                                    if isinstance(value, dict) and "percent" in value:
                                        self._store.insert_metric_numeric(
                                            agent_id=authenticated_agent_id,
                                            metric_name=f"{name}.percent",
                                            value=float(value["percent"]),
                                            timestamp=timestamp
                                        )
                                else:
                                    value_text = (
                                        value
                                        if isinstance(value, str)
                                        else json.dumps(value, ensure_ascii=False)
                                    )
                                    self._store.insert_metric_log(
                                        agent_id=authenticated_agent_id,
                                        metric_name=name,
                                        value=value_text,
                                        timestamp=timestamp,
                                    )
                            except Exception as exc:
                                self._store.insert_metric_log(
                                    agent_id=authenticated_agent_id,
                                    metric_name=name,
                                    value=f"store_error: {exc}",
                                    timestamp=timestamp,
                                )

                            await self.broadcast_ui(
                                {
                                    "event": "metric",
                                    "ok": True,
                                    "data": {
                                        "agent_id": authenticated_agent_id,
                                        "name": name,
                                        "dtype": dtype,
                                        "value": value,
                                        "timestamp": timestamp,
                                    },
                                }
                            )

                        resp = {"event": "submit_metrics", "ok": True, "data": {}}

                    elif event == "ui_login":
                        # ── SSO Login (IdP handles verification & token) ─
                        username = str(data.get("username", "")).strip()
                        password = str(data.get("password", "")).strip()
                        if not username or not password:
                            raise ValueError("username and password required")
                        
                        auth_result = self._idp.login(username, password)
                        if not auth_result:
                            raise ValueError("invalid credentials")
                            
                        resp = {
                            "event": "ui_login",
                            "ok": True,
                            "data": auth_result,
                        }

                    elif event == "ui_subscribe":
                        # ── validate JWT via IdP ─────────────────────────
                        token = data.get("token", "")
                        claims = self._idp.verify(str(token)) if token else None
                        if not claims:
                            raise ValueError("authentication required")
                        ui_username = claims["sub"]
                        ui_role = claims.get("role", "user")

                        is_ui = True
                        self._ui_connections[conn_id] = UiConnection(
                            ws=ws,
                            send_lock=send_lock,
                            username=ui_username,
                            role=ui_role,
                        )

                        requested_agent_id = data.get("agent_id")
                        if not isinstance(requested_agent_id, str) or not requested_agent_id:
                            requested_agent_id = None

                        agents = []
                        if hasattr(self._store, "list_agents"):
                            connected = {c.agent_id for c in self._connections.values()}
                            all_agents = self._store.list_agents()
                            # Non-admin users only see assigned agents
                            if ui_role != "admin":
                                assigned = set(
                                    self._idp.get_user_assignments(ui_username)
                                )
                                # If no assignments, show nothing (except maybe if we want a default?)
                                # Requirement: "Admin can assign agents to Users for monitoring"
                                # implies restrictive visibility.
                                all_agents = [
                                    a for a in all_agents
                                    if a.hostname in assigned
                                ]
                            for row in all_agents:
                                d = asdict(row)
                                d["connected"] = d.get("agent_id") in connected
                                agents.append(d)

                        selected_agent_id = requested_agent_id or (agents[0]["agent_id"] if agents else None)

                        plugins = []
                        plugins_dir = Path(__file__).parent / "plugins"
                        if plugins_dir.exists():
                            for pfile in plugins_dir.glob("*.json"):
                                plugins.append(pfile.stem)
                        if not plugins:
                            plugins = ["standard_monitoring"]

                        recent_metrics = []
                        if (
                            selected_agent_id
                            and hasattr(self._store, "get_recent_metrics")
                        ):
                            recent_metrics = self._store.get_recent_metrics(
                                agent_id=selected_agent_id, limit=500
                            )

                        template_obj = dict(self._default_template)
                        if selected_agent_id:
                            row = self._store.get_agent_row(selected_agent_id)
                            if row:
                                if row.template:
                                    try:
                                        template_obj = json.loads(row.template)
                                    except Exception:
                                        template_obj = self._load_plugin_config(row.plugin)
                                else:
                                    template_obj = self._load_plugin_config(row.plugin)

                        resp = {
                            "event": "ui_subscribe",
                            "ok": True,
                            "data": {
                                "agents": agents,
                                "selected_agent_id": selected_agent_id,
                                "template": template_obj,
                                "recent_metrics": recent_metrics,
                                "plugins": plugins,
                                "role": ui_role,
                                "username": ui_username,
                            },
                        }

                    elif event == "ui_run_once":
                        agent_id = data.get("agent_id")
                        name = data.get("name")
                        args = data.get("args") or {}
                        if not isinstance(agent_id, str) or not agent_id:
                            raise ValueError("agent_id is required")
                        if not isinstance(name, str) or not name:
                            raise ValueError("name is required")
                        if not isinstance(args, dict):
                            raise ValueError("args must be an object")

                        entry = self._registry.get(name)
                        if not entry:
                            raise ValueError(f"unknown function: {name}")

                        target_conn: Connection | None = None
                        for conn in self._connections.values():
                            if conn.agent_id == agent_id:
                                target_conn = conn
                                break
                        if target_conn is None:
                            raise ValueError("agent not connected")

                        payload = {
                            "event": "run_once",
                            "ok": True,
                            "data": {"name": name, "args": args},
                        }
                        async with target_conn.send_lock:
                            await target_conn.ws.send_text(_safe_json(payload))

                        resp = {"event": "ui_run_once", "ok": True, "data": {"sent": True}}

                    elif event == "ui_template_update":
                        template = data.get("template")
                        if not isinstance(template, (dict, str)):
                            raise ValueError("template must be an object or JSON string")

                        from utils.template_engine import verify_template  # type: ignore

                        verification = verify_template(template, self._registry)
                        if not verification.ok:
                            resp = {
                                "event": "ui_template_update",
                                "ok": False,
                                "data": asdict(verification),
                            }
                        else:
                            template_obj = (
                                json.loads(template) if isinstance(template, str) else template
                            )
                            if self._template_path is not None:
                                tmp_path = self._template_path.with_suffix(
                                    self._template_path.suffix + ".tmp"
                                )
                                tmp_path.write_text(
                                    json.dumps(template_obj, ensure_ascii=False, indent=2),
                                    encoding="utf-8",
                                )
                                tmp_path.replace(self._template_path)

                            await self.broadcast_template(template_obj)
                            for conn in list(self._connections.values()):
                                self._store.update_template(
                                    agent_id=conn.agent_id, template=template_obj
                                )

                            # Hot-reload detector thresholds from new template
                            try:
                                self._detector.reload_config(self._template_path)
                            except Exception:
                                pass

                            resp = {
                                "event": "ui_template_update",
                                "ok": True,
                                "data": {"verification": asdict(verification)},
                            }

                    elif event == "ui_get_alerts":
                        agent_id_filter = data.get("agent_id")
                        limit = int(data.get("limit", 100))
                        is_resolved = data.get("is_resolved")  # 0, 1, or None
                        alerts = self._store.list_alerts(
                            agent_id=agent_id_filter,
                            is_resolved=int(is_resolved) if is_resolved is not None else None,
                            limit=limit,
                        )
                        summary = self._store.alert_summary()
                        resp = {
                            "event": "ui_get_alerts",
                            "ok": True,
                            "data": {"alerts": alerts, "summary": summary},
                        }

                    elif event == "ui_resolve_alert":
                        alert_id = data.get("alert_id")
                        if not alert_id: raise ValueError("alert_id required")
                        ok = self._store.resolve_alert(int(alert_id))
                        resp = {"event": "ui_resolve_alert", "ok": ok, "data": {"alert_id": alert_id}}

                    elif event == "ui_get_rollups":
                        agent_id = data.get("agent_id")
                        if not agent_id: raise ValueError("agent_id required")
                        
                        cpu_rollups = self._store.get_rollups(agent_id=agent_id, metric_name="cpu_overall")
                        ram_rollups = self._store.get_rollups(agent_id=agent_id, metric_name="ram_percent")
                        
                        resp = {
                            "event": "ui_get_rollups",
                            "ok": True,
                            "data": {
                                "cpu": cpu_rollups,
                                "ram": ram_rollups
                            }
                        }

                    elif event == "ui_get_incidents":
                        host_id_filter = data.get("host_id") or data.get("agent_id")
                        status_filter = data.get("status")  # 'open' | 'resolved' | None
                        limit = int(data.get("limit", 200))
                        incidents = self._incident_store.list_incidents(
                            status=status_filter,
                            host_id=host_id_filter,
                            limit=limit,
                        )
                        summary = self._incident_store.incident_summary()
                        resp = {
                            "event": "ui_get_incidents",
                            "ok": True,
                            "data": {"incidents": incidents, "summary": summary},
                        }

                    elif event == "ui_resolve_incident":
                        incident_id = data.get("incident_id")
                        if not isinstance(incident_id, int):
                            raise ValueError("incident_id must be an integer")
                        ok = self._incident_store.resolve_incident(incident_id)
                        resp = {
                            "event": "ui_resolve_incident",
                            "ok": ok,
                            "data": {"incident_id": incident_id, "resolved": ok},
                        }
                        if ok:
                            await self.broadcast_ui_event(
                                "incident_resolved", {"incident_id": incident_id}
                            )

                    elif event == "ui_get_guidance":
                        incident_id = data.get("incident_id")
                        incident_key = data.get("incident_key")

                        incident = None
                        if incident_id:
                            incident = self._incident_store.get_incident(incident_id)
                        elif incident_key:
                            incidents = self._incident_store.list_incidents(limit=1000)
                            incident = next((i for i in incidents if i["incident_key"] == incident_key), None)

                        if not incident:
                            raise ValueError("Incident not found")

                        anomaly_type = incident["anomaly_type"]
                        guidance = self._store.get_guidance(anomaly_type)
                        
                        if not guidance:
                             # Fallback
                             guidance = {
                                "title": "General Anomaly",
                                "description": "No specific guidance available for this anomaly type.",
                                "steps": ["Investigate the metrics and logs for the affected host."],
                                "priority": "LOW",
                             }

                        resp = {
                            "event": "ui_get_guidance",
                            "ok": True,
                            "data": {"incident": incident, "guidance": guidance},
                        }

                    elif event == "ui_list_guidance":
                        search = str(data.get("search", "")).lower().strip()
                        all_guidance = self._store.list_guidance()
                        results = []
                        for entry in all_guidance:
                            key = entry["anomaly_type"]
                            if search and search not in key.lower() and search not in entry.get("title", "").lower() and search not in entry.get("description", "").lower():
                                continue
                            results.append({"key": key, **entry})
                        resp = {
                            "event": "ui_list_guidance",
                            "ok": True,
                            "data": {"guidance": results, "total": len(results)},
                        }

                    elif event == "ui_assign_agent":
                        # ── Admin-only: assign agent hostname to a user ──
                        # ── Admin-only check via IdP ─────────────────────
                        token = data.get("token", "")
                        claims = self._idp.verify(str(token)) if token else None
                        if not claims or claims.get("role") != "admin":
                            raise ValueError("admin privileges required")
                        target_username = str(data.get("username", "")).strip()
                        hostname = str(data.get("hostname", "")).strip()
                        if not target_username or not hostname:
                            raise ValueError("username and hostname required")
                        
                        # Note: user exists check also via IdP/Store
                        if not self._idp._store.get_user(target_username):
                            raise ValueError(f"user '{target_username}' not found")
                        ok_assign = self._idp._store.assign_agent(target_username, hostname)
                        resp = {
                            "event": "ui_assign_agent",
                            "ok": True,
                            "data": {
                                "username": target_username,
                                "hostname": hostname,
                                "new": ok_assign,
                            },
                        }

                    elif event == "ui_unassign_agent":
                        # ── Admin-only: remove agent assignment ──────────
                        token = data.get("token", "")
                        claims = self._idp.verify(str(token)) if token else None
                        if not claims or claims.get("role") != "admin":
                            raise ValueError("admin privileges required")
                        target_username = str(data.get("username", "")).strip()
                        hostname = str(data.get("hostname", "")).strip()
                        if not target_username or not hostname:
                            raise ValueError("username and hostname required")
                        ok_unassign = self._idp._store.unassign_agent(target_username, hostname)
                        resp = {
                            "event": "ui_unassign_agent",
                            "ok": ok_unassign,
                            "data": {
                                "username": target_username,
                                "hostname": hostname,
                                "removed": ok_unassign,
                            },
                        }

                    elif event == "ui_my_agents":
                        # ── Return agents assigned to the logged-in user ─
                        token = data.get("token", "")
                        claims = self._idp.verify(str(token)) if token else None
                        if not claims:
                            raise ValueError("authentication required")
                        ui_username = claims["sub"]
                        ui_role = claims.get("role", "user")
                        connected = {c.agent_id for c in self._connections.values()}
                        all_agents = self._store.list_agents() if hasattr(self._store, "list_agents") else []
                        if ui_role != "admin":
                            assigned = set(self._idp.get_user_assignments(ui_username))
                            all_agents = [a for a in all_agents if a.hostname in assigned]
                        agents_out = []
                        for row in all_agents:
                            d = asdict(row)
                            d["connected"] = d.get("agent_id") in connected
                            agents_out.append(d)
                        resp = {
                            "event": "ui_my_agents",
                            "ok": True,
                            "data": {
                                "agents": agents_out,
                                "username": ui_username,
                                "role": ui_role,
                            },
                        }

                    elif event == "ui_list_users":
                        # ── Admin-only: list UI users with assignments ───
                        token = data.get("token", "")
                        claims = self._idp.verify(str(token)) if token else None
                        if not claims or claims.get("role") != "admin":
                            raise ValueError("admin privileges required")
                        users = self._idp._store.list_users()
                        assignments = self._idp._store.list_assignments()
                        # Attach hostnames to each user
                        by_user: dict[str, list[str]] = {}
                        for a in assignments:
                            by_user.setdefault(a["username"], []).append(a["hostname"])
                        for u in users:
                            u["assigned_hostnames"] = by_user.get(u["username"], [])
                        resp = {
                            "event": "ui_list_users",
                            "ok": True,
                            "data": {"users": users},
                        }

                    elif event == "ui_upsert_guidance":
                        token = data.get("token", "")
                        claims = self._idp.verify(str(token)) if token else None
                        if not claims or claims.get("role") != "admin":
                            raise ValueError("admin privileges required")
                        
                        anomaly_type = str(data.get("anomaly_type", "")).strip()
                        title = str(data.get("title", "")).strip()
                        description = str(data.get("description", "")).strip()
                        steps = data.get("steps")
                        priority = str(data.get("priority", "LOW")).strip()
                        
                        if not anomaly_type or not title:
                            raise ValueError("anomaly_type and title are required")
                        if not isinstance(steps, list):
                            steps = []
                            
                        self._store.upsert_guidance(anomaly_type, title, description, steps, priority)
                        resp = {"event": "ui_upsert_guidance", "ok": True, "data": {"anomaly_type": anomaly_type}}

                    elif event == "ui_delete_guidance":
                        token = data.get("token", "")
                        claims = self._idp.verify(str(token)) if token else None
                        if not claims or claims.get("role") != "admin":
                            raise ValueError("admin privileges required")
                        
                        anomaly_type = str(data.get("anomaly_type", "")).strip()
                        if not anomaly_type:
                            raise ValueError("anomaly_type is required")
                            
                        ok = self._store.delete_guidance(anomaly_type)
                        resp = {"event": "ui_delete_guidance", "ok": ok, "data": {"anomaly_type": anomaly_type, "deleted": ok}}

                    elif event == "ui_set_agent_plugin":
                        token = data.get("token", "")
                        claims = self._idp.verify(str(token)) if token else None
                        if not claims:
                            raise ValueError("authentication required")
                        
                        ui_username = claims["sub"]
                        ui_role = claims.get("role", "user")
                        
                        agent_id = str(data.get("agent_id", "")).strip()
                        plugin_name = data.get("plugin") # can be None to unset
                        
                        if not agent_id:
                            raise ValueError("agent_id is required")
                        
                        agent_row = self._store.get_agent_row(agent_id)
                        if not agent_row:
                            raise ValueError("agent not found")
                        
                        # RBAC: Admin can change all, User only his allocated agents
                        if ui_role != "admin":
                            assigned = set(self._idp.get_user_assignments(ui_username))
                            if agent_row.hostname not in assigned:
                                raise ValueError("not authorized for this agent")
                        
                        self._store.update_plugin(agent_id=agent_id, plugin=plugin_name)
                        
                        # If agent is connected, send new template immediately
                        template_obj = self._load_plugin_config(plugin_name)
                        for conn in self._connections.values():
                            if conn.agent_id == agent_id:
                                async with conn.send_lock:
                                    await conn.ws.send_json({
                                        "event": "template_update",
                                        "ok": True,
                                        "data": {"template": template_obj}
                                    })
                                break

                        resp = {"event": "ui_set_agent_plugin", "ok": True, "data": {"agent_id": agent_id, "plugin": plugin_name}}

                    elif event == "ui_seed_alert":
                        # ── Admin: seed a dummy alert + incident via fake agent ──
                        token = data.get("token", "")
                        claims = self._idp.verify(str(token)) if token else None
                        if not claims or claims.get("role") != "admin":
                            raise ValueError("admin privileges required")

                        anomaly_type = str(data.get("anomaly_type", "statistical_anomaly")).strip()
                        severity = str(data.get("severity", "HIGH")).strip().upper()
                        service = str(data.get("service", "dummy.cpu_usage")).strip()
                        agent_id = str(data.get("agent_id", "dummy-seed-agent")).strip()

                        if severity not in ("HIGH", "MEDIUM", "LOW"):
                            severity = "HIGH"

                        # Ensure a dummy agent row exists for FK constraints
                        import uuid as _uuid
                        existing = self._store.get_agent_row(agent_id)
                        if not existing:
                            try:
                                self._store.register_agent(
                                    agent_version="0.0.0-seed",
                                    hostname=agent_id,
                                    os_name="seed",
                                    fingerprint="seed",
                                    role="user",
                                )
                                # Use the real agent_id we registered
                                all_a = self._store.list_agents()
                                seed_row = next((a for a in all_a if a.hostname == agent_id), None)
                                if seed_row:
                                    agent_id = seed_row.agent_id
                            except Exception:
                                pass

                        import hashlib as _hashlib
                        from datetime import datetime as _datetime
                        ts = _datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                        fingerprint = _hashlib.md5(
                            f"{agent_id}:{service}:{anomaly_type}".encode()
                        ).hexdigest()

                        cfg = self._detector._cfg
                        dedup_secs = (
                            cfg.get("dedup_high_secs", 300) if severity == "HIGH"
                            else cfg.get("dedup_medium_secs", 600) if severity == "MEDIUM"
                            else cfg.get("dedup_low_secs", 900)
                        )
                        alert = self._store.upsert_alert(
                            agent_id=agent_id,
                            service=service,
                            anomaly_type=anomaly_type,
                            severity=severity,
                            fingerprint=fingerprint,
                            timestamp=ts,
                            dedup_window_seconds=dedup_secs,
                            plugin="seed_tool",
                        )
                        try:
                            incident = self._incident_store.upsert_incident(
                                host_id=agent_id,
                                service=service,
                                plugin="seed_tool",
                                anomaly_type=anomaly_type,
                                severity=severity,
                                alert_id=alert.get("id"),
                                timestamp=ts,
                            )
                            alert["incident_id"] = incident.get("id")
                        except Exception as exc:
                            log.warning("Seed alert: incident upsert failed: %s", exc)

                        await self.broadcast_ui({"event": "alert", "ok": True, "data": alert})
                        resp = {
                            "event": "ui_seed_alert",
                            "ok": True,
                            "data": {"alert": alert},
                        }

                    elif event == "ui_get_task_schedule":
                        # ── Admin: read current Celery-like task schedule from plugin_defaults ──
                        token = data.get("token", "")
                        claims = self._idp.verify(str(token)) if token else None
                        if not claims or claims.get("role") != "admin":
                            raise ValueError("admin privileges required")

                        schedule = {}
                        if self._plugin_defaults_path.exists():
                            try:
                                schedule = _load_json(self._plugin_defaults_path).get("schedule", {})
                            except Exception:
                                pass

                        # Default schedule if not configured
                        defaults = {
                            "expire_alerts_minutes": 5,
                            "expire_incidents_minutes": 10,
                            "retention_cleanup_hours": 1,
                            "rollup_1m_minutes": 1,
                            "rollup_10m_minutes": 10,
                            "rollup_1h_minutes": 60,
                        }
                        defaults.update(schedule)
                        resp = {
                            "event": "ui_get_task_schedule",
                            "ok": True,
                            "data": {"schedule": defaults},
                        }

                    elif event == "ui_set_task_schedule":
                        # ── Admin: persist task schedule overrides to plugin_defaults ──
                        token = data.get("token", "")
                        claims = self._idp.verify(str(token)) if token else None
                        if not claims or claims.get("role") != "admin":
                            raise ValueError("admin privileges required")

                        new_schedule = data.get("schedule", {})
                        if not isinstance(new_schedule, dict):
                            raise ValueError("schedule must be an object")

                        allowed_keys = {
                            "expire_alerts_minutes", "expire_incidents_minutes",
                            "retention_cleanup_hours", "rollup_1m_minutes",
                            "rollup_10m_minutes", "rollup_1h_minutes",
                        }
                        validated = {}
                        for k, v in new_schedule.items():
                            if k in allowed_keys and isinstance(v, (int, float)) and v > 0:
                                validated[k] = float(v)

                        current = {}
                        if self._plugin_defaults_path.exists():
                            try:
                                current = _load_json(self._plugin_defaults_path)
                            except Exception:
                                pass
                        current["schedule"] = validated

                        tmp = self._plugin_defaults_path.with_suffix(".tmp")
                        tmp.write_text(
                            json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8"
                        )
                        tmp.replace(self._plugin_defaults_path)

                        resp = {
                            "event": "ui_set_task_schedule",
                            "ok": True,
                            "data": {"schedule": validated},
                        }

                    elif event == "ui_get_incidents":
                        # ── List incidents with summary stats ──────────────────
                        token = data.get("token", "")
                        claims = self._idp.verify(str(token)) if token else None
                        if not claims:
                            raise ValueError("authentication required")

                        ui_username = claims["sub"]
                        ui_role = claims.get("role", "user")
                        limit = min(int(data.get("limit", 100)), 500)

                        # Filter by host if user is not admin
                        host_filter = None
                        if ui_role != "admin":
                            assigned = self._idp.get_user_assignments(ui_username)
                            # This is tricky: IncidentStore uses host_id (which is agent_id).
                            # User assignments are hostnames.
                            # We should probably map hostname -> agent_id.
                            all_agents = self._store.list_agents()
                            assigned_ids = [a.agent_id for a in all_agents if a.hostname in assigned]
                            # For simplicity in this event, we'll return all for now if filter logic is too complex
                            # but ideally we filter. Let's filter by host_id.
                            incidents = []
                            for aid in assigned_ids:
                                incidents.extend(self._incident_store.list_incidents(host_id=aid, limit=limit))
                            # Re-sort because they were fetched per host
                            incidents.sort(key=lambda x: x["last_seen"], reverse=True)
                            incidents = incidents[:limit]
                        else:
                            incidents = self._incident_store.list_incidents(limit=limit)

                        # Map host_id to hostname for better UI display
                        try:
                            all_agents = self._store.list_agents()
                            agent_map = {a.agent_id: a.hostname for a in all_agents}
                            print(f"[DEBUG] Mapping {len(incidents)} incidents. Agents found: {list(agent_map.values())}")
                            for inc in incidents:
                                if "host_id" in inc:
                                    inc["hostname"] = agent_map.get(inc["host_id"], "Unknown Agent")
                                # Provide a shortened 'simple_key' for the UI (Upper case for visibility)
                                if "incident_key" in inc:
                                    inc["simple_key"] = inc["incident_key"][:8].upper()
                        except Exception as e:
                            print(f"[ERROR] Host mapping failed: {e}")

                        summary = self._incident_store.incident_summary()
                        resp = {
                            "event": "ui_get_incidents",
                            "ok": True,
                            "data": {
                                "incidents": incidents,
                                "summary": summary
                            }
                        }

                    elif event == "ui_resolve_incident":
                        # ── Mark an incident as resolved ──────────────────────
                        token = data.get("token", "")
                        claims = self._idp.verify(str(token)) if token else None
                        if not claims:
                            raise ValueError("authentication required")

                        ui_username = claims["sub"]
                        ui_role = claims.get("role", "user")
                        inc_id = int(data.get("incident_id", 0))

                        # RBAC: user can only resolve if assigned to that host
                        if ui_role != "admin":
                            inc = self._incident_store.get_incident(inc_id)
                            if not inc:
                                raise ValueError("incident not found")
                            assigned = self._idp.get_user_assignments(ui_username)
                            agent_row = self._store.get_agent_row(inc["host_id"])
                            if not agent_row or agent_row.hostname not in assigned:
                                raise ValueError("not authorized")

                        ok = self._incident_store.resolve_incident(inc_id)
                        resp = {
                            "event": "ui_resolve_incident",
                            "ok": ok,
                            "data": {"incident_id": inc_id, "resolved": ok}
                        }

                    elif event == "ui_get_rollups":
                        # ── Fetch rollup averages for dashboard charts (1m buckets) ──
                        agent_id = data.get("agent_id")
                        if not agent_id:
                            raise ValueError("agent_id required")

                        # We fetch the last 30 buckets of 1-minute rollups
                        cpu_rows = self._store.get_metrics_table(
                            table="metric_numeric_1m",
                            agent_id=agent_id,
                            metric_name="cpu_v1.0.0.usage_overall",
                            limit=30
                        )["rows"]

                        ram_rows = self._store.get_metrics_table(
                            table="metric_numeric_1m",
                            agent_id=agent_id,
                            metric_name="memory_v1.0.0.ram.percent",
                            limit=30
                        )["rows"]

                        resp = {
                            "event": "ui_get_rollups",
                            "ok": True,
                            "data": {
                                "cpu": cpu_rows,
                                "ram": ram_rows
                            }
                        }

                    elif event == "ui_get_metrics_table":
                        # ── Query any metric table with filters (admin + user) ──
                        token = data.get("token", "")
                        claims = self._idp.verify(str(token)) if token else None
                        if not claims:
                            raise ValueError("authentication required")

                        table_name = str(data.get("table", "metric_numeric")).strip()
                        agent_id_filter = data.get("agent_id") or None
                        metric_name_filter = data.get("metric_name") or None
                        from_ts = data.get("from_ts") or None
                        to_ts = data.get("to_ts") or None
                        limit = min(int(data.get("limit", 100)), 500)
                        offset = max(int(data.get("offset", 0)), 0)

                        result = self._store.get_metrics_table(
                            table=table_name,
                            agent_id=agent_id_filter,
                            metric_name=metric_name_filter,
                            from_ts=from_ts,
                            to_ts=to_ts,
                            limit=limit,
                            offset=offset,
                        )
                        resp = {
                            "event": "ui_get_metrics_table",
                            "ok": True,
                            "data": result,
                        }

                    else:
                        resp = {
                            "event": str(event),
                            "ok": False,
                            "error": f"unknown event: {event}",
                        }

                except Exception as exc:
                    resp = {"event": str(event), "ok": False, "error": str(exc)}

                if request_id is not None:
                    resp["request_id"] = request_id

                async with send_lock:
                    await ws.send_text(_safe_json(resp))

        except (WebSocketError, ConnectionError, asyncio.IncompleteReadError) as exc:
            log.info("client disconnected: %s", exc)
        except Exception:
            log.exception("client error")
        finally:
            removed_agent = self._connections.pop(conn_id, None)
            self._ui_connections.pop(conn_id, None)
            if removed_agent is not None:
                try:
                    await self.broadcast_ui_event(
                        "agent_disconnected", {"agent_id": removed_agent.agent_id}
                    )
                except Exception:
                    pass
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def broadcast_template(self, template: dict) -> None:
        payload = {"event": "template_update", "ok": True, "data": {"template": template}}
        text = _safe_json(payload)

        for conn in list(self._connections.values()):
            try:
                async with conn.send_lock:
                    await conn.ws.send_text(text)
            except Exception:
                continue


async def watch_template_file(
    app: MetricServer, template_path: Path, registry, store
):
    last_mtime: float | None = None

    from utils.template_engine import verify_template  # type: ignore

    while True:
        try:
            stat = template_path.stat()
            mtime = stat.st_mtime
        except FileNotFoundError:
            await asyncio.sleep(2)
            continue

        if last_mtime is None:
            last_mtime = mtime
        elif mtime != last_mtime:
            last_mtime = mtime
            try:
                template = _load_json(template_path)
                verification = verify_template(template, registry)
                if not verification.ok:
                    log.warning("Template file invalid: %s", verification)
                else:
                    log.info("Template file updated -> broadcasting to agents")
                    await app.broadcast_template(template)
                    for conn in list(app._connections.values()):
                        store.update_template(agent_id=conn.agent_id, template=template)
            except Exception as exc:
                log.warning("Failed to reload template: %s", exc)

        await asyncio.sleep(2)


async def main(host: str = "127.0.0.1", port: int = 8765, ui_port: int = 8000):
    repo_root = _add_agent_import_path()

    from utils.function_registry import FunctionRegistry, load_modules  # type: ignore

    registry = FunctionRegistry()
    load_modules(registry)

    # Use the new plugin system defaults
    plugin_dir = Path(__file__).parent / "plugins"
    defaults_path = Path(__file__).parent / "plugin_defaults.json"
    std_plugin_path = plugin_dir / "standard_monitoring.json"

    # Minimal fallback template if files are missing
    default_template = {
        "template": {
            "modules": ["cpu_v1.0.0", "memory_v1.0.0", "disk_v1.0.0", "network_v1.0.0", "system_v1.0.0", "process_v1.0.0"],
            "detectors": {}
        }
    }

    def _load_plugin_with_defaults(p_path: Path, d_path: Path) -> dict[str, Any]:
        merged = {}
        if d_path.exists():
            merged.update(_load_json(d_path))
        if p_path.exists():
            p_cfg = _load_json(p_path)
            merged["template"] = merged.get("template", {})
            merged["template"].update(p_cfg.get("template", {}))
        return merged

    if std_plugin_path.exists():
        default_template = _load_plugin_with_defaults(std_plugin_path, defaults_path)
    elif Path(__file__).with_name("template.json").exists():
        default_template = _load_json(Path(__file__).with_name("template.json"))

    store = get_storage()
    store.init_db()

    module_repo_root = Path(__file__).parent / "static" / "modules"
    app = MetricServer(
        store,
        registry,
        default_template=default_template,
        module_repo_root=module_repo_root,
        template_path=defaults_path, # Watch defaults instead of template.json
    )

    ws_server = await asyncio.start_server(app.handle_client, host, port)
    ws_addrs = ", ".join(str(sock.getsockname()) for sock in ws_server.sockets or [])
    print(f"WebSocket server listening on {ws_addrs}")

    ui_root = repo_root / "ui"
    async def _ui_handler(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await handle_static_http(reader, writer, root=ui_root)

    ui_server = await asyncio.start_server(
        _ui_handler, host, ui_port
    )
    ui_addrs = ", ".join(str(sock.getsockname()) for sock in ui_server.sockets or [])
    print(f"UI server listening on {ui_addrs}")
    print(f"UI root: {ui_root}")
    db_info = getattr(store, "url", str(store.path))
    print(f"DB: {db_info}")
    print(f"Default Plugin: Standard Monitoring")

    watcher_task = asyncio.create_task(watch_template_file(app, defaults_path, registry, store))
    rollups = RollupService(store.path)
    # Startup rollups (best-effort, do not block the event loop).
    async def _startup_rollup(bucket_seconds: int, target_table: str) -> None:
        try:
            await asyncio.to_thread(
                rollups.run_numeric_rollup,
                bucket_seconds=bucket_seconds,
                target_table=target_table,
            )
        except Exception:
            return

    startup_rollup_tasks = [
        asyncio.create_task(_startup_rollup(60, ROLLUP_1M)),
        asyncio.create_task(_startup_rollup(600, ROLLUP_10M)),
        asyncio.create_task(_startup_rollup(3600, ROLLUP_1H)),
    ]

    rollup_tasks = [
        asyncio.create_task(rollups.run_periodic(bucket_seconds=60, target_table=ROLLUP_1M)),
        asyncio.create_task(rollups.run_periodic(bucket_seconds=600, target_table=ROLLUP_10M)),
        asyncio.create_task(rollups.run_periodic(bucket_seconds=3600, target_table=ROLLUP_1H)),
    ]

    async def _expiration_loop():
        detector = AnomalyDetector(store)
        while True:
            try:
                await asyncio.to_thread(detector.run_expiration)
            except Exception:
                pass
            await asyncio.sleep(300)  # Run every 5 minutes

    expiration_task = asyncio.create_task(_expiration_loop())

    async with ws_server, ui_server:
        serve_tasks = [
            asyncio.create_task(ws_server.serve_forever()),
            asyncio.create_task(ui_server.serve_forever()),
        ]
        try:
            await asyncio.gather(*serve_tasks)
        finally:
            watcher_task.cancel()
            for t in startup_rollup_tasks:
                t.cancel()
            for t in rollup_tasks:
                t.cancel()
            expiration_task.cancel()
            for t in serve_tasks:
                t.cancel()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
