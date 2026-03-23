"""
Multi-Server Fleet Management System
Manages multiple Dell servers with unified monitoring and operations
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import json
from collections import defaultdict
import uuid

logger = logging.getLogger(__name__)

class ServerStatus(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    CONNECTING = "connecting"
    ERROR = "error"
    MAINTENANCE = "maintenance"

class ServerGroup:
    """Server group for organization"""
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.server_ids: Set[str] = set()
        self.created_at = datetime.now()
        self.tags: Set[str] = set()

@dataclass
class ServerInfo:
    """Server information and connection details"""
    id: str
    name: str
    host: str
    port: int
    username: str
    password: str
    model: Optional[str] = None
    service_tag: Optional[str] = None
    location: Optional[str] = None
    environment: Optional[str] = None  # production, staging, development
    tags: Set[str] = field(default_factory=set)
    groups: Set[str] = field(default_factory=set)
    created_at: datetime = field(default_factory=datetime.now)
    last_seen: Optional[datetime] = None
    status: ServerStatus = ServerStatus.OFFLINE
    health_score: float = 0.0
    alert_count: int = 0
    notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert server to dictionary for API responses — passwords are NEVER included"""
        return {
            "id": self.id,
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            # password intentionally omitted from API responses
            "model": self.model,
            "service_tag": self.service_tag,
            "location": self.location,
            "environment": self.environment,
            "tags": list(self.tags),  # Convert set to list
            "groups": list(self.groups),  # Convert set to list
            "status": self.status.value if isinstance(self.status, ServerStatus) else self.status,
            "health_score": self.health_score,
            "alert_count": self.alert_count,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None
        }

class FleetManager:
    """Manages multiple servers and provides fleet-wide operations"""
    
    def __init__(self):
        self.servers: Dict[str, ServerInfo] = {}
        self.server_groups: Dict[str, ServerGroup] = {}
        self.active_connections: Dict[str, Any] = {}
        self.monitoring_tasks: Dict[str, asyncio.Task] = {}
        self.fleet_metrics: Dict[str, Any] = {}
        self.alerts: List[Dict] = []
        
        # Default groups
        self._create_default_groups()
    
    def _create_default_groups(self):
        """Create default server groups"""
        default_groups = [
            ServerGroup("All Servers", "All registered servers"),
            ServerGroup("Production", "Production environment servers"),
            ServerGroup("Critical", "Critical infrastructure servers"),
            ServerGroup("Development", "Development and test servers")
        ]
        
        for group in default_groups:
            self.server_groups[group.name] = group
    
    def add_server(self, name: str, host: str, username: str, password: str, 
                   port: int = 443, model: str = None, service_tag: str = None,
                   location: str = None, environment: str = None, 
                   tags: List[str] = None, notes: str = None) -> str:
        """Add a new server to the fleet with duplicate detection"""
        
        # Check for duplicate server (same host, username, and port)
        for server_id, existing_server in self.servers.items():
            if (existing_server.host.lower() == host.lower() and 
                existing_server.username.lower() == username.lower() and 
                existing_server.port == port):
                logger.warning(f"Duplicate server detected: {name} ({host}:{port}) matches existing server {existing_server.name}")
                # Update existing server with new information if provided
                if name != existing_server.name:
                    existing_server.name = name
                    logger.info(f"Updated server name to: {name}")
                if model:
                    existing_server.model = model
                if service_tag:
                    existing_server.service_tag = service_tag
                if location:
                    existing_server.location = location
                if environment:
                    existing_server.environment = environment
                if tags:
                    # Merge tags, avoiding duplicates
                    existing_tags = set(existing_server.tags or [])
                    new_tags = set(tags)
                    existing_server.tags = list(existing_tags.union(new_tags))
                if notes:
                    existing_server.notes = notes
                
                logger.info(f"Updated existing server {existing_server.name} with new information")
                return server_id
        
        # If no duplicate found, create new server
        server_id = str(uuid.uuid4())
        server = ServerInfo(
            id=server_id,
            name=name,
            host=host,
            port=port,
            username=username,
            password=password,
            model=model,
            service_tag=service_tag,
            location=location,
            environment=environment,
            tags=set(tags or []),
            notes=notes,
            status=ServerStatus.OFFLINE,
            health_score=0.0,
            alert_count=0,
            created_at=datetime.now(),
            last_seen=None
        )
        
        self.servers[server_id] = server
        
        # Add to default groups
        self.server_groups["All Servers"].server_ids.add(server_id)
        if server.environment:
            env_group = f"{server.environment.title()} Servers"
            if env_group not in self.server_groups:
                self.server_groups[env_group] = ServerGroup(env_group, f"{server.environment} environment servers")
            self.server_groups[env_group].server_ids.add(server_id)
        
        logger.info(f"Added server {name} ({host}) to fleet")
        return server_id
    
    def remove_server(self, server_id: str) -> bool:
        """Remove a server from the fleet"""
        if server_id not in self.servers:
            return False
        
        server = self.servers[server_id]
        
        # Stop monitoring
        if server_id in self.monitoring_tasks:
            self.monitoring_tasks[server_id].cancel()
            del self.monitoring_tasks[server_id]
        
        # Close connection
        if server_id in self.active_connections:
            # Close connection logic here
            del self.active_connections[server_id]
        
        # Remove from groups
        for group in self.server_groups.values():
            group.server_ids.discard(server_id)
        
        # Remove server
        del self.servers[server_id]
        
        logger.info(f"Removed server {server.name} from fleet")
        return True
    
    def update_server(self, server_id: str, **kwargs) -> bool:
        """Update server information"""
        if server_id not in self.servers:
            return False
        
        server = self.servers[server_id]
        
        # Update server fields
        for key, value in kwargs.items():
            if hasattr(server, key):
                if key == 'tags' and isinstance(value, list):
                    # Convert to set for tags
                    setattr(server, key, set(value))
                else:
                    setattr(server, key, value)
        
        logger.info(f"Updated server {server.name}")
        return True
    
    def delete_server(self, server_id: str) -> bool:
        """Delete a server from the fleet"""
        if server_id not in self.servers:
            return False
        
        server_name = self.servers[server_id].name
        
        # Disconnect if connected
        if server_id in self.active_connections:
            asyncio.create_task(self.disconnect_server(server_id))
        
        # Remove from all groups
        for group in self.server_groups.values():
            group.server_ids.discard(server_id)
        
        # Delete server
        del self.servers[server_id]
        
        logger.info(f"Deleted server {server_name} from fleet")
        return True
    
    def get_server(self, server_id: str) -> Optional[ServerInfo]:
        """Get server information"""
        return self.servers.get(server_id)
    
    def get_servers_by_group(self, group_name: str) -> List[ServerInfo]:
        """Get all servers in a group"""
        if group_name not in self.server_groups:
            return []
        
        group = self.server_groups[group_name]
        return [self.servers[sid] for sid in group.server_ids if sid in self.servers]
    
    def get_servers_by_tag(self, tag: str) -> List[ServerInfo]:
        """Get all servers with a specific tag"""
        return [server for server in self.servers.values() if tag in server.tags]
    
    def get_servers_by_environment(self, environment: str) -> List[ServerInfo]:
        """Get all servers in a specific environment"""
        return [server for server in self.servers.values() if server.environment == environment]
    
    async def connect_server(self, server_id: str) -> bool:
        """Connect to a specific server"""
        if server_id not in self.servers:
            return False
        
        server = self.servers[server_id]
        server.status = ServerStatus.CONNECTING
        
        try:
            # Import here to avoid circular imports
            from integrations.redfish_client import RedfishClient
            
            # Create connection
            client = RedfishClient(
                host=server.host,
                username=server.username,
                password=server.password,
                port=server.port
            )
            
            success = await client.connect()
            
            if success:
                self.active_connections[server_id] = client
                server.status = ServerStatus.ONLINE
                server.last_seen = datetime.now()
                
                # Start monitoring
                await self.start_monitoring(server_id)
                
                logger.info(f"Connected to server {server.name}")
                return True
            else:
                server.status = ServerStatus.ERROR
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to server {server.name}: {e}")
            server.status = ServerStatus.ERROR
            return False
    
    async def disconnect_server(self, server_id: str) -> bool:
        """Disconnect from a specific server"""
        if server_id not in self.servers:
            return False
        
        server = self.servers[server_id]
        
        # Stop monitoring
        if server_id in self.monitoring_tasks:
            self.monitoring_tasks[server_id].cancel()
            del self.monitoring_tasks[server_id]
        
        # Close connection
        if server_id in self.active_connections:
            try:
                await self.active_connections[server_id].disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting from {server.name}: {e}")
            del self.active_connections[server_id]
        
        server.status = ServerStatus.OFFLINE
        logger.info(f"Disconnected from server {server.name}")
        return True
    
    async def start_monitoring(self, server_id: str):
        """Start monitoring a server"""
        if server_id not in self.servers or server_id in self.monitoring_tasks:
            return
        
        server = self.servers[server_id]
        
        # Create monitoring task
        self.monitoring_tasks[server_id] = asyncio.create_task(
            self._monitor_server_loop(server_id)
        )
        
        logger.info(f"Started monitoring server {server.name}")
    
    async def stop_monitoring(self, server_id: str):
        """Stop monitoring a server"""
        if server_id in self.monitoring_tasks:
            self.monitoring_tasks[server_id].cancel()
            del self.monitoring_tasks[server_id]
            logger.info(f"Stopped monitoring server {self.servers[server_id].name}")
    
    async def _monitor_server_loop(self, server_id: str):
        """Main monitoring loop for a server"""
        server = self.servers[server_id]
        
        while True:
            try:
                if server_id not in self.active_connections:
                    # Try to reconnect
                    await self.connect_server(server_id)
                    if server_id not in self.active_connections:
                        await asyncio.sleep(30)  # Wait before retry
                        continue
                
                client = self.active_connections[server_id]
                
                # Collect metrics with error handling
                try:
                    metrics = await self._collect_server_metrics(client, server_id)
                    
                    # Update server health
                    health_score = self._calculate_health_score(metrics)
                    server.health_score = health_score
                    
                    # Check for alerts
                    await self._check_server_alerts(server_id, metrics)
                    
                    # Update last seen
                    server.last_seen = datetime.now()
                    
                    # If we got here successfully, update status to online
                    if server.status == ServerStatus.ERROR:
                        server.status = ServerStatus.ONLINE
                        logger.info(f"Server {server.name} monitoring recovered")
                    
                except Exception as metrics_error:
                    logger.warning(f"Metrics collection error for {server.name}: {metrics_error}")
                    # Don't change status to error for metrics issues, just log it
                
                # Wait before next check
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Critical error monitoring server {server.name}: {e}")
                server.status = ServerStatus.ERROR
                await asyncio.sleep(60)
    
    async def _collect_server_metrics(self, client, server_id: str) -> Dict[str, Any]:
        """Collect metrics from a server"""
        metrics = {}
        
        try:
            # Get thermal data
            try:
                thermal_data = await client.get_temperature_sensors()
                metrics['thermal'] = thermal_data if isinstance(thermal_data, dict) else {}
            except Exception as e:
                logger.warning(f"Failed to get thermal data for server {server_id}: {e}")
                metrics['thermal'] = {}
            
            # Get power data
            try:
                power_data = await client.get_power_supplies()
                metrics['power'] = power_data if isinstance(power_data, dict) else {}
            except Exception as e:
                logger.warning(f"Failed to get power data for server {server_id}: {e}")
                metrics['power'] = {}
            
            # Get memory data
            try:
                memory_data = await client.get_memory()
                metrics['memory'] = memory_data if isinstance(memory_data, dict) else {}
            except Exception as e:
                logger.warning(f"Failed to get memory data for server {server_id}: {e}")
                metrics['memory'] = {}
            
            # Get storage data
            try:
                storage_data = await client.get_storage_devices()
                metrics['storage'] = storage_data if isinstance(storage_data, dict) else {}
            except Exception as e:
                logger.warning(f"Failed to get storage data for server {server_id}: {e}")
                metrics['storage'] = {}
            
            # Get system info
            try:
                system_info = await client.get_system_info()
                metrics['system'] = system_info
            except Exception as e:
                logger.warning(f"Failed to get system info for server {server_id}: {e}")
                metrics['system'] = {}
            
        except Exception as e:
            logger.error(f"Error collecting metrics from server {server_id}: {e}")
        
        return metrics
    
    def _calculate_health_score(self, metrics: Dict[str, Any]) -> float:
        """Calculate health score for a server"""
        if not metrics:
            return 75.0  # Default score when no metrics available
        
        scores = []
        
        # Thermal health
        if 'thermal' in metrics and metrics['thermal']:
            thermal = metrics['thermal']
            temps = thermal.get('Temperatures', [])
            if temps:
                max_temp = max(temp.get('ReadingCelsius', 0) for temp in temps if isinstance(temp, dict))
                if max_temp > 85:
                    scores.append(20)  # Critical
                elif max_temp > 75:
                    scores.append(60)  # Warning
                else:
                    scores.append(100)  # Good
            else:
                scores.append(85)  # No thermal data, assume good
        else:
            scores.append(85)  # No thermal data, assume good
        
        # Power health
        if 'power' in metrics and metrics['power']:
            power = metrics['power']
            psus = power.get('PowerSupplies', [])
            if psus:
                healthy_psus = sum(1 for psu in psus if isinstance(psu, dict) and psu.get('Status', {}).get('Health') == 'OK')
                if psus:
                    power_score = (healthy_psus / len(psus)) * 100
                    scores.append(power_score)
            else:
                scores.append(85)  # No power data, assume good
        else:
            scores.append(85)  # No power data, assume good
        
        # Memory health
        if 'memory' in metrics and metrics['memory']:
            memory = metrics['memory']
            dimms = memory.get('Memory', [])
            if dimms:
                healthy_dimms = sum(1 for dimm in dimms if isinstance(dimm, dict) and dimm.get('Status', {}).get('Health') == 'OK')
                if dimms:
                    memory_score = (healthy_dimms / len(dimms)) * 100
                    scores.append(memory_score)
            else:
                scores.append(85)  # No memory data, assume good
        else:
            scores.append(85)  # No memory data, assume good
        
        # Storage health
        if 'storage' in metrics and metrics['storage']:
            storage = metrics['storage']
            drives = storage.get('drives', [])
            if drives:
                healthy_drives = sum(1 for drive in drives if isinstance(drive, dict) and not drive.get('FailurePredicted', False))
                if drives:
                    storage_score = (healthy_drives / len(drives)) * 100
                    scores.append(storage_score)
            else:
                scores.append(85)  # No storage data, assume good
        else:
            scores.append(85)  # No storage data, assume good
        
        # System health based on system info
        if 'system' in metrics and metrics['system']:
            system = metrics['system']
            if hasattr(system, 'status') and system.status:
                if system.status.health == 'OK':
                    scores.append(100)
                elif system.status.health == 'Warning':
                    scores.append(70)
                else:
                    scores.append(40)
            else:
                scores.append(85)  # No system status, assume good
        else:
            scores.append(85)  # No system data, assume good
        
        return sum(scores) / len(scores) if scores else 75.0
    
    async def _check_server_alerts(self, server_id: str, metrics: Dict[str, Any]):
        """Check for alerts on a server"""
        server = self.servers[server_id]
        alerts = []
        
        # Check thermal alerts
        if 'thermal' in metrics:
            thermal = metrics['thermal']
            temps = thermal.get('Temperatures', [])
            for temp in temps:
                temp_value = temp.get('ReadingCelsius', 0)
                if temp_value > 85:
                    alerts.append({
                        'server_id': server_id,
                        'server_name': server.name,
                        'type': 'critical',
                        'metric': 'temperature',
                        'message': f"Critical temperature: {temp.get('Name')} = {temp_value}°C",
                        'timestamp': datetime.now()
                    })
                elif temp_value > 75:
                    alerts.append({
                        'server_id': server_id,
                        'server_name': server.name,
                        'type': 'warning',
                        'metric': 'temperature',
                        'message': f"High temperature: {temp.get('Name')} = {temp_value}°C",
                        'timestamp': datetime.now()
                    })
        
        # Check power alerts
        if 'power' in metrics:
            power = metrics['power']
            psus = power.get('PowerSupplies', [])
            for i, psu in enumerate(psus):
                psu_status = psu.get('Status', {}).get('Health')
                if psu_status != 'OK':
                    alerts.append({
                        'server_id': server_id,
                        'server_name': server.name,
                        'type': 'critical',
                        'metric': 'power',
                        'message': f"PSU {i+1} status: {psu_status}",
                        'timestamp': datetime.now()
                    })
        
        # Update server alert count
        server.alert_count = len(alerts)
        
        # Add to fleet alerts
        self.alerts.extend(alerts)
        
        # Keep only recent alerts (last 1000)
        if len(self.alerts) > 1000:
            self.alerts = self.alerts[-1000:]
    
    async def connect_all_servers(self) -> Dict[str, bool]:
        """Connect to all servers in the fleet"""
        results = {}
        
        for server_id in self.servers:
            results[server_id] = await self.connect_server(server_id)
            # Small delay between connections
            await asyncio.sleep(0.5)
        
        return results
    
    async def disconnect_all_servers(self) -> Dict[str, bool]:
        """Disconnect from all servers in the fleet"""
        results = {}
        
        for server_id in list(self.servers.keys()):
            results[server_id] = await self.disconnect_server(server_id)
        
        return results
    
    async def run_fleet_health_check(self) -> Dict[str, Any]:
        """Run health check on all connected servers"""
        results = {
            'timestamp': datetime.now().isoformat(),
            'total_servers': len(self.servers),
            'connected_servers': len(self.active_connections),
            'servers': {}
        }
        
        for server_id, server in self.servers.items():
            server_result = {
                'name': server.name,
                'host': server.host,
                'status': server.status.value,
                'health_score': server.health_score,
                'alert_count': server.alert_count,
                'last_seen': server.last_seen.isoformat() if server.last_seen else None
            }
            
            # Get detailed metrics if connected
            if server_id in self.active_connections:
                try:
                    metrics = await self._collect_server_metrics(self.active_connections[server_id], server_id)
                    server_result['metrics'] = metrics
                except Exception as e:
                    server_result['error'] = str(e)
            
            results['servers'][server_id] = server_result
        
        return results
    
    def get_fleet_overview(self) -> Dict[str, Any]:
        """Get fleet overview statistics"""
        total_servers = len(self.servers)
        online_servers = len([s for s in self.servers.values() if s.status == ServerStatus.ONLINE])
        offline_servers = len([s for s in self.servers.values() if s.status == ServerStatus.OFFLINE])
        error_servers = len([s for s in self.servers.values() if s.status == ServerStatus.ERROR])
        
        # Calculate average health score
        health_scores = [s.health_score for s in self.servers.values() if s.health_score > 0]
        avg_health = sum(health_scores) / len(health_scores) if health_scores else 0
        
        # Count alerts
        total_alerts = sum(s.alert_count for s in self.servers.values())
        
        # Group distribution
        group_counts = {}
        for group_name, group in self.server_groups.items():
            group_counts[group_name] = len(group.server_ids)
        
        # Environment distribution
        env_counts = defaultdict(int)
        for server in self.servers.values():
            if server.environment:
                env_counts[server.environment] += 1
        
        return {
            'timestamp': datetime.now().isoformat(),
            'total_servers': total_servers,
            'online_servers': online_servers,
            'offline_servers': offline_servers,
            'error_servers': error_servers,
            'average_health_score': round(avg_health, 1),
            'total_alerts': total_alerts,
            'groups': group_counts,
            'environments': dict(env_counts),
            'servers': {
                server_id: {
                    'name': server.name,
                    'host': server.host,
                    'status': server.status.value,
                    'health_score': server.health_score,
                    'alert_count': server.alert_count,
                    'environment': server.environment,
                    'location': server.location,
                    'tags': list(server.tags),
                    'groups': list(server.groups),
                    'last_seen': server.last_seen.isoformat() if server.last_seen else None
                }
                for server_id, server in self.servers.items()
            }
        }
    
    def get_recent_alerts(self, hours: int = 24, limit: int = 100) -> List[Dict]:
        """Get recent alerts from all servers"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        recent_alerts = [
            alert for alert in self.alerts
            if alert['timestamp'] >= cutoff_time
        ]
        
        # Sort by timestamp (newest first) and limit
        recent_alerts.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return recent_alerts[:limit]
    
    def create_group(self, name: str, description: str = "", server_ids: List[str] = None) -> str:
        """Create a new server group"""
        if name in self.server_groups:
            raise ValueError(f"Group '{name}' already exists")
        
        group = ServerGroup(name, description)
        
        if server_ids:
            for server_id in server_ids:
                if server_id in self.servers:
                    group.server_ids.add(server_id)
                    self.servers[server_id].groups.add(name)
        
        self.server_groups[name] = group
        logger.info(f"Created group '{name}' with {len(group.server_ids)} servers")
        
        return name
    
    def delete_group(self, name: str) -> bool:
        """Delete a server group"""
        if name not in self.server_groups:
            return False
        
        # Don't allow deleting default groups
        if name in ["All Servers", "Production", "Critical", "Development"]:
            return False
        
        group = self.server_groups[name]
        
        # Remove group from servers
        for server_id in group.server_ids:
            if server_id in self.servers:
                self.servers[server_id].groups.discard(name)
        
        del self.server_groups[name]
        logger.info(f"Deleted group '{name}'")
        
        return True
    
    def add_server_to_group(self, server_id: str, group_name: str) -> bool:
        """Add a server to a group"""
        if server_id not in self.servers or group_name not in self.server_groups:
            return False
        
        self.server_groups[group_name].server_ids.add(server_id)
        self.servers[server_id].groups.add(group_name)
        
        logger.info(f"Added server {self.servers[server_id].name} to group {group_name}")
        return True
    
    def remove_server_from_group(self, server_id: str, group_name: str) -> bool:
        """Remove a server from a group"""
        if server_id not in self.servers or group_name not in self.server_groups:
            return False
        
        self.server_groups[group_name].server_ids.discard(server_id)
        self.servers[server_id].groups.discard(group_name)
        
        logger.info(f"Removed server {self.servers[server_id].name} from group {group_name}")
        return True

# Global fleet manager instance
fleet_manager = FleetManager()
