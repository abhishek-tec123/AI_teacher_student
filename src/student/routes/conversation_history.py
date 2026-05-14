"""
Conversation History Routes

Provides endpoints for retrieving conversation history categorized by:
- Student ID
- Agent ID (subject)
- Session ID

Each session includes query, response, and timestamps.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from datetime import datetime

from student.repositories.conversation_repository import ConversationManager
from student.repositories.chat_session_repository import ChatSessionManager
from common.auth.dependencies import get_current_user

router = APIRouter()


class ConversationHistoryResponse(BaseModel):
    """Response model for conversation history."""
    student_id: str
    agents: List[Dict[str, Any]]
    total_conversations: int
    total_sessions: int


class AgentConversationData(BaseModel):
    """Model for agent-specific conversation data."""
    agent_id: str
    subject: str
    sessions: List[Dict[str, Any]]
    total_conversations: int


class SessionConversationData(BaseModel):
    """Model for session-specific conversation data."""
    session_id: str
    title: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    message_count: int
    conversations: List[Dict[str, Any]]


class ConversationData(BaseModel):
    """Model for individual conversation data."""
    conversation_id: str
    query: str
    response: str
    timestamp: str
    feedback: str
    confusion_type: str


@router.get("/conversation-history/{student_id}", response_model=ConversationHistoryResponse)
async def get_conversation_history(
    student_id: str,
    current_user: Dict = Depends(get_current_user),
    include_conversations: bool = Query(True, description="Include full conversation data"),
    limit_per_session: Optional[int] = Query(None, description="Limit conversations per session")
):
    """
    Get all conversation history for a student categorized by agent and session.
    
    Args:
        student_id: Student ID to retrieve history for
        include_conversations: Whether to include full conversation data
        limit_per_session: Optional limit on conversations per session
        
    Returns:
        Conversation history categorized by agent and session
    """
    try:
        # Verify the current user has access to this student's data
        if current_user.get("role") != "admin" and current_user.get("student_id") != student_id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to access this student's conversation history"
            )
        
        conversation_manager = ConversationManager()
        chat_session_manager = ChatSessionManager()
        
        # Get student document to understand the structure
        from common.db.database import DatabaseConnection
        db = DatabaseConnection()
        students = db.get_students_collection()
        
        student_doc = students.find_one({"student_id": student_id})
        if not student_doc:
            raise HTTPException(
                status_code=404,
                detail=f"Student {student_id} not found"
            )
        
        # Extract subject to agent_id mapping from student_details
        subject_agent_mapping = {}
        subject_agents = student_doc.get("student_details", {}).get("subject_agent", [])
        for agent_mapping in subject_agents:
            subject_name = agent_mapping.get("subject")
            agent_id = agent_mapping.get("subject_agent_id")
            if subject_name and agent_id:
                subject_agent_mapping[subject_name] = agent_id
        
        # Get conversation history and chat sessions
        conversation_history = student_doc.get("conversation_history", {})
        chat_sessions = student_doc.get("chat_sessions", {})
        
        # Organize data by agent/subject
        agents_data = []
        total_conversations = 0
        total_sessions = len(chat_sessions)
        
        for subject, conversations in conversation_history.items():
            # Group conversations by session
            sessions_data = {}
            agent_conversation_count = 0
            
            for conv in conversations:
                chat_session_id = conv.get("chat_session_id")
                if not chat_session_id:
                    continue
                
                # Get session info
                session_info = chat_sessions.get(chat_session_id, {})
                
                if chat_session_id not in sessions_data:
                    sessions_data[chat_session_id] = {
                        "session_id": chat_session_id,
                        "title": session_info.get("title", "Untitled Session"),
                        "created_at": session_info.get("created_at"),
                        "updated_at": session_info.get("updated_at"),
                        "message_count": session_info.get("message_count", 0),
                        "conversations": []
                    }
                
                # Add conversation data
                # Use the subject_agent_mapping for consistent agent_id
                final_agent_id = subject_agent_mapping.get(subject, subject)
                
                conv_data = {
                    "conversation_id": str(conv.get("_id", "")),
                    "query": conv.get("query", ""),
                    "response": conv.get("response", ""),
                    "timestamp": conv["timestamp"].isoformat() if conv.get("timestamp") else None,
                    "feedback": conv.get("feedback", "neutral"),
                    "confusion_type": conv.get("confusion_type", "NO_CONFUSION"),
                    "agent_id": final_agent_id,  # Use subject_agent_id first, then agent_id
                    "created_at": conv["timestamp"].isoformat() if conv.get("timestamp") else None,
                    "updated_at": conv["timestamp"].isoformat() if conv.get("timestamp") else None
                }
                
                sessions_data[chat_session_id]["conversations"].append(conv_data)
                agent_conversation_count += 1
            
            # Apply limit per session if specified
            if limit_per_session:
                for session_id in sessions_data:
                    sessions_data[session_id]["conversations"] = (
                        sessions_data[session_id]["conversations"][:limit_per_session]
                    )
            
            # Sort sessions by updated_at (most recent first)
            sorted_sessions = sorted(
                sessions_data.values(),
                key=lambda x: x.get("updated_at", datetime.min),
                reverse=True
            )
            
            # Sort conversations within each session by timestamp (most recent first)
            for session in sorted_sessions:
                session["conversations"].sort(
                    key=lambda x: x.get("timestamp", ""),
                    reverse=True
                )
            
            # Extract agent_id from student_details subject_agent mapping
            agent_id = subject_agent_mapping.get(subject, subject)  # Use mapped agent_id or fallback to subject name
            
            agents_data.append({
                "agent_id": agent_id,
                "subject": subject,
                "sessions": sorted_sessions,
                "total_conversations": agent_conversation_count
            })
            
            total_conversations += agent_conversation_count
        
        # Sort agents by total_conversations (most active first)
        agents_data.sort(key=lambda x: x["total_conversations"], reverse=True)
        
        return ConversationHistoryResponse(
            student_id=student_id,
            agents=agents_data,
            total_conversations=total_conversations,
            total_sessions=total_sessions
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving conversation history: {str(e)}"
        )


@router.get("/conversation-history/{student_id}/agent/{agent_id}")
async def get_agent_conversation_history(
    student_id: str,
    agent_id: str,
    current_user: Dict = Depends(get_current_user),
    limit: Optional[int] = Query(None, description="Limit number of conversations"),
    session_id: Optional[str] = Query(None, description="Filter by specific session")
):
    """
    Get conversation history for a specific student and agent.
    
    Args:
        student_id: Student ID
        agent_id: Agent ID or subject name
        limit: Optional limit on conversations
        session_id: Optional filter by specific session
        
    Returns:
        Agent-specific conversation history
    """
    try:
        # Verify authorization
        if current_user.get("role") != "admin" and current_user.get("student_id") != student_id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to access this student's conversation history"
            )
        
        conversation_manager = ConversationManager()
        
        # Get conversation history for the subject/agent
        if session_id:
            # Get conversations for specific session
            conversations = conversation_manager.get_conversations_by_chat_session(
                student_id=student_id,
                chat_session_id=session_id,
                limit=limit
            )
            # Filter by agent_id if needed
            if agent_id != "all":
                conversations = [c for c in conversations if c.get("agent_id") == agent_id]
        else:
            # Get all conversations for the subject
            conversations = conversation_manager.get_conversation_history(
                student_id=student_id,
                subject=agent_id,
                limit=limit
            )
        
        return {
            "student_id": student_id,
            "agent_id": agent_id,
            "conversations": conversations,
            "total_count": len(conversations)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving agent conversation history: {str(e)}"
        )


@router.get("/conversation-history/{student_id}/session/{session_id}")
async def get_session_conversation_history(
    student_id: str,
    session_id: str,
    current_user: Dict = Depends(get_current_user),
    limit: Optional[int] = Query(None, description="Limit number of conversations")
):
    """
    Get conversation history for a specific chat session.
    
    Args:
        student_id: Student ID
        session_id: Chat session ID
        limit: Optional limit on conversations
        
    Returns:
        Session-specific conversation history
    """
    try:
        # Verify authorization
        if current_user.get("role") != "admin" and current_user.get("student_id") != student_id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to access this student's conversation history"
            )
        
        conversation_manager = ConversationManager()
        chat_session_manager = ChatSessionManager()
        
        # Get session metadata
        session_data = chat_session_manager.get_chat_session(student_id, session_id)
        if not session_data:
            raise HTTPException(
                status_code=404,
                detail=f"Chat session {session_id} not found"
            )
        
        # Get conversations for this session
        conversations = conversation_manager.get_conversations_by_chat_session(
            student_id=student_id,
            chat_session_id=session_id,
            limit=limit
        )
        
        return {
            "student_id": student_id,
            "session_id": session_id,
            "session_info": session_data,
            "conversations": conversations,
            "total_conversations": len(conversations)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving session conversation history: {str(e)}"
        )


@router.get("/conversation-summary/{student_id}")
async def get_conversation_summary(
    student_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """
    Get a summary of all conversations for a student.
    
    Args:
        student_id: Student ID
        
    Returns:
        Summary statistics and overview
    """
    try:
        # Verify authorization
        if current_user.get("role") != "admin" and current_user.get("student_id") != student_id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to access this student's conversation summary"
            )
        
        conversation_manager = ConversationManager()
        chat_session_manager = ChatSessionManager()
        
        # Get recent activity
        recent_activity = conversation_manager.get_student_recent_activity(
            student_id=student_id,
            limit=10
        )
        
        # Get all chat sessions
        chat_sessions = chat_session_manager.get_student_chat_sessions(student_id)
        
        # Get student document for additional stats
        from common.db.database import DatabaseConnection
        db = DatabaseConnection()
        students = db.get_students_collection()
        
        student_doc = students.find_one({"student_id": student_id})
        conversation_history = student_doc.get("conversation_history", {}) if student_doc else {}
        
        # Calculate statistics
        total_conversations = sum(len(convs) for convs in conversation_history.values())
        total_agents = len(conversation_history)
        total_sessions = len(chat_sessions)
        
        # Get conversation summaries by subject
        subject_summaries = {}
        for subject in conversation_history.keys():
            summary = conversation_manager.get_subject_summary(student_id, subject)
            if summary:
                subject_summaries[subject] = summary
        
        return {
            "student_id": student_id,
            "statistics": {
                "total_conversations": total_conversations,
                "total_agents": total_agents,
                "total_sessions": total_sessions,
                "unique_agents": recent_activity.get("unique_agents", [])
            },
            "recent_activity": recent_activity.get("recent_activity", []),
            "chat_sessions": chat_sessions[:5],  # Recent 5 sessions
            "subject_summaries": subject_summaries
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving conversation summary: {str(e)}"
        )
