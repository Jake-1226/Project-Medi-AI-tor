"""
Advanced Alert System with Smart Notifications
Provides intelligent alerting with escalation, correlation, and multi-channel delivery
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import json
from collections import defaultdict, deque
import hashlib

logger = logging.getLogger(__name__)

class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"

class AlertStatus(Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"

class NotificationChannel(Enum):
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"
    SMS = "sms"
    IN_APP = "in_app"

@dataclass
class AlertRule:
    """Alert rule configuration"""
    name: str
    condition: str  # Metric expression
    severity: AlertSeverity
    threshold: float
    operator: str  # ">", "<", ">=", "<=", "=="
    duration: int  # Seconds condition must persist
    enabled: bool = True
    description: str = ""
    tags: Set[str] = field(default_factory=set)
    notification_channels: List[NotificationChannel] = field(default_factory=list)
    escalation_rules: List[Dict] = field(default_factory=list)

@dataclass
class Alert:
    """Alert instance"""
    id: str
    rule_name: str
    severity: AlertSeverity
    status: AlertStatus
    message: str
    details: Dict[str, Any]
    metric_name: str
    current_value: float
    threshold: float
    triggered_at: datetime
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    notification_sent: Dict[NotificationChannel, datetime] = field(default_factory=dict)
    escalation_level: int = 0
    correlation_id: Optional[str] = None
    tags: Set[str] = field(default_factory=set)
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "rule_name": self.rule_name,
            "severity": self.severity.value,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "metric_name": self.metric_name,
            "current_value": self.current_value,
            "threshold": self.threshold,
            "triggered_at": self.triggered_at.isoformat(),
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "acknowledged_by": self.acknowledged_by,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "notification_sent": {ch.value: dt.isoformat() for ch, dt in self.notification_sent.items()},
            "escalation_level": self.escalation_level,
            "correlation_id": self.correlation_id,
            "tags": list(self.tags)
        }

class AlertCorrelation:
    """Correlates related alerts to reduce noise"""
    
    def __init__(self):
        self.correlation_window = timedelta(minutes=5)
        self.similarity_threshold = 0.8
    
    def correlate_alerts(self, new_alert: Alert, existing_alerts: List[Alert]) -> Optional[str]:
        """Find correlation group for new alert"""
        for alert in existing_alerts:
            if alert.status not in [AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]:
                continue
            
            # Check time window
            if abs((new_alert.triggered_at - alert.triggered_at).total_seconds()) > self.correlation_window.total_seconds():
                continue
            
            # Check similarity
            similarity = self._calculate_similarity(new_alert, alert)
            if similarity >= self.similarity_threshold:
                return alert.correlation_id or alert.id
        
        return None
    
    def _calculate_similarity(self, alert1: Alert, alert2: Alert) -> float:
        """Calculate similarity between two alerts"""
        similarity_score = 0.0
        
        # Same metric name
        if alert1.metric_name == alert2.metric_name:
            similarity_score += 0.4
        
        # Same severity
        if alert1.severity == alert2.severity:
            similarity_score += 0.2
        
        # Overlapping tags
        common_tags = alert1.tags.intersection(alert2.tags)
        if common_tags:
            similarity_score += 0.3 * (len(common_tags) / max(len(alert1.tags), len(alert2.tags)))
        
        # Similar message content
        if alert1.rule_name == alert2.rule_name:
            similarity_score += 0.1
        
        return min(similarity_score, 1.0)

class NotificationEngine:
    """Handles multi-channel notification delivery"""
    
    def __init__(self):
        self.channel_configs = {}
        self.rate_limits = defaultdict(deque)
        self.rate_limit_window = timedelta(minutes=1)
        self.rate_limit_max = 10  # Max notifications per minute per channel
    
    async def send_notification(self, alert: Alert, channel: NotificationChannel, 
                              recipients: List[str], escalation_level: int = 0):
        """Send notification through specified channel"""
        # Check rate limiting
        if not self._check_rate_limit(channel):
            logger.warning(f"Rate limit exceeded for {channel.value}")
            return False
        
        try:
            if channel == NotificationChannel.EMAIL:
                success = await self._send_email(alert, recipients, escalation_level)
            elif channel == NotificationChannel.SLACK:
                success = await self._send_slack(alert, recipients, escalation_level)
            elif channel == NotificationChannel.WEBHOOK:
                success = await self._send_webhook(alert, recipients, escalation_level)
            elif channel == NotificationChannel.SMS:
                success = await self._send_sms(alert, recipients, escalation_level)
            elif channel == NotificationChannel.IN_APP:
                success = await self._send_in_app(alert, recipients)
            else:
                success = False
            
            if success:
                alert.notification_sent[channel] = datetime.now()
                logger.info(f"Notification sent via {channel.value} for alert {alert.id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to send {channel.value} notification: {e}")
            return False
    
    def _check_rate_limit(self, channel: NotificationChannel) -> bool:
        """Check if channel is rate limited"""
        now = datetime.now()
        rate_limit_queue = self.rate_limits[channel]
        
        # Remove old entries
        while rate_limit_queue and rate_limit_queue[0] < now - self.rate_limit_window:
            rate_limit_queue.popleft()
        
        # Check if we can send
        if len(rate_limit_queue) >= self.rate_limit_max:
            return False
        
        rate_limit_queue.append(now)
        return True
    
    async def _send_email(self, alert: Alert, recipients: List[str], escalation_level: int) -> bool:
        """Send email notification"""
        # Placeholder for email implementation
        logger.info(f"EMAIL: Alert {alert.id} - {alert.message}")
        return True
    
    async def _send_slack(self, alert: Alert, recipients: List[str], escalation_level: int) -> bool:
        """Send Slack notification"""
        # Placeholder for Slack implementation
        logger.info(f"SLACK: Alert {alert.id} - {alert.message}")
        return True
    
    async def _send_webhook(self, alert: Alert, recipients: List[str], escalation_level: int) -> bool:
        """Send webhook notification"""
        # Placeholder for webhook implementation
        logger.info(f"WEBHOOK: Alert {alert.id} - {alert.message}")
        return True
    
    async def _send_sms(self, alert: Alert, recipients: List[str], escalation_level: int) -> bool:
        """Send SMS notification"""
        # Placeholder for SMS implementation
        logger.info(f"SMS: Alert {alert.id} - {alert.message}")
        return True
    
    async def _send_in_app(self, alert: Alert, recipients: List[str]) -> bool:
        """Send in-app notification"""
        # This would be handled by WebSocket connections
        logger.info(f"IN_APP: Alert {alert.id} - {alert.message}")
        return True

class AlertSystem:
    """Main alert management system"""
    
    def __init__(self):
        self.rules: Dict[str, AlertRule] = {}
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: deque = deque(maxlen=10000)
        self.correlation_engine = AlertCorrelation()
        self.notification_engine = NotificationEngine()
        self.monitoring_active = False
        self.monitoring_task: Optional[asyncio.Task] = None
        
        # Default alert rules
        self._setup_default_rules()
    
    def _setup_default_rules(self):
        """Setup default alert rules"""
        default_rules = [
            AlertRule(
                name="high_inlet_temperature",
                condition="inlet_temp > 30",
                severity=AlertSeverity.WARNING,
                threshold=30.0,
                operator=">",
                duration=300,  # 5 minutes
                description="Inlet temperature exceeds normal range",
                tags={"thermal", "temperature"},
                notification_channels=[NotificationChannel.EMAIL, NotificationChannel.IN_APP]
            ),
            AlertRule(
                name="critical_inlet_temperature",
                condition="inlet_temp > 35",
                severity=AlertSeverity.CRITICAL,
                threshold=35.0,
                operator=">",
                duration=60,  # 1 minute
                description="Inlet temperature critical",
                tags={"thermal", "temperature", "critical"},
                notification_channels=[NotificationChannel.EMAIL, NotificationChannel.SLACK, NotificationChannel.SMS]
            ),
            AlertRule(
                name="high_cpu_temperature",
                condition="cpu_temp > 80",
                severity=AlertSeverity.WARNING,
                threshold=80.0,
                operator=">",
                duration=300,
                description="CPU temperature exceeds normal range",
                tags={"thermal", "cpu"},
                notification_channels=[NotificationChannel.EMAIL, NotificationChannel.IN_APP]
            ),
            AlertRule(
                name="critical_cpu_temperature",
                condition="cpu_temp > 85",
                severity=AlertSeverity.CRITICAL,
                threshold=85.0,
                operator=">",
                duration=120,
                description="CPU temperature critical",
                tags={"thermal", "cpu", "critical"},
                notification_channels=[NotificationChannel.EMAIL, NotificationChannel.SLACK, NotificationChannel.SMS]
            ),
            AlertRule(
                name="fan_failure",
                condition="fan_speed < 1000",
                severity=AlertSeverity.CRITICAL,
                threshold=1000.0,
                operator="<",
                duration=60,
                description="Fan speed too low - possible failure",
                tags={"thermal", "fan", "hardware"},
                notification_channels=[NotificationChannel.EMAIL, NotificationChannel.SLACK, NotificationChannel.SMS]
            ),
            AlertRule(
                name="power_consumption_high",
                condition="power_consumption > 700",
                severity=AlertSeverity.WARNING,
                threshold=700.0,
                operator=">",
                duration=600,
                description="Power consumption unusually high",
                tags={"power", "efficiency"},
                notification_channels=[NotificationChannel.EMAIL, NotificationChannel.IN_APP]
            ),
            AlertRule(
                name="power_efficiency_low",
                condition="power_efficiency < 70",
                severity=AlertSeverity.WARNING,
                threshold=70.0,
                operator="<",
                duration=300,
                description="Power efficiency below optimal",
                tags={"power", "efficiency"},
                notification_channels=[NotificationChannel.EMAIL, NotificationChannel.IN_APP]
            ),
            AlertRule(
                name="memory_errors",
                condition="memory_health < 80",
                severity=AlertSeverity.WARNING,
                threshold=80.0,
                operator="<",
                duration=180,
                description="Memory health degraded",
                tags={"memory", "hardware"},
                notification_channels=[NotificationChannel.EMAIL, NotificationChannel.IN_APP]
            ),
            AlertRule(
                name="storage_issues",
                condition="storage_health < 80",
                severity=AlertSeverity.WARNING,
                threshold=80.0,
                operator="<",
                duration=300,
                description="Storage health degraded",
                tags={"storage", "hardware"},
                notification_channels=[NotificationChannel.EMAIL, NotificationChannel.IN_APP]
            ),
            AlertRule(
                name="overall_health_critical",
                condition="overall_health < 60",
                severity=AlertSeverity.CRITICAL,
                threshold=60.0,
                operator="<",
                duration=120,
                description="Overall system health critical",
                tags={"system", "health", "critical"},
                notification_channels=[NotificationChannel.EMAIL, NotificationChannel.SLACK, NotificationChannel.SMS]
            )
        ]
        
        for rule in default_rules:
            self.rules[rule.name] = rule
    
    def add_rule(self, rule: AlertRule):
        """Add new alert rule"""
        self.rules[rule.name] = rule
        logger.info(f"Added alert rule: {rule.name}")
    
    def remove_rule(self, rule_name: str):
        """Remove alert rule"""
        if rule_name in self.rules:
            del self.rules[rule_name]
            logger.info(f"Removed alert rule: {rule_name}")
    
    async def evaluate_metrics(self, metrics: Dict[str, Any]):
        """Evaluate metrics against alert rules"""
        for rule_name, rule in self.rules.items():
            if not rule.enabled:
                continue
            
            try:
                await self._evaluate_rule(rule, metrics)
            except Exception as e:
                logger.error(f"Error evaluating rule {rule_name}: {e}")
    
    async def _evaluate_rule(self, rule: AlertRule, metrics: Dict[str, Any]):
        """Evaluate a single alert rule"""
        # Parse condition to get metric name
        metric_name = rule.condition.split()[0]
        
        if metric_name not in metrics:
            return
        
        current_value = metrics[metric_name].get("current_value", 0)
        
        # Check if condition is met
        condition_met = self._check_condition(current_value, rule.operator, rule.threshold)
        
        if condition_met:
            await self._handle_triggered_rule(rule, metric_name, current_value, metrics)
        else:
            await self._handle_resolved_rule(rule, metric_name)
    
    def _check_condition(self, value: float, operator: str, threshold: float) -> bool:
        """Check if condition is met"""
        if operator == ">":
            return value > threshold
        elif operator == "<":
            return value < threshold
        elif operator == ">=":
            return value >= threshold
        elif operator == "<=":
            return value <= threshold
        elif operator == "==":
            return value == threshold
        else:
            return False
    
    async def _handle_triggered_rule(self, rule: AlertRule, metric_name: str, 
                                   current_value: float, metrics: Dict[str, Any]):
        """Handle triggered alert rule"""
        alert_id = self._generate_alert_id(rule.name, metric_name)
        
        if alert_id in self.active_alerts:
            # Alert already exists, check if it should be escalated
            alert = self.active_alerts[alert_id]
            await self._check_escalation(alert, rule)
        else:
            # Create new alert
            alert = Alert(
                id=alert_id,
                rule_name=rule.name,
                severity=rule.severity,
                status=AlertStatus.ACTIVE,
                message=self._generate_alert_message(rule, metric_name, current_value),
                details={
                    "rule_description": rule.description,
                    "metric_details": metrics.get(metric_name, {}),
                    "all_metrics": metrics
                },
                metric_name=metric_name,
                current_value=current_value,
                threshold=rule.threshold,
                triggered_at=datetime.now(),
                tags=rule.tags.copy()
            )
            
            # Check for correlation
            correlation_id = self.correlation_engine.correlate_alerts(
                alert, list(self.active_alerts.values())
            )
            if correlation_id:
                alert.correlation_id = correlation_id
            
            self.active_alerts[alert_id] = alert
            self.alert_history.append(alert)
            
            # Send notifications
            await self._send_alert_notifications(alert, rule)
            
            logger.warning(f"Alert triggered: {alert_id} - {alert.message}")
    
    async def _handle_resolved_rule(self, rule: AlertRule, metric_name: str):
        """Handle resolved alert rule"""
        alert_id = self._generate_alert_id(rule.name, metric_name)
        
        if alert_id in self.active_alerts:
            alert = self.active_alerts[alert_id]
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = datetime.now()
            
            # Move to history
            self.alert_history.append(alert)
            del self.active_alerts[alert_id]
            
            # Send resolution notification
            await self._send_resolution_notification(alert, rule)
            
            logger.info(f"Alert resolved: {alert_id}")
    
    async def _check_escalation(self, alert: Alert, rule: AlertRule):
        """Check if alert should be escalated"""
        if not rule.escalation_rules:
            return
        
        # Check time-based escalation
        time_since_trigger = datetime.now() - alert.triggered_at
        
        for escalation_rule in rule.escalation_rules:
            if (time_since_trigger.total_seconds() >= escalation_rule.get("after_seconds", 0) and
                alert.escalation_level < escalation_rule.get("level", 1)):
                
                await self._escalate_alert(alert, rule, escalation_rule)
    
    async def _escalate_alert(self, alert: Alert, rule: AlertRule, escalation_rule: Dict):
        """Escalate alert to next level"""
        alert.escalation_level = escalation_rule.get("level", 1)
        
        # Update severity if specified
        if "severity" in escalation_rule:
            alert.severity = AlertSeverity(escalation_rule["severity"])
        
        # Send escalation notifications
        escalation_channels = escalation_rule.get("channels", rule.notification_channels)
        recipients = escalation_rule.get("recipients", [])
        
        for channel in escalation_channels:
            await self.notification_engine.send_notification(
                alert, channel, recipients, alert.escalation_level
            )
        
        logger.warning(f"Alert escalated: {alert.id} to level {alert.escalation_level}")
    
    async def _send_alert_notifications(self, alert: Alert, rule: AlertRule):
        """Send initial alert notifications"""
        for channel in rule.notification_channels:
            await self.notification_engine.send_notification(alert, channel, [])
    
    async def _send_resolution_notification(self, alert: Alert, rule: AlertRule):
        """Send alert resolution notifications"""
        # Create resolution message
        resolution_message = f"RESOLVED: {alert.message}"
        
        # Send to same channels as original alert
        for channel in rule.notification_channels:
            await self.notification_engine.send_notification(alert, channel, [])
    
    def _generate_alert_id(self, rule_name: str, metric_name: str) -> str:
        """Generate unique alert ID"""
        unique_string = f"{rule_name}_{metric_name}_{datetime.now().strftime('%Y%m%d')}"
        return hashlib.md5(unique_string.encode()).hexdigest()[:12]
    
    def _generate_alert_message(self, rule: AlertRule, metric_name: str, current_value: float) -> str:
        """Generate alert message"""
        return f"{rule.description}: {metric_name} = {current_value:.2f} (threshold: {rule.threshold})"
    
    def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> bool:
        """Acknowledge an alert"""
        if alert_id in self.active_alerts:
            alert = self.active_alerts[alert_id]
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.acknowledged_at = datetime.now()
            alert.acknowledged_by = acknowledged_by
            logger.info(f"Alert acknowledged: {alert_id} by {acknowledged_by}")
            return True
        return False
    
    def get_active_alerts(self) -> List[Alert]:
        """Get all active alerts"""
        return list(self.active_alerts.values())
    
    def get_alert_history(self, hours: int = 24) -> List[Alert]:
        """Get alert history for specified hours"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [alert for alert in self.alert_history if alert.triggered_at >= cutoff_time]
    
    def get_alert_statistics(self) -> Dict[str, Any]:
        """Get alert statistics"""
        active_by_severity = defaultdict(int)
        for alert in self.active_alerts.values():
            active_by_severity[alert.severity.value] += 1
        
        recent_alerts = self.get_alert_history(24)
        resolved_by_severity = defaultdict(int)
        for alert in recent_alerts:
            if alert.status == AlertStatus.RESOLVED:
                resolved_by_severity[alert.severity.value] += 1
        
        return {
            "active_alerts": len(self.active_alerts),
            "active_by_severity": dict(active_by_severity),
            "resolved_last_24h": len([a for a in recent_alerts if a.status == AlertStatus.RESOLVED]),
            "resolved_by_severity": dict(resolved_by_severity),
            "total_rules": len(self.rules),
            "enabled_rules": len([r for r in self.rules.values() if r.enabled]),
            "correlation_groups": len(set(a.correlation_id for a in self.active_alerts.values() if a.correlation_id))
        }

# Global alert system instance
alert_system = AlertSystem()
