from pymongo import MongoClient
from datetime import datetime
from typing import Optional, Dict, Any, List
from bson import ObjectId

from common.auth.password_utils import get_password_hash, verify_password, generate_default_password
from config.settings import settings
import logging
logger = logging.getLogger(__name__)

ADMINS_COLLECTION = "admins"

class AdminManager:
    def __init__(self):
        self.client = MongoClient(settings.mongodb_uri)
        self.db = self.client[settings.db_name]
        self.admins = self.db[ADMINS_COLLECTION]
    
    def initialize_admins_collection(self):
        """Initialize the admins collection if it doesn't exist."""
        if ADMINS_COLLECTION not in self.db.list_collection_names():
            logger.info(f"Collection '{ADMINS_COLLECTION}' does not exist. Creating...")
            temp_id = self.admins.insert_one({"_temp": True}).inserted_id
            self.admins.delete_one({"_id": temp_id})
            logger.info(f"Collection '{ADMINS_COLLECTION}' created.")
        else:
            logger.info(f"Collection '{ADMINS_COLLECTION}' exists.")
    
    def create_admin(
        self,
        name: str,
        email: str,
        password: Optional[str] = None,
        permissions: Optional[List[str]] = None
    ) -> tuple[str, str]:
        """Create a new admin user."""
        
        # Check if admin already exists
        existing_admin = self.admins.find_one({"email": email})
        if existing_admin:
            raise ValueError(f"Admin with email {email} already exists")
        
        # Generate password if not provided
        if password is None:
            password = generate_default_password()
        
        password_hash = get_password_hash(password)
        admin_id = str(ObjectId())
        
        admin_doc = {
            "_id": ObjectId(),
            "admin_id": admin_id,
            "name": name,
            "email": email,
            "auth": {
                "password_hash": password_hash,
                "is_active": True,
                "last_login": None,
                "role": "admin"
            },
            "permissions": permissions or ["all"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        self.admins.insert_one(admin_doc)
        return admin_id, password
    
    def authenticate_admin(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate admin by email and password."""
        admin = self.admins.find_one({
            "email": email,
            "auth.is_active": True
        })
        
        if not admin:
            return None
        
        if not verify_password(password, admin["auth"]["password_hash"]):
            return None
        
        # Update last login
        self.admins.update_one(
            {"admin_id": admin["admin_id"]},
            {"$set": {"auth.last_login": datetime.utcnow()}}
        )
        
        return {
            "user_id": admin["admin_id"],
            "email": admin["email"],
            "name": admin["name"],
            "role": admin["auth"]["role"],
            "is_active": admin["auth"]["is_active"],
            "permissions": admin["permissions"]
        }
    
    def get_admin_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get admin by email."""
        admin = self.admins.find_one({"email": email})
        if not admin:
            return None
        
        return {
            "user_id": admin["admin_id"],
            "email": admin["email"],
            "name": admin["name"],
            "role": admin["auth"]["role"],
            "is_active": admin["auth"]["is_active"],
            "permissions": admin["permissions"],
            "last_login": admin["auth"].get("last_login"),
            "created_at": admin["created_at"]
        }
    
    def get_admin_by_id(self, admin_id: str) -> Optional[Dict[str, Any]]:
        """Get admin by ID."""
        admin = self.admins.find_one({"admin_id": admin_id})
        if not admin:
            return None
        
        return {
            "user_id": admin["admin_id"],
            "email": admin["email"],
            "name": admin["name"],
            "role": admin["auth"]["role"],
            "is_active": admin["auth"]["is_active"],
            "permissions": admin["permissions"],
            "last_login": admin["auth"].get("last_login"),
            "created_at": admin["created_at"]
        }
    
    def update_admin_password(self, admin_id: str, new_password: str) -> bool:
        """Update admin password."""
        password_hash = get_password_hash(new_password)
        result = self.admins.update_one(
            {"admin_id": admin_id},
            {
                "$set": {
                    "auth.password_hash": password_hash,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        return result.modified_count > 0
    
    def list_admins(self) -> List[Dict[str, Any]]:
        """List all admins."""
        admins = self.admins.find(
            {},
            {
                "_id": 0,
                "admin_id": 1,
                "name": 1,
                "email": 1,
                "auth.is_active": 1,
                "auth.last_login": 1,
                "permissions": 1,
                "created_at": 1
            }
        )
        
        result = []
        for admin in admins:
            result.append({
                "user_id": admin["admin_id"],
                "name": admin["name"],
                "email": admin["email"],
                "is_active": admin["auth"]["is_active"],
                "last_login": admin["auth"].get("last_login"),
                "permissions": admin["permissions"],
                "created_at": admin["created_at"]
            })
        
        return result
    
    def deactivate_admin(self, admin_id: str) -> bool:
        """Deactivate an admin."""
        result = self.admins.update_one(
            {"admin_id": admin_id},
            {
                "$set": {
                    "auth.is_active": False,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        return result.modified_count > 0
    
    def close(self):
        """Close database connection."""
        self.client.close()
