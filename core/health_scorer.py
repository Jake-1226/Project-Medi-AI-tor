"""
Real-time health scoring algorithm for Dell PowerEdge servers.
Calculates overall health score (0-100) based on multiple subsystem metrics.
"""

from typing import Dict, List, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import math

class HealthLevel(Enum):
    CRITICAL = 0
    WARNING = 1
    INFO = 2
    HEALTHY = 3

@dataclass
class HealthMetric:
    """Individual health metric with weight and score"""
    name: str
    value: float
    status: HealthLevel
    weight: float
    details: str
    threshold: Tuple[float, float]  # (warning, critical)

@dataclass
class SubsystemHealth:
    """Health status for a subsystem"""
    name: str
    score: float
    status: HealthLevel
    metrics: List[HealthMetric]
    summary: str

class HealthScorer:
    """Calculates comprehensive health scores for server subsystems"""
    
    def __init__(self):
        # Subsystem weights (must sum to 1.0)
        self.subsystem_weights = {
            "thermal": 0.25,      # Temperature and cooling
            "power": 0.20,        # Power supplies and voltage
            "memory": 0.20,       # DIMMs and ECC errors
            "storage": 0.15,      # Drives and RAID
            "network": 0.10,      # NICs and connectivity
            "firmware": 0.10      # Firmware versions
        }
        
        # Thresholds for different metrics
        self.thresholds = {
            "temperature": {
                "warning": 70.0,   # °C
                "critical": 85.0
            },
            "fan_speed": {
                "warning_low": 1000,   # RPM
                "warning_high": 20000,
                "critical_low": 500,
                "critical_high": 25000
            },
            "power_efficiency": {
                "warning": 0.80,    # Efficiency ratio
                "critical": 0.70
            },
            "memory_ecc": {
                "warning": 10,      # Correctable errors per hour
                "critical": 100
            },
            "storage_health": {
                "warning": 0.90,    # Remaining life percentage
                "critical": 0.80
            },
            "network_errors": {
                "warning": 0.01,    # Error rate
                "critical": 0.05
            },
            "firmware_age": {
                "warning": 365,     # Days since latest
                "critical": 730
            }
        }
    
    def calculate_thermal_health(self, thermal_data: Dict) -> SubsystemHealth:
        """Calculate thermal subsystem health"""
        metrics = []
        
        # Temperature sensors
        temps = thermal_data.get("Temperatures", [])
        if temps:
            temp_scores = []
            for sensor in temps:
                temp_c = sensor.get("ReadingCelsius", 0)
                status = HealthLevel.HEALTHY
                
                if temp_c >= self.thresholds["temperature"]["critical"]:
                    status = HealthLevel.CRITICAL
                elif temp_c >= self.thresholds["temperature"]["warning"]:
                    status = HealthLevel.WARNING
                
                # Score based on distance from thresholds
                if status == HealthLevel.CRITICAL:
                    score = max(0, 40 - (temp_c - self.thresholds["temperature"]["critical"]))
                elif status == HealthLevel.WARNING:
                    score = max(40, 70 - (temp_c - self.thresholds["temperature"]["warning"]))
                else:
                    score = min(100, 100 - (temp_c / self.thresholds["temperature"]["warning"]) * 30)
                
                temp_scores.append(score)
                metrics.append(HealthMetric(
                    name=f"Temp_{sensor.get('Name', 'Unknown')}",
                    value=temp_c,
                    status=status,
                    weight=1.0 / len(temps),
                    details=f"{temp_c}°C at {sensor.get('Name', 'Unknown')}",
                    threshold=(self.thresholds["temperature"]["warning"], self.thresholds["temperature"]["critical"])
                ))
            
            avg_temp_score = sum(temp_scores) / len(temp_scores) if temp_scores else 100
        else:
            avg_temp_score = 50  # No data available
            metrics.append(HealthMetric(
                name="Temperature_Data",
                value=0,
                status=HealthLevel.WARNING,
                weight=1.0,
                details="No temperature data available",
                threshold=(0, 0)
            ))
        
        # Fan speeds
        fans = thermal_data.get("Fans", [])
        if fans:
            fan_scores = []
            for fan in fans:
                rpm = fan.get("Reading", 0)
                status = HealthLevel.HEALTHY
                
                thresholds = self.thresholds["fan_speed"]
                if rpm <= thresholds["critical_low"] or rpm >= thresholds["critical_high"]:
                    status = HealthLevel.CRITICAL
                elif rpm <= thresholds["warning_low"] or rpm >= thresholds["warning_high"]:
                    status = HealthLevel.WARNING
                
                # Score based on RPM range
                if status == HealthLevel.CRITICAL:
                    score = 20  # Lower score for critical fan issues
                elif status == HealthLevel.WARNING:
                    score = 50  # Lower score for fan warnings
                else:
                    score = 100
                
                fan_scores.append(score)
                metrics.append(HealthMetric(
                    name=f"Fan_{fan.get('Name', 'Unknown')}",
                    value=rpm,
                    status=status,
                    weight=1.0 / len(fans),
                    details=f"{rpm} RPM at {fan.get('Name', 'Unknown')}",
                    threshold=(thresholds["warning_low"], thresholds["critical_low"])
                ))
            
            avg_fan_score = sum(fan_scores) / len(fan_scores) if fan_scores else 100
        else:
            avg_fan_score = 50
            metrics.append(HealthMetric(
                name="Fan_Data",
                value=0,
                status=HealthLevel.WARNING,
                weight=1.0,
                details="No fan data available",
                threshold=(0, 0)
            ))
        
        # Combine temperature and fan scores
        overall_score = (avg_temp_score + avg_fan_score) / 2
        
        # Determine overall status
        critical_count = sum(1 for m in metrics if m.status == HealthLevel.CRITICAL)
        warning_count = sum(1 for m in metrics if m.status == HealthLevel.WARNING)
        
        # Adjust score based on critical/warning counts
        if critical_count > 0:
            overall_score = min(overall_score, 40)  # Cap at 40 for critical issues
        elif warning_count > 0:
            overall_score = min(overall_score, 70)  # Cap at 70 for warning issues
        
        if critical_count > 0:
            status = HealthLevel.CRITICAL
        elif warning_count > 0:
            status = HealthLevel.WARNING
        else:
            status = HealthLevel.HEALTHY
        
        summary = f"Thermal health: {critical_count} critical, {warning_count} warning issues"
        
        return SubsystemHealth(
            name="thermal",
            score=overall_score,
            status=status,
            metrics=metrics,
            summary=summary
        )
    
    def calculate_power_health(self, power_data: Dict) -> SubsystemHealth:
        """Calculate power subsystem health"""
        metrics = []
        
        psus = power_data.get("PowerSupplies", [])
        if psus:
            psu_scores = []
            for psu in psus:
                status = HealthLevel.HEALTHY
                score = 100
                
                # Check PSU status
                psu_status = psu.get("Status", {}).get("Health", "OK")
                if psu_status == "Critical":
                    status = HealthLevel.CRITICAL
                    score = 20
                elif psu_status in ["Warning", "Degraded"]:
                    status = HealthLevel.WARNING
                    score = 60
                
                # Check power output efficiency
                output_watts = psu.get("OutputWatts", 0)
                capacity_watts = psu.get("CapacityWatts", 1)
                efficiency = output_watts / capacity_watts if capacity_watts > 0 else 0
                
                if efficiency < self.thresholds["power_efficiency"]["critical"]:
                    if status.value > HealthLevel.CRITICAL.value:
                        status = HealthLevel.CRITICAL
                    score = min(score, 30)
                elif efficiency < self.thresholds["power_efficiency"]["warning"]:
                    if status.value > HealthLevel.WARNING.value:
                        status = HealthLevel.WARNING
                    score = min(score, 70)
                
                psu_scores.append(score)
                metrics.append(HealthMetric(
                    name=f"PSU_{psu.get('Name', 'Unknown')}",
                    value=efficiency * 100,
                    status=status,
                    weight=1.0 / len(psus),
                    details=f"{psu_status}, {output_watts}/{capacity_watts}W ({efficiency:.1%})",
                    threshold=(self.thresholds["power_efficiency"]["warning"], self.thresholds["power_efficiency"]["critical"])
                ))
            
            overall_score = sum(psu_scores) / len(psu_scores) if psu_scores else 100
        else:
            overall_score = 50
            metrics.append(HealthMetric(
                name="Power_Data",
                value=0,
                status=HealthLevel.WARNING,
                weight=1.0,
                details="No power supply data available",
                threshold=(0, 0)
            ))
        
        # Determine status
        critical_count = sum(1 for m in metrics if m.status == HealthLevel.CRITICAL)
        warning_count = sum(1 for m in metrics if m.status == HealthLevel.WARNING)
        
        if critical_count > 0:
            status = HealthLevel.CRITICAL
        elif warning_count > 0:
            status = HealthLevel.WARNING
        else:
            status = HealthLevel.HEALTHY
        
        summary = f"Power: {critical_count} critical, {warning_count} warning issues"
        
        return SubsystemHealth(
            name="power",
            score=overall_score,
            status=status,
            metrics=metrics,
            summary=summary
        )
    
    def calculate_memory_health(self, memory_data: Dict) -> SubsystemHealth:
        """Calculate memory subsystem health"""
        metrics = []
        
        dimms = memory_data.get("Memory", [])
        if dimms:
            dimm_scores = []
            for dimm in dimms:
                status = HealthLevel.HEALTHY
                score = 100
                
                # Check DIMM status
                dimm_status = dimm.get("Status", {}).get("Health", "OK")
                if dimm_status == "Critical":
                    status = HealthLevel.CRITICAL
                    score = 20
                elif dimm_status in ["Warning", "Degraded"]:
                    status = HealthLevel.WARNING
                    score = 60
                
                # Check for ECC errors
                ecc_data = dimm.get("Oem", {}).get("Dell", {}).get("DellMemory", {})
                correctable_errors = ecc_data.get("CorrectableEccErrors", 0)
                uncorrectable_errors = ecc_data.get("UncorrectableEccErrors", 0)
                
                if uncorrectable_errors > 0:
                    if status.value > HealthLevel.CRITICAL.value:
                        status = HealthLevel.CRITICAL
                    score = 10
                elif correctable_errors >= self.thresholds["memory_ecc"]["critical"]:
                    if status.value > HealthLevel.CRITICAL.value:
                        status = HealthLevel.CRITICAL
                    score = 30
                elif correctable_errors >= self.thresholds["memory_ecc"]["warning"]:
                    if status.value > HealthLevel.WARNING.value:
                        status = HealthLevel.WARNING
                    score = 70
                
                dimm_scores.append(score)
                error_info = f"CE: {correctable_errors}, UE: {uncorrectable_errors}" if (correctable_errors or uncorrectable_errors) else "No errors"
                metrics.append(HealthMetric(
                    name=f"DIMM_{dimm.get('DeviceLocator', 'Unknown')}",
                    value=correctable_errors,
                    status=status,
                    weight=1.0 / len(dimms),
                    details=f"{dimm_status}, {error_info}, {dimm.get('CapacityMiB', 0)}MB",
                    threshold=(self.thresholds["memory_ecc"]["warning"], self.thresholds["memory_ecc"]["critical"])
                ))
            
            overall_score = sum(dimm_scores) / len(dimm_scores) if dimm_scores else 100
        else:
            overall_score = 50
            metrics.append(HealthMetric(
                name="Memory_Data",
                value=0,
                status=HealthLevel.WARNING,
                weight=1.0,
                details="No memory data available",
                threshold=(0, 0)
            ))
        
        # Determine status
        critical_count = sum(1 for m in metrics if m.status == HealthLevel.CRITICAL)
        warning_count = sum(1 for m in metrics if m.status == HealthLevel.WARNING)
        
        if critical_count > 0:
            status = HealthLevel.CRITICAL
        elif warning_count > 0:
            status = HealthLevel.WARNING
        else:
            status = HealthLevel.HEALTHY
        
        summary = f"Memory: {critical_count} critical, {warning_count} warning issues"
        
        return SubsystemHealth(
            name="memory",
            score=overall_score,
            status=status,
            metrics=metrics,
            summary=summary
        )
    
    def calculate_overall_health(self, subsystem_data: Dict[str, Dict]) -> Dict[str, Any]:
        """Calculate overall server health score from all subsystems"""
        subsystem_healths = {}
        
        # Calculate each subsystem
        if "thermal" in subsystem_data:
            subsystem_healths["thermal"] = self.calculate_thermal_health(subsystem_data["thermal"])
        
        if "power" in subsystem_data:
            subsystem_healths["power"] = self.calculate_power_health(subsystem_data["power"])
        
        if "memory" in subsystem_data:
            subsystem_healths["memory"] = self.calculate_memory_health(subsystem_data["memory"])
        
        # Storage and network would be implemented similarly
        
        # Calculate weighted overall score
        overall_score = 0
        total_weight = 0
        
        for subsystem_name, health in subsystem_healths.items():
            weight = self.subsystem_weights.get(subsystem_name, 0)
            overall_score += health.score * weight
            total_weight += weight
        
        if total_weight > 0:
            overall_score /= total_weight
        else:
            overall_score = 50  # No data available
        
        # Determine overall status
        critical_subsystems = sum(1 for h in subsystem_healths.values() if h.status == HealthLevel.CRITICAL)
        warning_subsystems = sum(1 for h in subsystem_healths.values() if h.status == HealthLevel.WARNING)
        
        if critical_subsystems > 0:
            overall_status = HealthLevel.CRITICAL
        elif warning_subsystems > 0:
            overall_status = HealthLevel.WARNING
        else:
            overall_status = HealthLevel.HEALTHY
        
        return {
            "overall_score": round(overall_score, 1),
            "overall_status": overall_status.name,
            "subsystems": subsystem_healths,
            "critical_count": critical_subsystems,
            "warning_count": warning_subsystems,
            "healthy_count": len(subsystem_healths) - critical_subsystems - warning_subsystems,
            "summary": f"Server Health: {overall_status.name} - {critical_subsystems} critical, {warning_subsystems} warning issues"
        }

# Global health scorer instance
health_scorer = HealthScorer()
