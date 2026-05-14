from fastapi import APIRouter, Depends, Query
from typing import List, Optional
from common.auth.dependencies import require_role
from student.services.activity_tracker import (
    activity_tracker,
    ActivityType
)
from pydantic import BaseModel

router = APIRouter()

class ActivityResponse(BaseModel):
    id: str
    activity_type: str
    target_id: str
    target_name: str
    description: str
    time_ago: str
    timestamp: str
    metadata: dict

class ActivityStatsResponse(BaseModel):
    total_activities: int
    period_days: int
    by_type: List[dict]

@router.get("/recent", response_model=List[ActivityResponse])
def get_recent_activities(
    limit: int = Query(50, ge=1, le=200, description="Maximum number of activities to return"),
    activity_types: Optional[List[str]] = Query(None, description="Filter by activity types"),
    hours_back: Optional[int] = Query(None, ge=1, le=8760, description="Only show activities from last N hours"),
    current_user: dict = Depends(require_role("admin"))
):
    """
    Get recent activities from the system.
    
    Args:
        limit: Maximum number of activities to return (1-200)
        activity_types: Optional filter for specific activity types
        hours_back: Optional filter to show only recent activities
    
    Returns:
        List of recent activities with time ago formatting
    """
    # Convert string activity types to enum if provided
    activity_type_enums = None
    if activity_types:
        activity_type_enums = []
        for activity_type in activity_types:
            try:
                activity_type_enums.append(ActivityType(activity_type))
            except ValueError:
                # Skip invalid activity types
                continue
    
    activities = activity_tracker.get_recent_activities(
        limit=limit,
        activity_types=activity_type_enums,
        hours_back=hours_back
    )
    
    return activities

@router.get("/stats", response_model=ActivityStatsResponse)
def get_activity_stats(
    days_back: int = Query(7, ge=1, le=365, description="Number of days to look back for stats"),
    current_user: dict = Depends(require_role("admin"))
):
    """
    Get activity statistics for the past N days.
    
    Args:
        days_back: Number of days to look back (1-365)
    
    Returns:
        Activity statistics broken down by type
    """
    stats = activity_tracker.get_activity_stats(days_back=days_back)
    return stats

@router.get("/activity-types")
def get_activity_types(current_user: dict = Depends(require_role("admin"))):
    """
    Get available activity types for filtering.
    
    Returns:
        List of available activity types
    """
    return {
        "activity_types": [
            {
                "value": activity_type.value,
                "label": activity_type.value.replace("_", " ").title()
            }
            for activity_type in ActivityType
        ]
    }
