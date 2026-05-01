import hmac
import hashlib
import time 
from typing import Dict

def create_signature(api_key: str, secret_key: str, message: str) -> str:
    """Create HMAC signature for authentication"""
    signature = hmac.new(
        secret_key.encode('utf-8'),
        f"{api_key}:{message}".encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature


def create_auth_headers(api_key: str, secret_key: str) -> Dict[str, str]:
    """Create authentication headers with HMAC signature"""
    message = str(int(time.time()))  # Timestamp as message
    signature = create_signature(api_key, secret_key, message)
    
    return {
        'X-Api-Key': api_key,
        'X-Signature': signature,
        'X-Message': message,
        'Content-Type': 'application/json'
    }