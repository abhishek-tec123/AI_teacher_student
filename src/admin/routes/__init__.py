"""
Admin routes module
Contains all admin-related endpoints for user management, prompts, and system configuration
"""

from .management import router as management_router
from .prompts import router as prompts_router
from .system import router as system_router

# Aggregate all admin routers
admin_router = management_router
admin_router.include_router(prompts_router, prefix="/prompts")
admin_router.include_router(system_router, prefix="/system")

__all__ = ["admin_router"]
