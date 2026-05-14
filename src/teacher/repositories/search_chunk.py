from teacher.services.similarity_search import get_llm_response_from_chunk
import logging
logger = logging.getLogger(__name__)

logger = logging.getLogger("search")

def map_to_db_and_collection(class_: str, subject: str):
    return class_.strip(), subject.strip()

def search_and_generate(
    query: str,
    class_: str,
    subject: str,
    embedding_model
):
    try:
        db_name, collection_name = map_to_db_and_collection(class_, subject)

        response = get_llm_response_from_chunk(
            query=query,
            db_name=db_name,
            collection_name=collection_name,
            embedding_model=embedding_model
        )

        logger.info("✅ Search completed successfully.")
        return {"status": "success", "response": response}

    except Exception as e:
        logger.error(f"❌ Search error: {e}")
        raise
