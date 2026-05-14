"""
Student Management Module

Handles all student-related operations including:
- Student creation, retrieval, update, deletion
- Student profile management
- Student listing and search operations
- Student metadata handling
"""

from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from common.db.database import DatabaseConnection, generate_student_id, DEFAULT_CORE_MEMORY
import logging
logger = logging.getLogger(__name__)


class StudentManager:
    """
    Manages student operations and profile data.
    
    Provides CRUD operations for students and handles
    student profile management, metadata, and basic operations.
    """
    
    def __init__(self, db_connection: DatabaseConnection = None):
        """Initialize student manager with database connection."""
        self.db = db_connection or DatabaseConnection()
        self.students = self.db.get_students_collection()
    
    def _normalize_subject_agent(
        self,
        subject_agent: Optional[Any],
        class_name: str
    ) -> Optional[Any]:
        """
        Ensure subject_agent entries also store subject_agent_id when possible.
        
        - If items already contain subject_agent_id / agent_id / id, keep them.
        - If items only contain a subject name, resolve subject_agent_id using
          get_all_agents_of_class(class_name) and attach it.
        """
        if not subject_agent:
            return subject_agent

        try:
            from teacher.repositories.collections import (
                get_all_agents_of_class,
                list_all_collections,
            )

            subject_to_agent_id: Dict[str, str] = {}

            # Helper to index agents by subject
            def index_agents(agents_list, preferred_class: Optional[str] = None):
                if not isinstance(agents_list, list):
                    return
                for agent in agents_list:
                    if not isinstance(agent, dict):
                        continue
                    subj = agent.get("subject")
                    subj_agent_id = agent.get("subject_agent_id")
                    agent_class = agent.get("class")
                    if not subj or not subj_agent_id:
                        continue

                    # If we already have an ID for this subject, only override
                    # when the new one matches preferred_class more closely.
                    if subj in subject_to_agent_id:
                        if preferred_class and agent_class == preferred_class:
                            subject_to_agent_id[subj] = subj_agent_id
                        continue
                    subject_to_agent_id[subj] = subj_agent_id

            # 1) Try class-specific lookup first (fast, precise)
            if class_name:
                agents_response = get_all_agents_of_class(class_name)
                if isinstance(agents_response, dict):
                    index_agents(agents_response.get("agents"), preferred_class=class_name)
                elif isinstance(agents_response, list):
                    index_agents(agents_response, preferred_class=class_name)

            # 2) Fallback: scan all collections if we still don't have mappings
            if not subject_to_agent_id:
                all_agents_response = list_all_collections()
                if isinstance(all_agents_response, dict):
                    index_agents(
                        all_agents_response.get("agents"),
                        preferred_class=class_name or None,
                    )

            def enrich_entry(entry: Any) -> Any:
                # String entry -> treat as subject name
                if isinstance(entry, str):
                    subj = entry
                    agent_id = subject_to_agent_id.get(subj)
                    result = {"subject": subj}
                    if agent_id:
                        result["subject_agent_id"] = agent_id
                    return result

                # Dict entry -> ensure subject_agent_id present
                if isinstance(entry, dict):
                    # If already has an ID field, keep as-is
                    if any(
                        key in entry
                        for key in ("subject_agent_id", "agent_id", "id")
                    ):
                        return entry

                    subj = entry.get("subject")
                    if subj:
                        agent_id = subject_to_agent_id.get(subj)
                        if agent_id:
                            entry = dict(entry)  # shallow copy
                            entry["subject_agent_id"] = agent_id
                    return entry

                # Fallback: return as-is
                return entry

            # Normalize structure: list of entries is the main case
            if isinstance(subject_agent, list):
                return [enrich_entry(item) for item in subject_agent]

            # Single entry (dict or string)
            return enrich_entry(subject_agent)

        except Exception as e:
            logger.info(f"Warning: failed to normalize subject_agent for class '{class_name}': {e}")
            return subject_agent
    
    def initialize_db_collection(self):
        """Initialize database and collection if they don't exist."""
        return self.db.initialize_db_collection()
    
    def create_student(
        self,
        name: str,
        email: str,
        class_name: str,
        subject_agent: Optional[Dict] = None
    ) -> str:
        """
        Create a new student without authentication.
        
        Args:
            name: Student name
            email: Student email
            class_name: Student class/grade
            subject_agent: Optional subject agent configuration
            
        Returns:
            Generated student ID
        """
        student_id = generate_student_id()

        # Normalize subject_agent to ensure subject_agent_id is stored
        normalized_subject_agent = self._normalize_subject_agent(subject_agent, class_name)

        student_doc = {
            "student_id": student_id,
            "student_details": {
                "name": name,
                "email": email,
                "class": class_name,
                "subject_agent": normalized_subject_agent or {}
            },
            "student_core_memory": DEFAULT_CORE_MEMORY.copy(),
            "conversation_summary": {},
            "conversation_history": {},
            "subject_preferences": {},
            "metadata": {
                "created_at": datetime.utcnow(),
                "last_active": None,
                "last_conversation_id": {}
            }
        }

        self.students.insert_one(student_doc)
        return student_id
    
    def get_student(self, student_id: str) -> Optional[Dict[str, Any]]:
        """
        Get student by student ID.
        
        Args:
            student_id: Student identifier
            
        Returns:
            Student document or None if not found
        """
        return self.students.find_one({"student_id": student_id})
    
    def update_student(self, student_id: str, payload) -> Optional[Any]:
        """
        Update student information.
        
        Args:
            student_id: Student identifier
            payload: Update data (typically from Pydantic model)
            
        Returns:
            Update result or None if no updates
        """
        update_data = {}
        data = payload.dict(exclude_none=True)

        if "name" in data:
            update_data["student_details.name"] = data["name"]
        if "email" in data:
            update_data["student_details.email"] = data["email"]
        if "class_name" in data:
            update_data["student_details.class"] = data["class_name"]
        if "subject_agent" in data:
            # Determine the class to use for normalization:
            # prefer new class_name from payload, otherwise current student's class
            current_class = data.get("class_name")
            if not current_class:
                existing = self.get_student(student_id)
                current_class = (
                    existing.get("student_details", {}).get("class", "")
                    if existing
                    else ""
                )

            normalized_subject_agent = self._normalize_subject_agent(
                data["subject_agent"],
                current_class or ""
            )
            update_data["student_details.subject_agent"] = normalized_subject_agent

        if not update_data:
            return None

        result = self.students.update_one(
            {"student_id": student_id},
            {"$set": update_data}
        )

        # Log activity if update was successful
        if result.modified_count > 0:
            try:
                from ..activity_tracker import log_student_updated
                
                student = self.get_student(student_id)
                student_name = student["student_details"]["name"] if student else "Unknown Student"
                
                changes = []
                for field in update_data.keys():
                    if "name" in field:
                        changes.append("name")
                    elif "email" in field:
                        changes.append("email")
                    elif "class" in field:
                        changes.append("class")
                    elif "subject_agent" in field:
                        changes.append("subject_agent")
                
                if changes:
                    log_student_updated(
                        student_id=student_id,
                        student_name=student_name,
                        changes=changes
                    )
            except Exception as e:
                logger.info(f"Failed to log student update activity: {e}")

        return result
    
    def delete_student(self, student_id: str) -> Any:
        """
        Delete a student by ID.
        
        Args:
            student_id: Student identifier
            
        Returns:
            Delete result
        """
        result = self.students.delete_one({"student_id": student_id})
        return result
    
    def list_students(self) -> List[Dict[str, Any]]:
        """
        Get list of all students with basic information.
        
        Returns:
            List of student documents with basic details
        """
        students = self.students.find(
            {},
            {
                "_id": 0,
                "student_id": 1,
                "student_details.name": 1,
                "student_details.email": 1,
                "student_details.class": 1,
                "student_details.subject_agent": 1
            }
        )

        result = []
        for student in students:
            details = student.get("student_details", {})
            subject_agent = details.get("subject_agent", None)

            result.append({
                "student_id": student.get("student_id"),
                "name": details.get("name"),
                "email": details.get("email"),
                "class": details.get("class"),
                "subject_agent": subject_agent if subject_agent else None
            })

        return result
    
    def update_student_metadata(self, student_id: str, metadata_updates: Dict[str, Any]) -> bool:
        """
        Update student metadata.
        
        Args:
            student_id: Student identifier
            metadata_updates: Metadata fields to update
            
        Returns:
            True if successful, False otherwise
        """
        update_data = {}
        for key, value in metadata_updates.items():
            update_data[f"metadata.{key}"] = value
        
        result = self.students.update_one(
            {"student_id": student_id},
            {"$set": update_data}
        )
        
        return result.modified_count > 0
    
    def update_last_active(self, student_id: str) -> bool:
        """
        Update student's last active timestamp.
        
        Args:
            student_id: Student identifier
            
        Returns:
            True if successful, False otherwise
        """
        return self.update_student_metadata(
            student_id, 
            {"last_active": datetime.utcnow()}
        )
    
    def get_student_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Get student by email address.
        
        Args:
            email: Student email
            
        Returns:
            Student document or None if not found
        """
        student = self.students.find_one({"student_details.email": email})
        if not student:
            return None
        
        return {
            "user_id": student["student_id"],
            "email": student["student_details"]["email"],
            "name": student["student_details"]["name"],
            "role": student.get("auth", {}).get("role", "student"),
            "is_active": student.get("auth", {}).get("is_active", True),
            "last_login": student.get("auth", {}).get("last_login"),
            "created_at": student["metadata"]["created_at"]
        }
    
    def search_students(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search students by name or email.
        
        Args:
            query: Search query string
            limit: Maximum number of results
            
        Returns:
            List of matching students
        """
        students = self.students.find(
            {
                "$or": [
                    {"student_details.name": {"$regex": query, "$options": "i"}},
                    {"student_details.email": {"$regex": query, "$options": "i"}}
                ]
            },
            {
                "_id": 0,
                "student_id": 1,
                "student_details.name": 1,
                "student_details.email": 1,
                "student_details.class": 1
            }
        ).limit(limit)

        return [
            {
                "student_id": student["student_id"],
                "name": student["student_details"]["name"],
                "email": student["student_details"]["email"],
                "class": student["student_details"]["class"]
            }
            for student in students
        ]
