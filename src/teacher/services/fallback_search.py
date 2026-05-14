import logging
# -----------------------------
# Fallback synchronous search implementation
# -----------------------------
from teacher.search.search_utils import extract_core_question, embed_query, find_similar_chunks, find_similar_chunks_in_memory, validate_content_relevance
from teacher.search.response_cache import ResponseCache
from teacher.search.enhanced_similarity_utils import _get_cache_key, _cache_vector_results, _build_safe_out_of_scope_response, get_async_client
from teacher.search.search_utils import TOP_K
from admin.repositories.shared_knowledge_repository import shared_knowledge_manager
from teacher.services.structured_response import compute_quality_scores
from teacher.services.similarity_search import get_llm_response_from_chunk
from config.settings import settings
logger = logging.getLogger(__name__)

response_cache = ResponseCache()
# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
# -----------------------------
# Fallback synchronous search implementation
# -----------------------------
def _fallback_sync_search(
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
    Fallback synchronous search implementation.
    """
    _err = lambda msg: {"response": msg, "quality_scores": {}, "sources": []}

    if not embedding_model:
        return _err("No embedding model provided.")

    if not query or not query.strip():
        return _err("Query cannot be empty.")

    # Check response cache
    student_id = student_profile.get('student_id') if student_profile else None
    cached_response = response_cache.get_cached_response(query, student_id)
    
    if cached_response:
        return {
            "response": cached_response['response'], 
            "quality_scores": cached_response['quality_scores'],
            "sources": [],
            "from_cache": True,
            "repeat_count": cached_response['repeat_count']
        }

    # Extract core question and embed
    # Even when RL is disabled for shared documents, use the extracted core
    # question (not the full formatted prompt) for retrieval.
    core_question = extract_core_question(query)
    if disable_rl:
        logger.info(
            f"RL disabled for shared documents - using extracted core question from original prompt: "
            f"'{core_question[:100]}...'"
        )
    else:
        logger.info(f"Core question extracted for embedding (sync): '{core_question[:100]}...'")
    query_embedding = embed_query(core_question, embedding_model)

    # Generate cache key for this query
    cache_key = _get_cache_key(query, db_name or "", collection_name or "", top_k)

    # Synchronous searches
    all_results = []
    sources_info = []

    # Agent collection search with content validation
    if db_name and collection_name:
        try:
            client = get_async_client()
            if db_name in client.list_database_names() and collection_name in client[db_name].list_collection_names():
                agent_collection = client[db_name][collection_name]
                # Use core_question for similarity + validation
                agent_results = find_similar_chunks(query_embedding, agent_collection, limit=top_k, query=core_question)
                
                # Apply additional content validation
                validated_results = []
                for result in agent_results:
                    chunk_text = result.get('text', result.get('chunk_text', ''))
                    if validate_content_relevance(query, chunk_text):
                        result["source_type"] = "agent"
                        result["source_name"] = f"{db_name}.{collection_name}"
                        validated_results.append(result)
                    else:
                        logger.info(f"[EnhancedSearch] Skipping agent chunk due to failed content validation (sync)")
                
                all_results.extend(validated_results)
                if validated_results:
                    sources_info.append({
                        "type": "agent",
                        "name": f"{db_name}.{collection_name}",
                        "results_count": len(validated_results)
                    })
        except Exception as e:
            logger.error(f"Failed to search agent collection: {e}")

    # Shared documents search with content validation (simplified)
    if subject_agent_id:
        try:
            from teacher.repositories.get_agent_data import get_agent_data
            agent_data = get_agent_data(subject_agent_id)
            agent_metadata = agent_data.get("agent_metadata", {})
            agent_global_rag_enabled = agent_metadata.get("global_rag_enabled", False)
            
            if agent_global_rag_enabled:
                enabled_shared_docs = shared_knowledge_manager.get_agent_enabled_documents(subject_agent_id)
                if enabled_shared_docs:
                    client = get_async_client()
                    shared_collection = client[settings.db_name]["shared_knowledge"]
                    
                    for shared_doc in enabled_shared_docs:
                        doc_id = shared_doc["document_id"]
                        doc_name = shared_doc["document_name"]
                        
                        # Use in-memory cosine search with a more permissive
                        # similarity threshold for shared/global docs, driven
                        # by the extracted core_question.
                        shared_results = find_similar_chunks_in_memory(
                            query_embedding,
                            shared_collection,
                            top_k=top_k // len(enabled_shared_docs),
                            similarity_threshold=0.0,
                            query_text=core_question
                        )
                        
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
                                if validate_content_relevance(query, chunk_text):
                                    result["source_type"] = "shared"
                                    result["source_name"] = f"shared:{doc_name}"
                                    filtered_results.append(result)
                                else:
                                    logger.info(f"[EnhancedSearch] Skipping shared chunk due to failed content validation (sync)")
                        
                        all_results.extend(filtered_results)
                        if filtered_results:
                            sources_info.append({
                                "type": "shared",
                                "name": doc_name,
                                "document_id": doc_id,
                                "results_count": len(filtered_results)
                            })
        except Exception as e:
            logger.error(f"Failed to search shared documents: {e}")

    # Process results
    all_results.sort(key=lambda x: x.get('score', 0), reverse=True)
    
    # Separate agent and shared results
    agent_results = [doc for doc in all_results if doc.get('source_type') == 'agent']
    shared_results = [doc for doc in all_results if doc.get('source_type') == 'shared']
    
    logger.info(f"Total raw agent chunks (sync): {len(agent_results)}")
    logger.info(f"Total raw shared chunks (sync): {len(shared_results)}")
    
    # Apply high threshold filtering (>0.3) to agent results and slightly
    # more permissive threshold for shared/global docs.
    AGENT_HIGH_THRESHOLD = 0.3
    SHARED_HIGH_THRESHOLD = 0.2
    filtered_agent_results = [
        doc for doc in agent_results
        if doc.get("score", 0) >= AGENT_HIGH_THRESHOLD
    ]
    
    filtered_shared_results = [
        doc for doc in shared_results
        if doc.get("score", 0) >= SHARED_HIGH_THRESHOLD
    ]
    
    logger.info(f"✅ Agent chunks passing threshold {AGENT_HIGH_THRESHOLD} (sync): {len(filtered_agent_results)}")
    logger.info(f"✅ Shared chunks passing threshold {SHARED_HIGH_THRESHOLD} (sync): {len(filtered_shared_results)}")
    
    # ABSOLUTE RULE: If neither agent nor shared chunks pass the threshold, NEVER call the LLM
    if not filtered_agent_results and not filtered_shared_results:
        logger.error("🚫 NO RELEVANT CONTENT FOUND (sync): No chunks from agent or shared documents met threshold requirements. LLM call BLOCKED.")
        result = _build_safe_out_of_scope_response(query, "no_relevant_content")
        _cache_vector_results(cache_key, result)
        return result
    
    # Agent-first combination: agent chunks are primary, shared chunks supplement
    final_results = filtered_agent_results + filtered_shared_results
    
    # Sort final results by score and limit
    final_results.sort(key=lambda x: x.get('score', 0), reverse=True)
    all_results = final_results[:top_k]
    
    logger.info(f"Using {len(all_results)} total chunks for LLM (sync, agent first).")
    
    # Generate response
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
    
    response_result = get_llm_response_from_chunk(
        result_string=result_string,
        query=query,
        student_profile=student_profile,
        logger=logger
    )
    
    if isinstance(response_result, dict):
        response_text = response_result.get("response", "")
        quality_scores = response_result.get("quality_scores", {})
    else:
        response_text = str(response_result)
        quality_scores = {}
    
    # Compute quality scores if not provided
    if not quality_scores:
        logger.info(f"🔍 Computing quality scores with {len(all_results)} chunks")
        for i, chunk in enumerate(all_results):
            score = chunk.get("score", 0)
            source_type = chunk.get("source_type", "unknown")
            logger.info(f"   - Chunk {i+1}: score={score}, source_type={source_type}")
        quality_scores = compute_quality_scores(query, response_text, all_results, result_string)
        logger.info(f"📊 Final quality scores: {quality_scores}")
    
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