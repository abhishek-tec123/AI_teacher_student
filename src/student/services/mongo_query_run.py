import os
from pymongo import MongoClient
from config.settings import settings
import logging
logger = logging.getLogger(__name__)

client = MongoClient(settings.mongodb_uri)
db = client[settings.db_name]

db.students.update_many(
    {},
    {
        "$push": {
            "conversation_history.Science": {
                "$each": [],
                "$slice": 10
            }
        }
    }
)

logger.info("Cleanup done")
