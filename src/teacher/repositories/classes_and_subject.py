import os
from pymongo import MongoClient

logger = logging.getLogger("classes")
MONGODB_URI = settings.mongodb_uri

SYSTEM_DBS = {"admin", "local", "config"}

def list_all_classes():
    try:
        client = MongoClient(MONGODB_URI)

        classes = [
            db for db in client.list_database_names()
            if db not in SYSTEM_DBS
        ]

        return {
            "status": "success",
            "classes": classes
        }

    except Exception as e:
        logger.error(f"❌ Error fetching classes: {e}")
        return {
            "status": "error",
            "message": str(e)
        }

import os
from pymongo import MongoClient
from config.settings import settings
import logging
logger = logging.getLogger(__name__)

logger = logging.getLogger("subjects")
MONGODB_URI = settings.mongodb_uri

SYSTEM_DBS = {"admin", "local", "config"}

def get_subjects_by_class(selected_class: str):
    try:
        client = MongoClient(MONGODB_URI)

        if selected_class not in client.list_database_names():
            return {
                "status": "error",
                "message": f"No subjects found for class '{selected_class}'.",
                "available_classes": [
                    db for db in client.list_database_names()
                    if db not in SYSTEM_DBS
                ]
            }

        subjects = client[selected_class].list_collection_names()

        return {
            "status": "success",
            "class": selected_class,
            "subjects": subjects
        }

    except Exception as e:
        logger.error(f"❌ Error fetching subjects: {e}")
        return {
            "status": "error",
            "message": str(e)
        }
