from .authentication import router as authentication_router
from .authorization import router as authorization_router
from .analytics import router as analytics_router
from .monitoring import router as monitoring_router
from .activity import router as activity_router
from .core import router as core_router

from fastapi import APIRouter

# Auth router
auth_router = authentication_router
auth_router.include_router(authorization_router)

# Performance router
performance_router = monitoring_router
performance_router.include_router(analytics_router, prefix="/analytics")

# Activity router
activity_router = activity_router

# Core router
core_router = core_router

__all__ = [
    "auth_router",
    "performance_router",
    "activity_router",
    "core_router",
]
