"""
Cross-Server Fleet Correlation — Detect shared root causes across servers.

When investigating a problem on Server A, this engine automatically checks
if other servers in the same fleet/group show similar symptoms. If they do,
the root cause shifts from "server problem" to "shared infrastructure problem"
(e.g., datacenter cooling failure, PDU issue, network switch failure).

Patent relevance: "Method for cross-server symptom correlation in fleet
management, enabling automatic detection of shared infrastructure failures
by comparing real-time diagnostic data across multiple managed nodes."
"""

import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Set
from enum import Enum

logger = logging.getLogger(__name__)


class CorrelationScope(str, Enum):
    SINGLE_SERVER = "single_server"         # Problem is isolated to one server
    SERVER_GROUP = "server_group"           # Multiple servers in same group
    DATACENTER_WIDE = "datacenter_wide"    # Majority of servers affected
    INFRASTRUCTURE = "infrastructure"       # Shared infrastructure issue


@dataclass
class CorrelationSignal:
    """A signal indicating a potential cross-server correlation."""
    signal_type: str               # e.g., "thermal_spike", "power_anomaly"
    server_id: str
    server_name: str
    value: Any
    threshold: Any
    severity: str                  # warning, critical
    timestamp: str


@dataclass
class CorrelationResult:
    """Result of a cross-server correlation analysis."""
    scope: CorrelationScope
    affected_servers: List[str]
    total_servers_checked: int
    correlation_confidence: float    # 0.0 - 1.0
    shared_symptoms: List[str]
    likely_root_cause: str
    recommendation: str
    signals: List[CorrelationSignal] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> Dict:
        return {
            "scope": self.scope.value,
            "affected_servers": self.affected_servers,
            "total_servers_checked": self.total_servers_checked,
            "correlation_confidence": self.correlation_confidence,
            "shared_symptoms": self.shared_symptoms,
            "likely_root_cause": self.likely_root_cause,
            "recommendation": self.recommendation,
            "signals": [
                {
                    "type": s.signal_type, "server": s.server_name,
                    "value": s.value, "threshold": s.threshold,
                    "severity": s.severity, "timestamp": s.timestamp,
                }
                for s in self.signals
            ],
            "timestamp": self.timestamp,
        }


class FleetCorrelationEngine:
    """
    Analyzes symptoms across multiple servers to detect shared root causes.

    When a single server shows thermal anomalies:
      → Could be a fan failure (single server problem)
      → Could be a datacenter cooling failure (if neighbors show same symptoms)

    This engine checks fleet peers and escalates the diagnosis scope
    from single-server to infrastructure-wide when patterns match.
    """

    # Symptom checks mapped to what to look for in server health data
    SYMPTOM_CHECKS = {
        "thermal_spike": {
            "metrics": ["inlet_temp", "cpu_temp", "max_temp"],
            "threshold_key": "current_value",
            "warning_threshold": 75,
            "critical_threshold": 85,
            "infrastructure_cause": "Datacenter cooling failure or CRAC unit malfunction",
            "recommendation": "Check datacenter HVAC, CRAC units, and raised floor airflow. Compare with building management system data.",
        },
        "power_anomaly": {
            "metrics": ["power_consumption", "power_efficiency"],
            "threshold_key": "current_value",
            "warning_threshold": 0,  # Dynamic — checked by custom logic
            "critical_threshold": 0,
            "infrastructure_cause": "PDU overload, UPS issue, or utility power fluctuation",
            "recommendation": "Check PDU load balance, UPS status, and utility feed. Contact facilities team.",
        },
        "fan_anomaly": {
            "metrics": ["avg_fan_speed", "max_fan_speed"],
            "threshold_key": "current_value",
            "warning_threshold": 9000,
            "critical_threshold": 11000,
            "infrastructure_cause": "Ambient temperature rise causing fleet-wide fan ramp-up",
            "recommendation": "Check datacenter ambient temperature. All servers compensating suggests environmental cause.",
        },
    }

    # How many servers need to show same symptom for each scope level
    SCOPE_THRESHOLDS = {
        CorrelationScope.SERVER_GROUP: 0.30,    # 30% of group
        CorrelationScope.DATACENTER_WIDE: 0.60, # 60% of fleet
    }

    def __init__(self):
        self._recent_checks: Dict[str, Dict] = {}  # server_id → latest health data

    def update_server_health(self, server_id: str, server_name: str,
                             health_data: Dict[str, Any]):
        """Store the latest health snapshot for a server."""
        self._recent_checks[server_id] = {
            "server_name": server_name,
            "health_data": health_data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def correlate(self, trigger_server_id: str,
                  trigger_symptoms: List[str],
                  fleet_servers: Optional[Dict] = None) -> CorrelationResult:
        """
        Check if the trigger server's symptoms appear on other fleet servers.

        Args:
            trigger_server_id: The server being investigated
            trigger_symptoms: List of symptom types (e.g., ["thermal_spike"])
            fleet_servers: Optional dict of server_id → health_data to check

        Returns:
            CorrelationResult with scope, affected servers, and recommendation
        """
        now = datetime.now(timezone.utc).isoformat()
        servers_to_check = fleet_servers or self._recent_checks

        if len(servers_to_check) <= 1:
            return CorrelationResult(
                scope=CorrelationScope.SINGLE_SERVER,
                affected_servers=[trigger_server_id],
                total_servers_checked=1,
                correlation_confidence=0.0,
                shared_symptoms=[],
                likely_root_cause="Isolated server issue",
                recommendation="Investigate the individual server.",
                timestamp=now,
            )

        signals: List[CorrelationSignal] = []
        affected: Set[str] = {trigger_server_id}
        shared_symptoms: Set[str] = set()

        for symptom_type in trigger_symptoms:
            check = self.SYMPTOM_CHECKS.get(symptom_type)
            if not check:
                continue

            for sid, sdata in servers_to_check.items():
                if sid == trigger_server_id:
                    continue

                health = sdata.get("health_data", {}) if isinstance(sdata, dict) else {}
                sname = sdata.get("server_name", sid) if isinstance(sdata, dict) else sid
                metrics = health.get("metrics", health)

                for metric_name in check["metrics"]:
                    metric = metrics.get(metric_name, {})
                    if not isinstance(metric, dict):
                        continue
                    value = metric.get("current_value", metric.get("value"))
                    if value is None:
                        continue

                    severity = None
                    if check["critical_threshold"] > 0 and value >= check["critical_threshold"]:
                        severity = "critical"
                    elif check["warning_threshold"] > 0 and value >= check["warning_threshold"]:
                        severity = "warning"

                    if severity:
                        signals.append(CorrelationSignal(
                            signal_type=symptom_type,
                            server_id=sid,
                            server_name=sname,
                            value=value,
                            threshold=check["warning_threshold"],
                            severity=severity,
                            timestamp=now,
                        ))
                        affected.add(sid)
                        shared_symptoms.add(symptom_type)

        # Determine scope
        total = len(servers_to_check)
        affected_ratio = len(affected) / total if total > 0 else 0

        if affected_ratio >= self.SCOPE_THRESHOLDS[CorrelationScope.DATACENTER_WIDE]:
            scope = CorrelationScope.DATACENTER_WIDE
        elif affected_ratio >= self.SCOPE_THRESHOLDS[CorrelationScope.SERVER_GROUP]:
            scope = CorrelationScope.SERVER_GROUP
        elif len(affected) > 1:
            scope = CorrelationScope.SERVER_GROUP
        else:
            scope = CorrelationScope.SINGLE_SERVER

        # Build result
        if scope == CorrelationScope.SINGLE_SERVER:
            cause = "Isolated server issue — no similar symptoms on fleet peers"
            rec = "Investigate the individual server hardware."
            confidence = 0.0
        else:
            primary_symptom = list(shared_symptoms)[0] if shared_symptoms else trigger_symptoms[0]
            check = self.SYMPTOM_CHECKS.get(primary_symptom, {})
            cause = check.get("infrastructure_cause", "Shared infrastructure issue")
            rec = check.get("recommendation", "Check shared infrastructure.")
            confidence = min(affected_ratio * 1.2, 1.0)

        return CorrelationResult(
            scope=scope,
            affected_servers=list(affected),
            total_servers_checked=total,
            correlation_confidence=round(confidence, 2),
            shared_symptoms=list(shared_symptoms),
            likely_root_cause=cause,
            recommendation=rec,
            signals=signals,
            timestamp=now,
        )

    def get_fleet_symptom_summary(self) -> Dict[str, Any]:
        """Get a summary of current symptoms across the fleet."""
        summary = {
            "total_servers": len(self._recent_checks),
            "servers_with_anomalies": 0,
            "symptom_distribution": {},
        }

        for sid, sdata in self._recent_checks.items():
            health = sdata.get("health_data", {})
            metrics = health.get("metrics", health)
            has_anomaly = False

            for symptom_type, check in self.SYMPTOM_CHECKS.items():
                for metric_name in check["metrics"]:
                    metric = metrics.get(metric_name, {})
                    value = metric.get("current_value") if isinstance(metric, dict) else None
                    if value and check["warning_threshold"] > 0 and value >= check["warning_threshold"]:
                        has_anomaly = True
                        summary["symptom_distribution"].setdefault(symptom_type, 0)
                        summary["symptom_distribution"][symptom_type] += 1

            if has_anomaly:
                summary["servers_with_anomalies"] += 1

        return summary
