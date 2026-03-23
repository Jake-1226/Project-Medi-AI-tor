"""
Webhook manager for automated alerts and notifications.
Supports multiple webhook endpoints with configurable triggers and payloads.
"""

import asyncio
import aiohttp
import json
import logging
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)

class WebhookEvent(Enum):
    """Types of events that can trigger webhooks"""
    HEALTH_CRITICAL = "health_critical"
    HEALTH_WARNING = "health_warning"
    HEALTH_RECOVERY = "health_recovery"
    FIRMWARE_CRITICAL = "firmware_critical"
    MEMORY_ERROR = "memory_error"
    STORAGE_FAILURE = "storage_failure"
    THERMAL_ALERT = "thermal_alert"
    POWER_SUPPLY_FAILURE = "power_supply_failure"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    INVESTIGATION_COMPLETED = "investigation_completed"

@dataclass
class WebhookEndpoint:
    """Configuration for a webhook endpoint"""
    id: str
    name: str
    url: str
    secret: Optional[str] = None  # For HMAC signature
    events: List[WebhookEvent] = field(default_factory=list)
    enabled: bool = True
    timeout_seconds: int = 10
    retry_attempts: int = 3
    headers: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        # Convert string events to enum if needed
        if self.events and isinstance(self.events[0], str):
            self.events = [WebhookEvent(e) for e in self.events]

@dataclass
class WebhookPayload:
    """Standard webhook payload structure"""
    event_type: str
    timestamp: datetime
    server_info: Dict[str, Any]
    data: Dict[str, Any]
    severity: str  # "critical", "warning", "info"
    source: str = "medi-ai-tor"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "server_info": self.server_info,
            "data": self.data,
            "severity": self.severity,
            "source": self.source
        }

class WebhookManager:
    """Manages webhook notifications for automated alerts"""
    
    def __init__(self):
        self.endpoints: Dict[str, WebhookEndpoint] = {}
        self._session: Optional[aiohttp.ClientSession] = None
        self._event_handlers: Dict[WebhookEvent, List[Callable]] = {}
        
        # Default webhook configurations
        self._setup_default_endpoints()
    
    def _setup_default_endpoints(self):
        """Setup default webhook endpoints"""
        # Slack webhook example
        self.endpoints["slack_alerts"] = WebhookEndpoint(
            id="slack_alerts",
            name="Slack Alerts",
            url="https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK",
            events=[WebhookEvent.HEALTH_CRITICAL, WebhookEvent.HEALTH_WARNING],
            headers={"Content-Type": "application/json"}
        )
        
        # Teams webhook example
        self.endpoints["teams_alerts"] = WebhookEndpoint(
            id="teams_alerts",
            name="Microsoft Teams",
            url="https://outlook.office.com/webhook/YOUR-TEAMS-WEBHOOK",
            events=[WebhookEvent.HEALTH_CRITICAL, WebhookEvent.FIRMWARE_CRITICAL],
            headers={"Content-Type": "application/json"}
        )
        
        # Generic webhook for monitoring systems
        self.endpoints["monitoring"] = WebhookEndpoint(
            id="monitoring",
            name="Monitoring System",
            url="https://your-monitoring.com/webhooks/alerts",
            events=[e for e in WebhookEvent],  # All events
            headers={"Content-Type": "application/json", "Authorization": "Bearer YOUR_TOKEN"}
        )
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def close(self):
        """Close HTTP session"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def add_endpoint(self, endpoint: WebhookEndpoint):
        """Add a new webhook endpoint"""
        self.endpoints[endpoint.id] = endpoint
        logger.info(f"Added webhook endpoint: {endpoint.name}")
    
    def remove_endpoint(self, endpoint_id: str) -> bool:
        """Remove a webhook endpoint"""
        if endpoint_id in self.endpoints:
            del self.endpoints[endpoint_id]
            logger.info(f"Removed webhook endpoint: {endpoint_id}")
            return True
        return False
    
    def enable_endpoint(self, endpoint_id: str) -> bool:
        """Enable a webhook endpoint"""
        if endpoint_id in self.endpoints:
            self.endpoints[endpoint_id].enabled = True
            return True
        return False
    
    def disable_endpoint(self, endpoint_id: str) -> bool:
        """Disable a webhook endpoint"""
        if endpoint_id in self.endpoints:
            self.endpoints[endpoint_id].enabled = False
            return True
        return False
    
    async def send_webhook(self, endpoint_id: str, payload: WebhookPayload) -> bool:
        """Send webhook to specific endpoint"""
        endpoint = self.endpoints.get(endpoint_id)
        if not endpoint or not endpoint.enabled:
            return False
        
        session = await self._get_session()
        
        # Prepare payload for specific platform
        if "slack.com" in endpoint.url:
            formatted_payload = self._format_slack_payload(payload)
        elif "office.com" in endpoint.url:
            formatted_payload = self._format_teams_payload(payload)
        else:
            formatted_payload = payload.to_dict()
        
        # Add signature if secret is provided
        if endpoint.secret:
            signature = self._generate_signature(formatted_payload, endpoint.secret)
            endpoint.headers["X-Webhook-Signature"] = signature
        
        # Retry logic
        for attempt in range(endpoint.retry_attempts + 1):
            try:
                async with session.post(
                    endpoint.url,
                    json=formatted_payload,
                    headers=endpoint.headers,
                    timeout=aiohttp.ClientTimeout(total=endpoint.timeout_seconds)
                ) as response:
                    if response.status in [200, 201, 202, 204]:
                        logger.info(f"Webhook sent successfully to {endpoint.name}")
                        return True
                    else:
                        text = await response.text()
                        logger.warning(f"Webhook failed to {endpoint.name}: {response.status} - {text}")
                        
            except asyncio.TimeoutError:
                logger.warning(f"Webhook timeout to {endpoint.name} (attempt {attempt + 1})")
            except Exception as e:
                logger.error(f"Webhook error to {endpoint.name} (attempt {attempt + 1}): {str(e)}")
            
            if attempt < endpoint.retry_attempts:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        return False
    
    def _format_slack_payload(self, payload: WebhookPayload) -> Dict[str, Any]:
        """Format payload for Slack webhook"""
        color = {
            "critical": "danger",
            "warning": "warning",
            "info": "good"
        }.get(payload.severity, "good")
        
        return {
            "attachments": [{
                "color": color,
                "title": f"Medi-AI-tor Alert: {payload.event_type}",
                "fields": [
                    {"title": "Server", "value": payload.server_info.get("hostname", "Unknown"), "short": True},
                    {"title": "Severity", "value": payload.severity.upper(), "short": True},
                    {"title": "Timestamp", "value": payload.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC"), "short": True}
                ],
                "text": json.dumps(payload.data, indent=2) if payload.data else "No additional data"
            }]
        }
    
    def _format_teams_payload(self, payload: WebhookPayload) -> Dict[str, Any]:
        """Format payload for Microsoft Teams webhook"""
        theme_color = {
            "critical": "FF0000",
            "warning": "FFA500",
            "info": "00FF00"
        }.get(payload.severity, "00FF00")
        
        return {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": theme_color,
            "summary": f"Medi-AI-tor Alert: {payload.event_type}",
            "sections": [{
                "activityTitle": f"Medi-AI-tor Alert: {payload.event_type}",
                "activitySubtitle": f"Server: {payload.server_info.get('hostname', 'Unknown')}",
                "facts": [
                    {"name": "Severity", "value": payload.severity.upper()},
                    {"name": "Timestamp", "value": payload.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")}
                ],
                "text": json.dumps(payload.data, indent=2) if payload.data else "No additional data"
            }]
        }
    
    def _generate_signature(self, payload: Dict[str, Any], secret: str) -> str:
        """Generate HMAC signature for webhook payload"""
        import hmac
        import hashlib
        
        payload_str = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        signature = hmac.new(
            secret.encode(),
            payload_str.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return f"sha256={signature}"
    
    async def trigger_event(self, event_type: WebhookEvent, server_info: Dict[str, Any], 
                          data: Dict[str, Any], severity: str = "info"):
        """Trigger an event to all matching webhook endpoints"""
        payload = WebhookPayload(
            event_type=event_type.value,
            timestamp=datetime.utcnow(),
            server_info=server_info,
            data=data,
            severity=severity
        )
        
        # Send to all endpoints that subscribe to this event
        tasks = []
        for endpoint_id, endpoint in self.endpoints.items():
            if endpoint.enabled and event_type in endpoint.events:
                tasks.append(self.send_webhook(endpoint_id, payload))
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success_count = sum(1 for r in results if r is True)
            logger.info(f"Webhook event {event_type.value}: {success_count}/{len(tasks)} successful")
    
    def register_event_handler(self, event_type: WebhookEvent, handler: Callable):
        """Register a custom event handler"""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
    
    async def get_webhook_stats(self) -> Dict[str, Any]:
        """Get webhook statistics"""
        total = len(self.endpoints)
        enabled = sum(1 for e in self.endpoints.values() if e.enabled)
        
        return {
            "total_endpoints": total,
            "enabled_endpoints": enabled,
            "disabled_endpoints": total - enabled,
            "endpoints": [
                {
                    "id": e.id,
                    "name": e.name,
                    "enabled": e.enabled,
                    "events": [ev.value for ev in e.events]
                }
                for e in self.endpoints.values()
            ]
        }

# Global webhook manager instance
webhook_manager = WebhookManager()
