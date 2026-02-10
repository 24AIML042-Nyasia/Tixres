from typing import Dict, List, Any
from agent_auth.agent import MetricsAgent

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
