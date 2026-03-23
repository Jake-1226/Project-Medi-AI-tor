"""
Tests for the health scoring system.
"""

import pytest
from datetime import datetime, timedelta
from core.health_scorer import HealthScorer, HealthLevel, SubsystemHealth


class TestHealthScorer:
    """Test cases for HealthScorer"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.scorer = HealthScorer()
    
    def test_thermal_health_perfect(self):
        """Test thermal health with perfect readings"""
        thermal_data = {
            "Temperatures": [
                {"Name": "Inlet Temp", "ReadingCelsius": 25.0},
                {"Name": "CPU1 Temp", "ReadingCelsius": 35.0},
                {"Name": "CPU2 Temp", "ReadingCelsius": 33.0}
            ],
            "Fans": [
                {"Name": "Fan1", "Reading": 6000},
                {"Name": "Fan2", "Reading": 6200}
            ]
        }
        
        result = self.scorer.calculate_thermal_health(thermal_data)
        
        assert result.name == "thermal"
        assert result.score >= 90
        assert result.status == HealthLevel.HEALTHY
        assert "0 critical" in result.summary.lower()
        assert "0 warning" in result.summary.lower()
    
    def test_thermal_health_warning(self):
        """Test thermal health with warning temperatures"""
        thermal_data = {
            "Temperatures": [
                {"Name": "Inlet Temp", "ReadingCelsius": 78.0},  # Above warning threshold
                {"Name": "CPU1 Temp", "ReadingCelsius": 75.0},
                {"Name": "CPU2 Temp", "ReadingCelsius": 73.0}
            ],
            "Fans": [
                {"Name": "Fan1", "Reading": 6000},
                {"Name": "Fan2", "Reading": 6200}
            ]
        }
        
        result = self.scorer.calculate_thermal_health(thermal_data)
        
        assert result.name == "thermal"
        assert result.score < 90
        assert result.status == HealthLevel.WARNING
        assert "warning" in result.summary.lower()
    
    def test_thermal_health_critical(self):
        """Test thermal health with critical temperatures"""
        thermal_data = {
            "Temperatures": [
                {"Name": "Inlet Temp", "ReadingCelsius": 88.0},  # Above critical threshold
                {"Name": "CPU1 Temp", "ReadingCelsius": 85.0},
                {"Name": "CPU2 Temp", "ReadingCelsius": 83.0}
            ],
            "Fans": [
                {"Name": "Fan1", "Reading": 6000},
                {"Name": "Fan2", "Reading": 6200}
            ]
        }
        
        result = self.scorer.calculate_thermal_health(thermal_data)
        
        assert result.name == "thermal"
        assert result.score < 50
        assert result.status == HealthLevel.CRITICAL
        assert "critical" in result.summary.lower()
    
    def test_power_health_perfect(self):
        """Test power health with perfect PSUs"""
        power_data = {
            "PowerSupplies": [
                {
                    "Name": "PSU1",
                    "Status": {"Health": "OK"},
                    "OutputWatts": 600,  # Higher output for better efficiency
                    "CapacityWatts": 750
                },
                {
                    "Name": "PSU2",
                    "Status": {"Health": "OK"},
                    "OutputWatts": 580,  # Higher output for better efficiency
                    "CapacityWatts": 750
                }
            ]
        }
        
        result = self.scorer.calculate_power_health(power_data)
        
        assert result.name == "power"
        assert result.score >= 80  # Allow for warning threshold
        assert result.status in [HealthLevel.HEALTHY, HealthLevel.WARNING]
    
    def test_power_health_degraded(self):
        """Test power health with degraded efficiency"""
        power_data = {
            "PowerSupplies": [
                {
                    "Name": "PSU1",
                    "Status": {"Health": "Warning"},
                    "OutputWatts": 600,  # Higher output for better efficiency
                    "CapacityWatts": 750
                },
                {
                    "Name": "PSU2",
                    "Status": {"Health": "OK"},
                    "OutputWatts": 580,  # Higher output for better efficiency
                    "CapacityWatts": 750
                }
            ]
        }
        
        result = self.scorer.calculate_power_health(power_data)
        
        assert result.name == "power"
        assert result.score < 90
        assert result.status == HealthLevel.WARNING
    
    def test_memory_health_perfect(self):
        """Test memory health with perfect DIMMs"""
        memory_data = {
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
                },
                {
                    "DeviceLocator": "DIMM_A2",
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
        
        result = self.scorer.calculate_memory_health(memory_data)
        
        assert result.name == "memory"
        assert result.score >= 90
        assert result.status == HealthLevel.HEALTHY
    
    def test_memory_health_with_errors(self):
        """Test memory health with ECC errors"""
        memory_data = {
            "Memory": [
                {
                    "DeviceLocator": "DIMM_A1",
                    "Status": {"Health": "OK"},
                    "CapacityMiB": 16384,
                    "Oem": {
                        "Dell": {
                            "DellMemory": {
                                "CorrectableEccErrors": 50,  # Above warning threshold
                                "UncorrectableEccErrors": 0
                            }
                        }
                    }
                },
                {
                    "DeviceLocator": "DIMM_A2",
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
        
        result = self.scorer.calculate_memory_health(memory_data)
        
        assert result.name == "memory"
        assert result.score < 90
        assert result.status == HealthLevel.WARNING
    
    def test_memory_health_critical_errors(self):
        """Test memory health with uncorrectable errors"""
        memory_data = {
            "Memory": [
                {
                    "DeviceLocator": "DIMM_A1",
                    "Status": {"Health": "Critical"},
                    "CapacityMiB": 16384,
                    "Oem": {
                        "Dell": {
                            "DellMemory": {
                                "CorrectableEccErrors": 10,
                                "UncorrectableEccErrors": 5  # Uncorrectable errors
                            }
                        }
                    }
                }
            ]
        }
        
        result = self.scorer.calculate_memory_health(memory_data)
        
        assert result.name == "memory"
        assert result.score < 30
        assert result.status == HealthLevel.CRITICAL
    
    def test_overall_health_calculation(self):
        """Test overall health calculation from multiple subsystems"""
        subsystem_data = {
            "thermal": {
                "Temperatures": [
                    {"Name": "Inlet Temp", "ReadingCelsius": 25.0},
                    {"Name": "CPU1 Temp", "ReadingCelsius": 35.0}
                ],
                "Fans": [
                    {"Name": "Fan1", "Reading": 6000}
                ]
            },
            "power": {
                "PowerSupplies": [
                    {
                        "Name": "PSU1",
                        "Status": {"Health": "OK"},
                        "OutputWatts": 650,  # Better efficiency
                        "CapacityWatts": 750
                    }
                ]
            },
            "memory": {
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
        }
        
        result = self.scorer.calculate_overall_health(subsystem_data)
        
        assert "overall_score" in result
        assert "overall_status" in result
        assert "subsystems" in result
        assert result["overall_score"] >= 70  # All subsystems healthy
        assert result["overall_status"] in ["HEALTHY", "WARNING"]
        assert len(result["subsystems"]) == 3
    
    def test_overall_health_with_issues(self):
        """Test overall health with some subsystem issues"""
        subsystem_data = {
            "thermal": {
                "Temperatures": [
                    {"Name": "Inlet Temp", "ReadingCelsius": 88.0},  # Critical
                ],
                "Fans": [
                    {"Name": "Fan1", "Reading": 6000}
                ]
            },
            "power": {
                "PowerSupplies": [
                    {
                        "Name": "PSU1",
                        "Status": {"Health": "OK"},
                        "OutputWatts": 300,
                        "CapacityWatts": 750
                    }
                ]
            },
            "memory": {
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
        }
        
        result = self.scorer.calculate_overall_health(subsystem_data)
        
        assert result["overall_score"] < 80
        assert result["overall_status"] in ["WARNING", "CRITICAL"]
        assert result["critical_count"] >= 1
    
    def test_no_data_handling(self):
        """Test handling of missing or empty data"""
        # Test with empty thermal data
        result = self.scorer.calculate_thermal_health({})
        assert result.name == "thermal"
        assert result.score == 50  # Default score for no data
        assert result.status == HealthLevel.WARNING
        
        # Test with empty power data
        result = self.scorer.calculate_power_health({})
        assert result.name == "power"
        assert result.score == 50
        assert result.status == HealthLevel.WARNING
        
        # Test with empty memory data
        result = self.scorer.calculate_memory_health({})
        assert result.name == "memory"
        assert result.score == 50
        assert result.status == HealthLevel.WARNING
    
    def test_fan_speed_anomalies(self):
        """Test detection of fan speed anomalies"""
        thermal_data = {
            "Temperatures": [
                {"Name": "Inlet Temp", "ReadingCelsius": 25.0}
            ],
            "Fans": [
                {"Name": "Fan1", "Reading": 200},  # Too low
                {"Name": "Fan2", "Reading": 30000}  # Too high
            ]
        }
        
        result = self.scorer.calculate_thermal_health(thermal_data)
        
        assert result.status == HealthLevel.CRITICAL
        assert "critical" in result.summary.lower()
        assert result.score < 50
