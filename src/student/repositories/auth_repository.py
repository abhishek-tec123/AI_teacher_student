"""
Authentication Management Module

Handles all authentication-related operations including:
- User authentication and verification
- Password management (bcrypt only)
- User session management
- Role-based access control
- Student creation with authentication
"""

from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from common.db.database import get_database
from common.auth.password_utils import get_password_hash, verify_password, generate_default_password
from student.repositories.student_repository import StudentManager
import logging
logger = logging.getLogger(__name__)


DEFAULT_CORE_MEMORY = {
    "self_description": "",
    "study_preferences": "",
    "motivation_statement": "",
    "background_context": "",
    "current_focus_struggle": ""
}


def generate_student_id() -> str:
    import secrets
    return f"std_{secrets.token_hex(6)}"


class AuthRepository:
    """
    Manages authentication operations and user security.

    Provides functionality for user authentication, password management,
    student creation with authentication, and session handling.
    """

    def __init__(self, db=None):
        """Initialize auth manager with database connection."""
        self.db = db or get_database()
        self.students = self.db["students"]

    def create_student_with_auth(
        self,
        name: str,
        email: str,
        class_name: str,
        password: Optional[str] = None,
        subject_agent: Optional[Dict] = None
    ) -> Tuple[str, str]:
        """
        Create a new student with authentication.

        Args:
            name: Student name
            email: Student email
            class_name: Student class/grade
            password: Optional password (auto-generated if not provided)
            subject_agent: Optional subject agent configuration

        Returns:
            Tuple of (student_id, password)
        """
        student_id = generate_student_id()

        # Generate password if not provided
        if password is None:
            password = generate_default_password()

        # Hash password with bcrypt
        password_hash = get_password_hash(password)

        # Normalize subject_agent to ensure subject_agent_id is stored
        normalized_subject_agent = None
        try:
            student_repo = StudentManager(self.db)
            normalized_subject_agent = student_repo._normalize_subject_agent(
                subject_agent,
                class_name,
            )
        except Exception as e:
            logger.warning(f"Failed to normalize subject_agent during auth creation: {e}")
            normalized_subject_agent = subject_agent

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
            "auth": {
                "password_hash": password_hash,
                "is_active": True,
                "last_login": None,
                "role": "student"
            },
            "metadata": {
                "created_at": datetime.utcnow(),
                "last_active": None,
                "last_conversation_id": {}
            }
        }

        self.students.insert_one(student_doc)

        # Log activity
        try:
            from student.services.activity_tracker import log_student_created
            subject_agent_name = None
            if normalized_subject_agent:
                entry = normalized_subject_agent
                if isinstance(entry, list) and entry:
                    entry = entry[0]
                if isinstance(entry, dict):
                    subject_agent_name = (
                        entry.get("subject")
                        or entry.get("name")
                        or "Unknown Agent"
                    )
                elif isinstance(entry, str):
                    subject_agent_name = entry

            log_student_created(
                student_id=student_id,
                student_name=name,
                class_name=class_name,
                subject_agent=subject_agent_name
            )
        except Exception as e:
            logger.warning(f"Failed to log student creation activity: {e}")

        return student_id, password

    def authenticate_user(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Authenticate user with email and password.

        Args:
            email: User email
            password: User password

        Returns:
            User data if authentication successful, None otherwise
        """
        student = self.students.find_one({
            "student_details.email": email,
            "auth.is_active": True
        })

        if not student:
            return None

        stored_hash = student["auth"]["password_hash"]

        # Verify with bcrypt
        if not verify_password(password, stored_hash):
            return None

        # Update last login
        self.students.update_one(
            {"student_id": student["student_id"]},
            {"$set": {"auth.last_login": datetime.utcnow()}}
        )

        return {
            "user_id": student["student_id"],
            "email": student["student_details"]["email"],
            "name": student["student_details"]["name"],
            "class": student["student_details"]["class"],
            "role": student["auth"]["role"],
            "is_active": student["auth"]["is_active"]
        }

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Get user by email address.

        Args:
            email: User email

        Returns:
            User data or None if not found
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

    def update_password(self, student_id: str, new_password: str) -> bool:
        """
        Update user password.

        Args:
            student_id: Student identifier
            new_password: New password

        Returns:
            True if successful, False otherwise
        """
        password_hash = get_password_hash(new_password)

        result = self.students.update_one(
            {"student_id": student_id},
            {"$set": {"auth.password_hash": password_hash}}
        )
        return result.modified_count > 0

    def admin_update_student_password(self, student_id: str, password_hash: str) -> bool:
        """
        Admin function to update student password with pre-hashed password.

        Args:
            student_id: Student identifier
            password_hash: Already hashed password

        Returns:
            True if successful, False otherwise
        """
        result = self.students.update_one(
            {"student_id": student_id},
            {"$set": {"auth.password_hash": password_hash}}
        )
        return result.modified_count > 0

    def update_student_with_password(
        self,
        student_id: str,
        payload
    ) -> Optional[Any]:
        """
        Update student information including password.

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
            update_data["student_details.subject_agent"] = data["subject_agent"]

        # Handle password update
        if "password" in data:
            new_password = data["password"]
            update_data["auth.password_hash"] = get_password_hash(new_password)

        if not update_data:
            return None

        result = self.students.update_one(
            {"student_id": student_id},
            {"$set": update_data}
        )

        # Log activity if update was successful
        if result.modified_count > 0:
            try:
                from student.services.activity_tracker import log_student_updated

                student = self.students.find_one({"student_id": student_id})
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
                    elif "password_hash" in field:
                        changes.append("password")

                if changes:
                    log_student_updated(
                        student_id=student_id,
                        student_name=student_name,
                        changes=changes
                    )
            except Exception as e:
                logger.warning(f"Failed to log student update activity: {e}")

        return result

    def deactivate_user(self, student_id: str) -> bool:
        """
        Deactivate a user account.

        Args:
            student_id: Student identifier

        Returns:
            True if successful, False otherwise
        """
        result = self.students.update_one(
            {"student_id": student_id},
            {"$set": {"auth.is_active": False}}
        )
        return result.modified_count > 0

    def activate_user(self, student_id: str) -> bool:
        """
        Activate a user account.

        Args:
            student_id: Student identifier

        Returns:
            True if successful, False otherwise
        """
        result = self.students.update_one(
            {"student_id": student_id},
            {"$set": {"auth.is_active": True}}
        )
        return result.modified_count > 0

    def update_user_role(self, student_id: str, role: str) -> bool:
        """
        Update user role.

        Args:
            student_id: Student identifier
            role: New role (e.g., "student", "admin")

        Returns:
            True if successful, False otherwise
        """
        valid_roles = ["student", "admin", "teacher"]
        if role not in valid_roles:
            raise ValueError(f"Invalid role. Must be one of: {valid_roles}")

        result = self.students.update_one(
            {"student_id": student_id},
            {"$set": {"auth.role": role}}
        )
        return result.modified_count > 0

    def check_email_exists(self, email: str) -> bool:
        """
        Check if email already exists in the system.

        Args:
            email: Email to check

        Returns:
            True if email exists, False otherwise
        """
        student = self.students.find_one({"student_details.email": email})
        return student is not None

    def get_user_by_id(self, student_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user by student ID.

        Args:
            student_id: Student identifier

        Returns:
            User data or None if not found
        """
        student = self.students.find_one({"student_id": student_id})
        if not student:
            return None

        return {
            "user_id": student["student_id"],
            "email": student["student_details"]["email"],
            "name": student["student_details"]["name"],
            "class": student["student_details"]["class"],
            "role": student.get("auth", {}).get("role", "student"),
            "is_active": student.get("auth", {}).get("is_active", True),
            "last_login": student.get("auth", {}).get("last_login"),
            "created_at": student["metadata"]["created_at"]
        }

    def get_active_users_count(self) -> int:
        """
        Get count of active users.

        Returns:
            Number of active users
        """
        return self.students.count_documents({"auth.is_active": True})

    def get_users_by_role(self, role: str) -> list:
        """
        Get all users with a specific role.

        Args:
            role: Role to filter by

        Returns:
            List of users with specified role
        """
        students = self.students.find(
            {"auth.role": role},
            {
                "_id": 0,
                "student_id": 1,
                "student_details.name": 1,
                "student_details.email": 1,
                "student_details.class": 1,
                "auth.is_active": 1,
                "auth.last_login": 1
            }
        )

        return [
            {
                "user_id": student["student_id"],
                "name": student["student_details"]["name"],
                "email": student["student_details"]["email"],
                "class": student["student_details"]["class"],
                "is_active": student["auth"]["is_active"],
                "last_login": student["auth"]["last_login"]
            }
            for student in students
        ]

    def reset_password(self, email: str) -> Optional[str]:
        """
        Reset password for user and return new password.

        Args:
            email: User email

        Returns:
            New password if successful, None otherwise
        """
        student = self.students.find_one({"student_details.email": email})
        if not student:
            return None

        new_password = generate_default_password()
        password_hash = get_password_hash(new_password)

        result = self.students.update_one(
            {"student_id": student["student_id"]},
            {"$set": {"auth.password_hash": password_hash}}
        )

        if result.modified_count > 0:
            return new_password

        return None

AuthManager = AuthRepository
