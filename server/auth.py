"""auth.py – Lightweight JWT-based SSO auth for the Tixres UI.

Two roles
---------
  admin   – full access; manage users & assign agents; can only be created via CLI
  user    – read-only dashboard + sees only agents assigned to them

JWT structure (HS256-compatible dummy, no external lib required)
---------------------------------------------------------------
  header.payload.signature
  header  = base64url({"alg":"HS256","typ":"JWT"})
  payload = base64url({"sub": username, "role": role, "exp": unix_ts, "iat": unix_ts})
  sig     = HMAC-SHA256(header + "." + payload, SECRET)

SSO-compatibility note
----------------------
  The token shape is standard JWT so it can be replaced by a real OIDC IdP token
  by swapping _verify_token() with a JWKS-backed verifier.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import sqlite3
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── config ──────────────────────────────────────────────────────────
DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "agent_metrics.sqlite3"
TOKEN_TTL_SECONDS = 8 * 3600          # 8 hours
ADMIN_SECRET_ENV  = "SYSMON_JWT_SECRET"

# Persistent secret stored in DB so it survives restarts.
# A real deployment should load this from an env-var / secrets manager.
_CACHED_SECRET: str | None = None


# ── base64url helpers ───────────────────────────────────────────────

def _b64enc(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64dec(s: str) -> bytes:
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return urlsafe_b64decode(s)


# ── JWTProvider: The "IdP" core logic ────────────────────────────────

class JWTProvider:
    """Handles the cryptographic side of JWT (issuing and verifying).
    In a real SSO setup, this might be a remote OIDC provider.
    """
    def __init__(self, secret: str, ttl: int = TOKEN_TTL_SECONDS):
        self._secret = secret
        self._ttl = ttl
        self._header = _b64enc(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())

    def _sign(self, header_dot_payload: str) -> str:
        sig = hmac.new(self._secret.encode(), header_dot_payload.encode(), hashlib.sha256).digest()
        return _b64enc(sig)

    def issue_token(self, username: str, role: str) -> str:
        now = int(time.time())
        payload = _b64enc(json.dumps(
            {"sub": username, "role": role, "iat": now, "exp": now + self._ttl},
            separators=(",", ":"),
        ).encode())
        header_payload = f"{self._header}.{payload}"
        return f"{header_payload}.{self._sign(header_payload)}"

    def verify_token(self, token: str) -> dict[str, Any] | None:
        """Return the decoded payload dict if the token is valid, else None."""
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None
            header_payload = f"{parts[0]}.{parts[1]}"
            expected = self._sign(header_payload)
            if not hmac.compare_digest(expected, parts[2]):
                return None
            payload = json.loads(_b64dec(parts[1]))
            if payload.get("exp", 0) < time.time():
                return None
            return payload
        except Exception:
            return None

# Keep top-level functions for backward compatibility if needed, 
# but they now use a default provider if we want, or we can just migrate callers.
def issue_token(username: str, role: str, secret: str, ttl: int = TOKEN_TTL_SECONDS) -> str:
    return JWTProvider(secret, ttl).issue_token(username, role)

def verify_token(token: str, secret: str) -> dict[str, Any] | None:
    return JWTProvider(secret).verify_token(token)


# ── AuthStore: UI users ──────────────────────────────────────────────

try:
    from sqlalchemy import create_engine, text, Column, Integer, String, Text, TIMESTAMP, Index
    from sqlalchemy.orm import sessionmaker, Session
    from models import AuthConfig, UiUser, AgentAssignment, Base, SQLALCHEMY_AVAILABLE
except ImportError:
    SQLALCHEMY_AVAILABLE = False

class AuthStore:
    """Manages UI users (not agents) in the shared SQLite/PostgreSQL DB."""

    def __init__(self, path: Path = DEFAULT_DB_PATH) -> None:
        self._path = Path(path)
        self._use_sqlalchemy = SQLALCHEMY_AVAILABLE
        self._engine = None
        self._SessionLocal = None

        if self._use_sqlalchemy:
            from config_loader import get_db_url
            connection_url = get_db_url()
            
            self._engine = create_engine(connection_url)
            self._SessionLocal = sessionmaker(bind=self._engine, expire_on_commit=False)

    # ── schema ──────────────────────────────────────────────────────

    def init_db(self) -> None:
        if self._use_sqlalchemy and self._engine:
            Base.metadata.create_all(self._engine)
            # Seed secret if missing
            with self._engine.connect() as conn:
                row = conn.execute(text("SELECT value FROM auth_config WHERE key='jwt_secret';")).fetchone()
                if not row:
                    secret = secrets.token_hex(32)
                    conn.execute(text("INSERT INTO auth_config(key, value) VALUES ('jwt_secret', :v);"), {"v": secret})
                    conn.commit()
            return

        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as conn:
            # JWT signing secret (one row, seeded on first init)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS auth_config (
                  key   TEXT PRIMARY KEY,
                  value TEXT NOT NULL
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ui_users (
                  username    TEXT PRIMARY KEY,
                  pw_hash     TEXT NOT NULL,
                  role        TEXT NOT NULL DEFAULT 'user',
                  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  is_active   INTEGER DEFAULT 1
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_assignments (
                  username    TEXT NOT NULL,
                  hostname    TEXT NOT NULL,
                  assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  PRIMARY KEY (username, hostname)
                );
            """)
            # Seed secret if missing
            row = conn.execute("SELECT value FROM auth_config WHERE key='jwt_secret';").fetchone()
            if not row:
                secret = secrets.token_hex(32)
                conn.execute(
                    "INSERT INTO auth_config(key, value) VALUES ('jwt_secret', ?);", (secret,)
                )

    # ── secret management ────────────────────────────────────────────
    def get_secret(self) -> str:
        global _CACHED_SECRET
        if _CACHED_SECRET:
            return _CACHED_SECRET
        self.init_db()
        if self._use_sqlalchemy and self._engine:
            with self._engine.connect() as conn:
                row = conn.execute(text("SELECT value FROM auth_config WHERE key='jwt_secret';")).fetchone()
                if row:
                    _CACHED_SECRET = row[0]
                    return _CACHED_SECRET
        
        with sqlite3.connect(self._path) as conn:
            row = conn.execute("SELECT value FROM auth_config WHERE key='jwt_secret';").fetchone()
            _CACHED_SECRET = row[0] if row else secrets.token_hex(32)
        return _CACHED_SECRET

    # ── user CRUD ────────────────────────────────────────────────────
    @staticmethod
    def _hash_pw(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def create_user(self, username: str, password: str, role: str = "user") -> bool:
        self.init_db()
        if role not in ("user", "admin"):
            raise ValueError("role must be 'user' or 'admin'")
        pw_hash = self._hash_pw(password)
        
        if self._use_sqlalchemy and self._SessionLocal:
            with self._SessionLocal() as session:
                if session.query(UiUser).filter(UiUser.username == username).first():
                    return False
                new_user = UiUser(username=username, pw_hash=pw_hash, role=role)
                session.add(new_user)
                session.commit()
                return True

        try:
            with sqlite3.connect(self._path) as conn:
                conn.execute(
                    "INSERT INTO ui_users(username, pw_hash, role) VALUES (?, ?, ?);",
                    (username, pw_hash, role),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        self.init_db()
        pw_hash = self._hash_pw(password)
        
        if self._use_sqlalchemy and self._SessionLocal:
            with self._SessionLocal() as session:
                user = session.query(UiUser).filter(UiUser.username == username, UiUser.pw_hash == pw_hash).first()
                if not user or not user.is_active:
                    return None
                return {"username": user.username, "role": user.role}

        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT username, role, is_active FROM ui_users WHERE username=? AND pw_hash=?;",
                (username, pw_hash),
            ).fetchone()
        if not row or not row["is_active"]:
            return None
        return {"username": row["username"], "role": row["role"]}

    def get_user(self, username: str) -> dict[str, Any] | None:
        self.init_db()
        if self._use_sqlalchemy and self._SessionLocal:
            with self._SessionLocal() as session:
                u = session.query(UiUser).filter(UiUser.username == username).first()
                if not u: return None
                return {"username": u.username, "role": u.role, "is_active": u.is_active}

        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT username, role, is_active FROM ui_users WHERE username=?;",
                (username,),
            ).fetchone()
        return dict(row) if row else None

    def list_users(self) -> list[dict[str, Any]]:
        self.init_db()
        if self._use_sqlalchemy and self._SessionLocal:
            with self._SessionLocal() as session:
                users = session.query(UiUser).order_by(UiUser.created_at).all()
                return [{"username": u.username, "role": u.role, "is_active": u.is_active, "created_at": str(u.created_at)} for u in users]

        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT username, role, is_active, created_at FROM ui_users ORDER BY created_at;"
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_user(self, username: str) -> bool:
        self.init_db()
        if self._use_sqlalchemy and self._SessionLocal:
            with self._SessionLocal() as session:
                u = session.query(UiUser).filter(UiUser.username == username).first()
                if u:
                    session.delete(u)
                    session.commit()
                    return True
                return False

        with sqlite3.connect(self._path) as conn:
            cur = conn.execute("DELETE FROM ui_users WHERE username=?;", (username,))
        return cur.rowcount > 0

    # ── agent assignments ────────────────────────────────────────────
    def assign_agent(self, username: str, hostname: str) -> bool:
        self.init_db()
        if self._use_sqlalchemy and self._SessionLocal:
            with self._SessionLocal() as session:
                existing = session.query(AgentAssignment).filter(AgentAssignment.username == username, AgentAssignment.hostname == hostname).first()
                if existing: return False
                new_asgn = AgentAssignment(username=username, hostname=hostname)
                session.add(new_asgn)
                session.commit()
                return True

        try:
            with sqlite3.connect(self._path) as conn:
                conn.execute(
                    "INSERT INTO agent_assignments(username, hostname) VALUES (?, ?);",
                    (username, hostname),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def unassign_agent(self, username: str, hostname: str) -> bool:
        self.init_db()
        if self._use_sqlalchemy and self._SessionLocal:
            with self._SessionLocal() as session:
                asgn = session.query(AgentAssignment).filter(AgentAssignment.username == username, AgentAssignment.hostname == hostname).first()
                if asgn:
                    session.delete(asgn)
                    session.commit()
                    return True
                return False

        with sqlite3.connect(self._path) as conn:
            cur = conn.execute(
                "DELETE FROM agent_assignments WHERE username=? AND hostname=?;",
                (username, hostname),
            )
        return cur.rowcount > 0

    def get_assigned_hostnames(self, username: str) -> list[str]:
        self.init_db()
        if self._use_sqlalchemy and self._SessionLocal:
            with self._SessionLocal() as session:
                asgns = session.query(AgentAssignment).filter(AgentAssignment.username == username).all()
                return [a.hostname for a in asgns]

        with sqlite3.connect(self._path) as conn:
            rows = conn.execute(
                "SELECT hostname FROM agent_assignments WHERE username=? ORDER BY hostname;",
                (username,),
            ).fetchall()
        return [r[0] for r in rows]

    def list_assignments(self) -> list[dict[str, Any]]:
        self.init_db()
        if self._use_sqlalchemy and self._SessionLocal:
            with self._SessionLocal() as session:
                asgns = session.query(AgentAssignment).order_by(AgentAssignment.username, AgentAssignment.hostname).all()
                return [{"username": a.username, "hostname": a.hostname, "assigned_at": str(a.assigned_at)} for a in asgns]

        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT username, hostname, assigned_at FROM agent_assignments ORDER BY username, hostname;"
            ).fetchall()
        return [dict(r) for r in rows]

