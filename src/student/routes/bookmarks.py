"""
Student progress tracking routes
Handles recent activity, learning progress, and bookmarks
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from student.repositories.student_repository import StudentManager
from student.repositories.conversation_repository import ConversationManager
from student.repositories.bookmark_repository import BookmarkManager
from common.utils.dependencies import StudentManagerDep, BookmarkManagerDep, get_conversation_manager
from common.auth.dependencies import get_current_user
from pydantic import BaseModel
from typing import Optional, List
from bson import ObjectId

router = APIRouter()

class RecentActivityItem(BaseModel):
    conversation_id: str
    subject: str
    agent_id: str
    query: str
    response_preview: str
    timestamp: str
    time_ago: str
    feedback: str
    confusion_type: str

class UniqueAgentInfo(BaseModel):
    subject: str
    agent_id: str
    conversation_count: int

class RecentActivityResponse(BaseModel):
    student_id: str
    recent_activity: List[RecentActivityItem]
    total_count: int
    agents_used_count: int
    unique_agents: List[UniqueAgentInfo]

# Bookmark Models - Phase 1
class BookmarkRequest(BaseModel):
    conversation_id: str
    subject: str
    personal_notes: Optional[str] = ""

class BookmarkResponse(BaseModel):
    bookmark_id: str
    conversation_id: str
    subject: str
    original_query: str
    ai_response: str
    personal_notes: str
    created_at: str
    updated_at: str

class BookmarkUpdate(BaseModel):
    personal_notes: str

class BookmarkListResponse(BaseModel):
    bookmarks: List[BookmarkResponse]
    total: int
    page: int
    limit: int
    total_pages: int

# -------------------------------------------------
# Student Recent Activity
# -------------------------------------------------
@router.get("/{student_id}/recent-activity", response_model=RecentActivityResponse)
def get_student_recent_activity(
    student_id: str,
    limit: int = Query(6, ge=1, le=100, description="Maximum number of agents to show"),
    hours_back: Optional[int] = Query(None, ge=1, le=8760, description="Only show activities from last N hours"),
    student_manager: StudentManager = StudentManagerDep,
    conversation_manager: ConversationManager = Depends(get_conversation_manager),
    current_user: dict = Depends(get_current_user)
):
    """
    Get student's most recent conversation from each agent/subject.
    
    Args:
        student_id: Student identifier
        limit: Maximum number of agents to show (1-100)
        hours_back: Optional filter to show only recent activities within last N hours
    
    Returns:
        Recent activities across different subjects/agents
    """
    
    # 🔐 Students can only access their own activity
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Access denied: You can only access your own activity")
    
    # Get recent activity data
    activity_data = conversation_manager.get_student_recent_activity(
        student_id=student_id,
        limit=limit,
        hours_back=hours_back
    )
    
    return RecentActivityResponse(
        student_id=student_id,
        recent_activity=activity_data["recent_activity"],
        total_count=activity_data["total_count"],
        agents_used_count=activity_data["agents_used_count"],
        unique_agents=activity_data["unique_agents"]
    )


# ---------------------------
# BOOKMARK ROUTES - PHASE 1
# ---------------------------

@router.post("/{student_id}/bookmarks")
def create_bookmark(
    student_id: str,
    payload: BookmarkRequest,
    bookmark_manager: BookmarkManager = BookmarkManagerDep,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a bookmark for a conversation.
    Students can only bookmark their own conversations.
    """
    # Students can only bookmark their own conversations
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Access denied: You can only bookmark your own conversations")
    
    try:
        bookmark_id = bookmark_manager.add_bookmark(
            student_id=student_id,
            conversation_id=payload.conversation_id,
            subject=payload.subject,
            personal_notes=payload.personal_notes
        )
        
        return {
            "message": "Bookmark created successfully",
            "bookmark_id": bookmark_id
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create bookmark")

@router.get("/{student_id}/bookmarks", response_model=BookmarkListResponse)
def get_student_bookmarks(
    student_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Number of bookmarks per page"),
    bookmark_manager: BookmarkManager = BookmarkManagerDep,
    current_user: dict = Depends(get_current_user)
):
    """
    Get paginated list of student's bookmarks.
    Students can only access their own bookmarks.
    """
    # Students can only access their own bookmarks
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Access denied: You can only access your own bookmarks")
    
    try:
        bookmark_data = bookmark_manager.get_student_bookmarks(
            student_id=student_id,
            page=page,
            limit=limit
        )
        
        return BookmarkListResponse(**bookmark_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to retrieve bookmarks")

@router.put("/bookmarks/{bookmark_id}")
def update_bookmark(
    bookmark_id: str,
    payload: BookmarkUpdate,
    bookmark_manager: BookmarkManager = BookmarkManagerDep,
    current_user: dict = Depends(get_current_user)
):
    """
    Update personal notes for a bookmark.
    Students can only update their own bookmarks.
    """
    try:
        # First check if bookmark exists at all (without student validation)
        bookmark_exists = bookmark_manager.get_bookmark_by_id(bookmark_id)
        
        if not bookmark_exists:
            raise HTTPException(status_code=404, detail="Bookmark not found")
        
        # Now verify bookmark belongs to current user
        bookmark = bookmark_manager.get_student_bookmark_by_id(bookmark_id, current_user["user_id"])
        
        if not bookmark:
            raise HTTPException(status_code=403, detail="Access denied: Bookmark belongs to another student")
        
        success = bookmark_manager.update_bookmark_notes(
            bookmark_id=bookmark_id,
            student_id=current_user["user_id"],
            personal_notes=payload.personal_notes
        )
        
        if success:
            return {"message": "Bookmark updated successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to update bookmark")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update bookmark")

@router.delete("/bookmarks/{bookmark_id}")
def delete_bookmark(
    bookmark_id: str,
    bookmark_manager: BookmarkManager = BookmarkManagerDep,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a bookmark.
    Students can only delete their own bookmarks.
    """
    try:
        # First check if bookmark exists at all (without student validation)
        bookmark_exists = bookmark_manager.get_bookmark_by_id(bookmark_id)
        
        if not bookmark_exists:
            raise HTTPException(status_code=404, detail="Bookmark not found")
        
        # Now verify bookmark belongs to current user
        bookmark = bookmark_manager.get_student_bookmark_by_id(bookmark_id, current_user["user_id"])
        
        if not bookmark:
            raise HTTPException(status_code=403, detail="Access denied: Bookmark belongs to another student")
        
        success = bookmark_manager.delete_bookmark(
            bookmark_id=bookmark_id,
            student_id=current_user["user_id"]
        )
        
        if success:
            return {"message": "Bookmark deleted successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to delete bookmark")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to delete bookmark")
