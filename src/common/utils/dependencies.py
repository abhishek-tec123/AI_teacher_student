"""
FastAPI Dependency Providers

This module provides dependency injection functions for FastAPI routes.
"""

from fastapi import Depends
from student.repositories.student_repository import StudentManager
from student.repositories.conversation_repository import ConversationManager
from student.repositories.bookmark_repository import BookmarkManager
from student.repositories.preference_repository import PreferenceManager
from student.repositories.auth_repository import AuthManager
from student.repositories.chat_session_repository import ChatSessionManager


def get_student_manager() -> StudentManager:
    """Dependency provider for StudentManager."""
    return StudentManager()


def get_conversation_manager() -> ConversationManager:
    """Dependency provider for ConversationManager."""
    return ConversationManager()


def get_bookmark_manager() -> BookmarkManager:
    """Dependency provider for BookmarkManager."""
    return BookmarkManager()


def get_preference_manager() -> PreferenceManager:
    """Dependency provider for PreferenceManager."""
    return PreferenceManager()


def get_auth_manager() -> AuthManager:
    """Dependency provider for AuthManager."""
    return AuthManager()


def get_chat_session_manager() -> ChatSessionManager:
    """Dependency provider for ChatSessionManager."""
    return ChatSessionManager()


# Create dependency instances for use in routes
StudentManagerDep = Depends(get_student_manager)
ConversationManagerDep = Depends(get_conversation_manager)
BookmarkManagerDep = Depends(get_bookmark_manager)
PreferenceManagerDep = Depends(get_preference_manager)
AuthManagerDep = Depends(get_auth_manager)
ChatSessionManagerDep = Depends(get_chat_session_manager)
