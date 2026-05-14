import logging
# -----------------------------
# Enhanced Similarity Search Utils
# -----------------------------
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pymongo import MongoClient
from teacher.search.search_utils import validate_content_relevance, find_similar_chunks, find_similar_chunks_in_memory
from teacher.services.structured_response import compute_quality_scores
from admin.repositories.shared_knowledge_repository import shared_knowledge_manager
import asyncio
import os
from config.settings import settings
logger = logging.getLogger(__name__)
# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# -----------------------------
# MongoDB & Vector Search Config
# -----------------------------
MONGODB_URI = settings.mongodb_uri
VECTOR_INDEX_NAME = "vector_index"
VECTOR_PATH = "embedding.vector"
def _build_safe_out_of_scope_response(query: str, restriction_reason: str):
    """
    Central helper to build a safe, curriculum-bound response when no
    relevant RAG content is available or when content restrictions apply.
    """
    safe_msg = (
        "I'm not able to answer this question from the available learning materials. "
        "This teaching assistant can only answer using your curriculum content and teacher-provided documents. "
        "Please try asking with terms from your study materials or consult your teacher for help."
    )
    quality_scores = compute_quality_scores(
        query=query,
        response_text=safe_msg,
        retrieved_chunks=[],
        context_string="",
    )
    # Tag that this was blocked by RAG policy, not hallucinated
    quality_scores["content_restriction"] = restriction_reason
    return {
        "response": safe_msg,
        "quality_scores": quality_scores,
        "sources": [],
        "source_summary": [],
        "chunks_used": 0,
        "from_cache": False,
        "content_restriction": restriction_reason,
    }

# -----------------------------
# Async MongoDB Connection Pool
# -----------------------------
_connection_pool = None
_executor = ThreadPoolExecutor(max_workers=10)

def get_async_client():
    """Get async MongoDB client with connection pooling."""
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = MongoClient(
            MONGODB_URI,
            maxPoolSize=20,
            minPoolSize=5,
            maxIdleTimeMS=30000,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000
        )
    return _connection_pool

# -----------------------------
# Vector Search Cache
# -----------------------------
_vector_cache = {}
_cache_ttl = 300  # 5 minutes

def _get_cache_key(query: str, db_name: str, collection_name: str, top_k: int) -> str:
    """Generate cache key for vector search results."""
    content = f"{query}_{db_name}_{collection_name}_{top_k}"
    return hashlib.md5(content.encode()).hexdigest()

def _get_cached_vector_results(cache_key: str):
    """Get cached vector search results if valid."""
    if cache_key in _vector_cache:
        cached_data, timestamp = _vector_cache[cache_key]
        if time.time() - timestamp < _cache_ttl:
            logger.info(f"🎯 Using cached vector results for key: {cache_key[:8]}...")
            return cached_data
        else:
            del _vector_cache[cache_key]
    return None

def _cache_vector_results(cache_key: str, results):
    """Cache vector search results."""
    _vector_cache[cache_key] = (results, time.time())
    # Limit cache size
    if len(_vector_cache) > 100:
        oldest_key = min(_vector_cache.keys(), key=lambda k: _vector_cache[k][1])
        del _vector_cache[oldest_key]

async def _search_agent_collection_async(db_name: str, collection_name: str, query_embedding, top_k: int, query_text=""):
    """Async wrapper for agent collection search with content validation."""
    def _search():
        try:
            client = get_async_client()
            if db_name in client.list_database_names() and collection_name in client[db_name].list_collection_names():
                agent_collection = client[db_name][collection_name]
                agent_results = find_similar_chunks(query_embedding, agent_collection, limit=top_k, query=query_text)
                
                # Apply additional content validation
                validated_results = []
                for result in agent_results:
                    chunk_text = result.get('text', result.get('chunk_text', ''))
                    if validate_content_relevance(query_text, chunk_text):
                        result["source_type"] = "agent"
                        result["source_name"] = f"{db_name}.{collection_name}"
                        validated_results.append(result)
                    else:
                        logger.info(f"[EnhancedSearch] Skipping agent chunk due to failed content validation")
                
                return validated_results, f"{db_name}.{collection_name}"
            return [], None
        except Exception as e:
            logger.error(f"Failed to search agent collection: {e}")
            return [], None
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _search)

async def _search_shared_documents_async(subject_agent_id: str, query_embedding, top_k: int, query_text=""):
    """Async wrapper for shared documents search with content validation."""
    def _search():
        try:
            # Get agent metadata to check if global RAG is enabled
            agent_global_rag_enabled = False
            try:
                from teacher.repositories.get_agent_data import get_agent_data
                agent_data = get_agent_data(subject_agent_id)
                agent_metadata = agent_data.get("agent_metadata", {})
                agent_global_rag_enabled = agent_metadata.get("global_rag_enabled", False)
            except Exception as e:
                logger.warning(f"Failed to get agent metadata for {subject_agent_id}: {e}")
                agent_global_rag_enabled = False
            
            if not agent_global_rag_enabled:
                return [], []
            
            enabled_shared_docs = shared_knowledge_manager.get_agent_enabled_documents(subject_agent_id)
            if not enabled_shared_docs:
                return [], []
            
            client = get_async_client()
            shared_collection = client[settings.db_name]["shared_knowledge"]
            all_shared_results = []
            sources_info = []
            
            for shared_doc in enabled_shared_docs:
                doc_id = shared_doc["document_id"]
                doc_name = shared_doc["document_name"]
                
                # Search within this shared document using a more permissive
                # similarity threshold, relying on strict content validation
                # and document filters to keep results safe and RAG-only.
                shared_results = find_similar_chunks_in_memory(
                    query_embedding,
                    shared_collection,
                    top_k=top_k // len(enabled_shared_docs) if enabled_shared_docs else top_k,
                    similarity_threshold=0.0,
                    query_text=query_text
                )
                
                # Filter results to only include chunks from this document AND pass content validation
                filtered_results = []
                for result in shared_results:
                    is_match = (
                        result.get("subject_agent_id") == subject_agent_id or
                        result.get("document_id") == doc_id or
                        result.get("document", {}).get("doc_unique_id") == doc_id
                    )
                    
                    if is_match:
                        # Apply content validation
                        chunk_text = result.get('text', result.get('chunk_text', ''))
                        if validate_content_relevance(query_text, chunk_text):
                            result["source_type"] = "shared"
                            result["source_name"] = f"shared:{doc_name}"
                            filtered_results.append(result)
                        else:
                            logger.info(f"[EnhancedSearch] Skipping shared chunk due to failed content validation")
                
                all_shared_results.extend(filtered_results)
                if filtered_results:
                    sources_info.append({
                        "type": "shared",
                        "name": doc_name,
                        "document_id": doc_id,
                        "results_count": len(filtered_results)
                    })
            
            return all_shared_results, sources_info
            
        except Exception as e:
            logger.error(f"Failed to search shared documents: {e}")
            return [], []
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _search)
