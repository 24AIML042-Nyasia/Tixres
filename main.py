"""
IT Metrics Agent Client
Handles registration, authentication, and metrics submission to the server
"""

import time
import sys
import asyncio

from agent_core.execute import gather
from settings import SERVER_URL
from agent_core.agent import startup
from agent_db.models import fetch_unsent,mark_sent
from agent_auth.agent import MetricsAgent
from agent_auth.stand_alone import standalone_login, standalone_register
from logger import get_logger

logger = get_logger('Main')

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


async def run_agent(agent : MetricsAgent, sync_interval: int = 60, ping_interval: int = 300):
    """Run the agent main loop"""
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

async def run_wrap(server_url, sync , ping):
    import platform
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
    
    # if not agent.config.load():
    #     logger.error("Failed to load template")

        
    await asyncio.gather(run_agent(agent, sync, ping),gather(agent.config.template))


# ============================================================================
# COMMAND LINE INTERFACE
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="IT Metrics Agent Client")
    parser.add_argument("--server", required=True, help="Server URL (e.g., http://localhost:8000)")
    parser.add_argument("--purpose",  help="Purpose of the PC agent is running on",
                        default=None)
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
