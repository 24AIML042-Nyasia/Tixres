import json
from typing import Optional, Dict, Any, List
import requests
import hashlib

from agent_auth.hmac import create_auth_headers
from logger import get_logger

from modules.delete_temp import clean_temp
logger = get_logger()

class AgentConfig:
    """Agent configuration"""
    def __init__(self, server_url: str):
        self.server_url = server_url.rstrip('/')
        self.agent_id: Optional[str] = None
        self.api_key: Optional[str] = None
        self.secret_key: Optional[str] = None
        self.template: Optional[str] = None
        self.config_file = "agent_config.json"
        
    def load(self) -> bool:
        try:
            with open(self.config_file, 'r') as f:
                data = json.load(f)

            self.agent_id = data.get('agent_id')
            self.api_key = data.get('api_key')
            self.secret_key = data.get('secret_key')

            template = data.get("template")
            if isinstance(template, str):
                self.template = json.loads(template)
            else:
                self.template = template

            logger.info("Configuration loaded successfully")
            return True

        except FileNotFoundError:
            logger.info("No configuration file found")
            return False
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            return False
    
    def save(self):
        """Save configuration to file"""
        try:
            data = {
                'agent_id': self.agent_id,
                'api_key': self.api_key,
                'secret_key': self.secret_key,
                'template' : self.template
            }
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("Configuration saved successfully")
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            raise
    
    def is_registered(self) -> bool:
        """Check if agent is registered"""
        return all([self.agent_id, self.api_key, self.secret_key])

class MetricsAgent:
    """Agent client for metrics collection and submission"""
    
    def __init__(self, server_url: str, agent_version: str, hostname: str, os_name: str):
        self.config = AgentConfig(server_url)
        self.agent_version = agent_version
        self.hostname = hostname
        self.os_name = os_name
        self.fingerprint = self._generate_fingerprint()

    def _generate_fingerprint(self) -> str:
        """Generate unique fingerprint for this agent"""
        import platform
        import uuid
        
        # Combine system identifiers
        mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff)
                       for elements in range(0, 2*6, 2)][::-1])
        
        fingerprint_data = f"{self.hostname}:{mac}:{platform.machine()}"
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]
        return fingerprint

    def register(self) -> bool:
        """Register agent with server"""
        try:
            url = f"{self.config.server_url}/api/agent/register"
            
            payload = {
                "agent_version": self.agent_version,
                "hostname": self.hostname,
                "os": self.os_name,
                "fingerprint": self.fingerprint
            }
            
            logger.info(f"Registering agent at {url}")
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            self.config.agent_id = data['agent_id']
            self.config.api_key = data['api_key']
            self.config.secret_key = data['secret_key']
            template = data['template']

            if isinstance(template, str):
                template = json.loads(template)

            self.config.template = template
            self.config.save()
            
            logger.info(f"Agent registered successfully: {self.config.agent_id}")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Registration failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during registration: {e}")
            return False
    
    def login(self) -> bool:
        """Login to server and verify credentials"""
        try:
            if not self.config.is_registered():
                logger.error("Agent not registered. Please register first.")
                return False
            
            url = f"{self.config.server_url}/api/agent/login"
            headers = create_auth_headers(self.config.api_key, self.config.secret_key)
            
            payload = {
                "agent_id": self.config.agent_id
            }
            
            logger.info(f"Logging in agent: {self.config.agent_id}")
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            template = data["agent_info"]["template"]
            if isinstance(template, str):
                template = json.loads(template)

            self.config.template = template
            self.config.save()

            logger.info(f"Login successful: {data['message']}")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Login failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during login: {e}")
            return False
    
    def ping(self) -> bool:
        """Send heartbeat ping to server"""
        try:
            if not self.config.is_registered():
                logger.error("Agent not registered")
                return False
            
            url = f"{self.config.server_url}/api/agent/ping"
            headers = create_auth_headers(self.config.api_key, self.config.secret_key)
            
            payload = {
                "agent_id": self.config.agent_id
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            if data['action']:
                clean_temp()
            
            logger.debug("Heartbeat sent successfully")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Ping failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during ping: {e}")
            return False
    
    def submit_metrics(self, metrics: List[Dict[str, Any]]) -> bool:
        """Submit batch of metrics to server"""
        try:
            if not self.config.is_registered():
                logger.error("Agent not registered")
                return False
            
            if not metrics:
                logger.warning("No metrics to submit")
                return True
            
            url = f"{self.config.server_url}/api/metrics/submit"
            headers = create_auth_headers(self.config.api_key, self.config.secret_key)
            
            # Convert metrics to expected format
            formatted_metrics = []
            for metric in metrics:
                formatted_metrics.append({
                    "metric_name": metric['metric_name'],
                    "value": metric['value'],
                    "timestamp": metric['timestamp']
                })
            
            payload = {
                "agent_id": self.config.agent_id,
                "metrics": formatted_metrics
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"Metrics submitted: {data['count']} total ({data['numeric']} numeric, {data['json']} JSON)")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Metrics submission failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during metrics submission: {e}")
            return False

