"""
Demo script to simulate an agent collecting and storing metrics locally
This creates a local SQLite database with sample metrics that can be synced to the server
"""

import sqlite3
import random
import json
from datetime import datetime, timedelta
import time

DB_PATH = "agent_metrics.db"

def init_agent_database():
    """Initialize local agent database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Numeric metrics table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metric_numeric (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_name TEXT NOT NULL,
            value REAL NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            sent INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # JSON metrics table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metric_json (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_name TEXT NOT NULL,
            value TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            sent INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()
    print("Agent database initialized")


def insert_sample_metrics(count: int = 50):
    """Insert sample metrics into local database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    base_time = datetime.now() - timedelta(hours=2)
    
    print(f"\nInserting {count} sample metrics...")
    
    for i in range(count):
        # Generate timestamp (spread over last 2 hours)
        timestamp = (base_time + timedelta(minutes=i * 2.4)).strftime('%Y-%m-%d %H:%M:%S')
        
        # CPU Usage (numeric)
        cpu_usage = round(random.uniform(10, 95), 1)
        cursor.execute(
            "INSERT INTO metric_numeric (metric_name, value, timestamp) VALUES (?, ?, ?)",
            ('cpu_v1.0.0.usage_overall', cpu_usage, timestamp)
        )
        
        # Memory Usage (numeric)
        memory_usage = round(random.uniform(40, 85), 1)
        cursor.execute(
            "INSERT INTO metric_numeric (metric_name, value, timestamp) VALUES (?, ?, ?)",
            ('memory_v1.0.0.usage_percent', memory_usage, timestamp)
        )
        
        # Disk Usage (numeric)
        disk_usage = round(random.uniform(50, 70), 1)
        cursor.execute(
            "INSERT INTO metric_numeric (metric_name, value, timestamp) VALUES (?, ?, ?)",
            ('disk_v1.0.0.usage_percent', disk_usage, timestamp)
        )
        
        # Network bytes sent (numeric)
        network_sent = random.randint(1000000, 50000000)
        cursor.execute(
            "INSERT INTO metric_numeric (metric_name, value, timestamp) VALUES (?, ?, ?)",
            ('network_v1.0.0.bytes_sent', network_sent, timestamp)
        )
        
        # Top processes by memory (JSON)
        processes = [
            {
                "pid": random.randint(1000, 30000),
                "name": random.choice(["chrome.exe", "python.exe", "code.exe", "firefox.exe", "system"]),
                "memory_percent": round(random.uniform(1, 10), 2)
            }
            for _ in range(5)
        ]
        processes.sort(key=lambda x: x['memory_percent'], reverse=True)
        
        cursor.execute(
            "INSERT INTO metric_json (metric_name, value, timestamp) VALUES (?, ?, ?)",
            ('process_v1.0.0.top_memory', json.dumps(processes), timestamp)
        )
        
        # Top processes by CPU (JSON)
        cpu_processes = [
            {
                "pid": random.randint(1000, 30000),
                "name": random.choice(["chrome.exe", "python.exe", "code.exe", "firefox.exe", "system"]),
                "cpu_percent": round(random.uniform(0.5, 15), 2)
            }
            for _ in range(5)
        ]
        cpu_processes.sort(key=lambda x: x['cpu_percent'], reverse=True)
        
        cursor.execute(
            "INSERT INTO metric_json (metric_name, value, timestamp) VALUES (?, ?, ?)",
            ('process_v1.0.0.top_cpu', json.dumps(cpu_processes), timestamp)
        )
        
        # Disk I/O stats (JSON)
        disk_io = {
            "read_bytes": random.randint(100000, 5000000),
            "write_bytes": random.randint(100000, 5000000),
            "read_count": random.randint(100, 1000),
            "write_count": random.randint(100, 1000)
        }
        cursor.execute(
            "INSERT INTO metric_json (metric_name, value, timestamp) VALUES (?, ?, ?)",
            ('disk_v1.0.0.io_stats', json.dumps(disk_io), timestamp)
        )
    
    conn.commit()
    conn.close()
    
    print(f"✓ Inserted {count * 7} metrics successfully")


def show_stats():
    """Show statistics about stored metrics"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Count total metrics
    cursor.execute("SELECT COUNT(*) FROM metric_numeric")
    numeric_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM metric_json")
    json_count = cursor.fetchone()[0]
    
    # Count unsent metrics
    cursor.execute("SELECT COUNT(*) FROM metric_numeric WHERE sent = 0")
    numeric_unsent = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM metric_json WHERE sent = 0")
    json_unsent = cursor.fetchone()[0]
    
    # Get metric names
    cursor.execute("""
        SELECT metric_name, COUNT(*) as count 
        FROM metric_numeric 
        GROUP BY metric_name
    """)
    numeric_metrics = cursor.fetchall()
    
    cursor.execute("""
        SELECT metric_name, COUNT(*) as count 
        FROM metric_json 
        GROUP BY metric_name
    """)
    json_metrics = cursor.fetchall()
    
    conn.close()
    
    print("\n" + "="*60)
    print("METRICS DATABASE STATISTICS")
    print("="*60)
    print(f"\nTotal Metrics: {numeric_count + json_count}")
    print(f"  - Numeric: {numeric_count} ({numeric_unsent} unsent)")
    print(f"  - JSON: {json_count} ({json_unsent} unsent)")
    
    print(f"\nNumeric Metrics by Type:")
    for name, count in numeric_metrics:
        print(f"  - {name}: {count}")
    
    print(f"\nJSON Metrics by Type:")
    for name, count in json_metrics:
        print(f"  - {name}: {count}")
    
    print("="*60 + "\n")


def show_sample_metrics():
    """Show sample metrics from database"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("\n" + "="*60)
    print("SAMPLE METRICS")
    print("="*60)
    
    # Show 3 numeric metrics
    print("\nNumeric Metrics (sample):")
    cursor.execute("SELECT * FROM metric_numeric ORDER BY timestamp DESC LIMIT 3")
    for row in cursor.fetchall():
        print(f"  {dict(row)}")
    
    # Show 2 JSON metrics
    print("\nJSON Metrics (sample):")
    cursor.execute("SELECT * FROM metric_json ORDER BY timestamp DESC LIMIT 2")
    for row in cursor.fetchall():
        row_dict = dict(row)
        row_dict['value'] = json.loads(row_dict['value'])[:2]  # Show first 2 items
        print(f"  {row_dict}")
    
    conn.close()
    print("="*60 + "\n")


def continuous_collection(interval: int = 30):
    """Simulate continuous metric collection"""
    print(f"\n🔄 Starting continuous metric collection (every {interval} seconds)")
    print("Press Ctrl+C to stop\n")
    
    try:
        while True:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Collect metrics
            cpu_usage = round(random.uniform(10, 95), 1)
            memory_usage = round(random.uniform(40, 85), 1)
            
            cursor.execute(
                "INSERT INTO metric_numeric (metric_name, value, timestamp) VALUES (?, ?, ?)",
                ('cpu_v1.0.0.usage_overall', cpu_usage, timestamp)
            )
            
            cursor.execute(
                "INSERT INTO metric_numeric (metric_name, value, timestamp) VALUES (?, ?, ?)",
                ('memory_v1.0.0.usage_percent', memory_usage, timestamp)
            )
            
            # Top processes
            processes = [
                {
                    "pid": random.randint(1000, 30000),
                    "name": random.choice(["chrome.exe", "python.exe", "code.exe"]),
                    "memory_percent": round(random.uniform(1, 10), 2)
                }
                for _ in range(5)
            ]
            
            cursor.execute(
                "INSERT INTO metric_json (metric_name, value, timestamp) VALUES (?, ?, ?)",
                ('process_v1.0.0.top_memory', json.dumps(processes), timestamp)
            )
            
            conn.commit()
            conn.close()
            
            print(f"[{timestamp}] Collected: CPU={cpu_usage}%, Memory={memory_usage}%")
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n\n✓ Metric collection stopped")


if __name__ == "__main__":
    import sys
    
    print("\n" + "="*60)
    print("IT METRICS AGENT - DEMO SCRIPT")
    print("="*60)
    
    # Initialize database
    init_agent_database()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "generate":
            count = int(sys.argv[2]) if len(sys.argv) > 2 else 50
            insert_sample_metrics(count)
            show_stats()
            show_sample_metrics()
        
        elif command == "stats":
            show_stats()
        
        elif command == "sample":
            show_sample_metrics()
        
        elif command == "collect":
            interval = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            continuous_collection(interval)
        
        elif command == "clear":
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM metric_numeric")
            conn.execute("DELETE FROM metric_json")
            conn.commit()
            conn.close()
            print("✓ All metrics cleared")
        
        else:
            print(f"Unknown command: {command}")
    
    else:
        print("\nUsage:")
        print("  python demo_agent.py generate [count]  - Generate sample metrics (default: 50)")
        print("  python demo_agent.py stats             - Show database statistics")
        print("  python demo_agent.py sample            - Show sample metrics")
        print("  python demo_agent.py collect [seconds] - Continuous collection (default: 30s)")
        print("  python demo_agent.py clear             - Clear all metrics")
        print("\nExample:")
        print("  python demo_agent.py generate 100")
        print("  python demo_agent.py collect 10")
