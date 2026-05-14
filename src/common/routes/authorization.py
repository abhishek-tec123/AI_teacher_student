"""
Authorization routes
Handles user creation and admin operations
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from models.auth import (
    StudentCreateWithAuth, AdminCreateRequest
)
from common.auth.dependencies import get_current_user, require_role
from student.services.auth_service import (
    handle_create_student_with_auth, handle_create_admin, handle_admin_reset_student_password
)

router = APIRouter()

class ResetPasswordRequest_admin_reset_student(BaseModel):
    current_password: str
    new_password: str

@router.post("/create-student-with-auth")
def create_student_with_auth(
    payload: StudentCreateWithAuth,
    current_user: dict = Depends(require_role("admin"))
):
    """Create a new student with authentication (admin only)."""
    return handle_create_student_with_auth(payload)

@router.post("/create-admin")
def create_admin(
    payload: AdminCreateRequest,
    current_user: dict = Depends(require_role("admin"))
):
    """Create a new admin (admin only)."""
    return handle_create_admin(payload)

@router.post("/admin/admin-reset-student-password/{student_id}")
def reset_student_password(
    student_id: str,
    payload: ResetPasswordRequest_admin_reset_student,
    current_user: dict = Depends(get_current_user),
):
    return handle_admin_reset_student_password(
        student_id=student_id,
        payload=payload,
        current_user=current_user,
    )
