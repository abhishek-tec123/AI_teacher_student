from pymongo import MongoClient
from pymongo.errors import PyMongoError
from config.settings import settings
import logging
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------

logger = logging.getLogger("collections")

MONGODB_URI = settings.mongodb_uri
DB_NAME = settings.db_name
SYSTEM_DBS = {"admin", "local", "config", DB_NAME}

# ------------------------------------------------------------------------------
# Single Global MongoDB Client (Thread-safe & Reusable)
# ------------------------------------------------------------------------------

client = MongoClient(MONGODB_URI)


# ------------------------------------------------------------------------------
# Get All Agents From All Classes
# ------------------------------------------------------------------------------

def list_all_collections():
    """
    Returns all agents with metadata and performance metrics
    """
    try:
        result = []

        for db_name in client.list_database_names():
            if db_name in SYSTEM_DBS:
                continue

            db = client[db_name]

            for collection_name in db.list_collection_names():
                collection = db[collection_name]

                doc = collection.find_one(
                    {"agent_metadata.description": {"$exists": True}},
                    {
                        "agent_metadata.agent_name": 1,
                        "agent_metadata.agent_type": 1,
                        "agent_metadata.description": 1,
                        "subject_agent_id": 1,
                        "performance.total_conversations": 1,
                        "performance.unique_students": 1,
                        "performance.metrics.overall_score": 1
                    }
                )

                if not doc:
                    continue

                agent = doc.get("agent_metadata", {})
                performance = doc.get("performance", {})
                metrics = performance.get("metrics", {})

                result.append({
                    "class": db_name,
                    "subject": collection_name,
                    "agent_name": agent.get("agent_name"),
                    "agent_type": agent.get("agent_type"),
                    "description": agent.get("description"),
                    "subject_agent_id": doc.get("subject_agent_id"),
                    "total_conversations": performance.get("total_conversations", 0),
                    "unique_students": performance.get("unique_students", 0),
                    "overall_score": metrics.get("overall_score", 0)
                })

        return {
            "status": "success",
            "agent_count": len(result),
            "agents": result
        }

    except PyMongoError as e:
        logger.error(f"MongoDB error in list_all_collections: {e}")
        return {"status": "error", "message": str(e)}

    except Exception as e:
        logger.error(f"Unexpected error in list_all_collections: {e}")
        return {"status": "error", "message": str(e)}


# ------------------------------------------------------------------------------
# Get All Agents of a Specific Class
# ------------------------------------------------------------------------------

def get_all_agents_of_class(class_name):
    """
    Returns all agents belonging to a specific class (database)
    """
    try:
        if class_name in SYSTEM_DBS:
            return {
                "status": "error",
                "message": f"Class '{class_name}' is excluded."
            }

        if class_name not in client.list_database_names():
            return {
                "status": "error",
                "message": f"Class '{class_name}' does not exist."
            }

        db = client[class_name]
        result = []

        for collection_name in db.list_collection_names():
            collection = db[collection_name]

            doc = collection.find_one(
                {"agent_metadata.description": {"$exists": True}},
                {
                    "agent_metadata.agent_name": 1,
                    "agent_metadata.agent_type": 1,
                    "agent_metadata.description": 1,
                    "subject_agent_id": 1
                }
            )

            if not doc:
                continue

            agent = doc.get("agent_metadata", {})

            result.append({
                "class": class_name,
                "subject": collection_name,
                "agent_name": agent.get("agent_name"),
                "agent_type": agent.get("agent_type"),
                "description": agent.get("description"),
                "subject_agent_id": doc.get("subject_agent_id")
            })

        return {
            "status": "success",
            "agent_count": len(result),
            "agents": result
        }

    except PyMongoError as e:
        logger.error(f"MongoDB error in get_all_agents_of_class: {e}")
        return {"status": "error", "message": str(e)}

    except Exception as e:
        logger.error(f"Unexpected error in get_all_agents_of_class: {e}")
        return {"status": "error", "message": str(e)}


# ------------------------------------------------------------------------------
# Get General Collection (teacher_ai.general)
# ------------------------------------------------------------------------------
def get_general_collection():
    try:
        db = client["general"]
        subjects = []
        seen_agents = set()

        for col_name in db.list_collection_names():
            collection = db[col_name]

            cursor = collection.find(
                {
                    "agent_metadata.agent_name": {"$exists": True},
                    "agent_metadata.agent_type": "teacher"
                },
                {
                    "_id": 0,
                    "agent_metadata.agent_name": 1,
                    "agent_metadata.description": 1,
                    "subject_agent_id": 1
                }
            )

            for doc in cursor:
                agent_metadata = doc.get("agent_metadata", {})
                agent_name = agent_metadata.get("agent_name")
                subject_agent_id = doc.get("subject_agent_id")

                if not agent_name or not subject_agent_id:
                    continue

                if subject_agent_id in seen_agents:
                    continue

                seen_agents.add(subject_agent_id)

                subjects.append({
                    "name": agent_name,
                    "description": agent_metadata.get("description", ""),
                    "subject_agent_id": subject_agent_id,
                    "collection_name": col_name
                })

        subjects.sort(key=lambda x: x["name"].lower())

        return {"status": "success", "data": subjects}

    except Exception as e:
        return {"status": "error", "message": str(e)}