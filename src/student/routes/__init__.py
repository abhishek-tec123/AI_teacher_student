"""
Student routes module
Contains all student-related endpoints for profiles, chat, and progress tracking
"""

from .profile import router as profile_router
from .chat import router as chat_router
from .bookmarks import router as progress_router
from .chat_sessions import router as chat_sessions_router
from .documents import router as documents_router
from .conversation_history import router as conversation_history_router

# Aggregate all student routers without prefixes to maintain original paths
student_router = profile_router
student_router.include_router(chat_router)
student_router.include_router(progress_router)
student_router.include_router(chat_sessions_router)
student_router.include_router(documents_router)
student_router.include_router(conversation_history_router)

__all__ = ["student_router"]
