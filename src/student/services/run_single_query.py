import logging
from teacher.services.structured_response import generate_response_from_groq

logger = logging.getLogger(__name__)
"""
Run a single query using RetrieverAgent with formatted logs.
"""


def run_query(
    retriever_agent,
    query: str,
    db_name: str,
    collection_name: str,
    student_profile: dict = None,
    subject_agent_id: str = None,  # for shared knowledge
    top_k: int = 10,
    is_deep_dive: bool = False,
    chunk_context: str = None,
):
    """
    Execute a single query using the RetrieverAgent and print formatted logs.
    Returns: {"response": str, "quality_scores": dict, "chunk_context": str} or None on error.
    """
    logger.info("=" * 60)
    logger.info("🔍 Running single query")
    logger.info("=" * 60)

    try:
        # Deep-dive mode: bypass retriever and use stored chunk_context directly
        if is_deep_dive and chunk_context:
            logger.info("🔍 DEEP-DIVE: Bypassing retriever, using stored chunk context")
            response_text = generate_response_from_groq(
                input_text=chunk_context,
                query=query,
                student_profile=student_profile,
            )
            logger.info("\n" + "-" * 60)
            logger.info("✅ Deep-dive response generated successfully")
            logger.info("📝 LLM Response:")
            logger.info("-" * 60)
            logger.info(response_text)
            logger.info("-" * 60)
            return {
                "response": response_text,
                "quality_scores": {},
                "chunk_context": chunk_context,
                "from_cache": False,
            }

        # Normal retrieval flow
        result = retriever_agent.orchestrate_retrieval_and_response(
            query=query,
            db_name=db_name,
            collection_name=collection_name,
            student_profile=student_profile,
            subject_agent_id=subject_agent_id,  # Pass for shared knowledge
            top_k=top_k
        )

        response = result.get("response", result) if isinstance(result, dict) else result
        quality_scores = result.get("quality_scores", {}) if isinstance(result, dict) else {}
        chunk_context = result.get("chunk_context", "") if isinstance(result, dict) else ""

        logger.info("\n" + "-" * 60)
        logger.info("✅ Response generated successfully")
        logger.info("📝 LLM Response:")
        logger.info("-" * 60)
        logger.info(response)
        if quality_scores:
            logger.info("-" * 60)
            logger.info("📊 Quality Score Analysis:")
            for k, v in quality_scores.items():
                logger.info(f"   {k}: {v}%")
        logger.info("-" * 60)

        return result

    except Exception as e:
        logger.error(f"❌ Error during retrieval: {e}")
        logger.info(f"❌ Error during retrieval: {e}")
        return None
