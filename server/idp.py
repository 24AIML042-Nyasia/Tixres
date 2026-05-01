from __future__ import annotations

import logging
from typing import Any
from pathlib import Path

from auth import AuthStore, JWTProvider

log = logging.getLogger(__name__)

class TixresIdP:
    """The Tixres Identity Provider (SSO Service).
    In a real-world scenario, this would be a separate microservice.
    """
    def __init__(self, db_path: Path):
        self._store = AuthStore(db_path)
        self._store.init_db()
        self._secret = self._store.get_secret()
        self._jwt = JWTProvider(self._secret)

    def login(self, username: str, password: str) -> dict[str, Any] | None:
        """Authenticate user and return a token + profile."""
        user = self._store.authenticate(username, password)
        if not user:
            return None
        
        token = self._jwt.issue_token(user["username"], user["role"])
        return {
            "token": token,
            "username": user["username"],
            "role": user["role"]
        }

    def verify(self, token: str) -> dict[str, Any] | None:
        """Verify a token issued by this IdP."""
        return self._jwt.verify_token(token)

    def get_user_assignments(self, username: str) -> list[str]:
        """Get hostnames assigned to this user."""
        return self._store.get_assigned_hostnames(username)

    def is_admin(self, username: str) -> bool:
        """Check if a user is an admin."""
        user = self._store.get_user(username)
        return user and user["role"] == "admin"
