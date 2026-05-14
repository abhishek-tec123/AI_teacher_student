"""
Topic extraction routes
Handles extraction of topics and subtopics from subject agent content
"""

from fastapi import APIRouter, Depends, Query, HTTPException
import sys
import os
from typing import Optional
from fastapi import Request


from common.auth.dependencies import get_current_user
from teacher.services.topic_extraction_agent import TopicExtractionAgent
from config.settings import settings
import logging
logger = logging.getLogger(__name__)
# Configure logging

router = APIRouter()

def get_topic_agent(request: Request) -> TopicExtractionAgent:
    """Get TopicExtractionAgent with preloaded embedding model from app state."""
    embedding_model = getattr(request.app.state, 'embedding_model', None)
    return TopicExtractionAgent(embedding_model=embedding_model)

@router.get("/extract/{subject_agent_id}")
def extract_topics_from_agent(
    subject_agent_id: str,
    topic_agent: TopicExtractionAgent = Depends(get_topic_agent),
    current_user: dict = Depends(get_current_user),
    max_topics: int = Query(default=20, ge=1, le=50, description="Maximum number of topics to extract"),
    include_subtopics: bool = Query(default=True, description="Whether to include subtopics in the extraction")
):
    """
    Extract topics and subtopics from a subject agent's stored content.
    
    This endpoint analyzes all document chunks stored for a specific subject agent
    and uses LLM to identify and structure the main topics, subtopics, and syllabus hierarchy.
    
    Args:
        subject_agent_id: ID of the subject agent to extract topics from
        max_topics: Maximum number of topics to return (1-50)
        include_subtopics: Whether to include subtopics in the response
        
    Returns:
        JSON response containing extracted topics with confidence scores and metadata
    """
    try:
        logger.info(f"🎯 User {current_user.get('user_id')} requesting topic extraction for agent {subject_agent_id}")
        
        # Get agent information from the subject_agent_id
        # We need to determine the db_name and collection_name from the agent_id
        db_name, collection_name = _get_agent_database_info(subject_agent_id)
        
        if not db_name or not collection_name:
            raise HTTPException(
                status_code=404,
                detail=f"Subject agent {subject_agent_id} not found or invalid"
            )
        
        # Extract topics using the agent
        result = topic_agent.extract_topics_from_agent(
            subject_agent_id=subject_agent_id,
            db_name=db_name,
            collection_name=collection_name,
            max_topics=max_topics,
            include_subtopics=include_subtopics
        )
        
        if result.get("status") == "error":
            raise HTTPException(
                status_code=500,
                detail=result.get("message", "Failed to extract topics")
            )
        
        logger.info(f"✅ Successfully extracted {len(result.get('topics', []))} topics for agent {subject_agent_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error in topic extraction endpoint: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error during topic extraction: {str(e)}"
        )

@router.get("/extract/{subject_agent_id}/preview")
def preview_topics_extraction(
    subject_agent_id: str,
    topic_agent: TopicExtractionAgent = Depends(get_topic_agent),
    current_user: dict = Depends(get_current_user),
    sample_size: int = Query(default=5, ge=1, le=20, description="Number of content samples to analyze")
):
    """
    Preview topic extraction with limited sample size.
    
    This is a faster version that analyzes only a few samples to give a quick preview
    of what topics might be available.
    """
    try:
        logger.info(f"🔍 User {current_user.get('user_id')} requesting topic preview for agent {subject_agent_id}")
        
        # Get agent information
        db_name, collection_name = _get_agent_database_info(subject_agent_id)
        
        if not db_name or not collection_name:
            raise HTTPException(
                status_code=404,
                detail=f"Subject agent {subject_agent_id} not found or invalid"
            )
        
        # Extract topics with limited scope for preview
        result = topic_agent.extract_topics_from_agent(
            subject_agent_id=subject_agent_id,
            db_name=db_name,
            collection_name=collection_name,
            max_topics=10,  # Limited for preview
            include_subtopics=False  # No subtopics for preview
        )
        
        if result.get("status") == "error":
            raise HTTPException(
                status_code=500,
                detail=result.get("message", "Failed to extract topic preview")
            )
        
        # Add preview metadata
        result["preview_mode"] = True
        result["sample_size"] = sample_size
        
        logger.info(f"✅ Successfully generated topic preview for agent {subject_agent_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error in topic preview endpoint: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error during topic preview: {str(e)}"
        )

def _get_agent_database_info(subject_agent_id: str) -> tuple[Optional[str], Optional[str]]:
    """
    Get database name and collection name for a subject agent.
    
    This function searches through all collections to find where the subject_agent_id is stored.
    Returns (db_name, collection_name) or (None, None) if not found.
    """
    try:
        import os
        from pymongo import MongoClient
        
        MONGODB_URI = settings.mongodb_uri
        if not MONGODB_URI:
            logger.error("MONGODB_URI environment variable not set")
            return None, None
        
        client = MongoClient(MONGODB_URI)
        
        # Get all databases (excluding system databases)
        system_dbs = {"admin", "local", "config"}
        databases = [db for db in client.list_database_names() if db not in system_dbs]
        
        for db_name in databases:
            db = client[db_name]
            collections = db.list_collection_names()
            
            for collection_name in collections:
                collection = db[collection_name]
                
                # Check if this collection contains the subject_agent_id
                try:
                    sample = collection.find_one({"subject_agent_id": subject_agent_id})
                    if sample:
                        logger.info(f"Found agent {subject_agent_id} in {db_name}.{collection_name}")
                        client.close()
                        return db_name, collection_name
                except Exception:
                    # Skip collection if query fails
                    continue
        
        client.close()
        logger.warning(f"Subject agent {subject_agent_id} not found in any collection")
        return None, None
        
    except Exception as e:
        logger.error(f"Error searching for agent {subject_agent_id}: {e}")
        return None, None
