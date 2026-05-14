from fastapi import APIRouter, HTTPException, Depends
from student.agents.vector_performance_updater import get_vector_performance
from student.agents.agent_performance_monitor import AgentPerformanceMonitor
from common.auth.dependencies import require_any_role
import os
from pymongo import MongoClient
from config.settings import settings
import logging
logger = logging.getLogger(__name__)

router = APIRouter(tags=["agents"])

client = MongoClient(settings.mongodb_uri)

def get_all_agent_performance():
    try:
        all_agents = []
        processed_agent_ids = set()

        for db_name in client.list_database_names():
            if db_name in ["admin", "local", "config", settings.db_name]:
                continue

            db = client[db_name]

            for collection_name in db.list_collection_names():
                collection = db[collection_name]

                cursor = collection.find(
                    {"subject_agent_id": {"$ne": None}},
                    {
                        "_id": 1,
                        "subject_agent_id": 1,
                        "agent_metadata": 1,
                        "performance.metrics": 1,
                        "performance.performance_level": 1,
                        "performance.total_conversations": 1,
                        "performance.unique_students": 1,
                        "performance.last_updated": 1
                    }
                )

                for doc in cursor:
                    agent_id = doc.get("subject_agent_id")

                    if agent_id and agent_id not in processed_agent_ids:
                        processed_agent_ids.add(agent_id)

                        performance = doc.get("performance", {})

                        all_agents.append({
                            "document_id": str(doc.get("_id")),
                            "subject_agent_id": agent_id,
                            "database": db_name,
                            "collection": collection_name,
                            "agent_metadata": doc.get("agent_metadata", {}),
                            "metrics": performance.get("metrics", {}),
                            "performance_level": performance.get("performance_level"),
                            "total_conversations": performance.get("total_conversations"),
                            "unique_students": performance.get("unique_students"),
                            "last_updated": performance.get("last_updated"),
                        })

        return all_agents

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/all-agents-performance")
async def get_all_agents_performance_detailed(
    current_user: dict = Depends(require_any_role(["admin", "teacher"]))
):
    """
    Get FULL performance documents for all agents directly
    (scans vector documents across all databases)
    """

    try:
        logger.info(f"🚀 User {current_user.get('user_id')} requesting FULL agents performance")

        agents = get_all_agent_performance()

        return {
            "success": True,
            "message": f"Found {len(agents)} agents with detailed performance",
            "total_agents": len(agents),
            "agents": agents
        }

    except Exception as e:
        logger.info(f"❌ Error retrieving detailed agents performance: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving detailed agents performance: {str(e)}"
        )

@router.get("/agent-performance/{agent_id}")
async def get_single_agent_performance(
    agent_id: str,
    current_user: dict = Depends(require_any_role(["admin", "teacher"]))
):
    """
    Get performance details for a specific agent.
    
    Returns complete performance matrix from vector documents.
    """
    try:
        logger.info(f"🚀 User {current_user.get('user_id')} requesting performance for agent {agent_id}")
        
        # Get performance from vector documents
        vector_performance = get_vector_performance(agent_id)
        
        if not vector_performance or vector_performance.get("total_conversations", 0) == 0:
            # Try to get from agent performance summary as fallback
            logger.info(f"📦 Vector performance empty for {agent_id}, using monitor fallback")
            monitor = AgentPerformanceMonitor()
            summary = monitor.get_agent_performance_summary(agent_id)
            
            if summary:
                logger.info(f"✅ Retrieved performance summary for {agent_id}")
                return {
                    "success": True,
                    "message": f"Performance data for {agent_id}",
                    "agent_id": agent_id,
                    "source": "summary_collection",
                    "performance": summary
                }
            else:
                logger.info(f"❌ No performance data found for agent {agent_id}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Agent {agent_id} not found"
                )
        
        logger.info(f"✅ Retrieved vector performance for {agent_id}")
        return {
            "success": True,
            "message": f"Performance data for {agent_id}",
            "agent_id": agent_id,
            "source": "vector_documents",
            "performance": vector_performance
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.info(f"❌ Error retrieving agent performance for {agent_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving agent performance: {str(e)}"
        )
