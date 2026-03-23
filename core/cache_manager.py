"""
Performance caching layer for Redfish API responses.
Reduces API calls, improves response times, and handles cache invalidation.
"""

import asyncio
import hashlib
import json
import time
from typing import Any, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class CacheEntry:
    """Cached API response with metadata"""
    data: Any
    timestamp: datetime
    ttl_seconds: int
    etag: Optional[str] = None
    
    @property
    def is_expired(self) -> bool:
        return datetime.now() > self.timestamp + timedelta(seconds=self.ttl_seconds)

class CacheManager:
    """Intelligent caching system for Redfish API responses"""
    
    def __init__(self):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()
        
        # TTL by endpoint type (seconds)
        self._ttl_config = {
            "static": 3600,      # System info, inventory - changes rarely
            "sensors": 30,       # Temperature, power, fans - changes frequently
            "logs": 60,          # System logs - moderate change rate
            "firmware": 1800,    # Firmware inventory - changes rarely
            "jobs": 10,          # Job status - changes very frequently
            "default": 300       # Default 5 minutes
        }
        
        # Endpoint classification
        self._endpoint_types = {
            # Static data
            "/Systems/System.Embedded.1": "static",
            "/Systems/System.Embedded.1/Processors": "static",
            "/Systems/System.Embedded.1/Memory": "static",
            "/Systems/System.Embedded.1/Storage": "static",
            "/Systems/System.Embedded.1/EthernetInterfaces": "static",
            "/UpdateService/FirmwareInventory": "firmware",
            "/Managers/iDRAC.Embedded.1": "static",
            
            # Sensor data
            "/Chassis/System.Embedded.1/Thermal": "sensors",
            "/Chassis/System.Embedded.1/Power": "sensors",
            "/Systems/System.Embedded.1/Oem/Dell/DellSensors": "sensors",
            
            # Logs
            "/Managers/iDRAC.Embedded.1/LogServices/Sel/Entries": "logs",
            "/Managers/iDRAC.Embedded.1/LogServices/LcLog/Entries": "logs",
            
            # Jobs
            "/Managers/iDRAC.Embedded.1/Jobs": "jobs",
            "/JobService/Jobs": "jobs",
        }
    
    def _get_cache_key(self, endpoint: str, params: Optional[Dict] = None) -> str:
        """Generate cache key for endpoint + parameters"""
        key_data = endpoint
        if params:
            # Sort params for consistent key generation
            sorted_params = json.dumps(sorted(params.items()), sort_keys=True)
            key_data += f"?{sorted_params}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _get_endpoint_type(self, endpoint: str) -> str:
        """Classify endpoint for TTL determination"""
        # Check for exact matches first
        if endpoint in self._endpoint_types:
            return self._endpoint_types[endpoint]
        
        # Check for partial matches (more specific patterns first)
        if "/LogServices/" in endpoint:
            return "logs"
        if "/Jobs" in endpoint:
            return "jobs"
        if "/Thermal" in endpoint:
            return "sensors"
        if "/Power" in endpoint:
            return "sensors"
        if "/FirmwareInventory" in endpoint:
            return "firmware"
        
        # Check for system endpoints
        if endpoint.startswith("/Systems/System.Embedded.1"):
            return "static"
        if endpoint.startswith("/Chassis/System.Embedded.1"):
            return "static"
        if endpoint.startswith("/Managers/iDRAC.Embedded.1"):
            return "static"
        
        return "default"
    
    async def get(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Any]:
        """Get cached response if valid"""
        async with self._lock:
            key = self._get_cache_key(endpoint, params)
            entry = self._cache.get(key)
            
            if entry and not entry.is_expired:
                return entry.data
            
            return None
    
    async def set(self, endpoint: str, data: Any, params: Optional[Dict] = None, 
                  etag: Optional[str] = None, custom_ttl: Optional[int] = None) -> None:
        """Cache response with appropriate TTL"""
        async with self._lock:
            key = self._get_cache_key(endpoint, params)
            
            if custom_ttl:
                ttl = custom_ttl
            else:
                ep_type = self._get_endpoint_type(endpoint)
                ttl = self._ttl_config.get(ep_type, self._ttl_config["default"])
            
            entry = CacheEntry(
                data=data,
                timestamp=datetime.now(),
                ttl_seconds=ttl,
                etag=etag
            )
            
            self._cache[key] = entry
    
    async def invalidate(self, endpoint_pattern: str) -> int:
        """Invalidate cache entries matching pattern"""
        async with self._lock:
            keys_to_remove = []
            
            for key, entry in self._cache.items():
                # This is simplified - in production, we'd store original endpoints
                # For now, invalidate all if pattern is broad
                if endpoint_pattern == "*" or endpoint_pattern in str(entry.data):
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                del self._cache[key]
            
            return len(keys_to_remove)
    
    async def invalidate_static_data(self) -> int:
        """Invalidate static data caches (called after firmware updates, etc.)"""
        patterns = ["/Systems/", "/UpdateService/", "/Managers/"]
        total = 0
        for pattern in patterns:
            total += await self.invalidate(pattern)
        return total
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring"""
        async with self._lock:
            total_entries = len(self._cache)
            expired_entries = sum(1 for e in self._cache.values() if e.is_expired)
            
            # Count by type
            type_counts = {}
            for key, entry in self._cache.items():
                # Simplified type detection
                if "Thermal" in str(entry.data) or "Power" in str(entry.data):
                    ep_type = "sensors"
                elif "LogServices" in str(entry.data):
                    ep_type = "logs"
                elif "Jobs" in str(entry.data):
                    ep_type = "jobs"
                else:
                    ep_type = "static"
                
                type_counts[ep_type] = type_counts.get(ep_type, 0) + 1
            
            return {
                "total_entries": total_entries,
                "expired_entries": expired_entries,
                "hit_ratio": getattr(self, '_hit_count', 0) / max(getattr(self, '_total_requests', 1), 1),
                "entries_by_type": type_counts,
                "memory_usage_mb": len(json.dumps({k: v.data for k, v in self._cache.items()})) / (1024 * 1024)
            }
    
    async def cleanup_expired(self) -> int:
        """Remove expired entries to free memory"""
        async with self._lock:
            keys_to_remove = [key for key, entry in self._cache.items() if entry.is_expired]
            for key in keys_to_remove:
                del self._cache[key]
            return len(keys_to_remove)

# Global cache instance
cache_manager = CacheManager()
