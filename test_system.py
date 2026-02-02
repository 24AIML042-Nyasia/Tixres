"""
Integration test script for IT Metrics Storage System
Tests server, agent, and data flow
"""

import requests
import time
import json
import subprocess
import sys
import os
from datetime import datetime

# Test configuration
SERVER_URL = "http://localhost:8000"
TEST_TIMEOUT = 5

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def print_test(message):
    print(f"{Colors.BLUE}[TEST]{Colors.END} {message}")

def print_success(message):
    print(f"{Colors.GREEN}✓{Colors.END} {message}")

def print_error(message):
    print(f"{Colors.RED}✗{Colors.END} {message}")

def print_warning(message):
    print(f"{Colors.YELLOW}⚠{Colors.END} {message}")

def test_server_health():
    """Test if server is running and healthy"""
    print_test("Testing server health...")
    try:
        response = requests.get(f"{SERVER_URL}/health", timeout=TEST_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            print_success(f"Server is healthy: {data}")
            return True
        else:
            print_error(f"Server returned status {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print_error(f"Cannot connect to server: {e}")
        print_warning("Make sure the server is running: python server.py")
        return False

def test_agent_registration():
    """Test agent registration"""
    print_test("Testing agent registration...")
    try:
        payload = {
            "agent_version": "1.0.0-test",
            "hostname": "test-host",
            "os": "TestOS",
            "fingerprint": "test-fingerprint-123",
            "template": {"test": "data"}
        }
        
        response = requests.post(
            f"{SERVER_URL}/api/agent/register",
            json=payload,
            timeout=TEST_TIMEOUT
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success("Agent registered successfully")
            print(f"  Agent ID: {data['agent_id']}")
            print(f"  API Key: {data['api_key'][:20]}...")
            return data
        else:
            print_error(f"Registration failed: {response.status_code}")
            print(f"  Response: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print_error(f"Registration request failed: {e}")
        return None

def test_agent_login(credentials):
    """Test agent login with HMAC authentication"""
    print_test("Testing agent login...")
    try:
        import hmac
        import hashlib
        
        api_key = credentials['api_key']
        secret_key = credentials['secret_key']
        message = str(int(time.time()))
        
        # Create signature
        signature = hmac.new(
            secret_key.encode('utf-8'),
            f"{api_key}:{message}".encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        headers = {
            'X-Api-Key': api_key,
            'X-Signature': signature,
            'X-Message': message,
            'Content-Type': 'application/json'
        }
        
        payload = {
            "agent_id": credentials['agent_id']
        }
        
        response = requests.post(
            f"{SERVER_URL}/api/agent/login",
            json=payload,
            headers=headers,
            timeout=TEST_TIMEOUT
        )
        
        if response.status_code == 200:
            print_success("Agent login successful")
            data = response.json()
            print(f"  Message: {data['message']}")
            return True
        else:
            print_error(f"Login failed: {response.status_code}")
            print(f"  Response: {response.text}")
            return False
            
    except Exception as e:
        print_error(f"Login test failed: {e}")
        return False

def test_heartbeat(credentials):
    """Test agent heartbeat/ping"""
    print_test("Testing agent heartbeat...")
    try:
        import hmac
        import hashlib
        
        api_key = credentials['api_key']
        secret_key = credentials['secret_key']
        message = str(int(time.time()))
        
        signature = hmac.new(
            secret_key.encode('utf-8'),
            f"{api_key}:{message}".encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        headers = {
            'X-Api-Key': api_key,
            'X-Signature': signature,
            'X-Message': message,
            'Content-Type': 'application/json'
        }
        
        payload = {
            "agent_id": credentials['agent_id']
        }
        
        response = requests.post(
            f"{SERVER_URL}/api/agent/ping",
            json=payload,
            headers=headers,
            timeout=TEST_TIMEOUT
        )
        
        if response.status_code == 200:
            print_success("Heartbeat sent successfully")
            return True
        else:
            print_error(f"Heartbeat failed: {response.status_code}")
            return False
            
    except Exception as e:
        print_error(f"Heartbeat test failed: {e}")
        return False

def test_metrics_submission(credentials):
    """Test metrics submission"""
    print_test("Testing metrics submission...")
    try:
        import hmac
        import hashlib
        
        api_key = credentials['api_key']
        secret_key = credentials['secret_key']
        message = str(int(time.time()))
        
        signature = hmac.new(
            secret_key.encode('utf-8'),
            f"{api_key}:{message}".encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        headers = {
            'X-Api-Key': api_key,
            'X-Signature': signature,
            'X-Message': message,
            'Content-Type': 'application/json'
        }
        
        # Create test metrics
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        metrics = [
            {
                "metric_name": "test_v1.0.0.cpu_usage",
                "value": 45.5,
                "timestamp": timestamp
            },
            {
                "metric_name": "test_v1.0.0.memory_usage",
                "value": 67.2,
                "timestamp": timestamp
            },
            {
                "metric_name": "test_v1.0.0.process_list",
                "value": json.dumps([
                    {"pid": 1234, "name": "test.exe", "cpu": 12.5}
                ]),
                "timestamp": timestamp
            }
        ]
        
        payload = {
            "agent_id": credentials['agent_id'],
            "metrics": metrics
        }
        
        response = requests.post(
            f"{SERVER_URL}/api/metrics/submit",
            json=payload,
            headers=headers,
            timeout=TEST_TIMEOUT
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success(f"Metrics submitted successfully")
            print(f"  Total: {data['count']}, Numeric: {data['numeric']}, JSON: {data['json']}")
            return True
        else:
            print_error(f"Metrics submission failed: {response.status_code}")
            print(f"  Response: {response.text}")
            return False
            
    except Exception as e:
        print_error(f"Metrics submission test failed: {e}")
        return False

def test_ui_agents():
    """Test UI endpoint for listing agents"""
    print_test("Testing UI agents endpoint...")
    try:
        response = requests.get(
            f"{SERVER_URL}/api/ui/agents",
            timeout=TEST_TIMEOUT
        )
        
        if response.status_code == 200:
            agents = response.json()
            print_success(f"Retrieved {len(agents)} agents")
            if agents:
                print(f"  Sample agent: {agents[0]['hostname']}")
            return True
        else:
            print_error(f"Failed to retrieve agents: {response.status_code}")
            return False
            
    except Exception as e:
        print_error(f"UI agents test failed: {e}")
        return False

def test_ui_metrics():
    """Test UI endpoint for retrieving metrics"""
    print_test("Testing UI metrics endpoint...")
    try:
        # Test numeric metrics
        response = requests.get(
            f"{SERVER_URL}/api/ui/metrics/numeric?limit=10",
            timeout=TEST_TIMEOUT
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success(f"Retrieved {data['count']} numeric metrics")
        else:
            print_error(f"Failed to retrieve numeric metrics: {response.status_code}")
            return False
        
        # Test JSON metrics
        response = requests.get(
            f"{SERVER_URL}/api/ui/metrics/json?limit=10",
            timeout=TEST_TIMEOUT
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success(f"Retrieved {data['count']} JSON metrics")
            return True
        else:
            print_error(f"Failed to retrieve JSON metrics: {response.status_code}")
            return False
            
    except Exception as e:
        print_error(f"UI metrics test failed: {e}")
        return False

def test_ui_summary():
    """Test UI summary endpoint"""
    print_test("Testing UI summary endpoint...")
    try:
        response = requests.get(
            f"{SERVER_URL}/api/ui/metrics/summary",
            timeout=TEST_TIMEOUT
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success("Retrieved metrics summary")
            print(f"  Total Agents: {data['agents']['total']} (Active: {data['agents']['active']})")
            print(f"  Total Metrics: {data['metrics']['total']} (Last hour: {data['metrics']['last_hour']})")
            return True
        else:
            print_error(f"Failed to retrieve summary: {response.status_code}")
            return False
            
    except Exception as e:
        print_error(f"UI summary test failed: {e}")
        return False

def run_all_tests():
    """Run all integration tests"""
    print("\n" + "="*70)
    print("IT METRICS STORAGE SYSTEM - INTEGRATION TESTS")
    print("="*70 + "\n")
    
    results = []
    
    # Test 1: Server Health
    results.append(("Server Health", test_server_health()))
    
    if not results[-1][1]:
        print_error("\n⚠️  Server is not running. Please start the server first:")
        print("   python server.py")
        return
    
    print()
    
    # Test 2: Agent Registration
    credentials = test_agent_registration()
    results.append(("Agent Registration", credentials is not None))
    
    if not credentials:
        print_error("\n⚠️  Cannot continue tests without agent credentials")
        return
    
    print()
    
    # Test 3: Agent Login
    results.append(("Agent Login (HMAC Auth)", test_agent_login(credentials)))
    print()
    
    # Test 4: Heartbeat
    results.append(("Agent Heartbeat", test_heartbeat(credentials)))
    print()
    
    # Test 5: Metrics Submission
    results.append(("Metrics Submission", test_metrics_submission(credentials)))
    print()
    
    # Test 6: UI Agents
    results.append(("UI Agents List", test_ui_agents()))
    print()
    
    # Test 7: UI Metrics
    results.append(("UI Metrics Retrieval", test_ui_metrics()))
    print()
    
    # Test 8: UI Summary
    results.append(("UI Summary", test_ui_summary()))
    print()
    
    # Print summary
    print("="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = f"{Colors.GREEN}PASS{Colors.END}" if result else f"{Colors.RED}FAIL{Colors.END}"
        print(f"{status}  {test_name}")
    
    print("="*70)
    
    if passed == total:
        print(f"{Colors.GREEN}✓ All tests passed! ({passed}/{total}){Colors.END}")
        print("\nSystem is working correctly. You can now:")
        print("  1. Generate test data: python demo_agent.py generate 100")
        print("  2. Run the agent: python agent_client.py --server http://localhost:8000 --action run")
        print("  3. View the dashboard: Open dashboard.html in a browser")
    else:
        print(f"{Colors.RED}✗ Some tests failed ({passed}/{total} passed){Colors.END}")
        print("\nPlease check the errors above and ensure:")
        print("  1. Server is running")
        print("  2. All dependencies are installed")
        print("  3. No port conflicts")
    
    print()

if __name__ == "__main__":
    try:
        run_all_tests()
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
        sys.exit(1)
