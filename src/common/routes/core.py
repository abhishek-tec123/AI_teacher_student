"""
Core health check routes
Handles application health monitoring and status endpoints
"""

from fastapi import APIRouter
from datetime import datetime
import os
from pymongo import MongoClient
from config.settings import settings

router = APIRouter()

# Health check endpoint
@router.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    try:
        # Check database connection
        client = MongoClient(settings.mongodb_uri)
        client.admin.command('ping')
        db_status = "healthy"
        client.close()
    except Exception:
        db_status = "unhealthy"
    
    # Check cache status
    try:
        from common.cache.performance_cache import performance_cache
        cache_stats = performance_cache.get_cache_stats()
        cache_status = "healthy" if cache_stats.get("available") else "unhealthy"
    except Exception:
        cache_status = "unhealthy"
        cache_stats = {}
    
    return {
        "status": "healthy" if db_status == "healthy" and cache_status == "healthy" else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "database": db_status,
            "cache": cache_status,
            "api": "healthy"
        },
        "cache_stats": cache_stats
    }
