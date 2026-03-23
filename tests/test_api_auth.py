"""
Tests for authentication, authorization, and security features.
Tests run against the live server at http://127.0.0.1:8000.
"""

import pytest
import httpx
import time

BASE = "http://127.0.0.1:8000"

# Helper to get a token
async def get_token(username="admin", password="admin123"):
    async with httpx.AsyncClient() as c:
        for attempt in range(3):
            r = await c.post(f"{BASE}/api/auth/login", json={"username": username, "password": password})
            if r.status_code == 200:
                return r.json().get("token", "")
            if r.status_code == 429:
                time.sleep(62)  # Wait for rate limit window to reset
        return r.json().get("token", "")

def auth(token):
    return {"Authorization": f"Bearer {token}"}

@pytest.mark.integration
class TestAuthLogin:
    """Test login flow"""
    
    @pytest.mark.asyncio
    async def test_login_success(self):
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "admin123"})
            assert r.status_code == 200
            data = r.json()
            assert data["status"] == "success"
            assert "token" in data
            assert data["user"]["username"] == "admin"
            assert data["user"]["role"] == "admin"
    
    @pytest.mark.asyncio
    async def test_login_bad_password(self):
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "wrong"})
            assert r.status_code == 401
    
    @pytest.mark.asyncio
    async def test_login_bad_username(self):
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{BASE}/api/auth/login", json={"username": "nonexistent", "password": "x"})
            assert r.status_code == 401
    
    @pytest.mark.asyncio
    async def test_login_sets_cookie(self):
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "admin123"})
            assert "auth_token" in r.cookies

@pytest.mark.integration
class TestAuthMe:
    """Test /api/auth/me endpoint"""
    
    @pytest.mark.asyncio
    async def test_me_with_valid_token(self):
        token = await get_token()
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/api/auth/me", headers=auth(token))
            assert r.status_code == 200
            assert r.json()["user"]["username"] == "admin"
    
    @pytest.mark.asyncio
    async def test_me_without_token(self):
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/api/auth/me")
            assert r.status_code == 401
    
    @pytest.mark.asyncio
    async def test_me_with_invalid_token(self):
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/api/auth/me", headers=auth("invalid.token.here"))
            assert r.status_code == 401

@pytest.mark.integration
class TestAuthRBAC:
    """Test role-based access control"""
    
    @pytest.mark.asyncio
    async def test_viewer_permissions(self):
        token = await get_token("viewer", "viewer123")
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/api/auth/me", headers=auth(token))
            assert r.status_code == 200
            perms = r.json()["user"]["permissions"]
            assert "read_only" in perms
            assert "full_control" not in perms
    
    @pytest.mark.asyncio
    async def test_viewer_blocked_from_full_control(self):
        token = await get_token("viewer", "viewer123")
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{BASE}/api/execute", headers={**auth(token), "Content-Type": "application/json"},
                           json={"action": "force_restart", "action_level": "full_control"})
            assert r.status_code == 403
    
    @pytest.mark.asyncio
    async def test_viewer_allowed_read_only(self):
        token = await get_token("viewer", "viewer123")
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{BASE}/api/execute", headers={**auth(token), "Content-Type": "application/json"},
                           json={"action": "get_server_info", "action_level": "read_only"})
            # Should be 200 (if connected) or 400 (if not connected), but NOT 403
            assert r.status_code in [200, 400]
    
    @pytest.mark.asyncio
    async def test_operator_permissions(self):
        token = await get_token("operator", "operator123")
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/api/auth/me", headers=auth(token))
            perms = r.json()["user"]["permissions"]
            assert "read_only" in perms
            assert "diagnostic" in perms
            assert "full_control" not in perms
    
    @pytest.mark.asyncio
    async def test_viewer_blocked_from_audit_log(self):
        token = await get_token("viewer", "viewer123")
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/api/audit-log", headers=auth(token))
            assert r.status_code == 403
    
    @pytest.mark.asyncio
    async def test_admin_can_access_audit_log(self):
        token = await get_token("admin", "admin123")
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/api/audit-log", headers=auth(token))
            assert r.status_code == 200
            assert "entries" in r.json()

@pytest.mark.integration
class TestAuthLogout:
    """Test logout"""
    
    @pytest.mark.asyncio
    async def test_logout(self):
        token = await get_token()
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{BASE}/api/auth/logout", headers=auth(token))
            assert r.status_code == 200
            # Token should be invalid after logout
            r2 = await c.get(f"{BASE}/api/auth/me", headers=auth(token))
            assert r2.status_code == 401

@pytest.mark.integration
class TestUnauthenticatedAccess:
    """Test that sensitive endpoints require auth"""
    
    @pytest.mark.asyncio
    async def test_connect_requires_auth(self):
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{BASE}/api/connect", json={"host": "1.2.3.4", "username": "x", "password": "y"})
            assert r.status_code == 401
    
    @pytest.mark.asyncio
    async def test_execute_requires_auth(self):
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{BASE}/api/execute", json={"action": "get_server_info", "action_level": "read_only"})
            assert r.status_code == 401
    
    @pytest.mark.asyncio
    async def test_batch_execute_requires_auth(self):
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{BASE}/api/execute/batch", json={"commands": []})
            assert r.status_code == 401
    
    @pytest.mark.asyncio
    async def test_fleet_requires_auth(self):
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/api/fleet/overview")
            assert r.status_code == 401
    
    @pytest.mark.asyncio
    async def test_os_execute_requires_auth(self):
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{BASE}/api/os/execute", json={"action": "system_info"})
            assert r.status_code == 401

@pytest.mark.integration
class TestPublicEndpoints:
    """Test that public pages don't require auth"""
    
    @pytest.mark.asyncio
    async def test_customer_chat_public(self):
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/")
            assert r.status_code == 200
    
    @pytest.mark.asyncio
    async def test_login_page_public(self):
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/login")
            assert r.status_code == 200
    
    @pytest.mark.asyncio
    async def test_health_check_public(self):
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/api/health")
            assert r.status_code == 200
    
    @pytest.mark.asyncio
    async def test_technician_redirects_without_auth(self):
        async with httpx.AsyncClient(follow_redirects=False) as c:
            r = await c.get(f"{BASE}/technician")
            assert r.status_code == 302
