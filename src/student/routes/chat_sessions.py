"""
Student chat session routes
Handles chat session creation, management, and history retrieval
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from student.repositories.chat_session_repository import ChatSessionManager
from student.repositories.conversation_repository import ConversationManager
from common.utils.dependencies import StudentManagerDep, ChatSessionManagerDep
from common.auth.dependencies import get_current_user
from pydantic import BaseModel
from typing import Optional, List, Dict

router = APIRouter()

class CreateChatSessionRequest(BaseModel):
    student_id: str
    title: Optional[str] = None
    agent_type: Optional[str] = None
    agent_name: Optional[str] = None
    agent_id: Optional[str] = None

class UpdateChatSessionRequest(BaseModel):
    title: Optional[str] = None

@router.post("/chat-sessions")
def create_chat_session(
    request: CreateChatSessionRequest,
    chat_session_manager: ChatSessionManager = ChatSessionManagerDep,
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Create a new chat session with optional title.
    """
    
    student_id = request.student_id

    # 🔐 Students can only create their own chat sessions
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        title = request.title if request.title else "New Chat"

        chat_session_id = chat_session_manager.create_chat_session(
            student_id=student_id,
            title=title,
            agent_type=request.agent_type,
            agent_name=request.agent_name,
            agent_id=request.agent_id
        )

        return {
            "chat_session_id": chat_session_id,
            "title": title,
            "agent_type": request.agent_type,
            "agent_name": request.agent_name,
            "agent_id": request.agent_id,
            "message": "New chat session created successfully"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{student_id}/chat-sessions")
def get_chat_sessions(
    student_id: str,
    chat_session_manager: ChatSessionManager = ChatSessionManagerDep,
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Get all chat sessions for a student.
    """
    # 🔐 Students can only access their own chat sessions
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        chat_sessions = chat_session_manager.get_student_chat_sessions(student_id)
        return {
            "chat_sessions": chat_sessions,
            "total_count": len(chat_sessions)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve chat sessions: {str(e)}")

@router.get("/{student_id}/chat-sessions/{chat_session_id}")
def get_chat_session(
    student_id: str,
    chat_session_id: str,
    chat_session_manager: ChatSessionManager = ChatSessionManagerDep,
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Get a specific chat session for a student.
    """
    # 🔐 Students can only access their own chat sessions
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        chat_session = chat_session_manager.get_chat_session(student_id, chat_session_id)
        if not chat_session:
            raise HTTPException(status_code=404, detail="Chat session not found")
        
        return chat_session
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve chat session: {str(e)}")

@router.put("/{student_id}/chat-sessions/{chat_session_id}")
def update_chat_session(
    student_id: str,
    chat_session_id: str,
    request: UpdateChatSessionRequest,
    chat_session_manager: ChatSessionManager = ChatSessionManagerDep,
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Update a chat session (e.g., change title).
    """
    # 🔐 Students can only update their own chat sessions
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Validate chat session exists
    if not chat_session_manager.chat_session_exists(student_id, chat_session_id):
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    try:
        updates = {}
        if request.title is not None:
            updates["title"] = request.title
        
        if not updates:
            raise HTTPException(status_code=400, detail="No valid fields to update")
        
        modified_count = chat_session_manager.update_chat_session(
            student_id=student_id,
            chat_session_id=chat_session_id,
            updates=updates
        )
        
        if modified_count == 0:
            raise HTTPException(status_code=500, detail="Failed to update chat session")
        
        return {"message": "Chat session updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update chat session: {str(e)}")

@router.delete("/{student_id}/chat-sessions/{chat_session_id}")
def delete_chat_session(
    student_id: str,
    chat_session_id: str,
    chat_session_manager: ChatSessionManager = ChatSessionManagerDep,
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Delete a chat session and its associated conversations.
    """
    # 🔐 Students can only delete their own chat sessions
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Validate chat session exists
    if not chat_session_manager.chat_session_exists(student_id, chat_session_id):
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    try:
        modified_count = chat_session_manager.delete_chat_session(
            student_id=student_id,
            chat_session_id=chat_session_id
        )
        
        if modified_count == 0:
            raise HTTPException(status_code=500, detail="Failed to delete chat session")
        
        return {"message": "Chat session deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete chat session: {str(e)}")

@router.get("/{student_id}/active-chat-session/{subject}")
def get_active_chat_session(
    student_id: str,
    subject: str,
    chat_session_manager: ChatSessionManager = ChatSessionManagerDep,
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Get the active chat session for a student and subject.
    """
    # 🔐 Students can only access their own active sessions
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        active_session_id = chat_session_manager.get_active_chat_session(
            student_id=student_id,
            subject=subject
        )
        
        if not active_session_id:
            return {
                "active_chat_session_id": None,
                "message": "No active chat session found for this subject"
            }
        
        # Get full session details
        session_details = chat_session_manager.get_chat_session(
            student_id=student_id,
            chat_session_id=active_session_id
        )
        
        return {
            "active_chat_session_id": active_session_id,
            "session_details": session_details
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get active chat session: {str(e)}")

@router.post("/{student_id}/active-chat-session/{subject}")
def set_active_chat_session(
    student_id: str,
    subject: str,
    chat_session_id: str,
    chat_session_manager: ChatSessionManager = ChatSessionManagerDep,
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Set the active chat session for a student and subject.
    """
    # 🔐 Students can only manage their own active sessions
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        # Validate chat session exists and belongs to student
        if not chat_session_manager.chat_session_exists(student_id, chat_session_id):
            raise HTTPException(status_code=404, detail="Chat session not found")
        
        modified_count = chat_session_manager.set_active_chat_session(
            student_id=student_id,
            subject=subject,
            chat_session_id=chat_session_id
        )
        
        if modified_count == 0:
            raise HTTPException(status_code=500, detail="Failed to set active chat session")
        
        return {
            "message": "Active chat session set successfully",
            "active_chat_session_id": chat_session_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set active chat session: {str(e)}")

@router.delete("/{student_id}/active-chat-session/{subject}")
def clear_active_chat_session(
    student_id: str,
    subject: str,
    chat_session_manager: ChatSessionManager = ChatSessionManagerDep,
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Clear the active chat session for a student and subject.
    """
    # 🔐 Students can only manage their own active sessions
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        modified_count = chat_session_manager.clear_active_chat_session(
            student_id=student_id,
            subject=subject
        )
        
        return {
            "message": "Active chat session cleared successfully",
            "cleared_count": modified_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear active chat session: {str(e)}")

@router.get("/{student_id}/chat-sessions/{chat_session_id}/history")
def get_chat_session_history(
    student_id: str,
    chat_session_id: str,
    limit: Optional[int] = Query(None, ge=1, le=100),
    conversation_manager: ConversationManager = Depends(lambda: ConversationManager()),
    chat_session_manager: ChatSessionManager = ChatSessionManagerDep,
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Get conversation history for a specific chat session.
    """
    # 🔐 Students can only access their own chat history
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Validate chat session exists
    if not chat_session_manager.chat_session_exists(student_id, chat_session_id):
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    try:
        history = conversation_manager.get_conversations_by_chat_session(
            student_id=student_id,
            chat_session_id=chat_session_id,
            limit=limit
        )
        
        return {
            "chat_session_id": chat_session_id,
            "history": history,
            "total_count": len(history)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve chat history: {str(e)}")
