from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
from datetime import datetime

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    
    @validator('password')
    def validate_password(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Password cannot be empty')
        return v.strip()

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict

class TokenRefreshRequest(BaseModel):
    refresh_token: str

class TokenRefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str
    
    @validator('new_password')
    def validate_password_strength(cls, v):
        from common.auth.password_utils import validate_password_strength
        is_valid, error_msg = validate_password_strength(v)
        if not is_valid:
            raise ValueError(error_msg)
        return v

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str
    
    @validator('new_password')
    def validate_password_strength(cls, v):
        from common.auth.password_utils import validate_password_strength
        is_valid, error_msg = validate_password_strength(v)
        if not is_valid:
            raise ValueError(error_msg)
        return v

class UserResponse(BaseModel):
    user_id: str
    email: str
    name: str
    role: str
    is_active: bool
    last_login: Optional[datetime] = None
    created_at: datetime

class StudentCreateWithAuth(BaseModel):
    name: str
    email: EmailStr
    class_name: str
    password: Optional[str] = None
    subject_agent: Optional[List[dict]] = None
    
    @validator('password')
    def validate_password_strength(cls, v):
        if v is None:
            return v  # Will be generated if not provided
        from common.auth.password_utils import validate_password_strength
        is_valid, error_msg = validate_password_strength(v)
        if not is_valid:
            raise ValueError(error_msg)
        return v

class AdminCreateRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    permissions: Optional[List[str]] = []
    
    @validator('password')
    def validate_password_strength(cls, v):
        from common.auth.password_utils import validate_password_strength
        is_valid, error_msg = validate_password_strength(v)
        if not is_valid:
            raise ValueError(error_msg)
        return v
