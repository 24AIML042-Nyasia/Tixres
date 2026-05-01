import requests
import sqlite3
from pathlib import Path
import json
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import CHATBOT_BASE_URL as CHATBOT_URL

DB_PATH = Path(__file__).resolve().parents[1] / "server" / "data" / "agent_metrics.sqlite3"


def ingest_guidance():
    if not DB_PATH.exists():
        print(f"DB not found at {DB_PATH}")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM guidance")
        rows = cursor.fetchall()
        conn.close()

        docs = []
        for row in rows:
            content = f"Guidance for {row['anomaly_type']}:\nTitle: {row['title']}\nDescription: {row['description']}\nSteps: {row['steps']}\nPriority: {row['priority']}"
            docs.append({
                "content": content,
                "metadata": {
                    "source": "guidance_db",
                    "type": "troubleshooting",
                    "anomaly_type": row['anomaly_type']
                }
            })

        if not docs:
            print("No guidance found in DB.")
            return

        print(f"Ingesting {len(docs)} guidance entries...")
        response = requests.post(f"{CHATBOT_URL}/ingest/bulk", json=docs)
        if response.status_code == 201:
            print("Successfully ingested guidance.")
        else:
            print(f"Failed to ingest: {response.text}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    ingest_guidance()
