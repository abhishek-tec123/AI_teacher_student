"""
Chat Session Management Module

Handles all chat session operations including:
- Creating and managing chat sessions
- Chat session history tracking
- Chat session metadata management
- Integration with conversation system
"""

from bson import ObjectId
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from common.db.database import DatabaseConnection
import random
import string


class ChatSessionManager:
    """
    Manages chat session operations and metadata.
    
    Provides functionality for chat session creation, retrieval,
    updating, and integration with the conversation system.
    """
    
    def __init__(self, db_connection: DatabaseConnection = None):
        """Initialize chat session manager with database connection."""
        self.db = db_connection or DatabaseConnection()
        self.students = self.db.get_students_collection()
    
    def generate_chat_session_id(self) -> str:
        """Generate a unique chat session ID."""
        random_part = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        return f"chat_{random_part}"
    
    def generate_chat_title(self, first_query: str, subject: str = None) -> str:
        """Generate a chat title from the first query."""
        if not first_query:
            return "New Chat"
        
        # Simple title generation - can be enhanced with topic extraction
        words = first_query.split()
        if len(words) <= 5:
            title = first_query[:50] + ("..." if len(first_query) > 50 else "")
        else:
            title = " ".join(words[:5]) + "..."
        
        # Add subject if provided
        if subject:
            title = f"{subject}: {title}"
        
        return title
    
    def create_chat_session(
        self,
        student_id: str,
        title: Optional[str] = None,
        subject: Optional[str] = None,
        first_query: Optional[str] = None,
        agent_type: Optional[str] = None,
        agent_name: Optional[str] = None,
        agent_id: Optional[str] = None
    ) -> str:
        """
        Create a new chat session for a student within their existing document.
        
        Args:
            student_id: Student identifier
            title: Optional custom title
            subject: Optional subject for the chat
            first_query: Optional first query to generate title from
            agent_type: Optional agent type (e.g., 'subject', 'general')
            agent_name: Optional agent name (e.g., 'Math', 'Science')
            agent_id: Optional agent ID
            
        Returns:
            Chat session ID as string
        """
        chat_session_id = self.generate_chat_session_id()
        timestamp = datetime.utcnow()
        
        # Generate title if not provided
        if not title:
            title = self.generate_chat_title(first_query or "New Chat", subject)
        
        chat_session_data = {
            "title": title,
            "created_at": timestamp,
            "updated_at": timestamp,
            "message_count": 0
        }
        
        if subject:
            chat_session_data["subject"] = subject
        
        # Add agent information if provided
        if agent_type:
            chat_session_data["agent_type"] = agent_type
        if agent_name:
            chat_session_data["agent_name"] = agent_name
        if agent_id:
            chat_session_data["agent_id"] = agent_id
        
        # Add chat session to EXISTING student document
        self.students.update_one(
            {"student_id": student_id},
            {
                "$set": {
                    f"chat_sessions.{chat_session_id}": chat_session_data,
                    "metadata.last_active": timestamp
                }
            }
            # NO upsert=True - only work with existing students
        )
        
        return chat_session_id
    
    def get_student_chat_sessions(self, student_id: str) -> List[Dict[str, Any]]:
        """
        Get all chat sessions for a student.
        
        Args:
            student_id: Student identifier
            
        Returns:
            List of chat session data sorted by updated_at (most recent first)
        """
        doc = self.students.find_one(
            {"student_id": student_id},
            {"chat_sessions": 1}
        )
        
        if not doc:
            return []
        
        chat_sessions = doc.get("chat_sessions", {})
        
        # Convert to list and sort by updated_at
        session_list = []
        for session_id, session_data in chat_sessions.items():
            session_list.append({
                "chat_session_id": session_id,
                **session_data
            })
        
        # Sort by updated_at (most recent first)
        session_list.sort(
            key=lambda x: x.get("updated_at", datetime.min),
            reverse=True
        )
        
        # Serialize datetime objects
        for session in session_list:
            if session.get("created_at"):
                session["created_at"] = session["created_at"].isoformat()
            if session.get("updated_at"):
                session["updated_at"] = session["updated_at"].isoformat()
        
        return session_list
    
    def get_chat_session(self, student_id: str, chat_session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific chat session for a student.
        
        Args:
            student_id: Student identifier
            chat_session_id: Chat session identifier
            
        Returns:
            Chat session data or None if not found
        """
        doc = self.students.find_one(
            {"student_id": student_id},
            {f"chat_sessions.{chat_session_id}": 1}
        )
        
        if not doc:
            return None
        
        chat_sessions = doc.get("chat_sessions", {})
        session_data = chat_sessions.get(chat_session_id)
        
        if not session_data:
            return None
        
        # Add session ID and serialize datetime
        result = {
            "chat_session_id": chat_session_id,
            **session_data
        }
        
        if result.get("created_at"):
            result["created_at"] = result["created_at"].isoformat()
        if result.get("updated_at"):
            result["updated_at"] = result["updated_at"].isoformat()
        
        return result
    
    def update_chat_session(
        self,
        student_id: str,
        chat_session_id: str,
        updates: Dict[str, Any]
    ) -> int:
        """
        Update a chat session.
        
        Args:
            student_id: Student identifier
            chat_session_id: Chat session identifier
            updates: Dictionary of fields to update
            
        Returns:
            Number of modified documents (1 if successful, 0 otherwise)
        """
        # Always update the updated_at timestamp
        updates["updated_at"] = datetime.utcnow()
        
        result = self.students.update_one(
            {"student_id": student_id, f"chat_sessions.{chat_session_id}": {"$exists": True}},
            {
                "$set": {
                    f"chat_sessions.{chat_session_id}.{k}": v
                    for k, v in updates.items()
                }
            }
        )
        
        return result.modified_count
    
    def increment_message_count(self, student_id: str, chat_session_id: str) -> int:
        """
        Increment the message count for a chat session.
        
        Args:
            student_id: Student identifier
            chat_session_id: Chat session identifier
            
        Returns:
            Number of modified documents
        """
        result = self.students.update_one(
            {"student_id": student_id, f"chat_sessions.{chat_session_id}": {"$exists": True}},
            {
                "$inc": {f"chat_sessions.{chat_session_id}.message_count": 1},
                "$set": {f"chat_sessions.{chat_session_id}.updated_at": datetime.utcnow()}
            }
        )
        
        return result.modified_count
    
    def delete_chat_session(self, student_id: str, chat_session_id: str) -> int:
        """
        Delete a chat session and its associated conversations.
        
        Args:
            student_id: Student identifier
            chat_session_id: Chat session identifier
            
        Returns:
            Number of modified documents
        """
        # First, remove the chat session
        session_result = self.students.update_one(
            {"student_id": student_id},
            {"$unset": {f"chat_sessions.{chat_session_id}": ""}}
        )
        
        if session_result.modified_count > 0:
            # Remove all conversations associated with this chat session
            # This requires updating the conversation_history structure
            doc = self.students.find_one(
                {"student_id": student_id},
                {"conversation_history": 1}
            )
            
            if doc:
                conversation_history = doc.get("conversation_history", {})
                updates = {}
                
                # Remove conversations with this chat_session_id from all subjects
                for subject, conversations in conversation_history.items():
                    filtered_conversations = [
                        conv for conv in conversations 
                        if conv.get("chat_session_id") != chat_session_id
                    ]
                    
                    if len(filtered_conversations) != len(conversations):
                        updates[f"conversation_history.{subject}"] = filtered_conversations
                
                if updates:
                    self.students.update_one(
                        {"student_id": student_id},
                        {"$set": updates}
                    )
        
        return session_result.modified_count
    
    def get_chat_session_history(
        self,
        student_id: str,
        chat_session_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get conversation history for a specific chat session.
        
        Args:
            student_id: Student identifier
            chat_session_id: Chat session identifier
            limit: Optional maximum number of conversations to return
            
        Returns:
            List of conversation documents sorted by timestamp (newest first)
        """
        doc = self.students.find_one(
            {"student_id": student_id},
            {"conversation_history": 1}
        )
        
        if not doc:
            return []
        
        conversation_history = doc.get("conversation_history", {})
        session_conversations = []
        
        # Collect all conversations for this chat session
        for subject, conversations in conversation_history.items():
            for conv in conversations:
                if conv.get("chat_session_id") == chat_session_id:
                    conv_copy = conv.copy()
                    conv_copy["subject"] = subject
                    session_conversations.append(conv_copy)
        
        # Sort by timestamp (newest first)
        session_conversations.sort(
            key=lambda x: x.get("timestamp", datetime.min),
            reverse=True
        )
        
        # Apply limit if provided
        if limit is not None:
            session_conversations = session_conversations[:limit]
        
        # Serialize Mongo types
        return [
            {
                "conversation_id": str(conv.get("_id", "")),
                "chat_session_id": conv.get("chat_session_id"),
                "subject": conv.get("subject"),
                "query": conv.get("query", ""),
                "response": conv.get("response", ""),
                "feedback": conv.get("feedback", "neutral"),
                "confusion_type": conv.get("confusion_type", "NO_CONFUSION"),
                "timestamp": conv["timestamp"].isoformat() if conv.get("timestamp") else None,
                "evaluation": conv.get("evaluation", {})
            }
            for conv in session_conversations
        ]
    
    def get_or_create_active_chat_session(
        self,
        student_id: str,
        subject: str,
        query: Optional[str] = None,
        title: Optional[str] = None,
        agent_type: Optional[str] = None,
        agent_name: Optional[str] = None,
        agent_id: Optional[str] = None
    ) -> str:
        """
        Get the active chat session for a student and subject, or create a new one.
        Only works with existing student documents.
        
        Args:
            student_id: Student identifier
            subject: Subject name
            query: Optional query for title generation
            title: Optional custom title
            agent_type: Optional agent type
            agent_name: Optional agent name
            agent_id: Optional agent ID
            
        Returns:
            Chat session ID as string
            
        Raises:
            ValueError: If student doesn't exist
        """
        # First verify student exists
        student_doc = self.students.find_one({"student_id": student_id})
        if not student_doc:
            raise ValueError(f"Student {student_id} not found. Cannot create chat session.")
        
        # Check if there's an active chat session for this student and subject
        active_sessions = student_doc.get("active_chat_sessions", {})
        existing_session_id = active_sessions.get(subject)
        
        # If active session exists, validate it still exists
        if existing_session_id:
            chat_sessions = student_doc.get("chat_sessions", {})
            if existing_session_id in chat_sessions:
                # Increment message count and update timestamp
                self.increment_message_count(student_id, existing_session_id)
                return existing_session_id
            else:
                # Clean up invalid session reference
                self.students.update_one(
                    {"student_id": student_id},
                    {"$unset": {f"active_chat_sessions.{subject}": ""}}
                )
        
        # Create new chat session
        chat_session_id = self.create_chat_session(
            student_id=student_id,
            title=title,
            subject=subject,
            first_query=query,
            agent_type=agent_type,
            agent_name=agent_name,
            agent_id=agent_id
        )
        
        # Set as active session for this subject
        self.students.update_one(
            {"student_id": student_id},
            {"$set": {f"active_chat_sessions.{subject}": chat_session_id}}
        )
        
        return chat_session_id
    
    def set_active_chat_session(
        self,
        student_id: str,
        subject: str,
        chat_session_id: str
    ) -> int:
        """
        Manually set the active chat session for a student and subject.
        
        Args:
            student_id: Student identifier
            subject: Subject name
            chat_session_id: Chat session identifier
            
        Returns:
            Number of modified documents
        """
        # Validate chat session exists
        if not self.chat_session_exists(student_id, chat_session_id):
            return 0
        
        result = self.students.update_one(
            {"student_id": student_id},
            {"$set": {f"active_chat_sessions.{subject}": chat_session_id}}
        )
        
        return result.modified_count
    
    def get_active_chat_session(
        self,
        student_id: str,
        subject: str
    ) -> Optional[str]:
        """
        Get the active chat session for a student and subject.
        
        Args:
            student_id: Student identifier
            subject: Subject name
            
        Returns:
            Chat session ID or None if no active session
        """
        doc = self.students.find_one(
            {"student_id": student_id},
            {f"active_chat_sessions.{subject}": 1}
        )
        
        if not doc:
            return None
        
        active_sessions = doc.get("active_chat_sessions", {})
        session_id = active_sessions.get(subject)
        
        # Validate session still exists
        if session_id and self.chat_session_exists(student_id, session_id):
            return session_id
        
        return None
    
    def clear_active_chat_session(
        self,
        student_id: str,
        subject: str
    ) -> int:
        """
        Clear the active chat session for a student and subject.
        
        Args:
            student_id: Student identifier
            subject: Subject name
            
        Returns:
            Number of modified documents
        """
        result = self.students.update_one(
            {"student_id": student_id},
            {"$unset": {f"active_chat_sessions.{subject}": ""}}
        )
        
        return result.modified_count

    def chat_session_exists(self, student_id: str, chat_session_id: str) -> bool:
        """
        Check if a chat session exists for a student.
        
        Args:
            student_id: Student identifier
            chat_session_id: Chat session identifier
            
        Returns:
            True if chat session exists, False otherwise
        """
        doc = self.students.find_one(
            {"student_id": student_id},
            {f"chat_sessions.{chat_session_id}": 1}
        )
        
        return doc is not None and chat_session_id in doc.get("chat_sessions", {})
