import random
import string
from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database
from config.settings import settings
import logging
logger = logging.getLogger(__name__)



_client: Optional[MongoClient] = None


def get_mongo_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(
            settings.mongodb_uri,
            maxPoolSize=50,
            minPoolSize=10,
            maxIdleTimeMS=45000,
            serverSelectionTimeoutMS=5000,
        )
    return _client


def get_database(db_name: Optional[str] = None) -> Database:
    client = get_mongo_client()
    name = db_name or settings.db_name
    return client[name]


def close_mongo_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


# Legacy compatibility exports used by repository classes

DEFAULT_CORE_MEMORY = {
    "self_description": "",
    "study_preferences": "",
    "motivation_statement": "",
    "background_context": "",
    "current_focus_struggle": ""
}

DEFAULT_SUBJECT_PREFERENCE = {
    "level": "basic",
    "tone": "friendly",
    "learning_style": "step-by-step",
    "response_length": "long",
    "include_example": True,
    "common_mistakes": [],
    "confusion_counter": {},
    "quiz_score_history": [],
    "consecutive_low_scores": 0,
    "consecutive_perfect_scores": 0,
    "preferred_language": "auto",
    "last_detected_language": "english"
}


def generate_student_id() -> str:
    """Generate a unique student ID with random suffix."""
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"std_{random_part}"


def normalize_student_preference(pref: dict) -> dict:
    """Normalize student preference data with default values."""
    defaults = {
        "level": "basic",
        "tone": "friendly",
        "include_example": False,
        "learning_style": "step-by-step",
        "confidence_level": "medium",
        "common_mistakes": []
    }

    for key, value in defaults.items():
        if key not in pref or pref[key] is None:
            pref[key] = value

    if isinstance(pref.get("common_mistakes"), str):
        pref["common_mistakes"] = []

    return pref


class DatabaseConnection:
    """
    Legacy database connection wrapper for backward compatibility.
    Uses the singleton MongoClient under the hood.
    """

    def __init__(self, mongo_uri: str = None, db_name: str = None):
        self.mongo_uri = mongo_uri or settings.mongodb_uri
        self.db_name = db_name or settings.db_name
        self.client = get_mongo_client()
        self.db = self.client[self.db_name]

    def _connect(self):
        """Ensure connection is alive (no-op with singleton)."""
        pass

    def get_collection(self, collection_name: str):
        """Get a MongoDB collection."""
        return self.db[collection_name]

    def get_students_collection(self):
        """Get the students collection."""
        return self.get_collection("students")

    def initialize_db_collection(self):
        """Initialize database and collection if they don't exist."""
        if self.db_name not in self.client.list_database_names():
            logger.info(f"Database '{self.db_name}' will be created on first insert.")
        else:
            logger.info(f"Database '{self.db_name}' exists.")

        if "students" not in self.db.list_collection_names():
            logger.info("Collection 'students' does not exist. Creating...")
            students = self.get_students_collection()
            temp_id = students.insert_one({"_temp": True}).inserted_id
            students.delete_one({"_id": temp_id})
            logger.info("Collection 'students' created.")
        else:
            logger.info("Collection 'students' exists.")

    def close(self):
        """Close is a no-op for singleton; use close_mongo_client for full cleanup."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
