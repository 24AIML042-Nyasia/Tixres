from __future__ import annotations

import hashlib
import hmac
import time


def create_signature(api_key: str, secret_key: str, message: str) -> str:
    return hmac.new(
        secret_key.encode("utf-8"),
        f"{api_key}:{message}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_signature(api_key: str, secret_key: str, message: str, signature: str) -> bool:
    expected = create_signature(api_key, secret_key, message)
    return hmac.compare_digest(expected, signature)


def verify_timestamp(message: str, *, max_skew_seconds: int = 60) -> bool:
    try:
        ts = int(message)
    except Exception:
        return False

    now = int(time.time())
    return abs(now - ts) <= max_skew_seconds

