"""
Dell EMC Storage Array Integration for Dell Server AI Agent
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import aiohttp
import json
from urllib.parse import urljoin

from models.server_models import ComponentType, Severity, LogEntry

logger = logging.getLogger(__name__)

class DellEMCStorageClient:
    """Dell EMC Storage Array Integration Client"""
    
    def __init__(self, host: str, username: str, password: str, port: int = 443, verify_ssl: bool = False):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.verify_ssl = verify_ssl
        self.base_url = f"https://{host}:{port}/api/rest"
        self.session = None
        self.auth_token = None
        
    async def connect(self) -> bool:
        """Establish connection to Dell EMC Storage Array"""
        try:
            import ssl
            ssl_context = ssl.create_default_context()
            if not self.verify_ssl:
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=30),
                auth=aiohttp.BasicAuth(self.username, self.password)
            )
            
            # Test connection
            system_info = await self._get_system_info()
            if system_info:
                logger.info(f"Connected to Dell EMC Storage Array: {self.host}")
                return True
            else:
                logger.error("Failed to connect to Dell EMC Storage Array")
                return False
                
        except Exception as e:
            logger.error(f"Dell EMC Storage connection error: {str(e)}")
            return False
    
    async def disconnect(self):
        """Close the connection"""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def _get(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """Make GET request to Dell EMC Storage API"""
        if not self.session:
            raise RuntimeError("Not connected to Dell EMC Storage Array")
        
        url = urljoin(self.base_url, endpoint)
        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"GET request failed: {response.status} - {await response.text()}")
                    return None
        except Exception as e:
            logger.error(f"GET request error: {str(e)}")
            return None
    
    async def _post(self, endpoint: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Make POST request to Dell EMC Storage API"""
        if not self.session:
            raise RuntimeError("Not connected to Dell EMC Storage Array")
        
        url = urljoin(self.base_url, endpoint)
        try:
            async with self.session.post(url, json=data) as response:
                if response.status in [200, 201, 202]:
                    return await response.json()
                else:
                    logger.error(f"POST request failed: {response.status} - {await response.text()}")
                    return None
        except Exception as e:
            logger.error(f"POST request error: {str(e)}")
            return None
    
    async def _get_system_info(self) -> Optional[Dict[str, Any]]:
        """Get storage array system information"""
        return await self._get("system")
    
    async def get_storage_pools(self) -> List[Dict[str, Any]]:
        """Get storage pool information"""
        try:
            pools_data = await self._get("storage_pool")
            if not pools_data:
                return []
            
            pools = []
            for pool in pools_data.get("storage_pool", []):
                pool_info = {
                    "id": pool.get("id"),
                    "name": pool.get("name"),
                    "size_total_gb": pool.get("size_total", 0) / (1024**3) if pool.get("size_total") else 0,
                    "size_free_gb": pool.get("size_free", 0) / (1024**3) if pool.get("size_free") else 0,
                    "size_used_gb": pool.get("size_used", 0) / (1024**3) if pool.get("size_used") else 0,
                    "raid_level": pool.get("raid_level"),
                    "status": pool.get("status", "unknown"),
                    "health": pool.get("health", "unknown"),
                    "num_volumes": len(pool.get("volume", [])),
                    "pool_type": pool.get("pool_type", "traditional")
                }
                pools.append(pool_info)
            
            return pools
            
        except Exception as e:
            logger.error(f"Failed to get storage pools: {str(e)}")
            return []
    
    async def get_volumes(self) -> List[Dict[str, Any]]:
        """Get storage volume information"""
        try:
            volumes_data = await self._get("volume")
            if not volumes_data:
                return []
            
            volumes = []
            for volume in volumes_data.get("volume", []):
                volume_info = {
                    "id": volume.get("id"),
                    "name": volume.get("name"),
                    "size_gb": volume.get("size", 0) / (1024**3) if volume.get("size") else 0,
                    "volume_type": volume.get("volume_type"),
                    "status": volume.get("status", "unknown"),
                    "health": volume.get("health", "unknown"),
                    "pool_id": volume.get("pool_id"),
                    "wwn": volume.get("wwn"),
                    "mapped": volume.get("is_mapped", False),
                    "num_hosts": len(volume.get("host", [])),
                    "performance_tier": volume.get("performance_tier", "unknown")
                }
                volumes.append(volume_info)
            
            return volumes
            
        except Exception as e:
            logger.error(f"Failed to get volumes: {str(e)}")
            return []
    
    async def get_physical_disks(self) -> List[Dict[str, Any]]:
        """Get physical disk information"""
        try:
            disks_data = await self._get("disk")
            if not disks_data:
                return []
            
            disks = []
            for disk in disks_data.get("disk", []):
                disk_info = {
                    "id": disk.get("id"),
                    "name": disk.get("name"),
                    "serial_number": disk.get("serial_number"),
                    "size_gb": disk.get("size", 0) / (1024**3) if disk.get("size") else 0,
                    "manufacturer": disk.get("manufacturer"),
                    "model": disk.get("model"),
                    "type": disk.get("type"),
                    "speed_rpm": disk.get("speed_rpm"),
                    "status": disk.get("status", "unknown"),
                    "health": disk.get("health", "unknown"),
                    "temperature_celsius": disk.get("temperature"),
                    "power_on_hours": disk.get("power_on_hours"),
                    "location": disk.get("location"),
                    "pool_id": disk.get("pool_id")
                }
                disks.append(disk_info)
            
            return disks
            
        except Exception as e:
            logger.error(f"Failed to get physical disks: {str(e)}")
            return []
    
    async def get_storage_controllers(self) -> List[Dict[str, Any]]:
        """Get storage controller information"""
        try:
            controllers_data = await self._get("controller")
            if not controllers_data:
                return []
            
            controllers = []
            for controller in controllers_data.get("controller", []):
                controller_info = {
                    "id": controller.get("id"),
                    "name": controller.get("name"),
                    "model": controller.get("model"),
                    "serial_number": controller.get("serial_number"),
                    "status": controller.get("status", "unknown"),
                    "health": controller.get("health", "unknown"),
                    "firmware_version": controller.get("firmware_version"),
                    "cache_size_mb": controller.get("cache_size", 0) / (1024**2) if controller.get("cache_size") else 0,
                    "battery_status": controller.get("battery_status", "unknown"),
                    "temperature_celsius": controller.get("temperature"),
                    "num_ports": len(controller.get("port", [])),
                    "cpu_utilization": controller.get("cpu_utilization"),
                    "memory_utilization": controller.get("memory_utilization")
                }
                controllers.append(controller_info)
            
            return controllers
            
        except Exception as e:
            logger.error(f"Failed to get storage controllers: {str(e)}")
            return []
    
    async def get_performance_metrics(self) -> Dict[str, Any]:
        """Get storage performance metrics"""
        try:
            perf_data = await self._get("performance")
            if not perf_data:
                return {}
            
            metrics = {
                "timestamp": datetime.now().isoformat(),
                "iops_read": perf_data.get("iops_read", 0),
                "iops_write": perf_data.get("iops_write", 0),
                "throughput_read_mbps": perf_data.get("throughput_read", 0) / (1024**2) if perf_data.get("throughput_read") else 0,
                "throughput_write_mbps": perf_data.get("throughput_write", 0) / (1024**2) if perf_data.get("throughput_write") else 0,
                "latency_read_ms": perf_data.get("latency_read", 0),
                "latency_write_ms": perf_data.get("latency_write", 0),
                "cache_hit_ratio": perf_data.get("cache_hit_ratio", 0),
                "queue_depth": perf_data.get("queue_depth", 0),
                "cpu_utilization": perf_data.get("cpu_utilization", 0),
                "memory_utilization": perf_data.get("memory_utilization", 0)
            }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to get performance metrics: {str(e)}")
            return {}
    
    async def get_storage_logs(self, hours: int = 24) -> List[LogEntry]:
        """Get storage array logs"""
        try:
            logs_data = await self._get("log", {"hours": hours})
            if not logs_data:
                return []
            
            logs = []
            for log_entry in logs_data.get("log", []):
                severity_map = {
                    "INFO": Severity.INFO,
                    "WARNING": Severity.WARNING,
                    "ERROR": Severity.ERROR,
                    "CRITICAL": Severity.CRITICAL
                }
                
                log = LogEntry(
                    timestamp=datetime.fromisoformat(log_entry.get("timestamp", "").replace("Z", "+00:00")),
                    severity=severity_map.get(log_entry.get("severity", "INFO"), Severity.INFO),
                    message=log_entry.get("message", ""),
                    source="Dell EMC Storage",
                    component=ComponentType.STORAGE,
                    event_id=log_entry.get("id"),
                    raw_data=log_entry
                )
                logs.append(log)
            
            return sorted(logs, key=lambda x: x.timestamp, reverse=True)
            
        except Exception as e:
            logger.error(f"Failed to get storage logs: {str(e)}")
            return []
    
    async def create_volume(self, name: str, size_gb: int, pool_id: str, 
                          volume_type: str = "thin") -> Optional[Dict[str, Any]]:
        """Create a new storage volume"""
        try:
            volume_data = {
                "name": name,
                "size": size_gb * 1024**3,  # Convert to bytes
                "pool_id": pool_id,
                "volume_type": volume_type
            }
            
            result = await self._post("volume", volume_data)
            return result
            
        except Exception as e:
            logger.error(f"Failed to create volume: {str(e)}")
            return None
    
    async def delete_volume(self, volume_id: str) -> bool:
        """Delete a storage volume"""
        try:
            result = await self._post(f"volume/{volume_id}/delete", {})
            return result is not None
            
        except Exception as e:
            logger.error(f"Failed to delete volume: {str(e)}")
            return False
    
    async def expand_volume(self, volume_id: str, new_size_gb: int) -> bool:
        """Expand an existing volume"""
        try:
            expand_data = {
                "size": new_size_gb * 1024**3  # Convert to bytes
            }
            
            result = await self._post(f"volume/{volume_id}/expand", expand_data)
            return result is not None
            
        except Exception as e:
            logger.error(f"Failed to expand volume: {str(e)}")
            return False
    
    async def get_storage_health(self) -> Dict[str, Any]:
        """Get overall storage array health status"""
        try:
            pools = await self.get_storage_pools()
            controllers = await self.get_storage_controllers()
            disks = await self.get_physical_disks()
            
            # Calculate health metrics
            total_pools = len(pools)
            healthy_pools = len([p for p in pools if p.get("health") == "good"])
            
            total_controllers = len(controllers)
            healthy_controllers = len([c for c in controllers if c.get("health") == "good"])
            
            total_disks = len(disks)
            healthy_disks = len([d for d in disks if d.get("health") == "good"])
            
            # Determine overall health
            if (healthy_pools == total_pools and 
                healthy_controllers == total_controllers and 
                healthy_disks == total_disks):
                overall_health = "optimal"
            elif (healthy_pools >= total_pools * 0.9 and 
                  healthy_controllers >= total_controllers * 0.9 and 
                  healthy_disks >= total_disks * 0.9):
                overall_health = "good"
            elif (healthy_pools >= total_pools * 0.7 and 
                  healthy_controllers >= total_controllers * 0.7 and 
                  healthy_disks >= total_disks * 0.7):
                overall_health = "degraded"
            else:
                overall_health = "critical"
            
            return {
                "overall_health": overall_health,
                "total_pools": total_pools,
                "healthy_pools": healthy_pools,
                "total_controllers": total_controllers,
                "healthy_controllers": healthy_controllers,
                "total_disks": total_disks,
                "healthy_disks": healthy_disks,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get storage health: {str(e)}")
            return {
                "overall_health": "unknown",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    async def get_capacity_planning_info(self) -> Dict[str, Any]:
        """Get capacity planning information"""
        try:
            pools = await self.get_storage_pools()
            
            total_capacity = sum(p.get("size_total_gb", 0) for p in pools)
            used_capacity = sum(p.get("size_used_gb", 0) for p in pools)
            free_capacity = sum(p.get("size_free_gb", 0) for p in pools)
            
            # Calculate trends (simplified - in production would use historical data)
            utilization_rate = (used_capacity / total_capacity * 100) if total_capacity > 0 else 0
            
            # Predict when capacity will be exhausted (simplified linear projection)
            if utilization_rate > 80:
                time_to_full = "Critical - Less than 20% remaining"
            elif utilization_rate > 60:
                time_to_full = "Warning - Monitor growth"
            else:
                time_to_full = "Healthy"
            
            return {
                "total_capacity_gb": total_capacity,
                "used_capacity_gb": used_capacity,
                "free_capacity_gb": free_capacity,
                "utilization_rate": round(utilization_rate, 2),
                "time_to_full": time_to_full,
                "recommendations": self._generate_capacity_recommendations(utilization_rate, free_capacity),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get capacity planning info: {str(e)}")
            return {"error": str(e)}
    
    def _generate_capacity_recommendations(self, utilization_rate: float, free_capacity_gb: float) -> List[str]:
        """Generate capacity planning recommendations"""
        recommendations = []
        
        if utilization_rate > 90:
            recommendations.append("URGENT: Capacity critically low - immediate expansion required")
            recommendations.append("Consider data archiving or cleanup to free space")
        elif utilization_rate > 80:
            recommendations.append("HIGH PRIORITY: Plan capacity expansion within 30 days")
            recommendations.append("Monitor growth trends closely")
        elif utilization_rate > 70:
            recommendations.append("MEDIUM PRIORITY: Begin capacity planning for expansion")
            recommendations.append("Review data retention policies")
        elif utilization_rate > 50:
            recommendations.append("LOW PRIORITY: Monitor capacity trends")
            recommendations.append("Update capacity forecasts")
        else:
            recommendations.append("Good capacity utilization")
        
        if free_capacity_gb < 100:
            recommendations.append("Less than 100GB free - immediate attention required")
        elif free_capacity_gb < 500:
            recommendations.append("Less than 500GB free - plan for expansion")
        
        return recommendations
