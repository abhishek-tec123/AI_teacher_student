import logging
import os
import json
from datetime import datetime
from typing import List
from pymongo import MongoClient, UpdateOne
from langchain_huggingface import HuggingFaceEmbeddings
from teacher.services.embedding_runner import get_vectors_and_details

# ----------------------------
# Configure Logging
# ----------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ----------------------------
# Load .env
# ----------------------------
# ----------------------------
# MongoDB Utility Functions
# ----------------------------
def insert_chunks_to_db(embedding_json, collection):
    operations = []

    for entry in embedding_json:
        # ✅ FIX: unique_chunk_id is nested
        unique_chunk_id = entry["chunk"]["unique_chunk_id"]

        operations.append(
            UpdateOne(
                {"chunk.unique_chunk_id": unique_chunk_id},
                {"$setOnInsert": entry},
                upsert=True
            )
        )

    if not operations:
        return 0

    result = collection.bulk_write(operations, ordered=False)
    inserted_count = result.upserted_count

    logger.info(
        f"Bulk upserted {len(operations)} chunks. "
        f"Inserted new: {inserted_count}, matched existing: {result.matched_count}"
    )

    return inserted_count


def get_mongo_collection(db_name: str = None, collection_name: str = None):
    """Return a MongoDB collection object using provided or environment values."""
    MONGODB_URI = settings.mongodb_uri
    if not MONGODB_URI:
        raise ValueError("Please set MONGODB_URI environment variable.")

    db_name = db_name or settings.db_name
    collection_name = collection_name or settings.collection_name

    if not db_name or not collection_name:
        raise ValueError(
            "DB name and Collection name must be provided either as arguments or in environment variables."
        )

    client = MongoClient(MONGODB_URI)
    logger.info(f"Connected to MongoDB: {db_name}.{collection_name}")
    return client[db_name][collection_name], collection_name


import random
import string
from config.settings import settings
logger = logging.getLogger(__name__)

def generate_subject_agent_id():
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"agent_{random_part}"
# ----------------------------
# Main Processing Function
# ----------------------------
def create_vector_and_store_in_atlas(
    file_inputs,
    db_name,
    collection_name,
    embedding_model,
    original_filenames,
    agent_metadata: dict | None = None,
    subject_agent_id: str | None = None,
    file_storage_paths: List[str] | None = None,  # New parameter for file storage paths
):
    if embedding_model is None:
        raise ValueError("No embedding model provided. This function requires a pre-loaded embedding model.")

    embedding_model_name = getattr(embedding_model, "model_name", "provided_model")

    logger.info("Generating vectors and extracting metadata from files...")
    vector, doc_ids = get_vectors_and_details(
        file_inputs=file_inputs,
        embedding_model=embedding_model,
        original_filenames=original_filenames,
        subject_agent_id=subject_agent_id,  # ✅ pass down
        agent_metadata=agent_metadata,
        file_storage_paths=file_storage_paths,  # Pass storage paths to utility
    )

    logger.info(f"Generated embeddings for {len(vector)} chunks")

    # ✅ FIX: Only generate for NEW agent
    if subject_agent_id is None:
        subject_agent_id = generate_subject_agent_id()
        logger.info(f"Generated new subject_agent_id: {subject_agent_id}")
    else:
        logger.info(f"Using existing subject_agent_id: {subject_agent_id}")

    for entry in vector:
        entry["subject_agent_id"] = subject_agent_id
    
    # ✅ Attach agent metadata safely with global settings defaults
    if agent_metadata:
        # Ensure global settings are properly set with defaults
        processed_metadata = agent_metadata.copy()
        processed_metadata.setdefault("global_prompt_enabled", False)
        processed_metadata.setdefault("global_rag_enabled", False)
        
        logger.info(f"Attaching agent metadata with global settings: {processed_metadata}")
        for entry in vector:
            entry["agent_metadata"] = processed_metadata
    
    # ✅ NEW: Add performance tracking key to each entry
    performance_data = {
        "performance_period": "Last 30 days",
        "total_conversations": 0,
        "unique_students": 0,
        "student_usage": {
            "total_students": 0,
            "student_ids": [],
            "conversation_per_student": {},
            "student_performance": {}
        },
        "metrics": {
            "pedagogical_value": 0,
            "critical_confidence": 0,
            "rag_relevance": 0,
            "answer_completeness": 0,
            "hallucination_risk": 0,
            "overall_score": 0,
            "satisfaction_rate": 0,
            "feedback_counts": {
                "like": 0,
                "dislike": 0,
                "neutral": 0
            },
            "confusion_distribution": {}
        },
        "performance_level": "Critical",
        "health_indicators": {
            "quality_health": {
                "status": "No Data",
                "color": "gray"
            },
            "hallucination_health": {
                "status": "No Data",
                "color": "gray"
            },
            "satisfaction_health": {
                "status": "No Data",
                "color": "gray"
            }
        },
        "trend_analysis": {
            "trend": "No Data",
            "direction": "neutral"
        },
        "recommendations": [
            "Agent has no conversation data - needs testing and deployment"
        ],
        "last_updated": datetime.utcnow().isoformat()
    }
    
    for entry in vector:
        entry["performance"] = performance_data

    collection, used_collection_name = get_mongo_collection(db_name, collection_name)

    logger.info("Inserting chunks into MongoDB...")
    inserted_count = insert_chunks_to_db(vector, collection)

    logger.info(
        f"✅ Inserted {inserted_count} new chunks into MongoDB collection '{used_collection_name}'."
    )

    # ✅ FIX: file_name is nested under document
    unique_file_names = list({
        e["document"]["file_name"]
        for e in vector
        if e.get("document") and e["document"].get("file_name")
    })

    summary = {
        "subject_agent_id": subject_agent_id,
        "num_chunks": len(vector),
        "inserted_chunks": inserted_count,
        "file_names": unique_file_names,
        "embedding_model": embedding_model_name,
        "doc_unique_ids": doc_ids,
        "original_filenames": original_filenames,
        "agent_metadata": agent_metadata,
        "vector_unique_ids": [c["chunk"]["unique_chunk_id"] for c in vector],
    }

    logger.info("Summary of operation:")
    logger.info(json.dumps(summary, indent=2, ensure_ascii=False))

    # ✅ NEW: Create agent performance summary when new agent is created
    if subject_agent_id:
        try:
            from student.agents.agent_performance_monitor import AgentPerformanceMonitor
            
            monitor = AgentPerformanceMonitor()
            agent_metadata_for_performance = {
                "class": db_name,
                "subject": collection_name,
                "agent_metadata": agent_metadata or {},
                "document_count": len(vector)
            }
            
            success = monitor.create_agent_performance_summary(subject_agent_id, agent_metadata_for_performance)
            if success:
                logger.info(f"✅ Created agent performance summary for {subject_agent_id}")
            else:
                logger.warning(f"⚠️ Failed to create agent performance summary for {subject_agent_id}")
                
        except Exception as e:
            logger.error(f"❌ Error creating agent performance summary: {e}")

    # Log activity for new agent creation
    try:
        from student.services.activity_tracker import log_agent_created
        
        agent_name = agent_metadata.get("agent_name") if agent_metadata else collection_name
        if not agent_name:
            agent_name = collection_name
            
        log_agent_created(
            agent_id=subject_agent_id,
            agent_name=agent_name,
            subject=collection_name,
            class_name=db_name
        )
        logger.info(f"✅ Logged agent creation activity for {subject_agent_id}")
        
    except Exception as e:
        logger.error(f"❌ Failed to log agent creation activity: {e}")

    return summary


# ----------------------------
# Example usage (uncomment to run directly)
# ----------------------------
# if __name__ == "__main__":
#     files = ["doc1.txt", "doc2.txt"]
#     create_vector_and_store_in_atlas(files, db_name="myDatabase", collection_name="myCollection")


# ----------------------------
# Entry Point
# ----------------------------
# if __name__ == "__main__":
#     file_inputs = ["/Users/abhishek/Desktop/tutorAi/data/jesc1dd"]
#     create_vector_and_store_in_atlas(file_inputs)
