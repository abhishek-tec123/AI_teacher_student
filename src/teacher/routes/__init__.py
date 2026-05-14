"""
Vector routes module
Contains all vector database operations for search, management, and status
"""

from .vector_search import router as search_router
from .vector_management import router as management_router
from .vector_status import router as status_router

from fastapi import APIRouter

# Create main vector router
vector_router = APIRouter()

# Include all sub-routers
# Order matters: register fixed paths like "/all_collections" before
# dynamic catch-all routes like "/{subject_agent_id}" so they are matched first.
vector_router.include_router(search_router)
vector_router.include_router(status_router)
vector_router.include_router(management_router)

# Debug: Print router routes
# print(f"Vector router routes: {[route.path for route in vector_router.routes]}")

__all__ = ["vector_router"]
