"""config.py – Central configuration loader for the Tixres chatbot microservice.

All host/port settings are read from config.json at the project root.
Change that file to reconfigure any service.
"""
from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_CFG_PATH = _ROOT / "config.json"


def _load() -> dict:
    if _CFG_PATH.exists():
        with _CFG_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}


_cfg = _load()

# ── Chatbot service ───────────────────────────────────────────────────────────
CHATBOT_HOST: str = _cfg.get("chatbot", {}).get("host", "127.0.0.1")
CHATBOT_PORT: int = int(_cfg.get("chatbot", {}).get("port", 8001))

# Convenience base URL (useful for ingest scripts)
CHATBOT_BASE_URL: str = f"http://{CHATBOT_HOST}:{CHATBOT_PORT}"

# ── Main WS / UI server ───────────────────────────────────────────────────────
SERVER_HOST: str = _cfg.get("server", {}).get("host", "127.0.0.1")
WS_PORT: int     = int(_cfg.get("server", {}).get("ws_port", 8765))
UI_PORT: int     = int(_cfg.get("server", {}).get("ui_port", 8000))

# ── Celery / Redis ────────────────────────────────────────────────────────────
CELERY_BROKER:  str = _cfg.get("celery", {}).get("broker_url",  "redis://127.0.0.1:6379/0")
CELERY_BACKEND: str = _cfg.get("celery", {}).get("result_backend", "redis://127.0.0.1:6379/1")
