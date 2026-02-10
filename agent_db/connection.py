import sqlite3
from settings import AGENT_DB_PATH

def get_connection():
    conn = sqlite3.connect(AGENT_DB_PATH)
    conn.row_factory = sqlite3.Row 
    return conn


