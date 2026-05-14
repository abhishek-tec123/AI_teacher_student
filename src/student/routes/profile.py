"""
Student profile management routes
Handles student CRUD operations, authentication, and profile management
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from student.repositories.student_repository import StudentManager
from common.utils.dependencies import StudentManagerDep
from common.auth.dependencies import get_current_user, require_role
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict
from bson import ObjectId
import logging
logger = logging.getLogger(__name__)

router = APIRouter()

# -------------------------------------------------
# Student Subject Management
# -------------------------------------------------
@router.get("/{student_id}/subjects")
def get_student_subjects(
    student_id: str,
    student_manager: StudentManager = StudentManagerDep,
    current_user: dict = Depends(get_current_user)
):
    """
    Returns:
    1. Student assigned subjects
    2. All subjects from general collection
    """

    # Permission check
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Access denied")

    student = student_manager.get_student(student_id)

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # ------------------------------------------------
    # 1️⃣ Student Assigned Subjects (existing logic)
    # ------------------------------------------------
    # Try root level first (current schema), fallback to student_details for legacy
    subject_agent = student.get("subject_agent", [])
    if not subject_agent:
        subject_agent = student.get("student_details", {}).get("subject_agent", [])
    student_subjects = []

    if isinstance(subject_agent, list):
        for item in subject_agent:
            subject_name = ""

            if isinstance(item, dict):
                subject_name = item.get("subject", "") or item.get("name", "")
            elif isinstance(item, str):
                subject_name = item

            if subject_name:
                description = ""
                subject_agent_id = ""

                try:
                    from teacher.repositories.collections import get_all_agents_of_class

                    student_class = student.get("student_details", {}).get("class", "")
                    if student_class:
                        agents_response = get_all_agents_of_class(student_class)

                        if agents_response.get("status") == "success":
                            agents = agents_response.get("agents", [])
                            for agent in agents:
                                if agent.get("subject") == subject_name:
                                    description = agent.get("description", "")
                                    subject_agent_id = agent.get("subject_agent_id", "")
                                    break
                except Exception:
                    pass

                student_subjects.append({
                    "name": subject_name,
                    "description": description,
                    "subject_agent_id": subject_agent_id
                })

    # ------------------------------------------------
    # 2️⃣ All Subjects from "general" collection
    # ------------------------------------------------
    general_subjects = []

    try:
        from teacher.repositories.collections import get_general_collection

        general_response = get_general_collection()

        if general_response.get("status") == "success":
            for item in general_response.get("data", []):
                general_subjects.append({
                    "name": item.get("name", ""),
                    "description": item.get("description", ""),
                    "subject_agent_id": item.get("subject_agent_id", "")
                })

    except Exception as e:
        logger.warning(f"General subjects fetch error: {e}")

    # ------------------------------------------------
    # Final Response
    # ------------------------------------------------
    return {
        "student_subjects": student_subjects,
        "general_subjects": general_subjects
    }

class CreateStudentRequest(BaseModel):
    name: str
    email: EmailStr
    class_name: str
    subject_agent: Optional[List[Dict[str, str]]] = None

class UpdateStudent(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    class_name: Optional[str] = None
    subject_agent: Optional[List[Dict[str, str]]] = None

@router.post("/create-student")
def create_student(
    payload: CreateStudentRequest,
    student_manager: StudentManager = StudentManagerDep,
    current_user: dict = Depends(require_role("admin"))
):
    student_id = student_manager.create_student(
        name=payload.name,
        email=payload.email,
        class_name=payload.class_name,
        subject_agent=payload.subject_agent
    )

    return {
        "message": "Student created successfully",
        "student": {
            "student_id": student_id,
            "name": payload.name,
            "email": payload.email,
            "class": payload.class_name,
            "subject_agent": payload.subject_agent or {}
        }
    }

@router.get("/student-list")
def get_students(
    student_manager: StudentManager = StudentManagerDep,
    current_user: dict = Depends(get_current_user)
):
    # Students can only see themselves, admins can see all
    if current_user["role"] == "student":
        students = [student_manager.get_student(current_user["user_id"])]
        if students[0]:
            students = [{
                "student_id": students[0]["student_id"],
                "name": students[0]["student_details"]["name"],
                "email": students[0]["student_details"]["email"],
                "class": students[0]["student_details"]["class"],
                "subject_agent": students[0]["student_details"]["subject_agent"]
            }]
        else:
            students = []
    else:
        students = student_manager.list_students()

    return {
        "total": len(students),
        "students": students
    }

@router.get("/{student_id}")
def get_student(
    student_id: str,
    student_manager: StudentManager = StudentManagerDep,
    current_user: dict = Depends(get_current_user)
):
    # Students can only access their own data
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Access denied: You can only access your own data")
    
    student = student_manager.get_student(student_id)

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    return {
        "student_id": student["student_id"],
        "name": student["student_details"]["name"],
        "email": student["student_details"]["email"],
        "class_name": student["student_details"]["class"],
        "subject_agent": student["student_details"]["subject_agent"],
        "created_at": student["metadata"]["created_at"],
    }

@router.put("/{student_id}")
def update_student(
    student_id: str,
    payload: UpdateStudent,
    student_manager: StudentManager = StudentManagerDep,
    current_user: dict = Depends(get_current_user)
):
    # Students can only update their own data
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Access denied: You can only update your own data")
    
    result = student_manager.update_student(student_id, payload)

    if not result or result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Student not found")

    return {"message": "Student updated successfully"}

@router.delete("/{student_id}")
def delete_student(
    student_id: str,
    current_user: dict = Depends(require_role("admin"))
):
    manager = StudentManager()  # ✅ create instance
    result = manager.delete_student(student_id)  # now self is provided

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Student not found")

    return {"message": "Student deleted successfully"}
