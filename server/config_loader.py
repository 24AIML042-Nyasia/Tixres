import os
import json
from pathlib import Path
from dotenv import load_dotenv

def load_config():
    # 1. Load .env file
    root_dir = Path(__file__).resolve().parent.parent
    load_dotenv(root_dir / ".env")
    
    # 2. Start with defaults or config.json
    config = {}
    config_path = root_dir / "config.json"
    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
        except:
            pass
            
    # 3. Override with Environment Variables (Priority)
    db_config = config.get("database", {})
    
    db_config["engine"] = os.getenv("DB_ENGINE", db_config.get("engine", "sqlite"))
    db_config["host"] = os.getenv("DB_HOST", db_config.get("host", "127.0.0.1"))
    db_config["port"] = int(os.getenv("DB_PORT", db_config.get("port", 5432)))
    db_config["name"] = os.getenv("DB_NAME", db_config.get("name", "tixres"))
    db_config["user"] = os.getenv("DB_USER", db_config.get("user", "postgres"))
    db_config["password"] = os.getenv("DB_PASSWORD", db_config.get("password", ""))
    db_config["sqlite_path"] = os.getenv("DB_SQLITE_PATH", db_config.get("sqlite_path", "server/data/agent_metrics.sqlite3"))
    
    config["database"] = db_config
    
    # Also handle Celery if needed
    celery_config = config.get("celery", {})
    celery_config["broker_url"] = os.getenv("CELERY_BROKER_URL", celery_config.get("broker_url", "redis://localhost:6379/0"))
    celery_config["result_backend"] = os.getenv("CELERY_RESULT_BACKEND", celery_config.get("result_backend", "redis://localhost:6379/1"))
    config["celery"] = celery_config
    
    return config

def get_db_url():
    cfg = load_config()["database"]
    if cfg["engine"] == "postgresql":
        import urllib.parse
        user = cfg["user"]
        # Ensure the password is URL-encoded for the connection string
        # If it was already encoded in .env (like %40), unquote it first to get the raw password,
        # then quote_mirror it to ensure it's correctly formatted for the URL.
        raw_password = urllib.parse.unquote(cfg["password"])
        password = urllib.parse.quote_plus(raw_password)
        
        host = cfg["host"]
        port = cfg["port"]
        name = cfg["name"]
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"
    else:
        return f"sqlite:///{cfg['sqlite_path']}"
