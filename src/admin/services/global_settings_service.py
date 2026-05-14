"""
Global settings module to avoid circular imports.
This module stores system-wide settings that can be accessed from multiple modules.
"""

from typing import Dict, Any
from threading import Lock
from config.settings import settings

# Global RAG setting storage (in-memory for simplicity)
_global_rag_settings = {
    "enabled": False,
    "content": ""
}

_settings_lock = Lock()

def get_global_rag_settings() -> Dict[str, Any]:
    """Get a copy of the global RAG settings."""
    with _settings_lock:
        return _global_rag_settings.copy()

def set_global_rag_settings(enabled: bool, content: str = "") -> None:
    """Set the global RAG settings."""
    with _settings_lock:
        _global_rag_settings["enabled"] = enabled
        _global_rag_settings["content"] = content.strip()

def enable_global_rag(content: str) -> None:
    """Enable global RAG with the given content."""
    set_global_rag_settings(True, content)

def disable_global_rag() -> None:
    """Disable global RAG."""
    set_global_rag_settings(False)
