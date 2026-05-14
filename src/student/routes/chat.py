"""
Student chat routes
Handles agent queries, chat history, and conversation management
"""

from fastapi import APIRouter, Request, Depends, HTTPException, Query
from student.agents.query_handler import queryRouter
from student.repositories.student_repository import StudentManager
from student.repositories.conversation_repository import ConversationManager
from student.repositories.chat_session_repository import ChatSessionManager
from common.utils.dependencies import StudentManagerDep, get_conversation_manager, ChatSessionManagerDep
from common.auth.dependencies import get_current_user
from pydantic import BaseModel
from typing import Optional, List, Dict

router = APIRouter()

context_store: dict[str, list[dict[str, str]]] = {}

class AskRequest(BaseModel):
    student_id: str
    subject: str
    class_name: str
    query: str
    chat_session_id: Optional[str] = None
    language: Optional[str] = None  # "auto", "english", "hindi", "hinglish" - auto-detects if not provided

class ChatHistoryItem(BaseModel):
    student_id: str
    query: str
    response: str
    evaluation: Optional[Dict] = {}

@router.post("/agent-query")
def ask(
    payload: AskRequest, 
    request: Request, 
    current_user: dict = Depends(get_current_user),
    chat_session_manager: ChatSessionManager = ChatSessionManagerDep
):
    # Ensure student can only access their own data
    if current_user["role"] == "student" and current_user["user_id"] != payload.student_id:
        raise HTTPException(status_code=403, detail="Access denied: You can only query as yourself")
    
    # Handle chat session logic
    chat_session_id = payload.chat_session_id
    
    # If no chat session provided, get or create the active session for this subject
    if not chat_session_id:
        try:
            chat_session_id = chat_session_manager.get_or_create_active_chat_session(
                student_id=payload.student_id,
                subject=payload.subject,
                query=payload.query
            )
        except ValueError as e:
            # Student doesn't exist - this should be handled by student creation first
            raise HTTPException(status_code=404, detail=str(e))
        
        # Update payload with the chat session ID
        payload.chat_session_id = chat_session_id
    else:
        # Validate that the chat session exists and belongs to the student
        if not chat_session_manager.chat_session_exists(payload.student_id, chat_session_id):
            raise HTTPException(status_code=404, detail="Chat session not found")
        
        # Set this as the active session for this subject
        chat_session_manager.set_active_chat_session(
            student_id=payload.student_id,
            subject=payload.subject,
            chat_session_id=chat_session_id
        )
        
        # Increment message count for existing chat session
        chat_session_manager.increment_message_count(payload.student_id, chat_session_id)
    
    # Call the original queryRouter
    result = queryRouter(
        payload=payload,
        student_agent=request.app.state.student_agent,
        student_manager=request.app.state.student_manager,
        context_store=context_store
    )
    
    # Add chat session info to response
    if hasattr(result, 'content') and isinstance(result.content, dict):
        result.content["chat_session_id"] = chat_session_id
    
    return result

@router.get("/{student_id}/history/{subject}", response_model=List[ChatHistoryItem])
def get_chat_history(
    student_id: str,
    subject: str,
    limit: Optional[int] = None,
    student_manager: StudentManager = StudentManagerDep,
    conversation_manager: ConversationManager = Depends(get_conversation_manager),
    current_user: dict = Depends(get_current_user)
):
    """
    Get chat history for a specific student and subject(agent).
    """

    # 🔐 Students can only access their own history
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Access denied")

    history = conversation_manager.get_chat_history_by_agent(
        student_id=student_id,
        subject=subject,
        limit=limit
    )

    if not history:
        return []

    return history

from student.services.feedback_handler import record_feedback, FeedbackRequest
@router.post("/feedback")
def submit_feedback(
    payload: FeedbackRequest,
    conversation_manager: ConversationManager = Depends(get_conversation_manager),
    current_user: dict = Depends(get_current_user)
):
    return record_feedback(
        conversation_id=payload.conversation_id,
        feedback=payload.feedback,
        conversation_manager=conversation_manager
    )
