"""
Global model cache system to prevent reloading heavy models on every request.
This significantly improves application startup and response times.
"""

import os
import threading
from typing import Optional, Dict, Any
import spacy
from spacy.cli import download
# import tensorflow_hub as hub
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
import logging
logger = logging.getLogger(__name__)


class ModelCache:
    """Thread-safe singleton for caching heavy models and data."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._models: Dict[str, Any] = {}
        self._initialized = True
        logger.info("ModelCache initialized")
    
    def get_embedding_model(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> HuggingFaceEmbeddings:
        """Get or load a single HuggingFace embedding model with caching.
        Regardless of the requested name, we normalize to all-MiniLM-L6-v2 to avoid multiple loads.
        """
        normalized_model_name = "sentence-transformers/all-MiniLM-L6-v2"
        cache_key = f"embedding_{normalized_model_name.replace('/', '_')}"

        if cache_key not in self._models:
            if model_name != normalized_model_name:
                logger.info(
                    f"Normalizing requested embedding '{model_name}' to '{normalized_model_name}' to enforce single model."
                )
            logger.info(f"Loading embedding model '{normalized_model_name}'...")
            self._models[cache_key] = HuggingFaceEmbeddings(model_name=normalized_model_name)
            logger.info(f"Embedding model '{normalized_model_name}' loaded and cached")

        return self._models[cache_key]
    
    def preload_models(self):
        """Preload commonly used models at startup."""
        logger.info("Preloading common models...")
        
        # Preload embedding model
        self.get_embedding_model()
        
        logger.info("Model preloading completed")
    
    def clear_cache(self):
        """Clear all cached models (useful for testing)."""
        self._models.clear()
        logger.info("Model cache cleared")

# Global instance
model_cache = ModelCache()
