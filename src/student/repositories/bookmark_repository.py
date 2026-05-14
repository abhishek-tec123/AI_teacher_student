"""
Bookmark Management Module

Handles all bookmark-related operations including:
- Bookmark creation, retrieval, update, deletion
- Bookmark pagination and filtering
- Conversation-to-bookmark mapping
- Personal notes management
"""

from bson import ObjectId
from datetime import datetime
from typing import Optional, Dict, Any, List
from common.db.database import DatabaseConnection


class BookmarkManager:
    """
    Manages bookmark operations and storage.
    
    Provides functionality for creating, managing, and retrieving
    bookmarks that reference specific conversations.
    """
    
    def __init__(self, db_connection: DatabaseConnection = None):
        """Initialize bookmark manager with database connection."""
        self.db = db_connection or DatabaseConnection()
        self.students = self.db.get_students_collection()
        self.bookmarks = self.db.get_collection("bookmarks")
    
    def add_bookmark(
        self, 
        student_id: str, 
        conversation_id: str, 
        subject: str, 
        personal_notes: str = ""
    ) -> str:
        """
        Create a bookmark for a specific conversation.
        
        Args:
            student_id: Student identifier
            conversation_id: Conversation to bookmark
            subject: Subject/agent name
            personal_notes: Optional personal notes for the bookmark
            
        Returns:
            Bookmark ID as string
            
        Raises:
            ValueError: If conversation not found or already bookmarked
        """
        # Import conversation manager to get conversation data
        from .conversation_manager import ConversationManager
        conv_manager = ConversationManager(self.db)
        
        # Get conversation data first
        conversation = conv_manager.get_conversation_by_id(conversation_id, student_id)
        if not conversation:
            raise ValueError("Conversation not found or access denied")
        
        # Check if already bookmarked
        existing = self.bookmarks.find_one({
            "student_id": student_id,
            "conversation_id": conversation_id
        })
        
        if existing:
            raise ValueError("Conversation already bookmarked")
        
        # Create bookmark document
        bookmark_doc = {
            "student_id": student_id,
            "conversation_id": conversation_id,
            "subject": subject,
            "original_query": conversation["query"],
            "ai_response": conversation["response"],
            "personal_notes": personal_notes,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        # Insert into bookmarks collection
        result = self.bookmarks.insert_one(bookmark_doc)
        return str(result.inserted_id)
    
    def get_student_bookmarks(
        self, 
        student_id: str, 
        page: int = 1, 
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Get paginated list of student's bookmarks.
        
        Args:
            student_id: Student identifier
            page: Page number (1-based)
            limit: Number of bookmarks per page (max 100)
            
        Returns:
            Dict with bookmarks list, total count, and pagination info
        """
        if page < 1:
            page = 1
        if limit < 1 or limit > 100:
            limit = 10
            
        skip = (page - 1) * limit
        
        # Get total count
        total = self.bookmarks.count_documents({"student_id": student_id})
        
        # Get bookmarks with pagination
        bookmarks = list(self.bookmarks.find(
            {"student_id": student_id},
            {
                "_id": 1, 
                "conversation_id": 1, 
                "subject": 1, 
                "original_query": 1, 
                "ai_response": 1, 
                "personal_notes": 1, 
                "created_at": 1, 
                "updated_at": 1
            }
        ).sort("created_at", -1).skip(skip).limit(limit))
        
        # Format bookmarks for API response
        formatted_bookmarks = []
        for bookmark in bookmarks:
            formatted_bookmarks.append({
                "bookmark_id": str(bookmark["_id"]),
                "conversation_id": bookmark["conversation_id"],
                "subject": bookmark["subject"],
                "original_query": bookmark["original_query"],
                "ai_response": bookmark["ai_response"],
                "personal_notes": bookmark["personal_notes"],
                "created_at": bookmark["created_at"].isoformat(),
                "updated_at": bookmark["updated_at"].isoformat()
            })
        
        return {
            "bookmarks": formatted_bookmarks,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit
        }
    
    def get_bookmark_by_id(self, bookmark_id: str) -> Optional[Dict[str, Any]]:
        """
        Get bookmark by ID (without student validation).
        
        Args:
            bookmark_id: Bookmark identifier
            
        Returns:
            Bookmark data or None if not found
        """
        try:
            bookmark_obj_id = ObjectId(bookmark_id)
        except Exception:
            return None
        
        bookmark = self.bookmarks.find_one({"_id": bookmark_obj_id})
        
        if bookmark:
            return {
                "bookmark_id": str(bookmark["_id"]),
                "student_id": bookmark["student_id"],
                "conversation_id": bookmark["conversation_id"],
                "subject": bookmark["subject"],
                "original_query": bookmark["original_query"],
                "ai_response": bookmark["ai_response"],
                "personal_notes": bookmark["personal_notes"],
                "created_at": bookmark["created_at"].isoformat(),
                "updated_at": bookmark["updated_at"].isoformat()
            }
        
        return None
    
    def get_student_bookmark_by_id(
        self, 
        bookmark_id: str, 
        student_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get bookmark by ID with student validation.
        
        Args:
            bookmark_id: Bookmark identifier
            student_id: Student identifier for validation
            
        Returns:
            Bookmark data if found and belongs to student, None otherwise
        """
        try:
            bookmark_obj_id = ObjectId(bookmark_id)
        except Exception:
            return None
        
        bookmark = self.bookmarks.find_one({
            "_id": bookmark_obj_id,
            "student_id": student_id
        })
        
        if bookmark:
            return {
                "bookmark_id": str(bookmark["_id"]),
                "student_id": bookmark["student_id"],
                "conversation_id": bookmark["conversation_id"],
                "subject": bookmark["subject"],
                "original_query": bookmark["original_query"],
                "ai_response": bookmark["ai_response"],
                "personal_notes": bookmark["personal_notes"],
                "created_at": bookmark["created_at"].isoformat(),
                "updated_at": bookmark["updated_at"].isoformat()
            }
        
        return None
    
    def update_bookmark_notes(
        self, 
        bookmark_id: str, 
        student_id: str, 
        personal_notes: str
    ) -> bool:
        """
        Update personal notes for a bookmark.
        
        Args:
            bookmark_id: Bookmark identifier
            student_id: Student identifier for validation
            personal_notes: New personal notes content
            
        Returns:
            True if successful, False otherwise
        """
        try:
            bookmark_obj_id = ObjectId(bookmark_id)
        except Exception:
            return False
        
        result = self.bookmarks.update_one(
            {
                "_id": bookmark_obj_id,
                "student_id": student_id
            },
            {
                "$set": {
                    "personal_notes": personal_notes,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        return result.modified_count > 0
    
    def delete_bookmark(self, bookmark_id: str, student_id: str) -> bool:
        """
        Delete a bookmark.
        
        Args:
            bookmark_id: Bookmark identifier
            student_id: Student identifier for validation
            
        Returns:
            True if successful, False otherwise
        """
        try:
            bookmark_obj_id = ObjectId(bookmark_id)
        except Exception:
            return False
        
        result = self.bookmarks.delete_one({
            "_id": bookmark_obj_id,
            "student_id": student_id
        })
        
        return result.deleted_count > 0
    
    def get_bookmark_by_conversation_id(
        self, 
        conversation_id: str, 
        student_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Check if a conversation is bookmarked and return bookmark data.
        
        Args:
            conversation_id: Conversation identifier
            student_id: Student identifier
            
        Returns:
            Bookmark data if found, None otherwise
        """
        bookmark = self.bookmarks.find_one({
            "student_id": student_id,
            "conversation_id": conversation_id
        })
        
        if bookmark:
            return {
                "bookmark_id": str(bookmark["_id"]),
                "conversation_id": bookmark["conversation_id"],
                "subject": bookmark["subject"],
                "personal_notes": bookmark["personal_notes"],
                "created_at": bookmark["created_at"].isoformat(),
                "updated_at": bookmark["updated_at"].isoformat()
            }
        
        return None
    
    def get_bookmarks_by_subject(
        self, 
        student_id: str, 
        subject: str, 
        page: int = 1, 
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Get paginated bookmarks for a specific subject.
        
        Args:
            student_id: Student identifier
            subject: Subject/agent name
            page: Page number (1-based)
            limit: Number of bookmarks per page
            
        Returns:
            Dict with bookmarks list, total count, and pagination info
        """
        if page < 1:
            page = 1
        if limit < 1 or limit > 100:
            limit = 10
            
        skip = (page - 1) * limit
        
        # Get total count
        total = self.bookmarks.count_documents({
            "student_id": student_id,
            "subject": subject
        })
        
        # Get bookmarks with pagination
        bookmarks = list(self.bookmarks.find(
            {
                "student_id": student_id,
                "subject": subject
            },
            {
                "_id": 1, 
                "conversation_id": 1, 
                "subject": 1, 
                "original_query": 1, 
                "ai_response": 1, 
                "personal_notes": 1, 
                "created_at": 1, 
                "updated_at": 1
            }
        ).sort("created_at", -1).skip(skip).limit(limit))
        
        # Format bookmarks for API response
        formatted_bookmarks = []
        for bookmark in bookmarks:
            formatted_bookmarks.append({
                "bookmark_id": str(bookmark["_id"]),
                "conversation_id": bookmark["conversation_id"],
                "subject": bookmark["subject"],
                "original_query": bookmark["original_query"],
                "ai_response": bookmark["ai_response"],
                "personal_notes": bookmark["personal_notes"],
                "created_at": bookmark["created_at"].isoformat(),
                "updated_at": bookmark["updated_at"].isoformat()
            })
        
        return {
            "bookmarks": formatted_bookmarks,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit
        }
    
    def search_bookmarks(
        self, 
        student_id: str, 
        query: str, 
        page: int = 1, 
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Search bookmarks by query in original_query, ai_response, or personal_notes.
        
        Args:
            student_id: Student identifier
            query: Search query string
            page: Page number (1-based)
            limit: Number of bookmarks per page
            
        Returns:
            Dict with bookmarks list, total count, and pagination info
        """
        if page < 1:
            page = 1
        if limit < 1 or limit > 100:
            limit = 10
            
        skip = (page - 1) * limit
        
        # Build search filter
        search_filter = {
            "student_id": student_id,
            "$or": [
                {"original_query": {"$regex": query, "$options": "i"}},
                {"ai_response": {"$regex": query, "$options": "i"}},
                {"personal_notes": {"$regex": query, "$options": "i"}},
                {"subject": {"$regex": query, "$options": "i"}}
            ]
        }
        
        # Get total count
        total = self.bookmarks.count_documents(search_filter)
        
        # Get bookmarks with pagination
        bookmarks = list(self.bookmarks.find(
            search_filter,
            {
                "_id": 1, 
                "conversation_id": 1, 
                "subject": 1, 
                "original_query": 1, 
                "ai_response": 1, 
                "personal_notes": 1, 
                "created_at": 1, 
                "updated_at": 1
            }
        ).sort("created_at", -1).skip(skip).limit(limit))
        
        # Format bookmarks for API response
        formatted_bookmarks = []
        for bookmark in bookmarks:
            formatted_bookmarks.append({
                "bookmark_id": str(bookmark["_id"]),
                "conversation_id": bookmark["conversation_id"],
                "subject": bookmark["subject"],
                "original_query": bookmark["original_query"],
                "ai_response": bookmark["ai_response"],
                "personal_notes": bookmark["personal_notes"],
                "created_at": bookmark["created_at"].isoformat(),
                "updated_at": bookmark["updated_at"].isoformat()
            })
        
        return {
            "bookmarks": formatted_bookmarks,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit
        }
    
    def get_student_bookmark_stats(self, student_id: str) -> Dict[str, Any]:
        """
        Get bookmark statistics for a student.
        
        Args:
            student_id: Student identifier
            
        Returns:
            Dictionary with bookmark statistics
        """
        pipeline = [
            {"$match": {"student_id": student_id}},
            {"$group": {
                "_id": "$subject",
                "count": {"$sum": 1},
                "latest": {"$max": "$created_at"}
            }},
            {"$sort": {"count": -1}}
        ]
        
        subject_stats = list(self.bookmarks.aggregate(pipeline))
        
        total_bookmarks = self.bookmarks.count_documents({"student_id": student_id})
        
        return {
            "total_bookmarks": total_bookmarks,
            "subjects": [
                {
                    "subject": stat["_id"],
                    "count": stat["count"],
                    "latest_bookmark": stat["latest"].isoformat() if stat.get("latest") else None
                }
                for stat in subject_stats
            ]
        }
