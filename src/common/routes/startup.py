# import logging

# from teacher.services.model_cache import model_cache
# from student.repositories.student_repository import StudentManager
# from student.services.student_agent import StudentAgent

# EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# logger = logging.getLogger(__name__)

# # shared state (imported by routers)
# embedding_model = None
# student_agent = None
# student_manager = None


# async def startup_event():
#     global embedding_model, student_agent, student_manager

#     logger.info("Loading embedding model on startup...")
#     embedding_model = model_cache.get_embedding_model(EMBED_MODEL_NAME)
#     logger.info("Embedding model loaded and ready.")

#     student_agent = StudentAgent()
#     student_manager = StudentManager()
#     student_manager.initialize_db_collection()

#     logger.info("🚀 started successfully.")



from teacher.services.model_cache import model_cache
from student.repositories.student_repository import StudentManager
from student.services.student_agent import StudentAgent
import logging
import os
logger = logging.getLogger(__name__)

EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

logger = logging.getLogger("startup")

async def startup_event(app):
    logger.info("Initializing database on startup...")
    try:
        import sys
        scripts_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts")
        if scripts_path not in sys.path:
            sys.path.insert(0, scripts_path)
        from init_database import initialize_database
        initialize_database()
    except Exception as e:
        logger.warning(f"Database initialization skipped: {e}")

    logger.info("Loading embedding model on startup...")

    app.state.embedding_model = model_cache.get_embedding_model(
        EMBED_MODEL_NAME
    )

    app.state.student_agent = StudentAgent()
    app.state.student_manager = StudentManager()
    app.state.student_manager.initialize_db_collection()

    logger.info("🚀 started successfully.")
