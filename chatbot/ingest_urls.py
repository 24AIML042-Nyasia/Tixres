import requests
import trafilatura
from typing import List
import argparse
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import CHATBOT_BASE_URL as CHATBOT_URL

def ingest_urls(urls: List[str]):
    docs = []
    for url in urls:
        print(f"Fetching {url}...")
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            content = trafilatura.extract(downloaded)
            if content:
                docs.append({
                    "content": content,
                    "metadata": {
                        "source": url,
                        "type": "website"
                    }
                })
            else:
                print(f"Failed to extract content from {url}")
        else:
            print(f"Failed to download {url}")

    if not docs:
        print("No content extracted from URLs.")
        return

    print(f"Ingesting {len(docs)} documents...")
    response = requests.post(f"{CHATBOT_URL}/ingest/bulk", json=docs)
    if response.status_code == 201:
        print("Successfully ingested website data.")
    else:
        print(f"Failed to ingest: {response.text}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest website data into Tixres Chatbot")
    parser.add_argument("urls", nargs="+", help="List of URLs to ingest")
    args = parser.parse_args()
    
    ingest_urls(args.urls)
