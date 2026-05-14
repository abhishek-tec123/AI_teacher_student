"""
Performance Monitoring and Rate Limiting Middleware

Provides rate limiting, request monitoring, and performance tracking
for the agent performance APIs.
"""

import time
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict, deque
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import os
from config.settings import settings
import logging
logger = logging.getLogger(__name__)

class RateLimiter:
    """Redis-based rate limiter with fallback to in-memory."""
    
    def __init__(self):
        self.requests = defaultdict(lambda: deque())
        self.lock = asyncio.Lock()
        self.redis_client = None
        
        # Try to initialize Redis for distributed rate limiting
        try:
            import redis
            self.redis_client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,  # Separate DB for rate limiting
                password=settings.redis_password,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2
            )
            self.redis_client.ping()
            logger.info("Redis rate limiter initialized")
        except Exception as e:
            logger.warning(f"Redis rate limiter failed, using in-memory: {e}")
            self.redis_client = None
    
    async def is_allowed(self, key: str, limit: int, window: int) -> tuple[bool, Dict[str, Any]]:
        """
        Check if request is allowed based on rate limit.
        
        Args:
            key: Rate limit key (usually user_id or IP)
            limit: Number of requests allowed
            window: Time window in seconds
            
        Returns:
            Tuple of (allowed, info_dict)
        """
        now = time.time()
        
        if self.redis_client:
            return await self._redis_rate_limit(key, limit, window, now)
        else:
            return await self._memory_rate_limit(key, limit, window, now)
    
    async def _redis_rate_limit(self, key: str, limit: int, window: int, now: float) -> tuple[bool, Dict[str, Any]]:
        """Redis-based rate limiting."""
        try:
            # Use Redis sliding window algorithm
            pipe = self.redis_client.pipeline()
            pipe.zremrangebyscore(key, 0, now - window)  # Remove old entries
            pipe.zcard(key)  # Count current entries
            pipe.zadd(key, {str(now): now})  # Add current request
            pipe.expire(key, window)  # Set expiration
            results = pipe.execute()
            
            current_count = results[1]
            
            return current_count <= limit, {
                "limit": limit,
                "remaining": max(0, limit - current_count),
                "reset_time": int(now + window),
                "retry_after": window if current_count > limit else 0
            }
            
        except Exception as e:
            logger.error(f"Redis rate limiting error: {e}")
            # Fallback to memory-based limiting
            return await self._memory_rate_limit(key, limit, window, now)
    
    async def _memory_rate_limit(self, key: str, limit: int, window: int, now: float) -> tuple[bool, Dict[str, Any]]:
        """In-memory rate limiting fallback."""
        async with self.lock:
            requests = self.requests[key]
            
            # Remove old requests outside the window
            while requests and requests[0] <= now - window:
                requests.popleft()
            
            # Add current request
            requests.append(now)
            
            current_count = len(requests)
            
            return current_count <= limit, {
                "limit": limit,
                "remaining": max(0, limit - current_count),
                "reset_time": int(now + window),
                "retry_after": window if current_count > limit else 0
            }

class PerformanceMonitoringMiddleware(BaseHTTPMiddleware):
    """Middleware for performance monitoring and rate limiting."""
    
    def __init__(self, app):
        super().__init__(app)
        self.rate_limiter = RateLimiter()
        self.request_stats = defaultdict(lambda: {"count": 0, "total_time": 0, "errors": 0})
        
        # Rate limit settings
        self.rate_limits = {
            "admin": {"requests": 120, "window": 60},  # 100 requests per minute
            "teacher": {"requests": 120, "window": 60},  # 50 requests per minute
            "default": {"requests": 300, "window": 60}   # 20 requests per minute
        }
    
    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting and monitoring."""
        start_time = time.time()
        
        # Get client info
        client_ip = self._get_client_ip(request)
        user = getattr(request.state, 'user', None)
        user_id = user.get('user_id') if user else None
        user_role = user.get('role', 'default') if user else 'default'
        
        # Generate rate limit key
        rate_limit_key = f"{user_role}:{user_id or client_ip}"
        
        # Check rate limits
        rate_config = self.rate_limits.get(user_role, self.rate_limits["default"])
        allowed, rate_info = await self.rate_limiter.is_allowed(
            rate_limit_key,
            rate_config["requests"],
            rate_config["window"]
        )
        from fastapi.responses import JSONResponse

        if not allowed:
            logger.warning(f"Rate limit exceeded for {rate_limit_key}")

            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "limit": rate_info["limit"],
                    "window": rate_config["window"],
                    "retry_after": rate_info["retry_after"]
                },
                headers={
                    "X-RateLimit-Limit": str(rate_info["limit"]),
                    "X-RateLimit-Remaining": str(rate_info["remaining"]),
                    "X-RateLimit-Reset": str(rate_info["reset_time"]),
                    "Retry-After": str(rate_info["retry_after"])
                }
            )
        
        # Process request
        try:
            response = await call_next(request)
            status_code = response.status_code
            
            # Update statistics
            self._update_stats(request.url.path, time.time() - start_time, status_code)
            
            # Add rate limit headers
            response.headers["X-RateLimit-Limit"] = str(rate_info["limit"])
            response.headers["X-RateLimit-Remaining"] = str(rate_info["remaining"])
            response.headers["X-RateLimit-Reset"] = str(rate_info["reset_time"])
            
            # Add performance headers
            response.headers["X-Response-Time"] = f"{(time.time() - start_time)*1000:.2f}ms"
            
            return response
            
        except Exception as e:
            # Log error
            self._update_stats(request.url.path, time.time() - start_time, 500)
            logger.error(f"Request failed: {request.url.path} - {str(e)}")
            raise
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address from request."""
        # Check for forwarded headers first
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else "unknown"
    
    def _update_stats(self, path: str, duration: float, status_code: int):
        """Update request statistics."""
        self.request_stats[path]["count"] += 1
        self.request_stats[path]["total_time"] += duration
        
        if status_code >= 400:
            self.request_stats[path]["errors"] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        stats = {}
        for path, data in self.request_stats.items():
            if data["count"] > 0:
                stats[path] = {
                    "requests": data["count"],
                    "avg_response_time": (data["total_time"] / data["count"]) * 1000,  # ms
                    "error_rate": (data["errors"] / data["count"]) * 100,  # percentage
                    "total_errors": data["errors"]
                }
        return stats
    
    def reset_stats(self):
        """Reset statistics."""
        self.request_stats.clear()

# Global middleware instance
performance_monitoring = PerformanceMonitoringMiddleware
