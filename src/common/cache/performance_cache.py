"""
Performance Caching Utilities

Redis-based caching for agent performance data to improve API response times
and reduce database load.
"""

import json
import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import redis
from config.settings import settings
import logging
logger = logging.getLogger(__name__)


class PerformanceCache:
    """Redis-based cache for agent performance data."""
    
    _instance = None
    _instance_count = 0
    
    def __new__(cls):
        """Singleton pattern to ensure only one instance."""
        if cls._instance is None:
            cls._instance_count += 1
            instance_id = cls._instance_count
            logger.info(f"🏭 Creating PerformanceCache singleton instance #{instance_id}")
            cls._instance = super().__new__(cls)
        else:
            logger.info("🔄 Reusing existing PerformanceCache singleton instance")
        return cls._instance
    
    def __init__(self):
        """Initialize Redis connection."""
        # Check if already initialized to avoid re-initialization
        if hasattr(self, '_initialized'):
            return
            
        try:
            logger.info("🔗 Attempting to connect to Redis...")
            logger.info(f"   Host: {settings.redis_host}")
            logger.info(f"   Port: {settings.redis_port}")
            logger.info(f"   DB: {settings.redis_db}")
            
            self.redis_client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                password=settings.redis_password,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            # Test connection
            result = self.redis_client.ping()
            logger.info(f"✅ Redis connection successful: {result}")
            logger.info("Redis connection established successfully")
            
            # Mark as initialized
            self._initialized = True
            
        except Exception as e:
            logger.info(f"❌ Redis connection failed: {e}")
            logger.info("⚠️  Caching will be disabled - performance may be slower")
            logger.warning(f"Redis connection failed, caching disabled: {e}")
            self.redis_client = None
            self._initialized = True
    
    def is_available(self) -> bool:
        """Check if Redis cache is available."""
        return self.redis_client is not None
    
    def get_agent_overview(self, days: int) -> Optional[List[Dict[str, Any]]]:
        """Get cached agent overview data."""
        if not self.is_available():
            logger.info("🚫 Redis not available - cache miss for agent overview")
            return None
        
        try:
            cache_key = f"agent_overview:{days}"
            logger.info(f"🔍 Checking cache for key: {cache_key}")
            
            # Check if key exists before getting
            exists = self.redis_client.exists(cache_key)
            logger.info(f"📋 Key exists: {exists}")
            
            if exists:
                # Check TTL
                ttl = self.redis_client.ttl(cache_key)
                logger.info(f"⏰ Key TTL: {ttl} seconds")
            
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                logger.info(f"✅ Cache HIT for {cache_key}")
                return json.loads(cached_data)
            else:
                logger.info(f"❌ Cache MISS for {cache_key}")
                # Check all keys in Redis for debugging
                all_keys = self.redis_client.keys("*")
                logger.info(f"🔎 All Redis keys: {all_keys}")
        except Exception as e:
            logger.info(f"💥 Error getting cached agent overview: {e}")
            logger.error(f"Error getting cached agent overview: {e}")
        return None
    
    def set_agent_overview(self, days: int, data: List[Dict[str, Any]], ttl: int = 300) -> bool:
        """Cache agent overview data."""
        if not self.is_available():
            logger.info("🚫 Redis not available - cannot cache agent overview")
            return False
        
        try:
            cache_key = f"agent_overview:{days}"
            logger.info(f"💾 Caching data for key: {cache_key} (TTL: {ttl}s)")
            result = self.redis_client.setex(
                cache_key, 
                ttl, 
                json.dumps(data, default=str)
            )
            if result:
                logger.info(f"✅ Successfully cached {cache_key}")
            else:
                logger.info(f"❌ Failed to cache {cache_key}")
            return result
        except Exception as e:
            logger.info(f"💥 Error caching agent overview: {e}")
            logger.error(f"Error caching agent overview: {e}")
            return False
    
    def get_agent_performance(self, agent_id: str, days: int) -> Optional[Dict[str, Any]]:
        """Get cached agent performance data."""
        if not self.is_available():
            return None
        
        try:
            cache_key = f"agent_performance:{agent_id}:{days}"
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            logger.error(f"Error getting cached agent performance: {e}")
        return None
    
    def set_agent_performance(self, agent_id: str, days: int, data: Dict[str, Any], ttl: int = 300) -> bool:
        """Cache agent performance data."""
        if not self.is_available():
            return False
        
        try:
            cache_key = f"agent_performance:{agent_id}:{days}"
            return self.redis_client.setex(
                cache_key, 
                ttl, 
                json.dumps(data, default=str)
            )
        except Exception as e:
            logger.error(f"Error caching agent performance: {e}")
            return False
    
    def get_agent_registry(self) -> Optional[Dict[str, Any]]:
        """Get cached agent registry."""
        if not self.is_available():
            return None
        
        try:
            cache_key = "agent_registry"
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            logger.error(f"Error getting cached agent registry: {e}")
        return None
    
    def set_agent_registry(self, data: Dict[str, Any], ttl: int = 300) -> bool:
        """Cache agent registry."""
        if not self.is_available():
            return False
        
        try:
            cache_key = "agent_registry"
            return self.redis_client.setex(
                cache_key, 
                ttl, 
                json.dumps(data, default=str)
            )
        except Exception as e:
            logger.error(f"Error caching agent registry: {e}")
            return False
    
    def get_metrics_summary(self, days: int) -> Optional[Dict[str, Any]]:
        """Get cached metrics summary."""
        if not self.is_available():
            return None
        
        try:
            cache_key = f"metrics_summary:{days}"
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            logger.error(f"Error getting cached metrics summary: {e}")
        return None
    
    def set_metrics_summary(self, days: int, data: Dict[str, Any], ttl: int = 300) -> bool:
        """Cache metrics summary."""
        if not self.is_available():
            return False
        
        try:
            cache_key = f"metrics_summary:{days}"
            return self.redis_client.setex(
                cache_key, 
                ttl, 
                json.dumps(data, default=str)
            )
        except Exception as e:
            logger.error(f"Error caching metrics summary: {e}")
            return False
    
    def invalidate_agent_cache(self, agent_id: str) -> bool:
        """Invalidate all cache entries for a specific agent."""
        if not self.is_available():
            return False
        
        try:
            # Delete all keys matching the pattern
            pattern = f"agent_performance:{agent_id}:*"
            keys = self.redis_client.keys(pattern)
            if keys:
                return self.redis_client.delete(*keys) > 0
        except Exception as e:
            logger.error(f"Error invalidating agent cache: {e}")
        return False
    
    def invalidate_all_cache(self) -> bool:
        """Invalidate all performance cache entries."""
        if not self.is_available():
            return False
        
        try:
            patterns = [
                "agent_overview:*",
                "agent_performance:*", 
                "agent_registry",
                "metrics_summary:*"
            ]
            total_deleted = 0
            for pattern in patterns:
                keys = self.redis_client.keys(pattern)
                if keys:
                    total_deleted += self.redis_client.delete(*keys)
            return total_deleted > 0
        except Exception as e:
            logger.error(f"Error invalidating all cache: {e}")
        return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if not self.is_available():
            return {"available": False}
        
        try:
            info = self.redis_client.info()
            return {
                "available": True,
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory_human", "0B"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": (
                    info.get("keyspace_hits", 0) / 
                    max(info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0), 1)
                ) * 100
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"available": False, "error": str(e)}

# Global cache instance using singleton pattern
performance_cache = PerformanceCache()
