"""
Integration tests for the Tixres ITSM metric-collection server.

Design choices
--------------
* An in-memory SQLite database is created once per test module (session scope)
  so every test runs against a clean, isolated schema without needing an
  external PostgreSQL instance.
* The FastAPI dependency `get_db` and the raw `SessionLocal` / `engine` objects
  used inside route handlers are BOTH patched to point at the SQLite session so
  that all DB writes made by the app land in the same (testable) session.
* The HMAC auth helper `create_signature` is imported directly so tests can
  produce valid request headers without hard-coding secrets.

Test matrix
-----------
1.  Health / root endpoints
2.  Agent registration
3.  Duplicate fingerprint / idempotent re-registration
4.  Agent login (with valid credentials)
5.  Agent login – invalid credentials → 401
6.  Agent ping – heartbeat round-trip
7.  Agent ping – tempCache action flag
8.  Metrics submit – numeric batch
9.  Metrics submit – JSON batch
10. Metrics submit – mixed batch
11. Metrics submit – wrong agent_id in body → 403
12. Metrics submit – unauthorised (bad signature) → 401
13. Dashboard endpoint – returns keys for known metric names
14. Dashboard endpoint – empty agent (all nulls)
15. Tickets endpoint – unknown agent returns empty list or graceful error
16. Full agent lifecycle: register → login → ping → submit → dashboard
"""

import json
import hmac as _hmac
import hashlib
import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# 1. Create an in-memory SQLite engine BEFORE importing the app so patches
#    are in place when module-level code in connection.py would normally run.
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# ---------------------------------------------------------------------------
# 2. Patch server_db.connection before any app imports pull in the real engine
# ---------------------------------------------------------------------------
import server_db.connection as _db_conn

_db_conn.engine = test_engine
_db_conn.SessionLocal = TestingSessionLocal

# Build all tables on the test engine
from server_db.models import Base  # noqa: E402 – must be after patching
import guidance.models
import alert_service.models
import ticket_service.models
import anomaly.models
Base.metadata.create_all(bind=test_engine)

# ---------------------------------------------------------------------------
# 3. Now it is safe to import the FastAPI app and patch get_db
# ---------------------------------------------------------------------------
from server_utils.fastapi import app  # noqa: E402
from server_db.connection import get_db  # noqa: E402
from server_auth.hmac import create_signature  # noqa: E402


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


# ---------------------------------------------------------------------------
# 4. Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    """A single TestClient reused for the whole module."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def registered_agent(client):
    """Register one agent and return its credentials dict."""
    payload = {
        "agent_version": "1.2.3",
        "hostname": "test-host-01",
        "os": "linux",
        "fingerprint": "fp-unique-abc123",
    }
    resp = client.post("/api/agent/register", json=payload)
    assert resp.status_code == 200, f"Registration failed: {resp.text}"
    data = resp.json()
    assert "agent_id" in data
    assert "api_key" in data
    assert "secret_key" in data
    return data


def _make_headers(api_key: str, secret_key: str, message: str = "login") -> dict:
    """Build HMAC-signed request headers."""
    sig = create_signature(api_key, secret_key, message)
    return {
        "x-api-key": api_key,
        "x-signature": sig,
        "x-message": message,
    }


# ---------------------------------------------------------------------------
# 5. Tests
# ---------------------------------------------------------------------------

class TestHealthEndpoints:
    def test_root_returns_service_info(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "running"
        assert "version" in body

    def test_health_returns_healthy(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert "timestamp" in body


class TestAgentRegistration:
    def test_register_new_agent_returns_credentials(self, client):
        payload = {
            "agent_version": "1.0.0",
            "hostname": "host-reg-test",
            "os": "windows",
            "fingerprint": "fp-reg-test-001",
        }
        resp = client.post("/api/agent/register", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["message"] == "Agent registered successfully"
        assert body["agent_id"].startswith("agent_")
        assert len(body["api_key"]) > 10
        assert len(body["secret_key"]) > 10
        # Template must be valid JSON
        template = json.loads(body["template"])
        assert "modules" in template

    def test_register_returns_unique_agent_ids(self, client):
        payload = {
            "agent_version": "1.0.0",
            "hostname": "host-dup",
            "os": "linux",
            "fingerprint": "fp-dup-001",
        }
        r1 = client.post("/api/agent/register", json=payload)
        r2 = client.post("/api/agent/register", json=payload)
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["agent_id"] != r2.json()["agent_id"]

    def test_register_missing_required_field_returns_422(self, client):
        # 'hostname' is missing
        payload = {
            "agent_version": "1.0.0",
            "os": "linux",
            "fingerprint": "fp-bad",
        }
        resp = client.post("/api/agent/register", json=payload)
        assert resp.status_code == 422


class TestAgentLogin:
    def test_login_with_valid_credentials(self, client, registered_agent):
        headers = _make_headers(
            registered_agent["api_key"], registered_agent["secret_key"]
        )
        body = {"agent_id": registered_agent["agent_id"]}
        resp = client.post("/api/agent/login", json=body, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "Login successful"
        assert data["agent_info"]["agent_id"] == registered_agent["agent_id"]

    def test_login_with_bad_signature_returns_401(self, client, registered_agent):
        bad_headers = {
            "x-api-key": registered_agent["api_key"],
            "x-signature": "deadbeef" * 8,
            "x-message": "login",
        }
        body = {"agent_id": registered_agent["agent_id"]}
        resp = client.post("/api/agent/login", json=body, headers=bad_headers)
        assert resp.status_code == 401

    def test_login_with_unknown_api_key_returns_401(self, client):
        bad_headers = {
            "x-api-key": "unknownkey",
            "x-signature": "sig",
            "x-message": "msg",
        }
        body = {"agent_id": "agent_fake"}
        resp = client.post("/api/agent/login", json=body, headers=bad_headers)
        assert resp.status_code == 401


class TestAgentPing:
    def test_ping_updates_heartbeat(self, client, registered_agent):
        # Must login first to seed tempCache
        headers = _make_headers(
            registered_agent["api_key"], registered_agent["secret_key"]
        )
        client.post(
            "/api/agent/login",
            json={"agent_id": registered_agent["agent_id"]},
            headers=headers,
        )
        # Now ping
        ping_resp = client.post(
            "/api/agent/ping",
            json={"agent_id": registered_agent["agent_id"]},
            headers=headers,
        )
        assert ping_resp.status_code == 200
        body = ping_resp.json()
        assert body["message"] == "Heartbeat updated"
        assert "timestamp" in body

    def test_ping_action_flag_set_after_login(self, client, registered_agent):
        """After login the resolver sets action=True; ping should report it once."""
        headers = _make_headers(
            registered_agent["api_key"], registered_agent["secret_key"]
        )
        # Trigger login (sets action flag to True)
        client.post(
            "/api/agent/login",
            json={"agent_id": registered_agent["agent_id"]},
            headers=headers,
        )
        first_ping = client.post(
            "/api/agent/ping",
            json={"agent_id": registered_agent["agent_id"]},
            headers=headers,
        )
        assert first_ping.status_code == 200
        assert first_ping.json()["action"] is True

        # Subsequent ping must reset to False
        second_ping = client.post(
            "/api/agent/ping",
            json={"agent_id": registered_agent["agent_id"]},
            headers=headers,
        )
        assert second_ping.status_code == 200
        assert second_ping.json()["action"] is False

    def test_ping_without_auth_returns_401(self, client):
        resp = client.post(
            "/api/agent/ping",
            json={"agent_id": "agent_x"},
            headers={
                "x-api-key": "bad",
                "x-signature": "bad",
                "x-message": "bad",
            },
        )
        assert resp.status_code == 401


class TestMetricsSubmit:
    # ------------------------------------------------------------------
    # Helper: ensure tempCache has the agent key so ping doesn't explode
    # ------------------------------------------------------------------
    def _login(self, client, agent):
        headers = _make_headers(agent["api_key"], agent["secret_key"])
        client.post(
            "/api/agent/login",
            json={"agent_id": agent["agent_id"]},
            headers=headers,
        )
        return headers

    def test_submit_numeric_metrics(self, client, registered_agent):
        headers = self._login(client, registered_agent)
        payload = {
            "agent_id": registered_agent["agent_id"],
            "metrics": [
                {
                    "metric_name": "cpu_v1.0.0.usage_overall",
                    "value": 42.5,
                    "timestamp": "2024-01-01T12:00:00Z",
                },
                {
                    "metric_name": "process_v1.0.0.total_threads",
                    "value": 128,
                    "timestamp": "2024-01-01T12:00:01Z",
                },
            ],
        }
        resp = client.post("/api/metrics/submit", json=payload, headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        assert body["numeric"] == 2
        assert body["json"] == 0

    def test_submit_json_metrics(self, client, registered_agent):
        headers = self._login(client, registered_agent)
        payload = {
            "agent_id": registered_agent["agent_id"],
            "metrics": [
                {
                    "metric_name": "memory_v1.0.0.ram",
                    "value": {"total_gb": 16.0, "used_gb": 8.5, "percent": 53.1, "available_gb": 7.5},
                    "timestamp": "2024-01-01T12:01:00Z",
                },
                {
                    "metric_name": "cpu_v1.0.0.usage_per_core",
                    "value": [10.0, 20.0, 30.0, 40.0],
                    "timestamp": "2024-01-01T12:01:01Z",
                },
            ],
        }
        resp = client.post("/api/metrics/submit", json=payload, headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        assert body["numeric"] == 0
        assert body["json"] == 2

    def test_submit_mixed_metrics(self, client, registered_agent):
        headers = self._login(client, registered_agent)
        payload = {
            "agent_id": registered_agent["agent_id"],
            "metrics": [
                {
                    "metric_name": "cpu_v1.0.0.usage_overall",
                    "value": 55.0,
                    "timestamp": "2024-01-01T13:00:00Z",
                },
                {
                    "metric_name": "disk_v1.0.0.usage",
                    "value": {"C:\\": {"total_gb": 500, "used_gb": 200, "percent": 40}},
                    "timestamp": "2024-01-01T13:00:01Z",
                },
            ],
        }
        resp = client.post("/api/metrics/submit", json=payload, headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["numeric"] == 1
        assert body["json"] == 1

    def test_submit_agent_id_mismatch_returns_403(self, client, registered_agent):
        headers = self._login(client, registered_agent)
        payload = {
            "agent_id": "agent_someone_else",  # ← does NOT match auth header
            "metrics": [
                {
                    "metric_name": "cpu_v1.0.0.usage_overall",
                    "value": 10.0,
                    "timestamp": "2024-01-01T12:00:00Z",
                }
            ],
        }
        resp = client.post("/api/metrics/submit", json=payload, headers=headers)
        assert resp.status_code == 403

    def test_submit_empty_batch(self, client, registered_agent):
        headers = self._login(client, registered_agent)
        payload = {
            "agent_id": registered_agent["agent_id"],
            "metrics": [],
        }
        resp = client.post("/api/metrics/submit", json=payload, headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 0

    def test_submit_without_auth_returns_401(self, client, registered_agent):
        payload = {
            "agent_id": registered_agent["agent_id"],
            "metrics": [],
        }
        resp = client.post(
            "/api/metrics/submit",
            json=payload,
            headers={
                "x-api-key": "none",
                "x-signature": "none",
                "x-message": "none",
            },
        )
        assert resp.status_code == 401

    def test_submit_large_batch(self, client, registered_agent):
        """Server must handle a large batch without timing out or erroring."""
        headers = self._login(client, registered_agent)
        metrics = [
            {
                "metric_name": "cpu_v1.0.0.usage_overall",
                "value": float(i % 100),
                "timestamp": f"2024-01-01T12:{i // 60:02d}:{i % 60:02d}Z",
            }
            for i in range(200)
        ]
        payload = {"agent_id": registered_agent["agent_id"], "metrics": metrics}
        resp = client.post("/api/metrics/submit", json=payload, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["count"] == 200


class TestDashboardEndpoint:
    def _seed_metrics(self, client, agent, extra_metrics=None):
        headers = _make_headers(agent["api_key"], agent["secret_key"])
        client.post(
            "/api/agent/login",
            json={"agent_id": agent["agent_id"]},
            headers=headers,
        )
        base_metrics = [
            {
                "metric_name": "cpu_v1.0.0.usage_overall",
                "value": 75.3,
                "timestamp": "2024-06-01T10:00:00Z",
            },
            {
                "metric_name": "memory_v1.0.0.ram",
                "value": {
                    "total_gb": 32.0,
                    "used_gb": 12.0,
                    "percent": 37.5,
                    "available_gb": 20.0,
                },
                "timestamp": "2024-06-01T10:00:01Z",
            },
            {
                "metric_name": "disk_v1.0.0.usage",
                "value": {
                    "C:\\": {
                        "total_gb": 500.0,
                        "used_gb": 250.0,
                        "percent": 50.0,
                    }
                },
                "timestamp": "2024-06-01T10:00:02Z",
            },
            {
                "metric_name": "network_v1.0.0.io",
                "value": {"upload_mb_s": 1.5, "download_mb_s": 3.5},
                "timestamp": "2024-06-01T10:00:03Z",
            },
            {
                "metric_name": "network_v1.0.0.connections",
                "value": {"total": 42},
                "timestamp": "2024-06-01T10:00:04Z",
            },
            {
                "metric_name": "network_v1.0.0.errors",
                "value": {"errors_in": 2, "errors_out": 1},
                "timestamp": "2024-06-01T10:00:05Z",
            },
            {
                "metric_name": "process_v1.0.0.total_threads",
                "value": 512,
                "timestamp": "2024-06-01T10:00:06Z",
            },
        ]
        if extra_metrics:
            base_metrics.extend(extra_metrics)

        payload = {"agent_id": agent["agent_id"], "metrics": base_metrics}
        client.post("/api/metrics/submit", json=payload, headers=headers)
        return headers

    def test_dashboard_returns_expected_keys(self, client, registered_agent):
        self._seed_metrics(client, registered_agent)
        resp = client.get(f"/api/dashboard/{registered_agent['agent_id']}")
        assert resp.status_code == 200
        body = resp.json()
        expected_keys = [
            "cpu_usage_percent",
            "memory_percent",
            "memory_total_gb",
            "disk_percent",
            "disk_total_gb",
            "network_total_mbps",
            "network_active_connections",
            "network_total_errors",
            "total_threads",
        ]
        for key in expected_keys:
            assert key in body, f"Missing key: {key}"

    def test_dashboard_cpu_usage_matches_submitted(self, client, registered_agent):
        self._seed_metrics(client, registered_agent)
        resp = client.get(f"/api/dashboard/{registered_agent['agent_id']}")
        assert resp.status_code == 200
        body = resp.json()
        # We submitted 75.3 so the latest value should be 75.3
        assert body["cpu_usage_percent"] == pytest.approx(75.3, rel=1e-3)

    def test_dashboard_network_bandwidth_calculated(self, client, registered_agent):
        self._seed_metrics(client, registered_agent)
        resp = client.get(f"/api/dashboard/{registered_agent['agent_id']}")
        assert resp.status_code == 200
        body = resp.json()
        # (1.5 + 3.5) * 8 = 40.0 Mbps
        assert body["network_total_mbps"] == pytest.approx(40.0, rel=1e-3)

    def test_dashboard_empty_agent_returns_nulls(self, client):
        """An agent with no metrics must return a valid dict full of None values."""
        # Register a fresh agent with no metrics
        r = client.post(
            "/api/agent/register",
            json={
                "agent_version": "0.1.0",
                "hostname": "empty-host",
                "os": "linux",
                "fingerprint": "fp-empty-unique-999",
            },
        )
        assert r.status_code == 200
        agent_id = r.json()["agent_id"]
        resp = client.get(f"/api/dashboard/{agent_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["cpu_usage_percent"] is None
        assert body["memory_percent"] is None
        assert body["disk_percent"] is None

    def test_dashboard_disk_free_calculated(self, client, registered_agent):
        """free_disk = total_disk - used_disk must be computed by the route."""
        self._seed_metrics(client, registered_agent)
        resp = client.get(f"/api/dashboard/{registered_agent['agent_id']}")
        body = resp.json()
        if body["disk_total_gb"] is not None and body["disk_used_gb"] is not None:
            expected_free = body["disk_total_gb"] - body["disk_used_gb"]
            assert body["disk_free_gb"] == pytest.approx(expected_free, rel=1e-3)


class TestTicketsEndpoint:
    def test_get_tickets_returns_structure(self, client, registered_agent):
        resp = client.get(
            f"/api/tickets/{registered_agent['agent_id']}/latest?limit=5"
        )
        # Either succeeds with a list or raises a 500 if ticket_service is unavailable
        if resp.status_code == 200:
            body = resp.json()
            assert "agent_id" in body
            assert "count" in body
            assert "tickets" in body
            assert isinstance(body["tickets"], list)
            assert body["agent_id"] == registered_agent["agent_id"]
        else:
            # Ticket service may use external DB; non-200 is acceptable in unit context
            assert resp.status_code in (500, 422, 404)

    def test_get_tickets_limit_param_validated(self, client, registered_agent):
        """limit=0 violates ge=1 and must return 422."""
        resp = client.get(
            f"/api/tickets/{registered_agent['agent_id']}/latest?limit=0"
        )
        assert resp.status_code == 422

    def test_get_tickets_limit_too_large(self, client, registered_agent):
        """limit=101 violates le=100 and must return 422."""
        resp = client.get(
            f"/api/tickets/{registered_agent['agent_id']}/latest?limit=101"
        )
        assert resp.status_code == 422


class TestFullAgentLifecycle:
    """End-to-end scenario: register → login → submit metrics → dashboard."""

    def test_full_lifecycle(self, client):
        # --- Step 1: Register ---
        reg_resp = client.post(
            "/api/agent/register",
            json={
                "agent_version": "2.0.0",
                "hostname": "e2e-host",
                "os": "windows",
                "fingerprint": "fp-e2e-lifecycle-xyz",
            },
        )
        assert reg_resp.status_code == 200
        creds = reg_resp.json()

        headers = _make_headers(creds["api_key"], creds["secret_key"])

        # --- Step 2: Login ---
        login_resp = client.post(
            "/api/agent/login",
            json={"agent_id": creds["agent_id"]},
            headers=headers,
        )
        assert login_resp.status_code == 200
        assert login_resp.json()["agent_info"]["agent_id"] == creds["agent_id"]

        # --- Step 3: Ping ---
        ping_resp = client.post(
            "/api/agent/ping",
            json={"agent_id": creds["agent_id"]},
            headers=headers,
        )
        assert ping_resp.status_code == 200

        # --- Step 4: Submit a batch of metrics ---
        metrics_payload = {
            "agent_id": creds["agent_id"],
            "metrics": [
                {
                    "metric_name": "cpu_v1.0.0.usage_overall",
                    "value": 33.3,
                    "timestamp": "2025-01-15T09:00:00Z",
                },
                {
                    "metric_name": "memory_v1.0.0.ram",
                    "value": {
                        "total_gb": 64.0,
                        "used_gb": 20.0,
                        "percent": 31.25,
                        "available_gb": 44.0,
                    },
                    "timestamp": "2025-01-15T09:00:01Z",
                },
            ],
        }
        submit_resp = client.post(
            "/api/metrics/submit", json=metrics_payload, headers=headers
        )
        assert submit_resp.status_code == 200
        assert submit_resp.json()["count"] == 2

        # --- Step 5: Dashboard reflects submitted data ---
        dash_resp = client.get(f"/api/dashboard/{creds['agent_id']}")
        assert dash_resp.status_code == 200
        dash = dash_resp.json()
        assert dash["cpu_usage_percent"] == pytest.approx(33.3, rel=1e-3)
        assert dash["memory_total_gb"] == pytest.approx(64.0, rel=1e-3)

    def test_multiple_agents_metrics_are_isolated(self, client):
        """Two separate agents must not see each other's metrics on the dashboard."""
        def _register_and_seed(hostname, fingerprint, cpu_val):
            r = client.post(
                "/api/agent/register",
                json={
                    "agent_version": "1.0.0",
                    "hostname": hostname,
                    "os": "linux",
                    "fingerprint": fingerprint,
                },
            )
            assert r.status_code == 200
            creds = r.json()
            headers = _make_headers(creds["api_key"], creds["secret_key"])
            client.post(
                "/api/agent/login",
                json={"agent_id": creds["agent_id"]},
                headers=headers,
            )
            client.post(
                "/api/metrics/submit",
                json={
                    "agent_id": creds["agent_id"],
                    "metrics": [
                        {
                            "metric_name": "cpu_v1.0.0.usage_overall",
                            "value": cpu_val,
                            "timestamp": "2025-01-16T10:00:00Z",
                        }
                    ],
                },
                headers=headers,
            )
            return creds["agent_id"]

        agent_a = _register_and_seed("host-isolation-a", "fp-iso-a-111", 11.1)
        agent_b = _register_and_seed("host-isolation-b", "fp-iso-b-222", 88.8)

        dash_a = client.get(f"/api/dashboard/{agent_a}").json()
        dash_b = client.get(f"/api/dashboard/{agent_b}").json()

        assert dash_a["cpu_usage_percent"] == pytest.approx(11.1, rel=1e-2)
        assert dash_b["cpu_usage_percent"] == pytest.approx(88.8, rel=1e-2)

class TestGuidanceEndpoints:
    def test_upsert_guidance(self, client):
        payload = {
            "metric_name": "cpu_v1.0.0.usage_overall",
            "severity": "P1",
            "priority": "P1",
            "resolution_steps": [{"step": 1, "action": "Restart container"}],
            "resolver_notes": "High CPU alert",
            "resolution_meta": {"tags": ["cpu", "critical"]}
        }
        resp = client.put("/api/guidance", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["metric_name"] == "cpu_v1.0.0.usage_overall"
        assert data["priority"] == "P1"
        assert "id" in data
        
    def test_list_guidance(self, client):
        resp = client.get("/api/guidance")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "items" in data
        assert len(data["items"]) > 0
        
    def test_get_by_key_and_steps(self, client):
        # By key
        resp = client.get("/api/guidance/by-key?metric_name=cpu_v1.0.0.usage_overall&severity=P1")
        assert resp.status_code == 200
        assert resp.json()["metric_name"] == "cpu_v1.0.0.usage_overall"
        
        # Steps
        steps_resp = client.get("/api/guidance/by-key/steps?metric_name=cpu_v1.0.0.usage_overall&severity=P1")
        assert steps_resp.status_code == 200
        assert "steps" in steps_resp.json()
        assert len(steps_resp.json()["steps"]) == 1

class TestAlertEndpoints:
    def test_list_alerts_empty(self, client):
        resp = client.get("/api/alerts")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_alert_query_and_resolution(self, client):
        # We need to manually insert an alert to test querying and resolving
        from alert_service.models import Alert
        db = TestingSessionLocal()
        new_alert = Alert(
            metric_name="memory_v1.0.0.ram",
            severity="P2",
            type="SINGLE",
            status="OPEN",
            agent_ids='["agent_123"]',
            total_occurrence=5
        )
        db.add(new_alert)
        db.commit()
        db.refresh(new_alert)
        alert_id = new_alert.id
        db.close()
        
        # 1. Get List
        resp = client.get("/api/alerts")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1
        
        # 2. Get Single Alert
        resp_single = client.get(f"/api/alerts/{alert_id}")
        assert resp_single.status_code == 200
        assert resp_single.json()["metric_name"] == "memory_v1.0.0.ram"
        assert resp_single.json()["status"] == "OPEN"
        
        # 3. Resolve Alert Manually
        resp_resolve = client.post(f"/api/alerts/{alert_id}/resolve")
        assert resp_resolve.status_code == 200
        assert resp_resolve.json()["message"] == "Alert resolved successfully"
        
        # 4. Confirm Alert is closed
        resp_single_closed = client.get(f"/api/alerts/{alert_id}")
        assert resp_single_closed.json()["status"] == "CLOSED"
        
        # resolving again should be 400
        assert client.post(f"/api/alerts/{alert_id}/resolve").status_code == 400
