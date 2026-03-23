"""
Pytest configuration and fixtures for Medi-AI-tor tests.
"""

import pytest
import asyncio
import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_server_info():
    """Sample server information for testing"""
    return {
        "host": "100.71.148.195",
        "username": "root",
        "password": "calvin",
        "port": 443,
        "model": "PowerEdge R660",
        "service_tag": "ABC123",
        "hostname": "test-server"
    }


@pytest.fixture
def sample_thermal_data():
    """Sample thermal data for testing"""
    return {
        "Temperatures": [
            {"Name": "Inlet Temp", "ReadingCelsius": 25.0, "Status": {"Health": "OK"}},
            {"Name": "CPU1 Temp", "ReadingCelsius": 35.0, "Status": {"Health": "OK"}},
            {"Name": "CPU2 Temp", "ReadingCelsius": 33.0, "Status": {"Health": "OK"}},
            {"Name": "DIMM1 Temp", "ReadingCelsius": 30.0, "Status": {"Health": "OK"}},
            {"Name": "DIMM2 Temp", "ReadingCelsius": 31.0, "Status": {"Health": "OK"}}
        ],
        "Fans": [
            {"Name": "Fan1", "Reading": 6000, "Status": {"Health": "OK"}},
            {"Name": "Fan2", "Reading": 6200, "Status": {"Health": "OK"}},
            {"Name": "Fan3", "Reading": 5900, "Status": {"Health": "OK"}},
            {"Name": "Fan4", "Reading": 6100, "Status": {"Health": "OK"}}
        ]
    }


@pytest.fixture
def sample_power_data():
    """Sample power data for testing"""
    return {
        "PowerSupplies": [
            {
                "Name": "PSU1",
                "Status": {"Health": "OK", "State": "Enabled"},
                "OutputWatts": 300,
                "CapacityWatts": 750,
                "LineInputVoltage": 208,
                "PowerMetrics": {
                    "AverageConsumedPower": 300
                }
            },
            {
                "Name": "PSU2",
                "Status": {"Health": "OK", "State": "Enabled"},
                "OutputWatts": 280,
                "CapacityWatts": 750,
                "LineInputVoltage": 208,
                "PowerMetrics": {
                    "AverageConsumedPower": 280
                }
            }
        ],
        "PowerControl": [
            {
                "PowerConsumedWatts": 580,
                "PowerCapacityWatts": 1500,
                "PowerAvailableWatts": 920
            }
        ]
    }


@pytest.fixture
def sample_memory_data():
    """Sample memory data for testing"""
    return {
        "Memory": [
            {
                "DeviceLocator": "DIMM_A1",
                "Status": {"Health": "OK", "State": "Enabled"},
                "CapacityMiB": 16384,
                "OperatingSpeedMhz": 3200,
                "MemoryType": "DDR4",
                "Manufacturer": "Samsung",
                "PartNumber": "M393A4K40CB1-CRC",
                "SerialNumber": "12345678",
                "Oem": {
                    "Dell": {
                        "DellMemory": {
                            "CorrectableEccErrors": 0,
                            "UncorrectableEccErrors": 0
                        }
                    }
                }
            },
            {
                "DeviceLocator": "DIMM_A2",
                "Status": {"Health": "OK", "State": "Enabled"},
                "CapacityMiB": 16384,
                "OperatingSpeedMhz": 3200,
                "MemoryType": "DDR4",
                "Manufacturer": "Samsung",
                "PartNumber": "M393A4K40CB1-CRC",
                "SerialNumber": "87654321",
                "Oem": {
                    "Dell": {
                        "DellMemory": {
                            "CorrectableEccErrors": 0,
                            "UncorrectableEccErrors": 0
                        }
                    }
                }
            },
            {
                "DeviceLocator": "DIMM_B1",
                "Status": {"Health": "OK", "State": "Enabled"},
                "CapacityMiB": 16384,
                "OperatingSpeedMhz": 3200,
                "MemoryType": "DDR4",
                "Manufacturer": "Samsung",
                "PartNumber": "M393A4K40CB1-CRC",
                "SerialNumber": "11223344",
                "Oem": {
                    "Dell": {
                        "DellMemory": {
                            "CorrectableEccErrors": 5,
                            "UncorrectableEccErrors": 0
                        }
                    }
                }
            }
        ],
        "MemorySummary": {
            "TotalSystemMemoryGiB": 48,
            "Status": {"Health": "OK"}
        }
    }


@pytest.fixture
def sample_storage_data():
    """Sample storage data for testing"""
    return {
        "drives": [
            {
                "Name": "Disk.Bay.0:Enclosure.Internal.0-0:NVMe.Samsung.970.PRO.1TB",
                "Status": {"Health": "OK", "State": "Enabled"},
                "CapacityBytes": 1000204885504,
                "MediaType": "SSD",
                "Protocol": "NVMe",
                "Manufacturer": "Samsung",
                "Model": "970 PRO",
                "SerialNumber": "S466NB0K123456",
                "FailurePredicted": False
            },
            {
                "Name": "Disk.Bay.1:Enclosure.Internal.0-1:NVMe.Samsung.970.PRO.1TB",
                "Status": {"Health": "OK", "State": "Enabled"},
                "CapacityBytes": 1000204885504,
                "MediaType": "SSD",
                "Protocol": "NVMe",
                "Manufacturer": "Samsung",
                "Model": "970 PRO",
                "SerialNumber": "S466NB0K654321",
                "FailurePredicted": False
            }
        ],
        "StorageControllers": [
            {
                "Name": "PCIeRAID.Integrated.1-1",
                "Status": {"Health": "OK", "State": "Enabled"},
                "Model": "PERC H730P Mini",
                "FirmwareVersion": "25.5.5.0005"
            }
        ]
    }


@pytest.fixture
def sample_log_data():
    """Sample log data for testing"""
    return [
        {
            "MessageId": "SYS1001",
            "Severity": "Informational",
            "Message": "System power on",
            "Timestamp": "2024-01-15T10:00:00Z",
            "Component": "System"
        },
        {
            "MessageId": "TEMP2001",
            "Severity": "Warning",
            "Message": "Temperature sensor reading high",
            "Timestamp": "2024-01-15T10:05:00Z",
            "Component": "Thermal"
        },
        {
            "MessageId": "MEM3001",
            "Severity": "Critical",
            "Message": "Memory ECC error detected",
            "Timestamp": "2024-01-15T10:10:00Z",
            "Component": "Memory"
        },
        {
            "MessageId": "PSU4001",
            "Severity": "Warning",
            "Message": "Power supply efficiency degraded",
            "Timestamp": "2024-01-15T10:15:00Z",
            "Component": "Power"
        }
    ]


@pytest.fixture
def sample_firmware_data():
    """Sample firmware data for testing"""
    return {
        "firmware": [
            {
                "name": "BIOS",
                "version": "2.19.1",
                "update_available": True,
                "latest_version": "2.21.0",
                "critical": True
            },
            {
                "name": "iDRAC",
                "version": "7.00.60.00",
                "update_available": False,
                "latest_version": "7.00.60.00",
                "critical": False
            },
            {
                "name": "NIC",
                "version": "22.31.1.4",
                "update_available": True,
                "latest_version": "22.35.2.7",
                "critical": False
            },
            {
                "name": "RAID",
                "version": "52.28.3-4904",
                "update_available": True,
                "latest_version": "52.30.0-5168",
                "critical": True
            }
        ]
    }


@pytest.fixture
def mock_redfish_client():
    """Mock Redfish client for testing"""
    class MockRedfishClient:
        def __init__(self):
            self.connected = False
        
        async def connect(self):
            self.connected = True
            return True
        
        async def disconnect(self):
            self.connected = False
        
        async def get_temperature_sensors(self):
            return {
                "Temperatures": [
                    {"Name": "Inlet Temp", "ReadingCelsius": 25.0},
                    {"Name": "CPU1 Temp", "ReadingCelsius": 35.0}
                ],
                "Fans": [
                    {"Name": "Fan1", "Reading": 6000}
                ]
            }
        
        async def get_power_supplies(self):
            return {
                "PowerSupplies": [
                    {
                        "Name": "PSU1",
                        "Status": {"Health": "OK"},
                        "OutputWatts": 300,
                        "CapacityWatts": 750
                    }
                ]
            }
        
        async def get_memory(self):
            return {
                "Memory": [
                    {
                        "DeviceLocator": "DIMM_A1",
                        "Status": {"Health": "OK"},
                        "CapacityMiB": 16384,
                        "Oem": {
                            "Dell": {
                                "DellMemory": {
                                    "CorrectableEccErrors": 0,
                                    "UncorrectableEccErrors": 0
                                }
                            }
                        }
                    }
                ]
            }
    
    return MockRedfishClient()


# Test configuration
def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )


# Skip integration tests if no real server available
def pytest_collection_modifyitems(config, items):
    """Modify test collection to skip integration tests if needed"""
    skip_integration = not os.getenv("RUN_INTEGRATION_TESTS", "").lower() == "true"
    
    if skip_integration:
        skip_marker = pytest.mark.skip(reason="Integration tests disabled (set RUN_INTEGRATION_TESTS=true)")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_marker)
