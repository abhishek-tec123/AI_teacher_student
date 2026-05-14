"""
Topics routes module
Contains endpoints for extracting and managing topics from subject agents
"""

from .extract import router as extract_router

from fastapi import APIRouter

# Create main topics router
topics_router = APIRouter()

# Include sub-routers
topics_router.include_router(extract_router)

__all__ = ["topics_router"]
