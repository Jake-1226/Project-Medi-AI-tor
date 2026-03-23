"""
Tests for security features: error sanitization, input validation,
password hashing, encryption, security headers.
Mix of unit tests (no server) and integration tests (requires server).
"""

import pytest
import httpx
import time
import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

BASE = "http://127.0.0.1:8000"


@pytest.mark.unit
class TestErrorSanitization:
    """Test that _sanitize_error strips internal details"""

    def test_sanitize_strips_traceback(self):
        from main import _sanitize_error
        e = Exception('Traceback (most recent call last): File "/app/main.py"')
        assert "Traceback" not in _sanitize_error(e)
        assert "internal error" in _sanitize_error(e).lower()

    def test_sanitize_strips_file_paths(self):
        from main import _sanitize_error
        e = Exception('File "C:\\Users\\admin\\project\\main.py", line 42')
        assert "C:\\" not in _sanitize_error(e)

    def test_sanitize_keeps_short_messages(self):
        from main import _sanitize_error
        e = Exception("Connection refused")
        assert _sanitize_error(e) == "Connection refused"

    def test_sanitize_truncates_long_messages(self):
        from main import _sanitize_error
        e = Exception("x" * 500)
        result = _sanitize_error(e)
        assert len(result) <= 300

    def test_sanitize_strips_module_errors(self):
        from main import _sanitize_error
        e = Exception("ModuleNotFoundError: No module named 'foo'")
        assert "ModuleNotFoundError" not in _sanitize_error(e)


@pytest.mark.unit
class TestHostValidation:
    """Test hostname/IP validation"""

    def test_valid_ipv4(self):
        from main import _validate_host
        assert _validate_host("192.168.1.1") == "192.168.1.1"

    def test_valid_hostname(self):
        from main import _validate_host
        assert _validate_host("idrac.example.com") == "idrac.example.com"

    def test_valid_ipv6_bracket(self):
        from main import _validate_host
        assert _validate_host("[::1]") == "[::1]"

    def test_rejects_empty(self):
        from main import _validate_host
        with pytest.raises(Exception):
            _validate_host("")

    def test_rejects_path_traversal(self):
        from main import _validate_host
        with pytest.raises(Exception):
            _validate_host("../../../etc/passwd")

    def test_rejects_spaces(self):
        from main import _validate_host
        with pytest.raises(Exception):
            _validate_host("host name with spaces")

    def test_rejects_semicolons(self):
        from main import _validate_host
        with pytest.raises(Exception):
            _validate_host("host;rm -rf /")

    def test_rejects_too_long(self):
        from main import _validate_host
        with pytest.raises(Exception):
            _validate_host("a" * 254)


@pytest.mark.unit
class TestOSCommandWhitelist:
    """Test OS command whitelist"""

    def test_whitelist_contains_safe_commands(self):
        from main import _OS_COMMAND_WHITELIST
        assert "system_info" in _OS_COMMAND_WHITELIST
        assert "cpu_info" in _OS_COMMAND_WHITELIST
        assert "memory_info" in _OS_COMMAND_WHITELIST

    def test_whitelist_contains_custom_command(self):
        from main import _OS_COMMAND_WHITELIST
        assert "custom_command" in _OS_COMMAND_WHITELIST

    def test_whitelist_rejects_unknown(self):
        from main import _OS_COMMAND_WHITELIST
        assert "rm_rf" not in _OS_COMMAND_WHITELIST
        assert "eval" not in _OS_COMMAND_WHITELIST
        assert "exec" not in _OS_COMMAND_WHITELIST


@pytest.mark.unit
class TestPasswordHashing:
    """Test auth password hashing"""

    def test_hash_produces_salt_and_hash(self):
        from security.auth import AuthManager
        from core.config import AgentConfig
        am = AuthManager(AgentConfig())
        h = am._hash_password("test123")
        assert ":" in h
        salt, hash_val = h.split(":")
        assert len(salt) == 32  # 16 bytes hex
        assert len(hash_val) == 64  # sha256 hex

    def test_verify_correct_password(self):
        from security.auth import AuthManager
        from core.config import AgentConfig
        am = AuthManager(AgentConfig())
        h = am._hash_password("mysecret")
        assert am._verify_password("mysecret", h) is True

    def test_verify_wrong_password(self):
        from security.auth import AuthManager
        from core.config import AgentConfig
        am = AuthManager(AgentConfig())
        h = am._hash_password("correct")
        assert am._verify_password("wrong", h) is False

    def test_different_hashes_for_same_password(self):
        from security.auth import AuthManager
        from core.config import AgentConfig
        am = AuthManager(AgentConfig())
        h1 = am._hash_password("same")
        h2 = am._hash_password("same")
        assert h1 != h2  # Different salts


@pytest.mark.unit
class TestEncryption:
    """Test data encryption"""

    def test_encrypt_decrypt_roundtrip(self):
        from security.auth import AuthManager
        from core.config import AgentConfig
        am = AuthManager(AgentConfig())
        original = "sensitive_data_123"
        encrypted = am.encrypt_sensitive_data(original)
        assert encrypted != original
        decrypted = am.decrypt_sensitive_data(encrypted)
        assert decrypted == original

    def test_different_encryptions_for_same_data(self):
        from security.auth import AuthManager
        from core.config import AgentConfig
        am = AuthManager(AgentConfig())
        e1 = am.encrypt_sensitive_data("test")
        e2 = am.encrypt_sensitive_data("test")
        # Fernet produces different ciphertexts due to timestamp/IV
        assert e1 != e2


@pytest.mark.unit
class TestAccountLockout:
    """Test account lockout after failed attempts"""

    def test_not_locked_initially(self):
        from security.auth import AuthManager
        from core.config import AgentConfig
        am = AuthManager(AgentConfig())
        assert am._is_account_locked("admin") is False

    def test_locked_after_max_attempts(self):
        from security.auth import AuthManager
        from core.config import AgentConfig
        am = AuthManager(AgentConfig())
        for _ in range(5):
            am._record_failed_attempt("testuser")
        assert am._is_account_locked("testuser") is True

    def test_not_locked_under_threshold(self):
        from security.auth import AuthManager
        from core.config import AgentConfig
        am = AuthManager(AgentConfig())
        for _ in range(4):
            am._record_failed_attempt("testuser")
        assert am._is_account_locked("testuser") is False


@pytest.mark.integration
class TestSecurityHeaders:
    """Test that security headers are present on responses"""

    @pytest.mark.asyncio
    async def test_x_content_type_options(self):
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/login")
            assert r.headers.get("x-content-type-options") == "nosniff"

    @pytest.mark.asyncio
    async def test_x_frame_options(self):
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/login")
            assert r.headers.get("x-frame-options") == "DENY"

    @pytest.mark.asyncio
    async def test_x_xss_protection(self):
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/login")
            assert "1" in r.headers.get("x-xss-protection", "")

    @pytest.mark.asyncio
    async def test_content_security_policy(self):
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/login")
            csp = r.headers.get("content-security-policy", "")
            assert "default-src 'self'" in csp
            assert "script-src" in csp

    @pytest.mark.asyncio
    async def test_referrer_policy(self):
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{BASE}/login")
            assert "strict-origin" in r.headers.get("referrer-policy", "")


@pytest.mark.integration
class TestFleetPasswordNotExposed:
    """Test that fleet API never returns passwords"""

    @pytest.mark.asyncio
    async def test_fleet_overview_no_password(self):
        async with httpx.AsyncClient() as c:
            # Login first
            lr = await c.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "admin123"})
            if lr.status_code == 429:
                time.sleep(62)
                lr = await c.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "admin123"})
            token = lr.json().get("token", "")
            headers = {"Authorization": f"Bearer {token}"}
            
            r = await c.get(f"{BASE}/api/fleet/overview", headers=headers)
            body = r.text
            assert "calvin" not in body.lower()  # The iDRAC default password
            assert '"password"' not in body
