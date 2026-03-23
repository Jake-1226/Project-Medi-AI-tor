"""
Tests for major API endpoints — integration tests against live server.
Requires server running at http://127.0.0.1:8000.
"""

import pytest
import httpx
import time

BASE = "http://127.0.0.1:8000"


async def get_token(username="admin", password="admin123"):
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{BASE}/api/auth/login", json={"username": username, "password": password})
        if r.status_code == 429:
            time.sleep(62)
            r = await c.post(f"{BASE}/api/auth/login", json={"username": username, "password": password})
        return r.json().get("token", "")


def auth(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.mark.integration
class TestPageRoutes:
    """Test HTML page routes"""

    @pytest.mark.asyncio
    async def test_customer_chat_page(self):
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/")
            assert r.status_code == 200
            assert "html" in r.headers.get("content-type", "").lower()

    @pytest.mark.asyncio
    async def test_login_page(self):
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/login")
            assert r.status_code == 200
            assert "Medi-AI-tor" in r.text

    @pytest.mark.asyncio
    async def test_fleet_page(self):
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/fleet")
            assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_technician_requires_auth(self):
        async with httpx.AsyncClient(follow_redirects=False) as c:
            r = await c.get(f"{BASE}/technician")
            assert r.status_code == 302
            assert "/login" in r.headers.get("location", "")

    @pytest.mark.asyncio
    async def test_technician_with_auth(self):
        token = await get_token()
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/technician", cookies={"auth_token": token})
            assert r.status_code == 200


@pytest.mark.integration
class TestHealthEndpoint:
    """Test health check endpoint"""

    @pytest.mark.asyncio
    async def test_health_check(self):
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/api/health")
            assert r.status_code == 200
            data = r.json()
            assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_has_version(self):
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/api/health")
            assert "agent" in r.json()


@pytest.mark.integration
class TestConnectionEndpoints:
    """Test server connection endpoints"""

    @pytest.mark.asyncio
    async def test_connect_requires_auth(self):
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{BASE}/api/connect", json={"host": "1.2.3.4", "username": "x", "password": "y"})
            assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_connect_validates_host(self):
        token = await get_token()
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{BASE}/api/connect", headers=auth(token),
                           json={"host": "", "username": "root", "password": "pass"})
            assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_connect_rejects_localhost(self):
        token = await get_token()
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{BASE}/api/connect", headers=auth(token),
                           json={"host": "localhost", "username": "root", "password": "pass"})
            assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_connection_status(self):
        token = await get_token()
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/api/connection/status", headers=auth(token))
            # Should return status whether connected or not
            assert r.status_code == 200


@pytest.mark.integration
class TestExecuteEndpoints:
    """Test action execution endpoints"""

    @pytest.mark.asyncio
    async def test_execute_requires_auth(self):
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{BASE}/api/execute",
                           json={"action": "get_server_info", "action_level": "read_only"})
            assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_execute_checks_permissions(self):
        token = await get_token("viewer", "viewer123")
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{BASE}/api/execute", headers=auth(token),
                           json={"action": "force_restart", "action_level": "full_control"})
            assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_batch_execute_requires_auth(self):
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{BASE}/api/execute/batch", json={"commands": []})
            assert r.status_code == 401


@pytest.mark.integration
class TestFleetEndpoints:
    """Test fleet management endpoints"""

    @pytest.mark.asyncio
    async def test_fleet_overview_requires_auth(self):
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/api/fleet/overview")
            assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_fleet_overview_with_auth(self):
        token = await get_token()
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/api/fleet/overview", headers=auth(token))
            assert r.status_code == 200
            data = r.json()
            assert data["status"] == "success"
            assert "data" in data

    @pytest.mark.asyncio
    async def test_fleet_add_server(self):
        token = await get_token()
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{BASE}/api/fleet/servers", headers=auth(token),
                           json={"name": "TestSrv", "host": "10.0.0.99", "username": "root",
                                 "password": "pass", "port": 443})
            assert r.status_code == 200
            assert "server_id" in r.json()

    @pytest.mark.asyncio
    async def test_fleet_groups(self):
        token = await get_token()
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/api/fleet/groups", headers=auth(token))
            assert r.status_code == 200
            assert "groups" in r.json()

    @pytest.mark.asyncio
    async def test_fleet_analytics(self):
        token = await get_token()
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/api/fleet/analytics", headers=auth(token))
            assert r.status_code == 200
            assert "data" in r.json()

    @pytest.mark.asyncio
    async def test_fleet_alerts(self):
        token = await get_token()
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/api/fleet/alerts", headers=auth(token))
            assert r.status_code == 200


@pytest.mark.integration
class TestAuditLog:
    """Test audit log endpoint"""

    @pytest.mark.asyncio
    async def test_audit_log_admin_only(self):
        token = await get_token("viewer", "viewer123")
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/api/audit-log", headers=auth(token))
            assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_audit_log_returns_entries(self):
        token = await get_token()
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/api/audit-log?limit=10", headers=auth(token))
            assert r.status_code == 200
            data = r.json()
            assert "entries" in data
            assert isinstance(data["entries"], list)

    @pytest.mark.asyncio
    async def test_audit_log_records_login(self):
        token = await get_token()
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/api/audit-log?limit=50", headers=auth(token))
            entries = r.json().get("entries", [])
            events = [e["event"] for e in entries]
            assert "LOGIN_SUCCESS" in events


@pytest.mark.integration
class TestChatEndpoint:
    """Test chat endpoint"""

    @pytest.mark.asyncio
    async def test_chat_works_without_auth(self):
        """Customer chat is public (no auth required on /chat)"""
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{BASE}/chat",
                           json={"message": "hello", "action_level": "read_only"})
            # Should work (200) or fail gracefully (400 if not connected), but NOT 401
            assert r.status_code in [200, 400, 500]
            assert r.status_code != 401


@pytest.mark.integration
class TestQuickStatus:
    """Test quick status endpoint"""

    @pytest.mark.asyncio
    async def test_quick_status(self):
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/api/server/quick-status")
            assert r.status_code == 200
            data = r.json()
            assert "connected" in data
