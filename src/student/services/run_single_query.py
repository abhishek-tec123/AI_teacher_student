import logging
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
    top_k: int = 10
):
    """
    Execute a single query using the RetrieverAgent and print formatted logs.
    Returns: {"response": str, "quality_scores": dict} or None on error.
    """
    logger.info("=" * 60)
    logger.info("🔍 Running single query")
    logger.info("=" * 60)

    try:
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
