from fastapi import HTTPException, status
from student.repositories.student_repository import StudentManager
from student.repositories.auth_repository import AuthManager
from admin.repositories.admin_repository import AdminManager
from common.auth.jwt_handler import (
    create_access_token,
    create_refresh_token,
    verify_token,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from common.auth.password_utils import (
    get_password_hash,
    verify_password,
    validate_password_strength,
)

def authenticate_user(email: str, password: str):
    """Authenticate student or admin."""
    
    # Try student
    auth_manager = AuthManager()
    user = auth_manager.authenticate_user(email, password)
    
    if user:
        return user

    # Try admin
    admin_manager = AdminManager()
    user = admin_manager.authenticate_admin(email, password)

    if user:
        return user

    return None


def generate_tokens(user: dict):
    """Generate access and refresh tokens."""
    
    access_token = create_access_token(
        data={
            "sub": user["user_id"],
            "email": user["email"],
            "role": user["role"],
            "name": user["name"]
        }
    )

    refresh_token = create_refresh_token(
        data={
            "sub": user["user_id"],
            "email": user["email"]
        }
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


def handle_login(email: str, password: str):
    """Main login logic."""
    
    user = authenticate_user(email, password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    tokens = generate_tokens(user)

    return {
        **tokens,
        "user": user
    }


def handle_refresh_token(refresh_token: str):
    """Refresh access token logic."""

    token_data = verify_token(refresh_token, "refresh")
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    user_id = token_data.get("sub")

    # Check student
    student_manager = StudentManager()
    user = student_manager.get_student(user_id)

    if user:
        user_info = {
            "user_id": user["student_id"],
            "email": user["student_details"]["email"],
            "name": user["student_details"]["name"],
            "role": user["auth"]["role"]
        }
    else:
        # Check admin
        admin_manager = AdminManager()
        admin = admin_manager.get_admin_by_id(user_id)

        if not admin:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )

        user_info = admin

    access_token = create_access_token(
        data={
            "sub": user_info["user_id"],
            "email": user_info["email"],
            "role": user_info["role"],
            "name": user_info["name"]
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }
# =======================================================================================
def handle_change_password(current_user: dict, current_password: str, new_password: str):
    """
    Handles password change for both student and admin users.
    """

    if current_user["role"] == "student":
        auth_manager = AuthManager()

        # Verify current password
        user = auth_manager.authenticate_user(
            current_user["email"],
            current_password
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect"
            )

        # Update password
        success = auth_manager.update_password(
            current_user["user_id"],
            new_password
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to update password"
            )

    elif current_user["role"] == "admin":
        admin_manager = AdminManager()

        # Verify admin exists
        admin = admin_manager.get_admin_by_id(current_user["user_id"])
        if not admin:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Admin not found"
            )

        # Verify current password
        auth_user = admin_manager.authenticate_admin(
            current_user["email"],
            current_password
        )

        if not auth_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect"
            )

        # Update password
        success = admin_manager.update_admin_password(
            current_user["user_id"],
            new_password
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to update password"
            )

    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid user role"
        )

    return {"message": "Password updated successfully"}
# =======================================================================================
def handle_create_student_with_auth(payload):
    """
    Handles student creation with authentication.
    Admin only.
    """
    auth_manager = AuthManager()

    try:
        student_id, password = auth_manager.create_student_with_auth(
            name=payload.name,
            email=payload.email,
            class_name=payload.class_name,
            password=payload.password,
            subject_agent=payload.subject_agent
        )

        return {
            "message": "Student created successfully",
            "student_id": student_id,
            "temporary_password": password if payload.password is None else None,
            "student": {
                "student_id": student_id,
                "name": payload.name,
                "email": payload.email,
                "class": payload.class_name
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

def handle_create_admin(payload):
    """
    Handles admin creation.
    Admin only.
    """
    admin_manager = AdminManager()

    try:
        admin_id, password = admin_manager.create_admin(
            name=payload.name,
            email=payload.email,
            password=payload.password,
            permissions=payload.permissions
        )

        return {
            "message": "Admin created successfully",
            "admin_id": admin_id,
            "temporary_password": password,
            "admin": {
                "admin_id": admin_id,
                "name": payload.name,
                "email": payload.email,
                "permissions": payload.permissions
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
# =======================================================================================
def handle_admin_reset_student_password(
    student_id: str,
    payload,
    current_user: dict,
):
    """
    Allows admin to reset a student's password
    after verifying the current password.
    """

    # Role check
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    student_manager = StudentManager()

    student = student_manager.get_student(student_id)

    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )

    # Verify current password with bcrypt
    if not verify_password(payload.current_password, student["auth"]["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    # Validate new password
    is_valid, error = validate_password_strength(payload.new_password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error
        )

    # Hash new password with bcrypt
    password_hash = get_password_hash(payload.new_password)

    # Update password
    student_manager.admin_update_std_password(
        student_id,
        password_hash
    )

    return {"message": "Student password reset successfully"}
