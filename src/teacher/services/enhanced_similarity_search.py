import logging
# -----------------------------
# Enhanced similarity search with shared knowledge support
# -----------------------------
import asyncio
from teacher.services.similarity_search import (
    get_llm_response_from_chunk,
    retrieve_chunk_for_query_send_to_llm,
)
from teacher.search.enhanced_similarity_utils import (
    _search_agent_collection_async, 
    _search_shared_documents_async, 
    _get_cache_key, _get_cached_vector_results, 
    _cache_vector_results, _build_safe_out_of_scope_response
)
from teacher.search.search_utils import extract_core_question, embed_query
from teacher.search.response_cache import ResponseCache
from teacher.services.similarity_search import TOP_K
response_cache = ResponseCache()
from teacher.services.structured_response import compute_quality_scores
from teacher.services.fallback_search import _fallback_sync_search
logger = logging.getLogger(__name__)
# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# -----------------------------
# Enhanced search with shared knowledge
# -----------------------------
async def retrieve_chunks_with_shared_knowledge_async(
    query: str,
    db_name: str = None,
    collection_name: str = None,
    subject_agent_id: str = None,
    embedding_model=None,
    student_profile: dict = None,
    top_k: int = 15,
    disable_rl: bool = False
) -> dict:
    """
    Async enhanced retrieval that includes both agent-specific and shared knowledge documents.
    Returns: {"response": str, "quality_scores": dict, "sources": list}
    """
    
    # -----------------------------
    # Basic validation
    # -----------------------------
    _err = lambda msg: {"response": msg, "quality_scores": {}, "sources": []}

    if not embedding_model:
        logger.error("No embedding model provided.")
        return _err("No embedding model provided.")

    if not query or not query.strip():
        logger.error("Query cannot be empty.")
        return _err("Query cannot be empty.")

    # -----------------------------
    # Check vector cache first
    # -----------------------------
    cache_key = _get_cache_key(query, db_name or "", collection_name or "", top_k)
    cached_results = _get_cached_vector_results(cache_key)
    if cached_results:
        return cached_results

    # -----------------------------
    # Check for cached response
    # -----------------------------
    student_id = student_profile.get('student_id') if student_profile else None
    cached_response = response_cache.get_cached_response(query, student_id)
    
    if cached_response:
        logger.info(f"[ResponseCache] Returning cached response (repeat #{cached_response['repeat_count']})")
        result = {
            "response": cached_response['response'], 
            "quality_scores": cached_response['quality_scores'],
            "sources": [],
            "source_summary": [],
            "from_cache": True,
            "repeat_count": cached_response['repeat_count']
        }
        _cache_vector_results(cache_key, result)
        return result

    # -----------------------------
    # Extract core question for embedding
    # -----------------------------
    # Even when RL is disabled for shared documents, we still extract the
    # student's core question from the formatted prompt to drive retrieval.
    core_question = extract_core_question(query)
    if disable_rl:
        logger.info(
            f"RL disabled for shared documents - using extracted core question from original prompt: "
            f"'{core_question[:100]}...'"
        )
    else:
        logger.info(
            f"Core question extracted for embedding: '{core_question[:100]}...' "
            f"(full query length: {len(query)})"
        )
    
    # Generate query embedding using core question only
    query_embedding = embed_query(core_question, embedding_model)

    # -----------------------------
    # Parallel search for agent and shared documents
    # -----------------------------
    search_tasks = []
    
    if db_name and collection_name:
        # Use the extracted core_question for similarity + validation
        search_tasks.append(_search_agent_collection_async(db_name, collection_name, query_embedding, top_k, core_question))
    
    if subject_agent_id:
        # Use the extracted core_question for similarity + validation
        search_tasks.append(_search_shared_documents_async(subject_agent_id, query_embedding, top_k, core_question))
    
    # Execute searches in parallel
    search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
    
    # Process results
    all_results = []
    sources_info = []
    raw_agent_results = []
    raw_shared_results = []
    
    for result in search_results:
        if isinstance(result, Exception):
            logger.error(f"Search task failed: {result}")
            continue
            
        if result is None:
            continue
            
        # Handle agent collection results
        if len(result) == 2 and isinstance(result[0], list) and isinstance(result[1], (str, type(None))):
            agent_results, source_name = result
            if agent_results:
                raw_agent_results.extend(agent_results)
                if source_name:
                    sources_info.append({
                        "type": "agent",
                        "name": source_name,
                        "results_count": len(agent_results)
                    })
                    logger.info(f"Retrieved {len(agent_results)} chunks from {source_name}")
        
        # Handle shared documents results
        elif len(result) == 2 and isinstance(result[0], list) and isinstance(result[1], list):
            shared_results, shared_sources = result
            if shared_results:
                raw_shared_results.extend(shared_results)
                sources_info.extend(shared_sources)
                logger.info(f"Retrieved {len(shared_results)} chunks from shared documents")
    
    logger.info(f"Total raw agent chunks: {len(raw_agent_results)}")
    logger.info(f"Total raw shared chunks: {len(raw_shared_results)}")
    
    # Sort by score within each source
    raw_agent_results.sort(key=lambda x: x.get('score', 0), reverse=True)
    raw_shared_results.sort(key=lambda x: x.get('score', 0), reverse=True)
    
    # Apply high threshold filtering (>0.3) to agent results and a slightly
    # more permissive threshold for shared/global docs.
    AGENT_HIGH_THRESHOLD = 0.3
    SHARED_HIGH_THRESHOLD = 0.2
    filtered_agent_results = [
        doc for doc in raw_agent_results
        if doc.get("score", 0) >= AGENT_HIGH_THRESHOLD
    ]
    
    filtered_shared_results = [
        doc for doc in raw_shared_results
        if doc.get("score", 0) >= SHARED_HIGH_THRESHOLD
    ]
    
    logger.info(f"✅ Agent chunks passing threshold {AGENT_HIGH_THRESHOLD}: {len(filtered_agent_results)}")
    logger.info(f"✅ Shared chunks passing threshold {SHARED_HIGH_THRESHOLD}: {len(filtered_shared_results)}")
    
    # ABSOLUTE RULE: If neither agent nor shared chunks pass the threshold, NEVER call the LLM
    if not filtered_agent_results and not filtered_shared_results:
        logger.error("🚫 NO RELEVANT CONTENT FOUND: No chunks from agent or shared documents met threshold requirements. LLM call BLOCKED.")
        result = _build_safe_out_of_scope_response(query, "no_relevant_content")
        _cache_vector_results(cache_key, result)
        return result
    
    # Agent-first combination: agent chunks are primary, shared chunks supplement
    final_results = filtered_agent_results + filtered_shared_results
    
    # Sort final results by score and limit
    final_results.sort(key=lambda x: x.get('score', 0), reverse=True)
    all_results = final_results[:top_k]
    
    logger.info(f"Using {len(all_results)} total chunks for LLM (agent first).")
    
    # Log all selected chunks with detailed information for debugging
    logger.info("=" * 80)
    logger.info("🔍 SELECTED CHUNKS FOR LLM (AFTER THRESHOLD FILTERING):")
    logger.info("=" * 80)
    for i, chunk in enumerate(all_results):
        chunk_content = chunk.get('text', chunk.get('chunk_text', ''))
        chunk_preview = chunk_content[:200] + ("..." if len(chunk_content) > 200 else "")
        logger.info(f"SELECTED CHUNK {i+1}:")
        logger.info(f"  Score: {chunk.get('score', 0):.4f}")
        logger.info(f"  Source: {chunk.get('source_type', 'unknown')}")
        logger.info(f"  Content Preview: {chunk_preview}")
        logger.info(f"  Full Content Length: {len(chunk_content)} chars")
        logger.info("-" * 60)
    
    # Build context from chunks
    context_chunks = []
    for i, chunk in enumerate(all_results):
        chunk_content = chunk.get('text', chunk.get('chunk_text', ''))[:2000]
        source_info = f" ({chunk.get('source_type', 'unknown')})"
        context_chunks.append(f"Chunk {i+1}{source_info}: {chunk_content}")
    
    result_string = "\n\n".join(context_chunks)
    
    # Log what content is being sent to LLM for debugging
    logger.info(f"📤 Sending {len(context_chunks)} chunks to LLM, total chars: {len(result_string)}")
    if context_chunks:
        logger.info(f"📝 First chunk preview: {context_chunks[0][:200]}...")
    logger.info(f"📤 SENDING TO LLM:")
    logger.info("=" * 80)
    
    # Generate response
    logger.info(f"📤 CALLING LLM WITH:")
    logger.info(f"Query: {query[:200]}...")
    logger.info(f"Context Length: {len(result_string)} chars")
    logger.info("=" * 80)
    response_result = get_llm_response_from_chunk(
        result_string=result_string,
        query=query,
        student_profile=student_profile,
        logger=logger
    )
    
    logger.info("=" * 80)
    logger.info("📝 LLM RESPONSE RECEIVED:")
    logger.info("=" * 80)
    
    if isinstance(response_result, dict):
        response_text = response_result.get("response", "")
        quality_scores = response_result.get("quality_scores", {})
    else:
        response_text = str(response_result)
        quality_scores = {}
    
    # Log LLM response details for debugging
    logger.info(f"Response Length: {len(response_text)} chars")
    logger.info(f"Response Preview: {response_text[:300]}...")
    logger.info(f"Quality Scores: {quality_scores}")
    
    # Compute quality scores if not provided
    if not quality_scores:
        quality_scores = compute_quality_scores(query, response_text, all_results, result_string)
    
    result = {
        "response": response_text,
        "quality_scores": quality_scores,
        "sources": sources_info,
        "source_summary": [f"{src['type']}: {src['name']} ({src['results_count']} chunks)" for src in sources_info],
        "chunks_used": len(all_results),
        "from_cache": False
    }
    
    # Cache the result
    _cache_vector_results(cache_key, result)
    
    return result

def retrieve_chunks_with_shared_knowledge(
    query: str,
    db_name: str = None,
    collection_name: str = None,
    subject_agent_id: str = None,
    embedding_model=None,
    student_profile: dict = None,
    top_k: int = 15,
    disable_rl: bool = False
) -> dict:
    """
    Synchronous wrapper for backward compatibility.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If already in an event loop, use run_in_executor
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run, 
                    retrieve_chunks_with_shared_knowledge_async(
                        query, db_name, collection_name, subject_agent_id,
                        embedding_model, student_profile, top_k
                    )
                )
                return future.result(timeout=30)
        else:
            # If no event loop running, run directly
            return asyncio.run(
                retrieve_chunks_with_shared_knowledge_async(
                    query, db_name, collection_name, subject_agent_id,
                    embedding_model, student_profile, top_k
                )
            )
    except Exception as e:
        logger.error(f"Error in async wrapper: {e}")
        # Fallback to synchronous behavior
        return _fallback_sync_search(query, db_name, collection_name, subject_agent_id, embedding_model, student_profile, top_k, disable_rl)

# -----------------------------
# Backward compatibility wrapper
# -----------------------------
def retrieve_chunk_for_query_send_to_llm_enhanced(
    query: str,
    db_name: str = None,
    collection_name: str = None,
    subject_agent_id: str = None,
    embedding_model=None,
    student_profile: dict = None,
    top_k: int = TOP_K,
    disable_rl: bool = False
) -> dict:
    """
    Enhanced version of retrieve_chunk_for_query_send_to_llm that includes shared knowledge.
    Falls back to original behavior if no shared documents are enabled.
    """
    
    # If no subject_agent_id, use original search
    if not subject_agent_id:
        return retrieve_chunk_for_query_send_to_llm(
            query=query,
            db_name=db_name,
            collection_name=collection_name,
            embedding_model=embedding_model,
            student_profile=student_profile,
            top_k=top_k,
            disable_rl=disable_rl
        )
    
    # Use enhanced search with shared knowledge
    return retrieve_chunks_with_shared_knowledge(
        query=query,
        db_name=db_name,
        collection_name=collection_name,
        subject_agent_id=subject_agent_id,
        embedding_model=embedding_model,
        student_profile=student_profile,
        top_k=top_k,
        disable_rl=disable_rl
    )
