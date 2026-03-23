"""
Predictive Maintenance Engine for Dell Server AI Agent
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import statistics
from collections import defaultdict, deque

from models.server_models import ComponentType, Severity, LogEntry
from ai.predictive_analytics import PredictiveAnalytics, PredictionResult

logger = logging.getLogger(__name__)

class MaintenancePriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    EMERGENCY = "emergency"

class MaintenanceType(str, Enum):
    PREVENTIVE = "preventive"
    CORRECTIVE = "corrective"
    PREDICTIVE = "predictive"
    EMERGENCY = "emergency"

@dataclass
class MaintenanceRecommendation:
    """Maintenance recommendation with details"""
    component: str
    component_type: ComponentType
    maintenance_type: MaintenanceType
    priority: MaintenancePriority
    estimated_downtime: str  # in hours
    cost_estimate: Optional[str]
    parts_required: List[str]
    tools_required: List[str]
    skills_required: List[str]
    description: str
    steps: List[str]
    risk_factors: List[str]
    confidence_score: float
    recommended_date: Optional[datetime]
    created_at: datetime

@dataclass
class MaintenanceSchedule:
    """Scheduled maintenance activity"""
    id: str
    recommendation: MaintenanceRecommendation
    scheduled_date: datetime
    estimated_duration: int  # in hours
    assigned_to: Optional[str] = None
    status: str = "scheduled"  # scheduled, in_progress, completed, cancelled
    created_at: datetime = None
    completed_at: Optional[datetime] = None

class PredictiveMaintenance:
    """Predictive maintenance engine for Dell servers"""
    
    def __init__(self, predictive_analytics: PredictiveAnalytics):
        self.predictive_analytics = predictive_analytics
        self.maintenance_history: List[MaintenanceSchedule] = []
        self.component_lifecycles: Dict[str, Dict] = {}
        self.failure_patterns: Dict[str, List[Dict]] = defaultdict(list)
        
        # Maintenance thresholds and intervals
        self.maintenance_intervals = {
            ComponentType.POWER: {"preventive": 12, "predictive": 6},  # months
            ComponentType.FIRMWARE: {"preventive": 6, "predictive": 3},
            ComponentType.MEMORY: {"preventive": 24, "predictive": 12},
            ComponentType.PROCESSOR: {"preventive": 36, "predictive": 18},
            ComponentType.STORAGE: {"preventive": 18, "predictive": 9},
            ComponentType.THERMAL: {"preventive": 6, "predictive": 3},
            ComponentType.NETWORK: {"preventive": 12, "predictive": 6}
        }
        
        # Component failure rates (per 1000 hours)
        self.component_failure_rates = {
            ComponentType.POWER: 0.5,
            ComponentType.MEMORY: 0.3,
            ComponentType.PROCESSOR: 0.1,
            ComponentType.STORAGE: 1.2,
            ComponentType.FIRMWARE: 0.8,
            ComponentType.THERMAL: 0.4,
            ComponentType.NETWORK: 0.2
        }
    
    async def generate_maintenance_recommendations(self, server_id: str, 
                                                  server_info: Dict[str, Any],
                                                  logs: List[LogEntry]) -> List[MaintenanceRecommendation]:
        """Generate comprehensive maintenance recommendations"""
        recommendations = []
        
        # Get predictive analytics results
        predictions = self.predictive_analytics.predict_hardware_failure(server_id)
        maintenance_needs = self.predictive_analytics.predict_maintenance_needs(server_id)
        
        # Generate recommendations based on predictions
        for prediction in predictions + maintenance_needs:
            rec = await self._create_maintenance_recommendation(
                prediction, server_info, logs
            )
            if rec:
                recommendations.append(rec)
        
        # Generate age-based recommendations
        age_recommendations = await self._generate_age_based_recommendations(server_id, server_info)
        recommendations.extend(age_recommendations)
        
        # Generate usage-based recommendations
        usage_recommendations = await self._generate_usage_based_recommendations(server_id, server_info)
        recommendations.extend(usage_recommendations)
        
        # Generate log-based recommendations
        log_recommendations = await self._generate_log_based_recommendations(server_id, logs)
        recommendations.extend(log_recommendations)
        
        # Sort by priority and confidence
        recommendations.sort(key=lambda x: (
            self._priority_score(x.priority),
            x.confidence_score
        ), reverse=True)
        
        return recommendations
    
    async def _create_maintenance_recommendation(self, prediction: PredictionResult,
                                              server_info: Dict[str, Any],
                                              logs: List[LogEntry]) -> Optional[MaintenanceRecommendation]:
        """Create maintenance recommendation from prediction"""
        
        # Map prediction types to maintenance recommendations
        maintenance_mapping = {
            "temperature_failure": self._create_temperature_maintenance,
            "power_overconsumption": self._create_power_maintenance,
            "power_fluctuation": self._create_power_maintenance,
            "cpu_degradation": self._create_cpu_maintenance,
            "memory_degradation": self._create_memory_maintenance,
            "increasing_errors": self._create_system_maintenance,
            "critical_error_rate": self._create_emergency_maintenance,
            "preventive_maintenance": self._create_general_maintenance
        }
        
        creator_func = maintenance_mapping.get(prediction.prediction_type)
        if creator_func:
            return await creator_func(prediction, server_info, logs)
        
        return None
    
    async def _create_temperature_maintenance(self, prediction: PredictionResult,
                                           server_info: Dict[str, Any],
                                           logs: List[LogEntry]) -> MaintenanceRecommendation:
        """Create temperature-related maintenance recommendation"""
        
        return MaintenanceRecommendation(
            component="Cooling System",
            component_type=ComponentType.THERMAL,
            maintenance_type=MaintenanceType.PREDICTIVE,
            priority=self._map_risk_to_priority(prediction.risk_level),
            estimated_downtime="2-4",
            cost_estimate="$200-500",
            parts_required=["Thermal paste", "Cooling fans", "Air filters"],
            tools_required=["Screwdrivers", "Thermal paste applicator", "Compressed air"],
            skills_required=["Hardware maintenance", "Thermal management"],
            description=prediction.description,
            steps=[
                "Power down server and disconnect power",
                "Remove server cover and inspect internal components",
                "Clean dust from fans, heat sinks, and air vents",
                "Check fan operation and replace if necessary",
                "Apply new thermal paste to CPU heat sinks",
                "Verify airflow patterns and cable management",
                "Monitor temperatures after restart"
            ],
            risk_factors=[
                "Overheating can cause permanent CPU damage",
                "Thermal shutdown may impact business operations",
                "Cooling failure may cascade to other components"
            ],
            confidence_score=prediction.confidence,
            recommended_date=datetime.now() + timedelta(days=7),
            created_at=datetime.now()
        )
    
    async def _create_power_maintenance(self, prediction: PredictionResult,
                                      server_info: Dict[str, Any],
                                      logs: List[LogEntry]) -> MaintenanceRecommendation:
        """Create power-related maintenance recommendation"""
        
        return MaintenanceRecommendation(
            component="Power Supply System",
            component_type=ComponentType.POWER,
            maintenance_type=MaintenanceType.PREDICTIVE,
            priority=self._map_risk_to_priority(prediction.risk_level),
            estimated_downtime="1-2",
            cost_estimate="$300-800",
            parts_required=["Power supply unit", "Power cables", "UPS batteries"],
            tools_required=["Power tester", "Multimeter", "Screwdrivers"],
            skills_required=["Electrical safety", "Power system maintenance"],
            description=prediction.description,
            steps=[
                "Verify power redundancy and UPS functionality",
                "Test power supply output voltages",
                "Check power supply cooling fans",
                "Inspect power cables and connections",
                "Replace faulty power supply if needed",
                "Test system after power supply replacement",
                "Update power management settings"
            ],
            risk_factors=[
                "Power failure can cause complete system outage",
                "Power fluctuations may damage other components",
                "UPS failure eliminates redundancy"
            ],
            confidence_score=prediction.confidence,
            recommended_date=datetime.now() + timedelta(days=3),
            created_at=datetime.now()
        )
    
    async def _create_cpu_maintenance(self, prediction: PredictionResult,
                                    server_info: Dict[str, Any],
                                    logs: List[LogEntry]) -> MaintenanceRecommendation:
        """Create CPU-related maintenance recommendation"""
        
        return MaintenanceRecommendation(
            component="CPU System",
            component_type=ComponentType.PROCESSOR,
            maintenance_type=MaintenanceType.PREDICTIVE,
            priority=self._map_risk_to_priority(prediction.risk_level),
            estimated_downtime="2-3",
            cost_estimate="$500-1500",
            parts_required=["CPU", "Thermal paste", "Cooling solution"],
            tools_required=["CPU socket tool", "Thermal paste applicator"],
            skills_required=["CPU replacement", "Thermal management"],
            description=prediction.description,
            steps=[
                "Backup critical data and configurations",
                "Analyze CPU performance and utilization patterns",
                "Check for CPU-intensive processes",
                "Verify CPU cooling and thermal paste condition",
                "Consider CPU upgrade if performance is insufficient",
                "Replace CPU if degradation is confirmed",
                "Update BIOS and firmware after replacement"
            ],
            risk_factors=[
                "CPU failure requires complete system downtime",
                "Performance degradation impacts all applications",
                "CPU replacement may require OS reactivation"
            ],
            confidence_score=prediction.confidence,
            recommended_date=datetime.now() + timedelta(days=14),
            created_at=datetime.now()
        )
    
    async def _create_memory_maintenance(self, prediction: PredictionResult,
                                      server_info: Dict[str, Any],
                                      logs: List[LogEntry]) -> MaintenanceRecommendation:
        """Create memory-related maintenance recommendation"""
        
        return MaintenanceRecommendation(
            component="Memory System",
            component_type=ComponentType.MEMORY,
            maintenance_type=MaintenanceType.PREDICTIVE,
            priority=self._map_risk_to_priority(prediction.risk_level),
            estimated_downtime="1-2",
            cost_estimate="$200-800",
            parts_required=["Memory modules", "Memory cleaners"],
            tools_required=["Memory module extractors", "Anti-static wrist strap"],
            skills_required=["Memory installation", "ESD safety"],
            description=prediction.description,
            steps=[
                "Run comprehensive memory diagnostics",
                "Identify failing memory modules",
                "Check memory compatibility and configuration",
                "Clean memory contacts and slots",
                "Replace faulty memory modules",
                "Verify memory configuration after replacement",
                "Update system BIOS memory settings"
            ],
            risk_factors=[
                "Memory errors can cause system crashes",
                "ECC failures may indicate multiple module issues",
                "Memory mixing can cause compatibility problems"
            ],
            confidence_score=prediction.confidence,
            recommended_date=datetime.now() + timedelta(days=7),
            created_at=datetime.now()
        )
    
    async def _create_system_maintenance(self, prediction: PredictionResult,
                                      server_info: Dict[str, Any],
                                      logs: List[LogEntry]) -> MaintenanceRecommendation:
        """Create general system maintenance recommendation"""
        
        return MaintenanceRecommendation(
            component="System Components",
            component_type=ComponentType.SYSTEM,
            maintenance_type=MaintenanceType.PREDICTIVE,
            priority=self._map_risk_to_priority(prediction.risk_level),
            estimated_downtime="4-6",
            cost_estimate="$400-1200",
            parts_required=["Various replacement parts"],
            tools_required=["Server tool kit", "Diagnostic software"],
            skills_required=["System diagnostics", "Hardware maintenance"],
            description=prediction.description,
            steps=[
                "Perform comprehensive system diagnostics",
                "Review system logs for error patterns",
                "Check all hardware component health",
                "Update firmware and drivers",
                "Clean internal components and connectors",
                "Verify system cooling and airflow",
                "Document all maintenance activities"
            ],
            risk_factors=[
                "Multiple component failures may be related",
                "System downtime affects all services",
                "Complex troubleshooting may require extended downtime"
            ],
            confidence_score=prediction.confidence,
            recommended_date=datetime.now() + timedelta(days=10),
            created_at=datetime.now()
        )
    
    async def _create_emergency_maintenance(self, prediction: PredictionResult,
                                         server_info: Dict[str, Any],
                                         logs: List[LogEntry]) -> MaintenanceRecommendation:
        """Create emergency maintenance recommendation"""
        
        return MaintenanceRecommendation(
            component="Critical System Components",
            component_type=ComponentType.SYSTEM,
            maintenance_type=MaintenanceType.EMERGENCY,
            priority=MaintenancePriority.EMERGENCY,
            estimated_downtime="2-8",
            cost_estimate="$800-3000",
            parts_required=["Emergency replacement parts"],
            tools_required=["Emergency repair kit", "Diagnostic tools"],
            skills_required=["Emergency repair", "System recovery"],
            description=prediction.description,
            steps=[
                "IMMEDIATELY assess system stability",
                "Identify and isolate failing components",
                "Implement emergency workarounds if possible",
                "Schedule emergency maintenance window",
                "Replace critical failing components",
                "Verify system stability after repairs",
                "Monitor system closely for 24-48 hours"
            ],
            risk_factors=[
                "IMMEDIATE risk of system failure",
                "Potential data loss or corruption",
                "Extended downtime may be required"
            ],
            confidence_score=prediction.confidence,
            recommended_date=datetime.now(),  # Immediate
            created_at=datetime.now()
        )
    
    async def _create_general_maintenance(self, prediction: PredictionResult,
                                        server_info: Dict[str, Any],
                                        logs: List[LogEntry]) -> MaintenanceRecommendation:
        """Create general preventive maintenance recommendation"""
        
        return MaintenanceRecommendation(
            component="System Preventive Maintenance",
            component_type=ComponentType.SYSTEM,
            maintenance_type=MaintenanceType.PREVENTIVE,
            priority=MaintenancePriority.MEDIUM,
            estimated_downtime="2-4",
            cost_estimate="$300-800",
            parts_required=["Cleaning supplies", "Replacement filters"],
            tools_required=["Cleaning tools", "Diagnostic software"],
            skills_required=["Preventive maintenance", "System monitoring"],
            description=prediction.description,
            steps=[
                "Schedule preventive maintenance window",
                "Perform comprehensive system cleaning",
                "Check and update all firmware",
                "Verify backup and recovery systems",
                "Test redundant systems and failover",
                "Document system configuration and performance",
                "Create maintenance report and recommendations"
            ],
            risk_factors=[
                "Preventive maintenance reduces failure risk",
                "Scheduled downtime may impact operations",
                "Component aging may require future upgrades"
            ],
            confidence_score=prediction.confidence,
            recommended_date=datetime.now() + timedelta(days=30),
            created_at=datetime.now()
        )
    
    async def _generate_age_based_recommendations(self, server_id: str,
                                                server_info: Dict[str, Any]) -> List[MaintenanceRecommendation]:
        """Generate recommendations based on system age"""
        recommendations = []
        
        # Calculate system age (simplified - in production use actual deployment date)
        system_age_months = 36  # Assume 3 years for demo
        
        for component_type, intervals in self.maintenance_intervals.items():
            preventive_interval = intervals["preventive"]
            
            if system_age_months >= preventive_interval:
                priority = MaintenancePriority.HIGH if system_age_months > preventive_interval * 1.5 else MaintenancePriority.MEDIUM
                
                recommendation = MaintenanceRecommendation(
                    component=f"{component_type.value.title()} System",
                    component_type=component_type,
                    maintenance_type=MaintenanceType.PREVENTIVE,
                    priority=priority,
                    estimated_downtime="2-4",
                    cost_estimate="$200-600",
                    parts_required=[f"{component_type.value} replacement parts"],
                    tools_required=["Standard tool kit"],
                    skills_required=[f"{component_type.value} maintenance"],
                    description=f"System age ({system_age_months} months) exceeds recommended preventive maintenance interval ({preventive_interval} months)",
                    steps=[
                        f"Inspect {component_type.value} components for wear",
                        f"Check {component_type.value} performance metrics",
                        f"Update {component_type.value} firmware if available",
                        f"Plan for {component_type.value} replacement if needed"
                    ],
                    risk_factors=[
                        f"Aging {component_type.value} components have higher failure rates",
                        "Preventive maintenance extends component lifecycle"
                    ],
                    confidence_score=0.7,
                    recommended_date=datetime.now() + timedelta(days=14),
                    created_at=datetime.now()
                )
                
                recommendations.append(recommendation)
        
        return recommendations
    
    async def _generate_usage_based_recommendations(self, server_id: str,
                                                 server_info: Dict[str, Any]) -> List[MaintenanceRecommendation]:
        """Generate recommendations based on usage patterns"""
        recommendations = []
        
        # This would analyze actual usage metrics
        # For demo, assume high usage scenarios
        
        high_usage_components = [
            (ComponentType.PROCESSOR, "High CPU utilization detected"),
            (ComponentType.MEMORY, "High memory usage patterns"),
            (ComponentType.STORAGE, "High I/O activity")
        ]
        
        for component_type, description in high_usage_components:
            recommendation = MaintenanceRecommendation(
                component=f"{component_type.value.title()} System",
                component_type=component_type,
                maintenance_type=MaintenanceType.PREDICTIVE,
                priority=MaintenancePriority.MEDIUM,
                estimated_downtime="1-3",
                cost_estimate="$300-900",
                parts_required=[f"Enhanced {component_type.value} components"],
                tools_required=["Performance analysis tools"],
                skills_required=["Performance optimization", "Capacity planning"],
                description=description,
                steps=[
                    f"Analyze {component_type.value} usage patterns",
                    f"Check for {component_type.value} bottlenecks",
                    f"Consider {component_type.value} upgrade or optimization",
                    f"Monitor performance after maintenance"
                ],
                risk_factors=[
                    "High usage may accelerate component wear",
                    "Performance issues may impact user experience"
                ],
                confidence_score=0.6,
                recommended_date=datetime.now() + timedelta(days=21),
                created_at=datetime.now()
            )
            
            recommendations.append(recommendation)
        
        return recommendations
    
    async def _generate_log_based_recommendations(self, server_id: str,
                                                 logs: List[LogEntry]) -> List[MaintenanceRecommendation]:
        """Generate recommendations based on log analysis"""
        recommendations = []
        
        # Analyze recent logs for patterns
        recent_logs = [log for log in logs if datetime.now() - log.timestamp <= timedelta(days=7)]
        
        # Count errors by component
        component_errors = defaultdict(int)
        for log in recent_logs:
            if log.severity in [Severity.ERROR, Severity.CRITICAL]:
                component_errors[log.component] += 1
        
        # Generate recommendations for components with high error rates
        for component, error_count in component_errors.items():
            if error_count >= 5:  # Threshold for maintenance recommendation
                recommendation = MaintenanceRecommendation(
                    component=f"{component.value.title()} Components",
                    component_type=component,
                    maintenance_type=MaintenanceType.CORRECTIVE,
                    priority=MaintenancePriority.HIGH if error_count >= 10 else MaintenancePriority.MEDIUM,
                    estimated_downtime="2-4",
                    cost_estimate="$400-1000",
                    parts_required=[f"{component.value} replacement parts"],
                    tools_required=["Diagnostic tools", "Replacement parts"],
                    skills_required=[f"{component.value} troubleshooting"],
                    description=f"High error rate detected: {error_count} errors in last 7 days",
                    steps=[
                        f"Investigate {component.value} error patterns",
                        f"Identify root cause of {component.value} errors",
                        f"Replace failing {component.value} components",
                        f"Verify {component.value} functionality after repair"
                    ],
                    risk_factors=[
                        f"High error rate indicates imminent {component.value} failure",
                        "Component failure may cause system instability"
                    ],
                    confidence_score=0.8,
                    recommended_date=datetime.now() + timedelta(days=3),
                    created_at=datetime.now()
                )
                
                recommendations.append(recommendation)
        
        return recommendations
    
    def _map_risk_to_priority(self, risk_level: str) -> MaintenancePriority:
        """Map risk level to maintenance priority"""
        mapping = {
            "low": MaintenancePriority.LOW,
            "medium": MaintenancePriority.MEDIUM,
            "high": MaintenancePriority.HIGH,
            "critical": MaintenancePriority.CRITICAL
        }
        return mapping.get(risk_level, MaintenancePriority.MEDIUM)
    
    def _priority_score(self, priority: MaintenancePriority) -> int:
        """Convert priority to numeric score for sorting"""
        scores = {
            MaintenancePriority.EMERGENCY: 5,
            MaintenancePriority.CRITICAL: 4,
            MaintenancePriority.HIGH: 3,
            MaintenancePriority.MEDIUM: 2,
            MaintenancePriority.LOW: 1
        }
        return scores.get(priority, 1)
    
    async def schedule_maintenance(self, recommendation: MaintenanceRecommendation,
                                 scheduled_date: datetime,
                                 assigned_to: Optional[str] = None) -> MaintenanceSchedule:
        """Schedule a maintenance activity"""
        
        schedule = MaintenanceSchedule(
            id=f"maint_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            recommendation=recommendation,
            scheduled_date=scheduled_date,
            estimated_duration=int(recommendation.estimated_downtime.split('-')[0]),
            assigned_to=assigned_to,
            status="scheduled",
            created_at=datetime.now()
        )
        
        self.maintenance_history.append(schedule)
        
        logger.info(f"Scheduled maintenance: {recommendation.component} on {scheduled_date}")
        
        return schedule
    
    def get_maintenance_calendar(self, days_ahead: int = 30) -> List[Dict[str, Any]]:
        """Get maintenance calendar for upcoming period"""
        cutoff_date = datetime.now() + timedelta(days=days_ahead)
        
        upcoming_maintenance = []
        for schedule in self.maintenance_history:
            if (schedule.status == "scheduled" and 
                schedule.scheduled_date <= cutoff_date):
                
                upcoming_maintenance.append({
                    "id": schedule.id,
                    "component": schedule.recommendation.component,
                    "maintenance_type": schedule.recommendation.maintenance_type,
                    "priority": schedule.recommendation.priority,
                    "scheduled_date": schedule.scheduled_date.isoformat(),
                    "estimated_duration": schedule.estimated_duration,
                    "assigned_to": schedule.assigned_to,
                    "status": schedule.status,
                    "description": schedule.recommendation.description
                })
        
        return sorted(upcoming_maintenance, key=lambda x: x["scheduled_date"])
    
    def get_maintenance_statistics(self) -> Dict[str, Any]:
        """Get maintenance statistics and analytics"""
        
        total_maintenance = len(self.maintenance_history)
        completed_maintenance = len([s for s in self.maintenance_history if s.status == "completed"])
        
        # Maintenance by type
        maintenance_by_type = defaultdict(int)
        for schedule in self.maintenance_history:
            maintenance_by_type[schedule.recommendation.maintenance_type] += 1
        
        # Maintenance by priority
        maintenance_by_priority = defaultdict(int)
        for schedule in self.maintenance_history:
            maintenance_by_priority[schedule.recommendation.priority] += 1
        
        # Average downtime
        completed_schedules = [s for s in self.maintenance_history if s.status == "completed"]
        avg_downtime = 0
        if completed_schedules:
            avg_downtime = sum(s.estimated_duration for s in completed_schedules) / len(completed_schedules)
        
        return {
            "total_maintenance": total_maintenance,
            "completed_maintenance": completed_maintenance,
            "completion_rate": (completed_maintenance / total_maintenance * 100) if total_maintenance > 0 else 0,
            "maintenance_by_type": dict(maintenance_by_type),
            "maintenance_by_priority": dict(maintenance_by_priority),
            "average_downtime_hours": round(avg_downtime, 1),
            "upcoming_maintenance": len([s for s in self.maintenance_history if s.status == "scheduled"])
        }
