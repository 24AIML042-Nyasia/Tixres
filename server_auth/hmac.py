import secrets
import hmac
import hashlib
from fastapi import Header, HTTPException 
from sqlalchemy.orm import Session

from server_db.connection import SessionLocal
from server_db.models import AgentCredentials
from server_utils.logger import get_logger

logger = get_logger() 

def generate_credentials():
    api_key = secrets.token_urlsafe(32)
    secret_key = secrets.token_urlsafe(64)
    return api_key, secret_key

def create_signature(api_key: str, secret_key: str, message: str) -> str:
    signature = hmac.new(
        secret_key.encode('utf-8'),
        f"{api_key}:{message}".encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature

def verify_signature(api_key: str, message: str, signature: str) -> bool:
    db = SessionLocal()
    try:
        cred = db.query(AgentCredentials).filter(
            AgentCredentials.api_key == api_key
        ).first()
        
        if not cred:
            logger.warning(f"API key not found: {api_key}")
            return False
        
        if not cred.is_active:
            logger.warning(f"Inactive agent attempted authentication: {api_key}")
            return False
        
        secret_key = cred.secret_key
        expected_signature = create_signature(api_key, secret_key, message)
        
        return hmac.compare_digest(signature, expected_signature)
    finally:
        db.close()

async def verify_auth(
    x_api_key: str = Header(...),
    x_signature: str = Header(...),
    x_message: str = Header(...)
):
    if not verify_signature(x_api_key, x_message, x_signature):
        raise HTTPException(status_code=401, detail="Invalid authentication")
    
    db = SessionLocal()
    try:
        cred = db.query(AgentCredentials).filter(
            AgentCredentials.api_key == x_api_key
        ).first()
        
        if not cred:
            raise HTTPException(status_code=401, detail="Agent not found")
        
        return cred.agent_id
    finally:
        db.close()