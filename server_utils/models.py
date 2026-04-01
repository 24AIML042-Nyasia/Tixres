from typing import Dict, Any, Optional, List
from pydantic import BaseModel

class AgentRegisterRequest(BaseModel):
    agent_version: str
    hostname: str
    os: str
    fingerprint: str
    template: Optional[Dict[str, Any]] = None
    purpose: Optional[str] = "general"

class AgentRegisterResponse(BaseModel):
    agent_id: str
    api_key: str
    secret_key: str
    template: str
    purpose: str
    message: str

class AgentLoginRequest(BaseModel):
    agent_id: str

class AgentLoginResponse(BaseModel):
    message: str
    agent_info: Dict[str, Any]

class PingRequest(BaseModel):
    agent_id: str

class MetricData(BaseModel):
    metric_name: str
    value: Any
    timestamp: str

class MetricBatchRequest(BaseModel):
    agent_id: str
    metrics: List[MetricData]

class AgentInfo(BaseModel):
    agent_id: str
    agent_version: str
    hostname: str
    os: str
    created_at: str
    updated_at: str
    heartbeat: Optional[str]
    fingerprint: str
    template: Optional[str]
    purpose: Optional[str]
