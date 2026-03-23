"""
Multi-Server Management for Dell Server AI Agent
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import json

from models.server_models import ServerInfo, HealthStatus, ActionLevel
from core.agent_core import DellAIAgent
from core.config import AgentConfig

logger = logging.getLogger(__name__)

class ServerGroup(str, Enum):
    PRODUCTION = "production"
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    BACKUP = "backup"

class ServerStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    WARNING = "warning"
    CRITICAL = "critical"
    MAINTENANCE = "maintenance"
    UNKNOWN = "unknown"

@dataclass
class ServerConnection:
    """Server connection configuration"""
    id: str
    name: str
    host: str
    username: str
    password: str
    port: int = 443
    group: ServerGroup = ServerGroup.PRODUCTION
    location: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    enabled: bool = True
    last_connected: Optional[datetime] = None
    connection_attempts: int = 0
    max_connection_attempts: int = 3

@dataclass
class ServerMetrics:
    """Metrics for a server"""
    server_id: str
    timestamp: datetime
    cpu_utilization: Optional[float] = None
    memory_utilization: Optional[float] = None
    disk_utilization: Optional[float] = None
    temperature_average: Optional[float] = None
    power_consumption: Optional[float] = None
    health_score: Optional[float] = None
    status: ServerStatus = ServerStatus.UNKNOWN

class MultiServerManager:
    """Manages multiple Dell servers simultaneously"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.servers: Dict[str, ServerConnection] = {}
        self.agents: Dict[str, DellAIAgent] = {}
        self.server_metrics: Dict[str, List[ServerMetrics]] = {}
        self.server_groups: Dict[ServerGroup, Set[str]] = {
            group: set() for group in ServerGroup
        }
        self.monitoring_tasks: Dict[str, asyncio.Task] = {}
        self.global_metrics = {
            "total_servers": 0,
            "online_servers": 0,
            "offline_servers": 0,
            "warning_servers": 0,
            "critical_servers": 0,
            "last_updated": datetime.now()
        }
    
    async def add_server(self, server: ServerConnection) -> bool:
        """Add a new server to management"""
        try:
            # Validate server connection
            if not await self._test_server_connection(server):
                logger.error(f"Failed to connect to server: {server.host}")
                return False
            
            # Add to servers registry
            self.servers[server.id] = server
            self.server_groups[server.group].add(server.id)
            
            # Create agent for this server
            agent = DellAIAgent(self.config)
            success = await agent.connect_to_server(
                host=server.host,
                username=server.username,
                password=server.password,
                port=server.port
            )
            
            if success:
                self.agents[server.id] = agent
                server.last_connected = datetime.now()
                server.connection_attempts = 0
                
                # Initialize metrics storage
                self.server_metrics[server.id] = []
                
                # Start monitoring
                await self._start_server_monitoring(server.id)
                
                logger.info(f"Added server to management: {server.name} ({server.host})")
                return True
            else:
                # Remove from registry if connection failed
                del self.servers[server.id]
                self.server_groups[server.group].discard(server.id)
                return False
                
        except Exception as e:
            logger.error(f"Failed to add server {server.host}: {str(e)}")
            return False
    
    async def remove_server(self, server_id: str) -> bool:
        """Remove a server from management"""
        try:
            if server_id not in self.servers:
                return False
            
            server = self.servers[server_id]
            
            # Stop monitoring
            await self._stop_server_monitoring(server_id)
            
            # Disconnect agent
            if server_id in self.agents:
                await self.agents[server_id].disconnect()
                del self.agents[server_id]
            
            # Remove from registries
            del self.servers[server_id]
            self.server_groups[server.group].discard(server_id)
            if server_id in self.server_metrics:
                del self.server_metrics[server_id]
            
            logger.info(f"Removed server from management: {server.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove server {server_id}: {str(e)}")
            return False
    
    async def _test_server_connection(self, server: ServerConnection) -> bool:
        """Test connection to a server"""
        try:
            agent = DellAIAgent(self.config)
            success = await agent.connect_to_server(
                host=server.host,
                username=server.username,
                password=server.password,
                port=server.port
            )
            
            if success:
                await agent.disconnect()
                return True
            return False
            
        except Exception as e:
            logger.error(f"Connection test failed for {server.host}: {str(e)}")
            return False
    
    async def _start_server_monitoring(self, server_id: str):
        """Start monitoring a server"""
        if server_id in self.monitoring_tasks:
            return
        
        task = asyncio.create_task(self._monitor_server(server_id))
        self.monitoring_tasks[server_id] = task
    
    async def _stop_server_monitoring(self, server_id: str):
        """Stop monitoring a server"""
        if server_id in self.monitoring_tasks:
            self.monitoring_tasks[server_id].cancel()
            del self.monitoring_tasks[server_id]
    
    async def _monitor_server(self, server_id: str):
        """Monitor a single server"""
        while server_id in self.servers and server_id in self.agents:
            try:
                server = self.servers[server_id]
                agent = self.agents[server_id]
                
                if not server.enabled:
                    await asyncio.sleep(300)  # 5 minutes
                    continue
                
                # Collect metrics
                metrics = await self._collect_server_metrics(server_id, agent)
                if metrics:
                    self.server_metrics[server_id].append(metrics)
                    
                    # Keep only last 1000 metrics
                    if len(self.server_metrics[server_id]) > 1000:
                        self.server_metrics[server_id] = self.server_metrics[server_id][-1000:]
                
                # Update global metrics
                await self._update_global_metrics()
                
                # Check for alerts
                await self._check_server_alerts(server_id, metrics)
                
                # Wait before next collection
                await asyncio.sleep(60)  # 1 minute intervals
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitoring error for server {server_id}: {str(e)}")
                await asyncio.sleep(300)  # 5 minutes on error
    
    async def _collect_server_metrics(self, server_id: str, agent: DellAIAgent) -> Optional[ServerMetrics]:
        """Collect metrics from a server"""
        try:
            # Get health status
            health_result = await agent.execute_action(
                action_level=ActionLevel.READ_ONLY,
                command="health_check",
                parameters={}
            )
            
            # Get performance metrics
            perf_result = await agent.execute_action(
                action_level=ActionLevel.DIAGNOSTIC,
                command="performance_analysis",
                parameters={}
            )
            
            # Determine server status
            status = ServerStatus.ONLINE
            health_score = 100.0
            
            if health_result and "health_status" in health_result:
                health_status = health_result["health_status"]
                if health_status.get("overall_status") == "critical":
                    status = ServerStatus.CRITICAL
                    health_score = 30.0
                elif health_status.get("overall_status") == "warning":
                    status = ServerStatus.WARNING
                    health_score = 60.0
                elif health_status.get("overall_status") == "offline":
                    status = ServerStatus.OFFLINE
                    health_score = 0.0
            
            # Extract performance data
            perf_data = perf_result.get("performance_metrics", {})
            
            metrics = ServerMetrics(
                server_id=server_id,
                timestamp=datetime.now(),
                cpu_utilization=perf_data.get("cpu_utilization"),
                memory_utilization=perf_data.get("memory_utilization"),
                disk_utilization=perf_data.get("disk_utilization"),
                temperature_average=perf_data.get("temperature_average"),
                power_consumption=perf_data.get("power_consumption"),
                health_score=health_score,
                status=status
            )
            
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to collect metrics for server {server_id}: {str(e)}")
            return ServerMetrics(
                server_id=server_id,
                timestamp=datetime.now(),
                status=ServerStatus.OFFLINE,
                health_score=0.0
            )
    
    async def _update_global_metrics(self):
        """Update global metrics across all servers"""
        total = len(self.servers)
        online = 0
        offline = 0
        warning = 0
        critical = 0
        
        for server_id, server in self.servers.items():
            if not server.enabled:
                continue
            
            # Get latest metrics
            if server_id in self.server_metrics and self.server_metrics[server_id]:
                latest_metrics = self.server_metrics[server_id][-1]
                status = latest_metrics.status
                
                if status == ServerStatus.ONLINE:
                    online += 1
                elif status == ServerStatus.OFFLINE:
                    offline += 1
                elif status == ServerStatus.WARNING:
                    warning += 1
                elif status == ServerStatus.CRITICAL:
                    critical += 1
            else:
                offline += 1
        
        self.global_metrics.update({
            "total_servers": total,
            "online_servers": online,
            "offline_servers": offline,
            "warning_servers": warning,
            "critical_servers": critical,
            "last_updated": datetime.now()
        })
    
    async def _check_server_alerts(self, server_id: str, metrics: ServerMetrics):
        """Check for server alerts and trigger notifications"""
        if not metrics:
            return
        
        server = self.servers[server_id]
        
        # Temperature alert
        if metrics.temperature_average and metrics.temperature_average > 80:
            await self._trigger_alert(
                server_id,
                "high_temperature",
                f"High temperature detected: {metrics.temperature_average:.1f}°C",
                "warning"
            )
        
        # CPU utilization alert
        if metrics.cpu_utilization and metrics.cpu_utilization > 90:
            await self._trigger_alert(
                server_id,
                "high_cpu",
                f"High CPU utilization: {metrics.cpu_utilization:.1f}%",
                "warning"
            )
        
        # Memory utilization alert
        if metrics.memory_utilization and metrics.memory_utilization > 90:
            await self._trigger_alert(
                server_id,
                "high_memory",
                f"High memory utilization: {metrics.memory_utilization:.1f}%",
                "warning"
            )
        
        # Server status change alert
        if metrics.status in [ServerStatus.CRITICAL, ServerStatus.OFFLINE]:
            await self._trigger_alert(
                server_id,
                "server_down",
                f"Server status: {metrics.status}",
                "critical"
            )
    
    async def _trigger_alert(self, server_id: str, alert_type: str, message: str, severity: str):
        """Trigger an alert for a server"""
        server = self.servers[server_id]
        logger.warning(f"ALERT [{severity.upper()}] {server.name}: {message}")
        
        # In a production system, this would send notifications
        # via email, Slack, PagerDuty, etc.
    
    async def execute_on_servers(self, server_ids: List[str], action_level: ActionLevel, 
                                command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an action on multiple servers"""
        results = {}
        
        tasks = []
        for server_id in server_ids:
            if server_id in self.agents:
                task = asyncio.create_task(
                    self._execute_on_single_server(server_id, action_level, command, parameters)
                )
                tasks.append((server_id, task))
        
        # Wait for all tasks to complete
        for server_id, task in tasks:
            try:
                result = await task
                results[server_id] = result
            except Exception as e:
                results[server_id] = {"error": str(e)}
        
        return results
    
    async def _execute_on_single_server(self, server_id: str, action_level: ActionLevel,
                                       command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute action on a single server"""
        if server_id not in self.agents:
            return {"error": "Server not connected"}
        
        agent = self.agents[server_id]
        return await agent.execute_action(action_level, command, parameters)
    
    async def execute_on_group(self, group: ServerGroup, action_level: ActionLevel,
                              command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an action on all servers in a group"""
        server_ids = list(self.server_groups[group])
        return await self.execute_on_servers(server_ids, action_level, command, parameters)
    
    async def execute_on_all_servers(self, action_level: ActionLevel, command: str, 
                                   parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an action on all servers"""
        server_ids = list(self.servers.keys())
        return await self.execute_on_servers(server_ids, action_level, command, parameters)
    
    def get_server_list(self) -> List[Dict[str, Any]]:
        """Get list of all managed servers"""
        servers = []
        for server_id, server in self.servers.items():
            # Get latest metrics
            latest_metrics = None
            if server_id in self.server_metrics and self.server_metrics[server_id]:
                latest_metrics = self.server_metrics[server_id][-1]
            
            server_info = {
                "id": server_id,
                "name": server.name,
                "host": server.host,
                "group": server.group,
                "location": server.location,
                "tags": server.tags,
                "enabled": server.enabled,
                "last_connected": server.last_connected,
                "connection_attempts": server.connection_attempts,
                "status": latest_metrics.status if latest_metrics else ServerStatus.UNKNOWN,
                "health_score": latest_metrics.health_score if latest_metrics else 0.0
            }
            
            if latest_metrics:
                server_info.update({
                    "cpu_utilization": latest_metrics.cpu_utilization,
                    "memory_utilization": latest_metrics.memory_utilization,
                    "temperature_average": latest_metrics.temperature_average,
                    "power_consumption": latest_metrics.power_consumption,
                    "last_updated": latest_metrics.timestamp
                })
            
            servers.append(server_info)
        
        return servers
    
    def get_server_metrics(self, server_id: str, hours: int = 24) -> List[Dict[str, Any]]:
        """Get metrics for a specific server"""
        if server_id not in self.server_metrics:
            return []
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        metrics = self.server_metrics[server_id]
        
        filtered_metrics = [
            m for m in metrics if m.timestamp >= cutoff_time
        ]
        
        return [
            {
                "timestamp": m.timestamp.isoformat(),
                "cpu_utilization": m.cpu_utilization,
                "memory_utilization": m.memory_utilization,
                "disk_utilization": m.disk_utilization,
                "temperature_average": m.temperature_average,
                "power_consumption": m.power_consumption,
                "health_score": m.health_score,
                "status": m.status
            }
            for m in filtered_metrics
        ]
    
    def get_group_summary(self, group: ServerGroup) -> Dict[str, Any]:
        """Get summary of a server group"""
        server_ids = self.server_groups[group]
        total_servers = len(server_ids)
        
        if total_servers == 0:
            return {
                "group": group,
                "total_servers": 0,
                "online_servers": 0,
                "offline_servers": 0,
                "warning_servers": 0,
                "critical_servers": 0,
                "average_health_score": 0.0
            }
        
        online = offline = warning = critical = 0
        health_scores = []
        
        for server_id in server_ids:
            if server_id in self.server_metrics and self.server_metrics[server_id]:
                latest_metrics = self.server_metrics[server_id][-1]
                status = latest_metrics.status
                
                if status == ServerStatus.ONLINE:
                    online += 1
                elif status == ServerStatus.OFFLINE:
                    offline += 1
                elif status == ServerStatus.WARNING:
                    warning += 1
                elif status == ServerStatus.CRITICAL:
                    critical += 1
                
                if latest_metrics.health_score is not None:
                    health_scores.append(latest_metrics.health_score)
        
        avg_health = sum(health_scores) / len(health_scores) if health_scores else 0.0
        
        return {
            "group": group,
            "total_servers": total_servers,
            "online_servers": online,
            "offline_servers": offline,
            "warning_servers": warning,
            "critical_servers": critical,
            "average_health_score": round(avg_health, 1)
        }
    
    def get_global_summary(self) -> Dict[str, Any]:
        """Get global summary of all servers"""
        return self.global_metrics.copy()
    
    async def enable_server(self, server_id: str) -> bool:
        """Enable a server for monitoring"""
        if server_id not in self.servers:
            return False
        
        self.servers[server_id].enabled = True
        await self._start_server_monitoring(server_id)
        return True
    
    async def disable_server(self, server_id: str) -> bool:
        """Disable a server from monitoring"""
        if server_id not in self.servers:
            return False
        
        self.servers[server_id].enabled = False
        await self._stop_server_monitoring(server_id)
        return True
    
    async def reconnect_server(self, server_id: str) -> bool:
        """Reconnect to a server"""
        if server_id not in self.servers:
            return False
        
        server = self.servers[server_id]
        
        # Test connection
        if await self._test_server_connection(server):
            # Create new agent
            agent = DellAIAgent(self.config)
            success = await agent.connect_to_server(
                host=server.host,
                username=server.username,
                password=server.password,
                port=server.port
            )
            
            if success:
                # Replace old agent
                if server_id in self.agents:
                    await self.agents[server_id].disconnect()
                
                self.agents[server_id] = agent
                server.last_connected = datetime.now()
                server.connection_attempts = 0
                
                # Restart monitoring
                await self._start_server_monitoring(server_id)
                
                logger.info(f"Reconnected to server: {server.name}")
                return True
        
        server.connection_attempts += 1
        return False
    
    async def shutdown(self):
        """Shutdown the multi-server manager"""
        # Stop all monitoring tasks
        for server_id in list(self.monitoring_tasks.keys()):
            await self._stop_server_monitoring(server_id)
        
        # Disconnect all agents
        for agent in self.agents.values():
            await agent.disconnect()
        
        self.agents.clear()
        logger.info("Multi-server manager shutdown complete")
