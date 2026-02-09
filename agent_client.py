"""
IT Metrics Agent Client
Handles registration, authentication, and metrics submission to the server
"""

import requests
import hmac
import hashlib
import json
import sqlite3
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import time
import sys
from agent_core.execute import gather
import asyncio
from settings import SERVER_URL
from agent_core.agent import startup

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Agent database path
AGENT_DB_PATH = "app.db"

# ============================================================================
# CONFIGURATION
# ============================================================================

class AgentConfig:
    """Agent configuration"""
    def __init__(self, server_url: str):
        self.server_url = server_url.rstrip('/')
        self.agent_id: Optional[str] = None
        self.api_key: Optional[str] = None
        self.secret_key: Optional[str] = None
        self.config_file = "agent_config.json"
        
    def load(self):
        """Load configuration from file"""
        try:
            with open(self.config_file, 'r') as f:
                data = json.load(f)
                self.agent_id = data.get('agent_id')
                self.api_key = data.get('api_key')
                self.secret_key = data.get('secret_key')
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
                'secret_key': self.secret_key
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


# ============================================================================
# HMAC AUTHENTICATION
# ============================================================================

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


# ============================================================================
# AGENT CLIENT
# ============================================================================

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
    
    def register(self, template: Optional[Dict[str, Any]] = None) -> bool:
        """Register agent with server"""
        try:
            url = f"{self.config.server_url}/api/agent/register"
            
            payload = {
                "agent_version": self.agent_version,
                "hostname": self.hostname,
                "os": self.os_name,
                "fingerprint": self.fingerprint,
                "template": template
            }
            
            logger.info(f"Registering agent at {url}")
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            self.config.agent_id = data['agent_id']
            self.config.api_key = data['api_key']
            self.config.secret_key = data['secret_key']
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


# ============================================================================
# LOCAL DATABASE FUNCTIONS (matching agent-side code)
# ============================================================================

def get_connection():
    """Get connection to local metrics database"""
    conn = sqlite3.connect(AGENT_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_unsent(table: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Fetch unsent metrics from local database"""
    conn = get_connection()
    cursor = conn.execute(
        f"""
        SELECT id, metric_name, value, timestamp
        FROM {table}
        WHERE sent = 0
        ORDER BY timestamp
        LIMIT ?
        """,
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    
    # Convert to list of dicts
    return [dict(row) for row in rows]


def mark_sent(table: str, ids: List[int]):
    """Mark metrics as sent in local database"""
    if not ids:
        return

    conn = get_connection()
    placeholders = ",".join("?" for _ in ids)
    conn.execute(
        f"UPDATE {table} SET sent = 1 WHERE id IN ({placeholders})",
        ids
    )
    conn.commit()
    conn.close()


# ============================================================================
# MAIN AGENT LOOP
# ============================================================================

def sync_metrics(agent: MetricsAgent, batch_size: int = 100):
    """Sync unsent metrics to server"""
    try:
        # Fetch unsent numeric metrics
        numeric_metrics = fetch_unsent('metric_numeric', batch_size)
        
        # Fetch unsent JSON metrics
        json_metrics = fetch_unsent('metric_json', batch_size)
        
        all_metrics = numeric_metrics + json_metrics
        
        if not all_metrics:
            logger.debug("No unsent metrics to sync")
            return True
        
        # Submit to server
        if agent.submit_metrics(all_metrics):
            # Mark as sent
            if numeric_metrics:
                numeric_ids = [m['id'] for m in numeric_metrics]
                mark_sent('metric_numeric', numeric_ids)
            
            if json_metrics:
                json_ids = [m['id'] for m in json_metrics]
                mark_sent('metric_json', json_ids)
            
            logger.info(f"Synced {len(all_metrics)} metrics successfully")
            return True
        else:
            logger.error("Failed to submit metrics to server")
            return False
            
    except Exception as e:
        logger.error(f"Error syncing metrics: {e}")
        return False


async def run_agent(server_url: str, sync_interval: int = 60, ping_interval: int = 300):
    """Run the agent main loop"""
    import platform
    
    # Initialize agent
    agent = MetricsAgent(
        server_url=server_url,
        agent_version="1.0.0",
        hostname=platform.node(),
        os_name=platform.system()
    )
    
    # Load existing configuration or register
    if not agent.config.load():
        logger.info("Agent not registered, registering now...")
        if not agent.register():
            logger.error("Failed to register agent, exiting")
            sys.exit(1)
    
    # Login
    if not agent.login():
        logger.error("Failed to login, exiting")
        sys.exit(1)
    
    # Main loop
    logger.info("Agent started, entering main loop")
    last_sync = 0
    last_ping = 0
    
    try:
        while True:
            current_time = time.time()

            # Sync metrics
            if current_time - last_sync >= sync_interval:
                logger.info("Syncing metrics...")
                sync_metrics(agent, batch_size=100)
                last_sync = current_time
            
            # Send ping
            if current_time - last_ping >= ping_interval:
                logger.info("Sending heartbeat...")
                agent.ping()
                last_ping = current_time
            
            # Sleep for a bit
            await asyncio.sleep(10)
            
    except KeyboardInterrupt:
        logger.info("Agent stopped by user")
    except Exception as e:
        logger.error(f"Agent error: {e}")
        raise


# ============================================================================
# STANDALONE FUNCTIONS
# ============================================================================

def standalone_register(server_url: str) -> bool:
    """Standalone registration function"""
    import platform
    
    agent = MetricsAgent(
        server_url=server_url,
        agent_version="1.0.0",
        hostname=platform.node(),
        os_name=platform.system()
    )
    
    return agent.register()


def standalone_login(server_url: str) -> bool:
    """Standalone login function"""
    import platform
    
    agent = MetricsAgent(
        server_url=server_url,
        agent_version="1.0.0",
        hostname=platform.node(),
        os_name=platform.system()
    )
    
    agent.config.load()
    return agent.login()


def standalone_submit(server_url: str, metrics: List[Dict[str, Any]]) -> bool:
    """Standalone metrics submission function"""
    import platform
    
    agent = MetricsAgent(
        server_url=server_url,
        agent_version="1.0.0",
        hostname=platform.node(),
        os_name=platform.system()
    )
    
    agent.config.load()
    return agent.submit_metrics(metrics)

async def run_wrap(server, sync , ping):
    await asyncio.gather(run_agent(server, sync, ping),gather())


# ============================================================================
# COMMAND LINE INTERFACE
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="IT Metrics Agent Client")
    parser.add_argument("--server", required=True, help="Server URL (e.g., http://localhost:8000)")
    parser.add_argument("--action", choices=['register', 'login', 'run', 'sync'], 
                       default='run', help="Action to perform")
    parser.add_argument("--sync-interval", type=int, default=60, 
                       help="Metrics sync interval in seconds (default: 60)")
    parser.add_argument("--ping-interval", type=int, default=300,
                       help="Heartbeat ping interval in seconds (default: 300)")
    
    args = parser.parse_args()
    
    if args.action == 'register':
        if standalone_register(args.server):
            print("Registration successful!")
            sys.exit(0)
        else:
            print("Registration failed!")
            sys.exit(1)
    
    elif args.action == 'login':
        if standalone_login(args.server):
            print("Login successful!")
            sys.exit(0)
        else:
            print("Login failed!")
            sys.exit(1)
    
    elif args.action == 'sync':
        import platform
        agent = MetricsAgent(
            server_url=args.server,
            agent_version="1.0.0",
            hostname=platform.node(),
            os_name=platform.system()
        )
        agent.config.load()
        
        if sync_metrics(agent):
            print("Sync successful!")
            sys.exit(0)
        else:
            print("Sync failed!")
            sys.exit(1)
    
    elif args.action == 'run':
        startup()
        asyncio.run(run_wrap(args.server, args.sync_interval, args.ping_interval))
