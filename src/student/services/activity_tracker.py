from pymongo import MongoClient
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from enum import Enum
import os
from config.settings import settings
import logging
logger = logging.getLogger(__name__)
MONGO_URI = settings.mongodb_uri
DB_NAME = settings.db_name
ACTIVITY_COLLECTION = "activity_logs"

class ActivityType(str, Enum):
    AGENT_CREATED = "agent_created"
    AGENT_UPDATED = "agent_updated"
    AGENT_DELETED = "agent_deleted"
    STUDENT_CREATED = "student_created"
    STUDENT_UPDATED = "student_updated"

class ActivityTracker:
    def __init__(self):
        try:
            self.client = MongoClient(MONGO_URI)
            self.db = self.client[DB_NAME]
            self.activities = self.db[ACTIVITY_COLLECTION]
            
            # Create indexes for better performance
            self.activities.create_index([("timestamp", -1)])
            self.activities.create_index([("activity_type", 1)])
            self.activities.create_index([("target_id", 1)])
            self.connected = True
        except Exception as e:
            logger.info(f"Warning: Could not connect to MongoDB for activity tracking: {e}")
            self.connected = False
    
    def log_activity(
        self,
        activity_type: ActivityType,
        target_id: str,
        target_name: str,
        description: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Log an activity event."""
        if not self.connected:
            logger.info(f"Activity tracking disabled: {activity_type.value} - {description}")
            return "disabled"
        
        activity_doc = {
            "activity_type": activity_type,
            "target_id": target_id,
            "target_name": target_name,
            "description": description,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow()
        }
        
        result = self.activities.insert_one(activity_doc)
        return str(result.inserted_id)
    
    def get_recent_activities(
        self,
        limit: int = 50,
        activity_types: Optional[List[ActivityType]] = None,
        hours_back: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get recent activities with optional filtering."""
        if not self.connected:
            logger.info("Activity tracking disabled - no database connection")
            return []
        
        # Build query
        query = {}
        
        if activity_types:
            query["activity_type"] = {"$in": activity_types}
        
        if hours_back:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
            query["timestamp"] = {"$gte": cutoff_time}
        
        # Fetch activities
        activities = list(
            self.activities.find(query)
            .sort("timestamp", -1)
            .limit(limit)
        )
        
        # Format and return
        formatted_activities = []
        for activity in activities:
            # Calculate time ago
            now = datetime.utcnow()
            activity_time = activity["timestamp"]
            time_diff = now - activity_time
            
            if time_diff.total_seconds() < 60:
                time_ago = f"{int(time_diff.total_seconds())} seconds ago"
            elif time_diff.total_seconds() < 3600:
                time_ago = f"{int(time_diff.total_seconds() / 60)} mins ago"
            elif time_diff.total_seconds() < 86400:
                time_ago = f"{int(time_diff.total_seconds() / 3600)} hours ago"
            else:
                time_ago = f"{int(time_diff.total_seconds() / 86400)} days ago"
            
            formatted_activities.append({
                "id": str(activity["_id"]),
                "activity_type": activity["activity_type"],
                "target_id": activity["target_id"],
                "target_name": activity["target_name"],
                "description": activity["description"],
                "time_ago": time_ago,
                "timestamp": activity["timestamp"].isoformat(),
                "metadata": activity.get("metadata", {})
            })
        
        return formatted_activities
    
    def get_activity_stats(self, days_back: int = 7) -> Dict[str, Any]:
        """Get activity statistics for the past N days."""
        if not self.connected:
            logger.info("Activity tracking disabled - no database connection")
            return {
                "total_activities": 0,
                "period_days": days_back,
                "by_type": []
            }
        
        cutoff_time = datetime.utcnow() - timedelta(days=days_back)
        
        pipeline = [
            {"$match": {"timestamp": {"$gte": cutoff_time}}},
            {"$group": {
                "_id": "$activity_type",
                "count": {"$sum": 1},
                "latest": {"$max": "$timestamp"}
            }},
            {"$sort": {"count": -1}}
        ]
        
        stats = list(self.activities.aggregate(pipeline))
        
        total_activities = sum(stat["count"] for stat in stats)
        
        return {
            "total_activities": total_activities,
            "period_days": days_back,
            "by_type": [
                {
                    "activity_type": stat["_id"],
                    "count": stat["count"],
                    "latest": stat["latest"].isoformat()
                }
                for stat in stats
            ]
        }
    
    def close(self):
        """Close the database connection."""
        if self.connected:
            self.client.close()

# Global instance
activity_tracker = ActivityTracker()

def log_agent_created(agent_id: str, agent_name: str, subject: str, class_name: str):
    """Helper function to log agent creation."""
    return activity_tracker.log_activity(
        activity_type=ActivityType.AGENT_CREATED,
        target_id=agent_id,
        target_name=agent_name,
        description=f"New agent created for {subject}",
        metadata={
            "subject": subject,
            "class": class_name,
            "action": "created"
        }
    )

def log_agent_updated(agent_id: str, agent_name: str, subject: str, class_name: str, changes: List[str]):
    """Helper function to log agent updates."""
    return activity_tracker.log_activity(
        activity_type=ActivityType.AGENT_UPDATED,
        target_id=agent_id,
        target_name=agent_name,
        description=f"Agent updated for {subject}",
        metadata={
            "subject": subject,
            "class": class_name,
            "changes": changes,
            "action": "updated"
        }
    )

def log_student_created(student_id: str, student_name: str, class_name: str, subject_agent: Optional[str] = None):
    """Helper function to log student creation."""
    description = f"New student joined"
    if subject_agent:
        description += f" - {subject_agent}"
    
    return activity_tracker.log_activity(
        activity_type=ActivityType.STUDENT_CREATED,
        target_id=student_id,
        target_name=student_name,
        description=description,
        metadata={
            "class": class_name,
            "subject_agent": subject_agent,
            "action": "created"
        }
    )

def log_student_updated(student_id: str, student_name: str, changes: List[str]):
    """Helper function to log student updates."""
    return activity_tracker.log_activity(
        activity_type=ActivityType.STUDENT_UPDATED,
        target_id=student_id,
        target_name=student_name,
        description=f"Student profile updated",
        metadata={
            "changes": changes,
            "action": "updated"
        }
    )

def log_agent_deleted(agent_id: str, dropped_collections: List[str], collections_with_multiple_agents: List[str], deleted_chunks: int):
    """Helper function to log agent deletion."""
    description = f"Agent deleted - {deleted_chunks} chunks removed"
    
    if dropped_collections:
        description += f", {len(dropped_collections)} collection(s) dropped"
    
    if collections_with_multiple_agents:
        description += f", {len(collections_with_multiple_agents)} multi-agent collection(s) cleaned"
    
    return activity_tracker.log_activity(
        activity_type=ActivityType.AGENT_DELETED,
        target_id=agent_id,
        target_name=f"Agent {agent_id}",
        description=description,
        metadata={
            "dropped_collections": dropped_collections,
            "collections_with_multiple_agents": collections_with_multiple_agents,
            "deleted_chunks": deleted_chunks,
            "action": "deleted"
        }
    )
