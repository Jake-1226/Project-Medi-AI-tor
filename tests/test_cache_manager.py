"""
Tests for the cache manager system.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from core.cache_manager import CacheManager, CacheEntry


class TestCacheManager:
    """Test cases for CacheManager"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.cache = CacheManager()
    
    @pytest.mark.asyncio
    async def test_cache_set_and_get(self):
        """Test basic cache set and get operations"""
        endpoint = "/Systems/System.Embedded.1"
        data = {"test": "data", "value": 123}
        
        # Set cache
        await self.cache.set(endpoint, data)
        
        # Get from cache
        result = await self.cache.get(endpoint)
        
        assert result is not None
        assert result == data
    
    @pytest.mark.asyncio
    async def test_cache_miss(self):
        """Test cache miss scenario"""
        endpoint = "/NonExistent/Endpoint"
        
        result = await self.cache.get(endpoint)
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_cache_expiration(self):
        """Test cache entry expiration"""
        endpoint = "/Systems/System.Embedded.1"
        data = {"test": "data"}
        
        # Set with very short TTL
        await self.cache.set(endpoint, data, custom_ttl=1)
        
        # Should be available immediately
        result = await self.cache.get(endpoint)
        assert result == data
        
        # Wait for expiration
        await asyncio.sleep(2)
        
        # Should be expired now
        result = await self.cache.get(endpoint)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_cache_with_params(self):
        """Test cache with parameters"""
        endpoint = "/Systems/System.Embedded.1"
        params1 = {"expand": "."}
        params2 = {"expand": "*", "levels": "1"}
        data1 = {"test": "data1"}
        data2 = {"test": "data2"}
        
        # Set cache with different params
        await self.cache.set(endpoint, data1, params1)
        await self.cache.set(endpoint, data2, params2)
        
        # Get with specific params
        result1 = await self.cache.get(endpoint, params1)
        result2 = await self.cache.get(endpoint, params2)
        
        assert result1 == data1
        assert result2 == data2
        assert result1 != result2
    
    @pytest.mark.asyncio
    async def test_cache_invalidation(self):
        """Test cache invalidation"""
        endpoint1 = "/Systems/System.Embedded.1"
        endpoint2 = "/Chassis/System.Embedded.1"
        data1 = {"test": "data1"}
        data2 = {"test": "data2"}
        
        # Set cache entries
        await self.cache.set(endpoint1, data1)
        await self.cache.set(endpoint2, data2)
        
        # Verify both are cached
        assert await self.cache.get(endpoint1) == data1
        assert await self.cache.get(endpoint2) == data2
        
        # Invalidate all
        cleared = await self.cache.invalidate("*")
        
        assert cleared == 2
        assert await self.cache.get(endpoint1) is None
        assert await self.cache.get(endpoint2) is None
    
    @pytest.mark.asyncio
    async def test_cache_static_data_invalidation(self):
        """Test static data cache invalidation"""
        endpoints = [
            "/Systems/System.Embedded.1",
            "/UpdateService/FirmwareInventory",
            "/Managers/iDRAC.Embedded.1"
        ]
        
        # Set static data
        for endpoint in endpoints:
            await self.cache.set(endpoint, {"data": f"static_{endpoint}"})
        
        # Verify cached
        for endpoint in endpoints:
            assert await self.cache.get(endpoint) is not None
        
        # Invalidate static data
        cleared = await self.cache.invalidate_static_data()
        
        assert cleared == len(endpoints)
        
        # Verify cleared
        for endpoint in endpoints:
            assert await self.cache.get(endpoint) is None
    
    @pytest.mark.asyncio
    async def test_cache_ttl_by_endpoint_type(self):
        """Test TTL assignment by endpoint type"""
        # Static endpoint should have long TTL
        static_endpoint = "/Systems/System.Embedded.1"
        static_data = {"test": "static"}
        
        await self.cache.set(static_endpoint, static_data)
        entry = self.cache._cache[self.cache._get_cache_key(static_endpoint)]
        
        assert entry.ttl_seconds == self.cache._ttl_config["static"]
        
        # Sensor endpoint should have short TTL
        sensor_endpoint = "/Chassis/System.Embedded.1/Thermal"
        sensor_data = {"test": "sensor"}
        
        await self.cache.set(sensor_endpoint, sensor_data)
        entry = self.cache._cache[self.cache._get_cache_key(sensor_endpoint)]
        
        assert entry.ttl_seconds == self.cache._ttl_config["sensors"]
    
    @pytest.mark.asyncio
    async def test_cache_cleanup_expired(self):
        """Test cleanup of expired entries"""
        # Set some entries
        await self.cache.set("/endpoint1", {"data": "1"}, custom_ttl=1)
        await self.cache.set("/endpoint2", {"data": "2"}, custom_ttl=3600)
        
        # Wait for first to expire
        await asyncio.sleep(2)
        
        # Cleanup expired
        cleared = await self.cache.cleanup_expired()
        
        assert cleared == 1
        assert await self.cache.get("/endpoint1") is None
        assert await self.cache.get("/endpoint2") is not None
    
    @pytest.mark.asyncio
    async def test_cache_stats(self):
        """Test cache statistics"""
        # Add some entries
        await self.cache.set("/static", {"data": "static"})
        await self.cache.set("/sensors", {"data": "sensors"})
        await self.cache.set("/jobs", {"data": "jobs"})
        
        stats = await self.cache.get_cache_stats()
        
        assert stats["total_entries"] == 3
        assert stats["expired_entries"] == 0
        assert "entries_by_type" in stats
        assert "memory_usage_mb" in stats
        assert stats["memory_usage_mb"] > 0
    
    @pytest.mark.asyncio
    async def test_cache_etag_support(self):
        """Test ETag support in cache"""
        endpoint = "/Systems/System.Embedded.1"
        data = {"test": "data"}
        etag = '"123456789"'
        
        # Set with ETag
        await self.cache.set(endpoint, data, etag=etag)
        
        # Get cache entry
        key = self.cache._get_cache_key(endpoint)
        entry = self.cache._cache[key]
        
        assert entry.etag == etag
    
    @pytest.mark.asyncio
    async def test_concurrent_access(self):
        """Test concurrent cache access"""
        endpoint = "/concurrent/endpoint"
        
        # Concurrent sets
        tasks = []
        for i in range(10):
            task = self.cache.set(endpoint, {"value": i})
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
        # Should still work
        result = await self.cache.get(endpoint)
        assert result is not None
        assert "value" in result
    
    def test_cache_key_generation(self):
        """Test cache key generation"""
        endpoint = "/Systems/System.Embedded.1"
        params1 = {"expand": "."}
        params2 = {"expand": "*"}
        params3 = {"expand": "."}  # Same as params1
        
        key1 = self.cache._get_cache_key(endpoint, params1)
        key2 = self.cache._get_cache_key(endpoint, params2)
        key3 = self.cache._get_cache_key(endpoint, params3)
        
        # Keys should be different for different params
        assert key1 != key2
        
        # Keys should be same for same params
        assert key1 == key3
        
        # Keys should be consistent
        assert key1 == self.cache._get_cache_key(endpoint, params1)
    
    def test_endpoint_type_classification(self):
        """Test endpoint type classification"""
        # Static endpoints
        assert self.cache._get_endpoint_type("/Systems/System.Embedded.1") == "static"
        assert self.cache._get_endpoint_type("/UpdateService/FirmwareInventory") == "firmware"
        
        # Sensor endpoints
        assert self.cache._get_endpoint_type("/Chassis/System.Embedded.1/Thermal") == "sensors"
        assert self.cache._get_endpoint_type("/Chassis/System.Embedded.1/Power") == "sensors"
        
        # Log endpoints
        assert self.cache._get_endpoint_type("/Managers/iDRAC.Embedded.1/LogServices/Sel/Entries") == "logs"
        
        # Job endpoints
        assert self.cache._get_endpoint_type("/Managers/iDRAC.Embedded.1/Jobs") == "jobs"
        
        # Default
        assert self.cache._get_endpoint_type("/Some/Other/Endpoint") == "default"
