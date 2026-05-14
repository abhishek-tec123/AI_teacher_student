import logging
"""
EmbeddingStoreAgent - A reusable agent for storing embeddings in MongoDB Atlas.

This agent handles:
- Loading and processing documents
- Generating embeddings
- Storing vectors in MongoDB Atlas

IMPORTANT: This agent is PASSIVE - it only executes when methods are explicitly called.
Perfect for use in REST APIs, terminal scripts, or any other context.

Usage:
    agent = EmbeddingStoreAgent()  # No execution on init
    summary = agent.store_embeddings(...)  # Executes only when called
"""

import os
from typing import List, Optional, Dict, Any
from langchain_huggingface import HuggingFaceEmbeddings
import sys
logger = logging.getLogger(__name__)

# Add current directory and parent directory to path for imports
_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

try:
    from teacher.services.model_cache import model_cache
except ImportError:
    try:
        from model_cache import model_cache
    except ImportError:
        # Direct import from parent directory
        import importlib.util
        model_cache_path = os.path.join(_parent_dir, "model_cache.py")
        spec = importlib.util.spec_from_file_location("model_cache", model_cache_path)
        model_cache_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(model_cache_module)
        model_cache = model_cache_module.model_cache

try:
    from teacher.services.vector_store_atlas import create_vector_and_store_in_atlas
except ImportError:
    try:
        from teacher.services.vector_store_atlas import create_vector_and_store_in_atlas
    except ImportError:
        # Direct import from embaddings directory
        import importlib.util
        vector_store_path = os.path.join(_parent_dir, "embaddings", "VectorStoreInAtls.py")
        spec = importlib.util.spec_from_file_location("VectorStoreInAtls", vector_store_path)
        vector_store_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vector_store_module)
        create_vector_and_store_in_atlas = vector_store_module.create_vector_and_store_in_atlas

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class EmbeddingStoreAgent:
    """
    Agent for storing embeddings in MongoDB Atlas.
    
    This agent encapsulates the functionality to:
    1. Load embedding models
    2. Process files and generate embeddings
    3. Store vectors in MongoDB Atlas
    
    Example:
        agent = EmbeddingStoreAgent()
        agent.store_embeddings(
            file_paths=["/path/to/file1.pdf", "/path/to/file2.pdf"],
            db_name="10th",
            collection_name="Science"
        )
    """
    
    def __init__(
        self,
        embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        embedding_model: Optional[HuggingFaceEmbeddings] = None
    ):
        """
        Initialize the EmbeddingStoreAgent.
        
        Args:
            embedding_model_name: Name of the embedding model to use
            embedding_model: Pre-loaded embedding model (optional, will load if not provided)
        """
        self.embedding_model_name = embedding_model_name
        self._embedding_model = embedding_model
        
    @property
    def embedding_model(self) -> HuggingFaceEmbeddings:
        """Lazy load embedding model if not already loaded."""
        if self._embedding_model is None:
            logger.info(f"Loading embedding model: {self.embedding_model_name}")
            self._embedding_model = model_cache.get_embedding_model(self.embedding_model_name)
            logger.info("Embedding model loaded successfully")
        return self._embedding_model
    
    def store_embeddings(
        self,
        file_paths: List[str],
        db_name: str,
        collection_name: str,
        original_filenames: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Store embeddings for given files in MongoDB Atlas.
        
        Args:
            file_paths: List of file paths to process
            db_name: MongoDB database name
            collection_name: MongoDB collection name
            original_filenames: Optional list of original filenames (for tracking)
            
        Returns:
            Dictionary containing summary of the operation:
            - num_chunks: Total number of chunks processed
            - inserted_chunks: Number of new chunks inserted
            - file_names: List of unique file names
            - embedding_model: Model name used
            - all_unique_ids: List of unique document IDs
            - original_filenames: Original filenames if provided
            
        Raises:
            ValueError: If file_paths is empty or embedding model is not available
            Exception: If MongoDB connection or processing fails
        """
        if not file_paths:
            raise ValueError("file_paths cannot be empty")
        
        logger.info(f"Starting embedding storage process for {len(file_paths)} file(s)")
        logger.info(f"Target: {db_name}.{collection_name}")
        
        try:
            summary = create_vector_and_store_in_atlas(
                file_inputs=file_paths,
                db_name=db_name,
                collection_name=collection_name,
                embedding_model=self.embedding_model,
                original_filenames=original_filenames
            )
            
            logger.info("✅ Embedding storage completed successfully")
            return summary
            
        except Exception as e:
            logger.error(f"❌ Error storing embeddings: {e}")
            raise
    
    def get_embedding_model_info(self) -> Dict[str, str]:
        """Get information about the current embedding model."""
        model = self.embedding_model
        return {
            "model_name": getattr(model, 'model_name', self.embedding_model_name),
            "model_type": type(model).__name__
        }
