from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any, List

from .jwt_handler import extract_user_from_token
from student.repositories.student_repository import StudentManager
from admin.repositories.admin_repository import AdminManager

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """Get current authenticated user from JWT token."""
    
    # Extract user from token
    user = extract_user_from_token(credentials.credentials)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify user still exists and is active
    if user["role"] == "student":
        student_manager = StudentManager()
        student = student_manager.get_student(user["user_id"])
        if not student or not student["auth"]["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Student account not found or inactive",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Add additional student info
        user.update({
            "created_at": student["metadata"]["created_at"],
            "class": student["student_details"]["class"]
        })
    
    elif user["role"] == "admin":
        admin_manager = AdminManager()
        admin = admin_manager.get_admin_by_id(user["user_id"])
        if not admin or not admin["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Admin account not found or inactive",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Add additional admin info
        user.update({
            "permissions": admin["permissions"],
            "created_at": admin["created_at"]
        })
    
    return user

def require_role(required_role: str):
    """Dependency to require specific user role."""
    
    def role_checker(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if current_user["role"] != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {required_role}"
            )
        return current_user
    
    return role_checker

def require_any_role(allowed_roles: List[str]):
    """Dependency to require any of the specified user roles."""
    
    def role_checker(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required one of roles: {', '.join(allowed_roles)}"
            )
        return current_user
    
    return role_checker

def require_permission(permission: str):
    """Dependency to require specific permission (for admins)."""
    
    def permission_checker(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if current_user["role"] != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Admin access required"
            )
        
        # Check if admin has required permission
        permissions = current_user.get("permissions", [])
        if "all" not in permissions and permission not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required permission: {permission}"
            )
        
        return current_user
    
    return permission_checker

def get_optional_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))) -> Optional[Dict[str, Any]]:
    """Get current user if token is provided, without raising errors."""
    
    if not credentials:
        return None
    
    user = extract_user_from_token(credentials.credentials)
    if not user:
        return None
    
    # Verify user still exists and is active
    if user["role"] == "student":
        student_manager = StudentManager()
        student = student_manager.get_student(user["user_id"])
        if not student or not student["auth"]["is_active"]:
            return None
    
    elif user["role"] == "admin":
        admin_manager = AdminManager()
        admin = admin_manager.get_admin_by_id(user["user_id"])
        if not admin or not admin["is_active"]:
            return None
    
    return user
