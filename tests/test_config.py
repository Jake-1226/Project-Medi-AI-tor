"""
Tests for configuration management.
Unit tests — no server required.
"""

import pytest
import os
from unittest.mock import patch
from core.config import AgentConfig, SecurityLevel, LogLevel


@pytest.mark.unit
class TestAgentConfigDefaults:
    """Test default configuration values"""

    def test_default_port(self):
        config = AgentConfig()
        assert config.default_redfish_port == 443

    def test_default_security_level(self):
        config = AgentConfig()
        assert config.security_level == SecurityLevel.HIGH

    def test_default_timeout(self):
        config = AgentConfig()
        assert config.connection_timeout == 30

    def test_default_demo_mode_off(self):
        config = AgentConfig()
        assert config.demo_mode is False

    def test_default_ssl_verify_off(self):
        config = AgentConfig()
        assert config.verify_ssl is False

    def test_default_log_level(self):
        config = AgentConfig()
        assert config.log_level == LogLevel.INFO


@pytest.mark.unit
class TestAgentConfigFromEnv:
    """Test loading config from environment"""

    def test_from_env_defaults(self):
        with patch.dict(os.environ, {}, clear=False):
            config = AgentConfig.from_env()
            assert config.default_redfish_port == 443
            assert config.security_level == SecurityLevel.MEDIUM  # env default is medium

    def test_from_env_custom_port(self):
        with patch.dict(os.environ, {"REDFISH_PORT": "8443"}):
            config = AgentConfig.from_env()
            assert config.default_redfish_port == 8443

    def test_from_env_demo_mode_true(self):
        with patch.dict(os.environ, {"DEMO_MODE": "true"}):
            config = AgentConfig.from_env()
            assert config.demo_mode is True

    def test_from_env_demo_mode_yes(self):
        with patch.dict(os.environ, {"DEMO_MODE": "yes"}):
            config = AgentConfig.from_env()
            assert config.demo_mode is True

    def test_from_env_demo_mode_1(self):
        with patch.dict(os.environ, {"DEMO_MODE": "1"}):
            config = AgentConfig.from_env()
            assert config.demo_mode is True

    def test_from_env_demo_mode_false(self):
        with patch.dict(os.environ, {"DEMO_MODE": "false"}):
            config = AgentConfig.from_env()
            assert config.demo_mode is False

    def test_from_env_security_level_low(self):
        with patch.dict(os.environ, {"SECURITY_LEVEL": "low"}):
            config = AgentConfig.from_env()
            assert config.security_level == SecurityLevel.LOW

    def test_from_env_security_level_high(self):
        with patch.dict(os.environ, {"SECURITY_LEVEL": "high"}):
            config = AgentConfig.from_env()
            assert config.security_level == SecurityLevel.HIGH


@pytest.mark.unit
class TestActionPermissions:
    """Test action permission checking"""

    def test_read_only_allowed_at_low(self):
        config = AgentConfig(security_level=SecurityLevel.LOW)
        assert config.is_action_allowed("read_only") is True

    def test_diagnostic_blocked_at_low(self):
        config = AgentConfig(security_level=SecurityLevel.LOW)
        assert config.is_action_allowed("diagnostic") is False

    def test_full_control_blocked_at_low(self):
        config = AgentConfig(security_level=SecurityLevel.LOW)
        assert config.is_action_allowed("full_control") is False

    def test_read_only_allowed_at_medium(self):
        config = AgentConfig(security_level=SecurityLevel.MEDIUM)
        assert config.is_action_allowed("read_only") is True

    def test_diagnostic_allowed_at_medium(self):
        config = AgentConfig(security_level=SecurityLevel.MEDIUM)
        assert config.is_action_allowed("diagnostic") is True

    def test_full_control_blocked_at_medium(self):
        config = AgentConfig(security_level=SecurityLevel.MEDIUM)
        assert config.is_action_allowed("full_control") is False

    def test_all_allowed_at_high(self):
        config = AgentConfig(security_level=SecurityLevel.HIGH)
        assert config.is_action_allowed("read_only") is True
        assert config.is_action_allowed("diagnostic") is True
        assert config.is_action_allowed("full_control") is True

    def test_unknown_action_blocked(self):
        config = AgentConfig(security_level=SecurityLevel.HIGH)
        assert config.is_action_allowed("unknown_action") is False

    def test_action_level_enum_value(self):
        """Test that ActionLevel enum values work too"""
        from models.server_models import ActionLevel
        config = AgentConfig(security_level=SecurityLevel.HIGH)
        assert config.is_action_allowed(ActionLevel.READ_ONLY) is True
        assert config.is_action_allowed(ActionLevel.FULL_CONTROL) is True


@pytest.mark.unit
class TestConfigToDict:
    """Test config serialization"""

    def test_to_dict_returns_dict(self):
        config = AgentConfig()
        d = config.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_has_all_fields(self):
        config = AgentConfig()
        d = config.to_dict()
        assert "default_redfish_port" in d
        assert "security_level" in d
        assert "demo_mode" in d
        assert "connection_timeout" in d

    def test_to_dict_values_match(self):
        config = AgentConfig(demo_mode=True, default_redfish_port=9443)
        d = config.to_dict()
        assert d["demo_mode"] is True
        assert d["default_redfish_port"] == 9443
