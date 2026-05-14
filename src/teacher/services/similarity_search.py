import logging
# -----------------------------
# Student-adaptive similarity search + Groq LLM
# -----------------------------

import os
import numpy as np
from pymongo import MongoClient
from config.settings import settings
from teacher.services.structured_response import generate_response_from_groq, compute_quality_scores
from teacher.search.search_utils import extract_core_question, embed_query, find_similar_chunks
# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# -----------------------------
# MongoDB & Vector Search Config
# -----------------------------
MONGODB_URI = settings.mongodb_uri
VECTOR_INDEX_NAME = "vector_index"
# In the current schema, the embedding vector is stored under `embedding.vector`
VECTOR_PATH = "embedding.vector"

TOP_K = 10
MIN_SCORE_THRESHOLD = 0.3  # Threshold for chunk selection - balanced with content validation

from teacher.search.response_cache import ResponseCache
logger = logging.getLogger(__name__)
# Global cache instance
response_cache = ResponseCache()

# -----------------------------
# Vector search helpers
# -----------------------------

# -----------------------------
# LLM response helper
# -----------------------------
def get_llm_response_from_chunk(
    result_string: str,
    query: str,
    student_profile: dict,
    logger
) -> str:
    """
    Calls the Groq LLM with a combined result string.
    STRICT VALIDATION: Only processes responses if valid content is provided.
    Returns the response text.
    """
    # ABSOLUTE CONTENT VALIDATION
    if not result_string or not result_string.strip():
        logger.error("🚫 EMPTY CONTENT: No valid content provided to LLM. Response BLOCKED.")
        return (
            "I don't have access to any relevant learning materials for this question. "
            "Please ask about topics covered in your current curriculum or consult your teacher."
        )
    
    if len(result_string.strip()) < 50:
        logger.error("🚫 INSUFFICIENT CONTENT: Content too short for meaningful response. Response BLOCKED.")
        return (
            "The available learning materials don't contain enough information about this topic. "
            "Please try a more specific question related to your curriculum."
        )
    
    try:
        response_text = generate_response_from_groq(
            input_text=result_string,
            query=query,
            student_profile=student_profile
        )

        if not response_text.strip():
            logger.warning("LLM returned empty response despite valid content.")
            return (
                "I'm not able to generate a response from the available learning materials. "
                "Please try rephrasing your question or ask your teacher for clarification."
            )

        logger.info(f"✅ LLM response generated successfully ({len(response_text)} chars)")
        return response_text

    except Exception as e:
        logger.error(f"🚫 LLM invocation failed: {e}")
        return "I'm not able to process this question with the available learning materials. Please ask your teacher for help."

# -----------------------------
# Main retrieval + LLM
# -----------------------------
def retrieve_chunk_for_query_send_to_llm(
    query: str,
    db_name: str = None,
    collection_name: str = None,
    embedding_model=None,
    student_profile: dict = None,
    top_k: int = TOP_K,
    disable_rl: bool = False
) -> dict:
    """
    Retrieves relevant chunks for a query and generates an LLM response.
    Returns: {"response": str, "quality_scores": dict}
    """
    db_name = db_name or ""
    collection_name = collection_name or ""

    # -----------------------------
    # Basic validation
    # -----------------------------
    _err = lambda msg: {"response": msg, "quality_scores": {}}

    if not embedding_model:
        logger.error("No embedding model provided.")
        return _err("No embedding model provided.")

    if not query or not query.strip():
        logger.error("Query cannot be empty.")
        return _err("Query cannot be empty.")

    # -----------------------------
    # Check for cached response first
    # -----------------------------
    student_id = student_profile.get('student_id') if student_profile else None
    cached_response = response_cache.get_cached_response(query, student_id)
    
    if cached_response:
        logger.info(f"[ResponseCache] Returning cached response (repeat #{cached_response['repeat_count']})")
        return {
            "response": cached_response['response'], 
            "quality_scores": cached_response['quality_scores'],
            "from_cache": True,
            "repeat_count": cached_response['repeat_count']
        }

    # -----------------------------
    # Connect to MongoDB
    # -----------------------------
    try:
        client = MongoClient(MONGODB_URI)

        if db_name not in client.list_database_names():
            return _err(f"Database '{db_name}' does not exist.")

        if collection_name not in client[db_name].list_collection_names():
            return _err(f"Collection '{collection_name}' does not exist in database '{db_name}'.")

        collection = client[db_name][collection_name]
        doc_count = collection.count_documents({})

        if doc_count == 0:
            return _err(f"Collection '{collection_name}' is empty.")

        logger.info(f"[MongoDB] Connected to {db_name}.{collection_name} ({doc_count} documents)")

    except Exception as e:
        logger.error(f"MongoDB connection failed: {e}")
        return _err("Failed to connect to MongoDB.")

    # -----------------------------
    # Extract core question for embedding (better similarity scores)
    # Use full query for LLM response generation
    # -----------------------------
    core_question = extract_core_question(query)
    logger.info(f"Core question extracted for embedding: '{core_question[:100]}...' (full query length: {len(query)})")
    
    # Generate query embedding using core question only
    query_embedding = embed_query(core_question, embedding_model)

    # -----------------------------
    # Retrieve chunks
    # -----------------------------
    results = find_similar_chunks(query_embedding, collection, query, limit=top_k)
    logger.info(f"[VectorSearch] Atlas search returned {len(results)} results")

    if not results:
        # ABSOLUTE RULE: No chunks retrieved = NO LLM call - no exceptions
        logger.error("🚫 NO CHUNKS RETRIEVED: Vector search returned no results. LLM call BLOCKED.")
        safe_msg = (
            "I'm not able to answer this question from the available learning materials. "
            "This question appears to be outside the scope of the current curriculum. "
            "Please try rephrasing your question with terms from your study materials or ask your teacher for help."
        )
        quality_scores = compute_quality_scores(
            query=query,
            response_text=safe_msg,
            retrieved_chunks=[],
            context_string="",
        )
        return {"response": safe_msg, "quality_scores": quality_scores, "content_restriction": "no_chunks_found"}

    # -----------------------------
    # LOG ALL retrieved chunks
    # -----------------------------
    logger.info("Retrieved chunks (before threshold filtering):")
    for idx, doc in enumerate(results):
        logger.info(
            f"[RAW {idx + 1}] Score: {doc.get('score', 0):.4f}, "
            f"Unique ID: {doc.get('unique_id')}, "
            f"Chunk ID: {doc.get('unique_chunk_id')}"
        )

    # -----------------------------
    # Filter by similarity threshold - BALANCED WITH CONTENT VALIDATION
    # -----------------------------
    MIN_SCORE_THRESHOLD = 0.3  # Threshold for chunk selection - content validation prevents false positives
    filtered_results = [
        doc for doc in results
        if doc.get("score", 0) >= MIN_SCORE_THRESHOLD
    ]

    if not filtered_results:
        # ABSOLUTE RULE: If nothing passes the similarity threshold, NEVER call the LLM
        logger.error(f"🚫 NO CHUNKS PASSED THRESHOLD: No chunks passed MIN_SCORE_THRESHOLD={MIN_SCORE_THRESHOLD}. LLM call BLOCKED.")
        safe_msg = (
            "I'm not able to find relevant content in the learning materials for this question. "
            "This question appears to be outside the scope of the current curriculum. "
            "Please try asking it in a different way using terms from your study materials or consult your teacher."
        )
        quality_scores = compute_quality_scores(
            query=query,
            response_text=safe_msg,
            retrieved_chunks=[],
            context_string="",
        )
        return {"response": safe_msg, "quality_scores": quality_scores, "content_restriction": "below_threshold"}

    # -----------------------------
    # LOG accepted chunks with content
    # -----------------------------
    logger.info("=" * 80)
    logger.info("✅ Chunks passed threshold and will be sent to LLM:")
    logger.info("=" * 80)
    for idx, doc in enumerate(filtered_results):
        chunk_text = doc.get("chunk_text", "")
        logger.info(
            f"[ACCEPTED {idx + 1}] Score: {doc['score']:.4f}, "
            f"Unique ID: {doc.get('unique_id')}, "
            f"Chunk ID: {doc.get('unique_chunk_id')}"
        )
        # logger.info(f"Chunk {idx + 1} Content ({len(chunk_text)} chars):")
        # logger.info(chunk_text[:300] + ("..." if len(chunk_text) > 300 else ""))
        # logger.info("-" * 80)

    # -----------------------------
    # Build combined result string
    # -----------------------------
    result_string = "\n---\n".join(doc["chunk_text"] for doc in filtered_results)
    logger.info(f"Combined context string length: {len(result_string)} chars")

    # -----------------------------
    # Call LLM function
    # -----------------------------
    # logger.info(f"Calling LLM with query: {query}")
    logger.info(f"Context chunks: {len(filtered_results)} chunks, {len(result_string)} total chars")
    
    response_text = get_llm_response_from_chunk(
        result_string=result_string,
        query=query,
        student_profile=student_profile or {},
        logger=logger
    )

    # -----------------------------
    # Compute Quality Score Analysis
    # -----------------------------
    quality_scores = compute_quality_scores(
        query=query,
        response_text=response_text,
        retrieved_chunks=filtered_results,
        context_string=result_string,
    )

    # -----------------------------
    # Cache the response for future use
    # -----------------------------
    response_cache.cache_response(query, response_text, quality_scores, student_id)

    return {"response": response_text, "quality_scores": quality_scores, "from_cache": False, "content_restriction": "none"}