import os
from pymongo import MongoClient
from config.settings import settings
import logging
logger = logging.getLogger(__name__)

logger = logging.getLogger("dbstatus")

MONGODB_URI = settings.mongodb_uri

def map_to_db_and_collection(class_: str, subject: str):
    return class_.strip(), subject.strip()

def check_db_status(class_: str, subject: str):
    try:
        db_name, collection_name = map_to_db_and_collection(class_, subject)
        client = MongoClient(MONGODB_URI)

        if db_name not in client.list_database_names():
            return {
                "status": "error",
                "message": f"Database '{db_name}' does not exist",
                "available_databases": client.list_database_names()
            }

        if collection_name not in client[db_name].list_collection_names():
            return {
                "status": "error",
                "message": f"Collection '{collection_name}' does not exist",
                "available_collections": client[db_name].list_collection_names()
            }

        return {
            "status": "success",
            "database": db_name,
            "collection": collection_name,
            "document_count": client[db_name][collection_name].count_documents({})
        }

    except Exception as e:
        logger.error(f"DB status error: {e}")
        return {"status": "error", "message": str(e)}
