# get_agent_data.py
import os
from fastapi import HTTPException
from pymongo import MongoClient
from config.settings import settings

def get_agent_data(subject_agent_id: str):
    """Retrieve agent metadata and associated file names."""

    MONGODB_URI = settings.mongodb_uri
    if not MONGODB_URI:
        raise HTTPException(status_code=500, detail="MongoDB URI not configured")

    client = MongoClient(MONGODB_URI)

    # Loop through all databases
    for db_name in client.list_database_names():
        if db_name in ["admin", "local", "config"]:
            continue

        db = client[db_name]

        # Loop through collections
        for collection_name in db.list_collection_names():
            collection = db[collection_name]

            agent_doc = collection.find_one({"subject_agent_id": subject_agent_id})

            if agent_doc:
                file_names = collection.distinct(
                    "document.file_name",
                    {"subject_agent_id": subject_agent_id}
                )

                return {
                    "subject_agent_id": subject_agent_id,
                    "class": db_name,
                    "subject": collection_name,
                    "agent_metadata": agent_doc.get("agent_metadata", {}),
                    "file_names": file_names,
                }

    raise HTTPException(status_code=404, detail="Agent not found")
