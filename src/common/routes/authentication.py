"""
Authentication routes
Handles login, token management, and user authentication
"""

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from models.auth import (
    LoginRequest, LoginResponse, TokenRefreshRequest, TokenRefreshResponse,
    PasswordChangeRequest, UserResponse
)
from common.auth.dependencies import get_current_user
from student.services.auth_service import (
    handle_login, handle_refresh_token, handle_change_password
)

router = APIRouter()
security = HTTPBearer()

@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    return handle_login(payload.email, payload.password)

@router.post("/refresh", response_model=TokenRefreshResponse)
def refresh_token(payload: TokenRefreshRequest):
    return handle_refresh_token(payload.refresh_token)

@router.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current user information."""
    return UserResponse(**current_user)

@router.post("/change-password")
def change_password(
    payload: PasswordChangeRequest,
    current_user: dict = Depends(get_current_user)
):
    """Change current user's password."""
    return handle_change_password(
        current_user=current_user,
        current_password=payload.current_password,
        new_password=payload.new_password
    )
