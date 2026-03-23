"""
Tests for fleet manager — server management, health scoring, alerts, groups.
Unit tests — no real server required.
"""

import pytest
import asyncio
import sys
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.fleet_manager import FleetManager, ServerInfo, ServerStatus, ServerGroup


@pytest.fixture
def fm():
    """Fresh fleet manager for each test"""
    return FleetManager()


@pytest.fixture
def sample_server_id(fm):
    """Add a sample server and return its ID"""
    return fm.add_server(
        name="Test Server",
        host="192.168.1.100",
        username="root",
        password="testpass",
        port=443,
        environment="lab",
        location="Test Lab"
    )


@pytest.mark.unit
class TestFleetManagerAddServer:
    def test_add_server_returns_id(self, fm):
        sid = fm.add_server("S1", "1.2.3.4", "root", "pass")
        assert sid is not None
        assert len(sid) > 0

    def test_add_server_stored(self, fm):
        sid = fm.add_server("S1", "1.2.3.4", "root", "pass")
        assert sid in fm.servers
        assert fm.servers[sid].name == "S1"
        assert fm.servers[sid].host == "1.2.3.4"

    def test_add_server_default_status_offline(self, fm):
        sid = fm.add_server("S1", "1.2.3.4", "root", "pass")
        assert fm.servers[sid].status == ServerStatus.OFFLINE

    def test_add_server_with_environment(self, fm):
        sid = fm.add_server("S1", "1.2.3.4", "root", "pass", environment="production")
        assert fm.servers[sid].environment == "production"

    def test_add_server_auto_assigned_to_all_servers_group(self, fm):
        sid = fm.add_server("S1", "1.2.3.4", "root", "pass")
        assert sid in fm.server_groups["All Servers"].server_ids

    def test_add_duplicate_host_returns_existing_id(self, fm):
        sid1 = fm.add_server("S1", "1.2.3.4", "root", "pass")
        sid2 = fm.add_server("S1b", "1.2.3.4", "root", "pass")
        assert sid1 == sid2  # Same host returns same ID

    def test_add_server_with_tags(self, fm):
        sid = fm.add_server("S1", "1.2.3.4", "root", "pass", tags=["critical", "gpu"])
        assert "critical" in fm.servers[sid].tags


@pytest.mark.unit
class TestFleetManagerRemoveServer:
    def test_remove_existing_server(self, fm, sample_server_id):
        assert fm.remove_server(sample_server_id) is True
        assert sample_server_id not in fm.servers

    def test_remove_nonexistent_server(self, fm):
        assert fm.remove_server("nonexistent-id") is False


@pytest.mark.unit
class TestFleetManagerGetServer:
    def test_get_existing_server(self, fm, sample_server_id):
        server = fm.get_server(sample_server_id)
        assert server is not None
        assert server.name == "Test Server"

    def test_get_nonexistent_returns_none(self, fm):
        assert fm.get_server("fake-id") is None


@pytest.mark.unit
class TestServerInfoToDict:
    def test_to_dict_excludes_password(self, fm, sample_server_id):
        server = fm.get_server(sample_server_id)
        d = server.to_dict()
        assert "password" not in d

    def test_to_dict_has_required_fields(self, fm, sample_server_id):
        d = fm.get_server(sample_server_id).to_dict()
        assert "id" in d
        assert "name" in d
        assert "host" in d
        assert "status" in d
        assert "health_score" in d


@pytest.mark.unit
class TestHealthScoring:
    """Test _calculate_health_score with parsed Redfish objects"""

    def test_all_healthy_score_high(self, fm):
        metrics = {
            'thermal': [{'reading_celsius': 30, 'status': 'OK'}],
            'power': [{'status': 'OK (Enabled)'}, {'status': 'OK (Enabled)'}],
            'memory': [{'size_gb': 32, 'status': 'OK'}, {'size_gb': 32, 'status': 'OK'}],
            'storage': [{'status': 'OK'}, {'status': 'OK'}],
            'system': {'overall_health': 'OK'},
        }
        score = fm._calculate_health_score(metrics)
        assert score >= 90.0

    def test_critical_temp_lowers_score(self, fm):
        metrics = {
            'thermal': [{'reading_celsius': 90, 'status': 'Critical'}],
            'power': [{'status': 'OK'}],
            'memory': [{'size_gb': 32, 'status': 'OK'}],
            'storage': [{'status': 'OK'}],
            'system': {'overall_health': 'OK'},
        }
        score = fm._calculate_health_score(metrics)
        assert score < 85.0  # Critical temp should pull score down

    def test_psu_failure_lowers_score(self, fm):
        metrics = {
            'thermal': [{'reading_celsius': 30, 'status': 'OK'}],
            'power': [{'status': 'OK'}, {'status': 'Critical (UnavailableOffline)'}],
            'memory': [{'size_gb': 32, 'status': 'OK'}],
            'storage': [{'status': 'OK'}],
            'system': {'overall_health': 'OK'},
        }
        score = fm._calculate_health_score(metrics)
        assert score < 95.0  # One failed PSU

    def test_empty_metrics_returns_default(self, fm):
        score = fm._calculate_health_score({})
        assert score == 75.0

    def test_none_metrics_returns_default(self, fm):
        score = fm._calculate_health_score(None)
        assert score == 75.0

    def test_score_is_rounded(self, fm):
        metrics = {
            'thermal': [{'reading_celsius': 30, 'status': 'OK'}],
            'power': [],
            'memory': [],
            'storage': [],
        }
        score = fm._calculate_health_score(metrics)
        # Score should have at most 1 decimal
        assert score == round(score, 1)


@pytest.mark.unit
class TestAlertChecking:
    """Test _check_server_alerts"""

    @pytest.mark.asyncio
    async def test_critical_temp_generates_alert(self, fm, sample_server_id):
        metrics = {
            'thermal': [{'reading_celsius': 90, 'name': 'CPU1', 'id': 'T1'}],
            'power': [],
        }
        await fm._check_server_alerts(sample_server_id, metrics)
        assert fm.servers[sample_server_id].alert_count > 0
        assert any('critical' in a.get('type', '') for a in fm.alerts)

    @pytest.mark.asyncio
    async def test_warning_temp_generates_warning(self, fm, sample_server_id):
        metrics = {
            'thermal': [{'reading_celsius': 80, 'name': 'CPU1', 'id': 'T1'}],
            'power': [],
        }
        await fm._check_server_alerts(sample_server_id, metrics)
        assert any('warning' in a.get('type', '') for a in fm.alerts)

    @pytest.mark.asyncio
    async def test_normal_temp_no_alerts(self, fm, sample_server_id):
        metrics = {
            'thermal': [{'reading_celsius': 40, 'name': 'CPU1', 'id': 'T1'}],
            'power': [{'status': 'OK', 'id': 'PSU1'}],
        }
        await fm._check_server_alerts(sample_server_id, metrics)
        assert fm.servers[sample_server_id].alert_count == 0

    @pytest.mark.asyncio
    async def test_psu_failure_generates_critical(self, fm, sample_server_id):
        metrics = {
            'thermal': [],
            'power': [{'status': 'Critical (UnavailableOffline)', 'id': 'PSU.Slot.1'}],
        }
        await fm._check_server_alerts(sample_server_id, metrics)
        assert any('critical' in a.get('type', '') for a in fm.alerts)
        assert any('PSU' in a.get('message', '') for a in fm.alerts)


@pytest.mark.unit
class TestGroupManagement:
    def test_default_groups_created(self, fm):
        assert "All Servers" in fm.server_groups

    def test_create_group(self, fm):
        fm.create_group("Test Group", "For testing")
        assert "Test Group" in fm.server_groups

    def test_delete_group(self, fm):
        fm.create_group("Temp", "Temp group")
        assert fm.delete_group("Temp") is True
        assert "Temp" not in fm.server_groups

    def test_cannot_delete_all_servers_group(self, fm):
        result = fm.delete_group("All Servers")
        assert result is False  # Protected group

    def test_add_server_to_group(self, fm, sample_server_id):
        fm.create_group("MyGroup", "Test")
        fm.add_server_to_group(sample_server_id, "MyGroup")
        assert sample_server_id in fm.server_groups["MyGroup"].server_ids

    def test_remove_server_from_group(self, fm, sample_server_id):
        fm.create_group("MyGroup", "Test")
        fm.add_server_to_group(sample_server_id, "MyGroup")
        fm.remove_server_from_group(sample_server_id, "MyGroup")
        assert sample_server_id not in fm.server_groups["MyGroup"].server_ids


@pytest.mark.unit
class TestFleetOverview:
    def test_overview_empty(self, fm):
        overview = fm.get_fleet_overview()
        assert overview["total_servers"] == 0

    def test_overview_with_servers(self, fm, sample_server_id):
        overview = fm.get_fleet_overview()
        assert overview["total_servers"] == 1
        assert overview["offline_servers"] == 1  # Not connected yet

    def test_overview_has_groups(self, fm):
        overview = fm.get_fleet_overview()
        assert "groups" in overview

    def test_overview_has_environments(self, fm, sample_server_id):
        overview = fm.get_fleet_overview()
        assert "environments" in overview
