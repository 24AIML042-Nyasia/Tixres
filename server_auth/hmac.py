import secrets
import hmac
import hashlib
from fastapi import Header, HTTPException 

from server_db.conncetion import get_db
from server_utils.logger import get_logger

logger = get_logger() 

def generate_credentials():
    """Generate API key and secret key for agent"""
    api_key = secrets.token_urlsafe(32)
    secret_key = secrets.token_urlsafe(64)
    return api_key, secret_key

def create_signature(api_key: str, secret_key: str, message: str) -> str:
    """Create HMAC signature"""
    signature = hmac.new(
        secret_key.encode('utf-8'),
        f"{api_key}:{message}".encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature

def verify_signature(api_key: str, message: str, signature: str) -> bool:
    """Verify HMAC signature"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT secret_key, is_active FROM agent_credentials WHERE api_key = ?",
        (api_key,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        logger.warning(f"API key not found: {api_key}")
        return False
    
    if not row['is_active']:
        logger.warning(f"Inactive agent attempted authentication: {api_key}")
        return False
    
    secret_key = row['secret_key']
    expected_signature = create_signature(api_key, secret_key, message)
    
    return hmac.compare_digest(signature, expected_signature)

async def verify_auth(
    x_api_key: str = Header(...),
    x_signature: str = Header(...),
    x_message: str = Header(...)
):
    """Dependency for verifying HMAC authentication"""
    if not verify_signature(x_api_key, x_message, x_signature):
        raise HTTPException(status_code=401, detail="Invalid authentication")
    
    # Get agent_id from api_key
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT agent_id FROM agent_credentials WHERE api_key = ?", (x_api_key,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=401, detail="Agent not found")
    
    return row['agent_id']