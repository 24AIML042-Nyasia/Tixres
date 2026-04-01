"""
agent_auth.hmac
----------------
Lightweight helper to generate HMAC auth headers for upstream API calls.

Protocol
========
Signature input: f"{api_key}:{message}"
Hash: HMAC-SHA256 using secret_key (hex digest)
Headers emitted:
  X-Api-Key    -> api_key
  X-Signature  -> hex digest
  X-Message    -> message (timestamp by default)
  Content-Type -> application/json
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Dict, Optional


def create_signature(api_key: str, secret_key: str, message: str) -> str:
    """Create HMAC signature for authentication."""
    return hmac.new(
        secret_key.encode("utf-8"),
        f"{api_key}:{message}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def create_auth_headers(api_key: str, secret_key: str, *, message: Optional[str] = None) -> Dict[str, str]:
    """
    Create authentication headers with HMAC signature.

    Args:
        api_key: public API key issued by upstream.
        secret_key: shared secret used to sign requests.
        message: optional nonce/message; defaults to current unix timestamp.
    """
    msg = message or str(int(time.time()))
    signature = create_signature(api_key, secret_key, msg)
    return {
        "X-Api-Key": api_key,
        "X-Signature": signature,
        "X-Message": msg,
        "Content-Type": "application/json",
    }

