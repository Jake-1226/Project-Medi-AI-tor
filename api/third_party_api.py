"""
Third-Party Integration API for Dell Server AI Agent
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import json
import aiohttp
from fastapi import HTTPException

from models.server_models import ActionLevel, ServerInfo
from core.agent_core import DellAIAgent

from collections import defaultdict
from typing import Dict, List, Callable  # if you are using these type hints

logger = logging.getLogger(__name__)

class IntegrationType(str, Enum):
    WEBHOOK = "webhook"
    REST_API = "rest_api"
    STREAMING = "streaming"
    POLLING = "polling"

class EventType(str, Enum):
    SERVER_ALERT = "server_alert"
    MAINTENANCE_REQUIRED = "maintenance_required"
    PERFORMANCE_DEGRADED = "performance_degraded"
    HEALTH_CHECK = "health_check"
    ERROR_OCCURRED = "error_occurred"
    THRESHOLD_EXCEEDED = "threshold_exceeded"

@dataclass
class WebhookConfig:
    """Webhook configuration for third-party integration"""
    url: str
    secret: Optional[str] = None
    events: List[EventType] = None
    headers: Dict[str, str] = None
    timeout: int = 30
    retry_count: int = 3
    enabled: bool = True

@dataclass
class Integration:
    """Third-party integration configuration"""
    id: str
    name: str
    type: IntegrationType
    config: Dict[str, Any]
    enabled: bool = True
    created_at: datetime = None
    last_used: Optional[datetime] = None
    success_count: int = 0
    failure_count: int = 0

class ThirdPartyAPI:
    """Third-party integration API for external systems"""
    
    def __init__(self, agent: DellAIAgent):
        self.agent = agent
        self.integrations: Dict[str, Integration] = {}
        self.webhooks: Dict[str, WebhookConfig] = {}
        self.event_handlers: Dict[EventType, List[Callable]] = defaultdict(list)
        self.rate_limits: Dict[str, Dict] = {}
        
        # Initialize built-in integrations
        self._initialize_builtin_integrations()
    
    def _initialize_builtin_integrations(self):
        """Initialize built-in third-party integrations"""
        
        # Slack integration
        slack_integration = Integration(
            id="slack",
            name="Slack Notifications",
            type=IntegrationType.WEBHOOK,
            config={
                "webhook_url": "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK",
                "channel": "#server-alerts",
                "username": "Dell AI Agent"
            },
            enabled=False
        )
        self.integrations["slack"] = slack_integration
        
        # Microsoft Teams integration
        teams_integration = Integration(
            id="teams",
            name="Microsoft Teams",
            type=IntegrationType.WEBHOOK,
            config={
                "webhook_url": "https://outlook.office.com/webhook/YOUR-TEAMS-WEBHOOK",
                "title": "Dell Server Alert"
            },
            enabled=False
        )
        self.integrations["teams"] = teams_integration
        
        # PagerDuty integration
        pagerduty_integration = Integration(
            id="pagerduty",
            name="PagerDuty",
            type=IntegrationType.REST_API,
            config={
                "api_key": "your-pagerduty-api-key",
                "service_key": "your-service-key",
                "base_url": "https://api.pagerduty.com"
            },
            enabled=False
        )
        self.integrations["pagerduty"] = pagerduty_integration
        
        # ServiceNow integration
        servicenow_integration = Integration(
            id="servicenow",
            name="ServiceNow",
            type=IntegrationType.REST_API,
            config={
                "instance": "your-instance.service-now.com",
                "username": "api-user",
                "password": "api-password",
                "assignment_group": "Infrastructure"
            },
            enabled=False
        )
        self.integrations["servicenow"] = servicenow_integration
        
        # Email integration
        email_integration = Integration(
            id="email",
            name="Email Notifications",
            type=IntegrationType.WEBHOOK,
            config={
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "username": "your-email@gmail.com",
                "password": "your-app-password",
                "recipients": ["admin@company.com"]
            },
            enabled=False
        )
        self.integrations["email"] = email_integration
    
    async def create_integration(self, integration: Integration) -> bool:
        """Create a new third-party integration"""
        try:
            integration.created_at = datetime.now()
            self.integrations[integration.id] = integration
            
            # Test the integration
            if await self._test_integration(integration):
                logger.info(f"Created integration: {integration.name}")
                return True
            else:
                # Remove if test fails
                del self.integrations[integration.id]
                return False
                
        except Exception as e:
            logger.error(f"Failed to create integration: {str(e)}")
            return False
    
    async def update_integration(self, integration_id: str, updates: Dict[str, Any]) -> bool:
        """Update an existing integration"""
        if integration_id not in self.integrations:
            return False
        
        try:
            integration = self.integrations[integration_id]
            
            # Update configuration
            for key, value in updates.items():
                if hasattr(integration, key):
                    setattr(integration, key, value)
                elif key in integration.config:
                    integration.config[key] = value
            
            # Test the updated integration
            if await self._test_integration(integration):
                logger.info(f"Updated integration: {integration.name}")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Failed to update integration {integration_id}: {str(e)}")
            return False
    
    async def delete_integration(self, integration_id: str) -> bool:
        """Delete an integration"""
        if integration_id not in self.integrations:
            return False
        
        del self.integrations[integration_id]
        logger.info(f"Deleted integration: {integration_id}")
        return True
    
    async def enable_integration(self, integration_id: str) -> bool:
        """Enable an integration"""
        if integration_id not in self.integrations:
            return False
        
        self.integrations[integration_id].enabled = True
        return True
    
    async def disable_integration(self, integration_id: str) -> bool:
        """Disable an integration"""
        if integration_id not in self.integrations:
            return False
        
        self.integrations[integration_id].enabled = False
        return True
    
    async def _test_integration(self, integration: Integration) -> bool:
        """Test an integration connection"""
        try:
            if integration.type == IntegrationType.WEBHOOK:
                return await self._test_webhook(integration)
            elif integration.type == IntegrationType.REST_API:
                return await self._test_rest_api(integration)
            else:
                return True  # Other types not tested
                
        except Exception as e:
            logger.error(f"Integration test failed: {str(e)}")
            return False
    
    async def _test_webhook(self, integration: Integration) -> bool:
        """Test webhook integration"""
        webhook_url = integration.config.get("webhook_url")
        if not webhook_url:
            return False
        
        test_payload = {
            "test": True,
            "message": "Test message from Dell Server AI Agent",
            "timestamp": datetime.now().isoformat()
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    webhook_url,
                    json=test_payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    return response.status in [200, 201, 202]
            except Exception:
                return False
    
    async def _test_rest_api(self, integration: Integration) -> bool:
        """Test REST API integration"""
        base_url = integration.config.get("base_url")
        if not base_url:
            return False
        
        # Generic API test - try to authenticate
        headers = {}
        if integration.config.get("api_key"):
            headers["Authorization"] = f"Token {integration.config['api_key']}"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{base_url}/api/v1/status",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    return response.status == 200
            except Exception:
                return False
    
    async def send_event(self, event_type: EventType, data: Dict[str, Any]) -> Dict[str, Any]:
        """Send event to all enabled integrations"""
        results = {}
        
        # Add timestamp to event data
        event_data = {
            "event_type": event_type.value,
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        
        # Send to all enabled integrations
        for integration_id, integration in self.integrations.items():
            if not integration.enabled:
                continue
            
            try:
                if integration.type == IntegrationType.WEBHOOK:
                    result = await self._send_webhook_event(integration, event_data)
                elif integration.type == IntegrationType.REST_API:
                    result = await self._send_rest_api_event(integration, event_data)
                else:
                    result = {"status": "skipped", "reason": "Unsupported integration type"}
                
                results[integration_id] = result
                
                # Update statistics
                if result.get("status") == "success":
                    integration.success_count += 1
                else:
                    integration.failure_count += 1
                
                integration.last_used = datetime.now()
                
            except Exception as e:
                logger.error(f"Failed to send event to {integration_id}: {str(e)}")
                results[integration_id] = {
                    "status": "error",
                    "error": str(e)
                }
                integration.failure_count += 1
        
        # Call custom event handlers
        for handler in self.event_handlers[event_type]:
            try:
                await handler(event_data)
            except Exception as e:
                logger.error(f"Event handler error: {str(e)}")
        
        return results
    
    async def _send_webhook_event(self, integration: Integration, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send event via webhook"""
        webhook_url = integration.config.get("webhook_url")
        if not webhook_url:
            return {"status": "error", "error": "No webhook URL configured"}
        
        # Prepare payload based on integration type
        payload = self._prepare_webhook_payload(integration, event_data)
        
        headers = integration.config.get("headers", {})
        headers["Content-Type"] = "application/json"
        
        # Add signature if secret is configured
        secret = integration.config.get("secret")
        if secret:
            import hmac
            import hashlib
            
            signature = hmac.new(
                secret.encode(),
                json.dumps(payload).encode(),
                hashlib.sha256
            ).hexdigest()
            headers["X-Signature"] = f"sha256={signature}"
        
        async with aiohttp.ClientSession() as session:
            try:
                timeout = aiohttp.ClientTimeout(total=integration.config.get("timeout", 30))
                async with session.post(webhook_url, json=payload, headers=headers, timeout=timeout) as response:
                    return {
                        "status": "success" if response.status < 400 else "error",
                        "status_code": response.status,
                        "response": await response.text()
                    }
            except Exception as e:
                return {"status": "error", "error": str(e)}
    
    async def _send_rest_api_event(self, integration: Integration, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send event via REST API"""
        base_url = integration.config.get("base_url")
        if not base_url:
            return {"status": "error", "error": "No base URL configured"}
        
        # Prepare API call based on integration type
        api_call = self._prepare_rest_api_call(integration, event_data)
        
        headers = {}
        if integration.config.get("api_key"):
            headers["Authorization"] = f"Token {integration.config['api_key']}"
        elif integration.config.get("username") and integration.config.get("password"):
            import base64
            credentials = f"{integration.config['username']}:{integration.config['password']}"
            encoded = base64.b64encode(credentials.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
        
        async with aiohttp.ClientSession() as session:
            try:
                method = api_call.get("method", "POST").lower()
                url = f"{base_url}{api_call['endpoint']}"
                data = api_call.get("data", {})
                
                timeout = aiohttp.ClientTimeout(total=30)
                
                if method == "post":
                    async with session.post(url, json=data, headers=headers, timeout=timeout) as response:
                        return {
                            "status": "success" if response.status < 400 else "error",
                            "status_code": response.status,
                            "response": await response.text()
                        }
                elif method == "get":
                    async with session.get(url, params=data, headers=headers, timeout=timeout) as response:
                        return {
                            "status": "success" if response.status < 400 else "error",
                            "status_code": response.status,
                            "response": await response.text()
                        }
                else:
                    return {"status": "error", "error": f"Unsupported method: {method}"}
                    
            except Exception as e:
                return {"status": "error", "error": str(e)}
    
    def _prepare_webhook_payload(self, integration: Integration, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare webhook payload based on integration type"""
        
        if integration.id == "slack":
            return {
                "text": f"Dell Server Alert: {event_data['event_type']}",
                "channel": integration.config.get("channel", "#general"),
                "username": integration.config.get("username", "Dell AI Agent"),
                "attachments": [
                    {
                        "color": "danger" if "critical" in event_data['event_type'] else "warning",
                        "fields": [
                            {
                                "title": "Event Type",
                                "value": event_data['event_type'],
                                "short": True
                            },
                            {
                                "title": "Timestamp",
                                "value": event_data['timestamp'],
                                "short": True
                            }
                        ],
                        "text": json.dumps(event_data['data'], indent=2)
                    }
                ]
            }
        
        elif integration.id == "teams":
            return {
                "title": integration.config.get("title", "Dell Server Alert"),
                "text": f"Event: {event_data['event_type']}",
                "themeColor": "FF0000" if "critical" in event_data['event_type'] else "FFFF00",
                "sections": [
                    {
                        "facts": [
                            {"name": "Event Type", "value": event_data['event_type']},
                            {"name": "Timestamp", "value": event_data['timestamp']}
                        ]
                    }
                ],
                "potentialAction": [
                    {
                        "@type": "OpenUri",
                        "name": "View Details",
                        "targets": [{"os": "default", "uri": "http://localhost:8000"}]
                    }
                ]
            }
        
        elif integration.id == "email":
            return {
                "to": integration.config.get("recipients", []),
                "subject": f"Dell Server Alert: {event_data['event_type']}",
                "body": f"""
Event Type: {event_data['event_type']}
Timestamp: {event_data['timestamp']}

Details:
{json.dumps(event_data['data'], indent=2)}
                """.strip()
            }
        
        else:
            # Default payload
            return event_data
    
    def _prepare_rest_api_call(self, integration: Integration, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare REST API call based on integration type"""
        
        if integration.id == "pagerduty":
            return {
                "method": "POST",
                "endpoint": "/v1/incidents",
                "data": {
                    "incident": {
                        "type": "incident",
                        "title": f"Dell Server Alert: {event_data['event_type']}",
                        "service": {"id": integration.config.get("service_key")},
                        "details": json.dumps(event_data),
                        "priority": {"id": "high" if "critical" in event_data['event_type'] else "medium"}
                    }
                }
            }
        
        elif integration.id == "servicenow":
            return {
                "method": "POST",
                "endpoint": "/api/now/table/incident",
                "data": {
                    "short_description": f"Dell Server Alert: {event_data['event_type']}",
                    "description": json.dumps(event_data),
                    "assignment_group": integration.config.get("assignment_group"),
                    "priority": "1" if "critical" in event_data['event_type'] else "2",
                    "impact": "2",
                    "urgency": "2"
                }
            }
        
        else:
            # Default API call
            return {
                "method": "POST",
                "endpoint": "/api/v1/events",
                "data": event_data
            }
    
    def register_event_handler(self, event_type: EventType, handler: Callable):
        """Register a custom event handler"""
        self.event_handlers[event_type].append(handler)
    
    def unregister_event_handler(self, event_type: EventType, handler: Callable):
        """Unregister a custom event handler"""
        if handler in self.event_handlers[event_type]:
            self.event_handlers[event_type].remove(handler)
    
    async def trigger_server_alert(self, server_info: Dict[str, Any], alert_type: str, 
                                 message: str, severity: str = "warning") -> Dict[str, Any]:
        """Trigger a server alert event"""
        event_data = {
            "server": server_info,
            "alert_type": alert_type,
            "message": message,
            "severity": severity
        }
        
        return await self.send_event(EventType.SERVER_ALERT, event_data)
    
    async def trigger_maintenance_alert(self, server_info: Dict[str, Any], 
                                      maintenance_type: str, description: str) -> Dict[str, Any]:
        """Trigger a maintenance alert event"""
        event_data = {
            "server": server_info,
            "maintenance_type": maintenance_type,
            "description": description
        }
        
        return await self.send_event(EventType.MAINTENANCE_REQUIRED, event_data)
    
    async def trigger_performance_alert(self, server_info: Dict[str, Any], 
                                      metrics: Dict[str, Any], threshold: float) -> Dict[str, Any]:
        """Trigger a performance alert event"""
        event_data = {
            "server": server_info,
            "metrics": metrics,
            "threshold": threshold
        }
        
        return await self.send_event(EventType.PERFORMANCE_DEGRADED, event_data)
    
    def get_integrations_list(self) -> List[Dict[str, Any]]:
        """Get list of all integrations"""
        return [
            {
                "id": integration.id,
                "name": integration.name,
                "type": integration.type.value,
                "enabled": integration.enabled,
                "created_at": integration.created_at.isoformat() if integration.created_at else None,
                "last_used": integration.last_used.isoformat() if integration.last_used else None,
                "success_count": integration.success_count,
                "failure_count": integration.failure_count
            }
            for integration in self.integrations.values()
        ]
    
    def get_integration_stats(self, integration_id: str) -> Optional[Dict[str, Any]]:
        """Get statistics for a specific integration"""
        if integration_id not in self.integrations:
            return None
        
        integration = self.integrations[integration_id]
        total_calls = integration.success_count + integration.failure_count
        success_rate = (integration.success_count / total_calls * 100) if total_calls > 0 else 0
        
        return {
            "integration_id": integration_id,
            "name": integration.name,
            "enabled": integration.enabled,
            "total_calls": total_calls,
            "success_count": integration.success_count,
            "failure_count": integration.failure_count,
            "success_rate": round(success_rate, 2),
            "last_used": integration.last_used.isoformat() if integration.last_used else None
        }
    
    async def test_integration(self, integration_id: str) -> Dict[str, Any]:
        """Test a specific integration"""
        if integration_id not in self.integrations:
            return {"status": "error", "error": "Integration not found"}
        
        integration = self.integrations[integration_id]
        
        try:
            success = await self._test_integration(integration)
            return {
                "status": "success" if success else "error",
                "message": "Integration test passed" if success else "Integration test failed"
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def get_supported_integrations(self) -> List[Dict[str, Any]]:
        """Get list of supported integration types"""
        return [
            {
                "id": "slack",
                "name": "Slack",
                "type": IntegrationType.WEBHOOK,
                "description": "Send alerts to Slack channels",
                "config_fields": ["webhook_url", "channel", "username"]
            },
            {
                "id": "teams",
                "name": "Microsoft Teams",
                "type": IntegrationType.WEBHOOK,
                "description": "Send alerts to Microsoft Teams",
                "config_fields": ["webhook_url", "title"]
            },
            {
                "id": "pagerduty",
                "name": "PagerDuty",
                "type": IntegrationType.REST_API,
                "description": "Create incidents in PagerDuty",
                "config_fields": ["api_key", "service_key", "base_url"]
            },
            {
                "id": "servicenow",
                "name": "ServiceNow",
                "type": IntegrationType.REST_API,
                "description": "Create incidents in ServiceNow",
                "config_fields": ["instance", "username", "password", "assignment_group"]
            },
            {
                "id": "email",
                "name": "Email",
                "type": IntegrationType.WEBHOOK,
                "description": "Send email notifications",
                "config_fields": ["smtp_server", "smtp_port", "username", "password", "recipients"]
            }
        ]
