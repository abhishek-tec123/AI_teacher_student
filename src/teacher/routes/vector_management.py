"""
Vector management routes
Handles vector creation, agent management, and shared documents
"""

from fastapi import APIRouter, UploadFile, File, Form, Request, HTTPException, Depends
from typing import List, Optional
from fastapi.responses import JSONResponse
from common.auth.dependencies import get_current_user
from student.repositories.student_repository import StudentManager
from common.utils.dependencies import StudentManagerDep
from admin.repositories.shared_knowledge_repository import shared_knowledge_manager
from pydantic import BaseModel

router = APIRouter()

class ClassRequest(BaseModel):
    class_name: str

class AgentDocumentRequest(BaseModel):
    agent_id: str
    agent_name: str = ""
    class_name: str = ""
    subject: str = ""

# -------------------------------------------------
# Student Subject Management (Original Route)
# -------------------------------------------------
@router.get("/student/{student_id}/subjects")
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
        logger.info("General fetch error:", e)

    # ------------------------------------------------
    # Final Response
    # ------------------------------------------------
    return {
        "student_subjects": student_subjects,
        "general_subjects": general_subjects
    }

# -------------------------------------------------
# Vector Creation & Management
# -------------------------------------------------
@router.post("/create_vectors")
async def create_vectors(
    request: Request,
    subject: str = Form(...),
    class_: Optional[str] = Form(None),  # optional for subject-only mode

    # Optional agent metadata
    agent_type: Optional[str] = Form(None),
    agent_name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    teaching_tone: Optional[str] = Form(None),
    
    # Global settings
    global_prompt_enabled: bool = Form(False),
    global_rag_enabled: bool = Form(False),

    files: Optional[List[UploadFile]] = File(None)
):
    from teacher.services.vector_creator import create_vectors_service
    
    # Build agent metadata dict only if values exist
    agent_metadata = {k: v for k, v in {
        "agent_type": agent_type,
        "agent_name": agent_name,
        "description": description,
        "teaching_tone": teaching_tone,
    }.items() if v is not None} or None

    # Determine mode
    mode = "teacher_agent" if class_ else "subject_only"

    # Call service (class_ can be None for general DB)
    result = await create_vectors_service(
        subject=subject,
        class_=class_,
        files=files,
        embedding_model=request.app.state.embedding_model,
        agent_metadata=agent_metadata,
        global_prompt_enabled=global_prompt_enabled,
        global_rag_enabled=global_rag_enabled,
    )

    # Add mode info to response
    response = {
        "mode": mode,
        **result
    }

    return response

# -------------------------------------------------
# Agent Management
# -------------------------------------------------
from teacher.services.update_vectors import update_agent_data, delete_agent_data
from teacher.repositories.get_agent_data import get_agent_data
import logging
logger = logging.getLogger(__name__)

@router.get("/{subject_agent_id}")
async def get_agent(subject_agent_id: str):
    return get_agent_data(subject_agent_id)

@router.put("/{subject_agent_id}")
async def update_agent(
    request: Request,
    subject_agent_id: str,
    class_: str | None = Form(None),
    subject: str | None = Form(None),
    agent_type: str | None = Form(None),
    agent_name: str | None = Form(None),
    description: str | None = Form(None),
    teaching_tone: str | None = Form(None),
    global_prompt_enabled: bool = Form(False),
    global_rag_enabled: bool = Form(False),
    files: Optional[List[UploadFile]] = None,
):
    return await update_agent_data(
        subject_agent_id=subject_agent_id,
        class_=class_,
        subject=subject,
        agent_type=agent_type,
        agent_name=agent_name,
        description=description,
        teaching_tone=teaching_tone,
        global_prompt_enabled=global_prompt_enabled,
        global_rag_enabled=global_rag_enabled,
        files=files,
        embedding_model=request.app.state.embedding_model,
        create_vectors_service=request.app.state.create_vectors_service
    )

@router.delete("/{subject_agent_id}")
async def delete_agent(subject_agent_id: str):
    result = await delete_agent_data(subject_agent_id)

    if not result["deleted"]:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Build enhanced response with collection and storage deletion information
    response = {
        "message": f"Agent {subject_agent_id} deleted successfully.",
        "deleted_chunks": result["deleted_chunks"],
        "dropped_collections": result.get("dropped_collections", []),
        "collections_with_multiple_agents": result.get("collections_with_multiple_agents", []),
        "collections_dropped_count": len(result.get("dropped_collections", [])),
        "multi_agent_collections_cleaned": len(result.get("collections_with_multiple_agents", [])),
        "storage_deletion": result.get("storage_deletion", {}),
        "total_files_deleted": result.get("total_files_deleted", 0),
        "total_bytes_freed": result.get("total_bytes_freed", 0),
        "total_mb_freed": round(result.get("total_bytes_freed", 0) / (1024*1024), 2)
    }

    # Add specific messages for different scenarios
    if response["collections_dropped_count"] > 0:
        response["message"] += f" Dropped {response['collections_dropped_count']} collection(s)."
    
    if response["multi_agent_collections_cleaned"] > 0:
        response["message"] += f" Cleaned {response['multi_agent_collections_cleaned']} multi-agent collection(s)."
    
    if response["total_files_deleted"] > 0:
        response["message"] += f" Deleted {response['total_files_deleted']} storage files ({response['total_mb_freed']} MB freed)."

    return response

@router.post("/agent_of_class")
def agent(request: ClassRequest):
    from teacher.repositories.collections import get_all_agents_of_class
    
    data = get_all_agents_of_class(request.class_name)
    return JSONResponse(content=data)

# -------------------------------------------------
# Shared Documents Management
# -------------------------------------------------
@router.post("/{subject_agent_id}/shared-documents/enable")
async def enable_shared_document_for_agent(
    subject_agent_id: str,
    payload: AgentDocumentRequest,
    current_user: dict = Depends(get_current_user)
):
    """Enable a shared document for a specific agent."""
    try:
        # Get all shared documents to find one to enable
        shared_docs = shared_knowledge_manager.list_shared_documents()
        if shared_docs.get("status") != "success":
            raise HTTPException(status_code=500, detail="Failed to fetch shared documents")
        
        # For now, enable all shared documents (can be made selective later)
        enabled_count = 0
        for doc in shared_docs["documents"]:
            result = shared_knowledge_manager.enable_document_for_agent(
                document_id=doc["document_id"],
                agent_id=subject_agent_id,
                agent_name=payload.agent_name,
                class_name=payload.class_name,
                subject=payload.subject
            )
            if result.get("status") == "success":
                enabled_count += 1
        
        return {
            "status": "success",
            "message": f"Enabled {enabled_count} shared documents for agent",
            "subject_agent_id": subject_agent_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{subject_agent_id}/shared-documents/disable")
async def disable_shared_document_for_agent(
    subject_agent_id: str,
    document_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Disable a shared document for a specific agent."""
    try:
        result = shared_knowledge_manager.disable_document_for_agent(
            document_id=document_id,
            agent_id=subject_agent_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{subject_agent_id}/shared-documents")
async def get_agent_shared_documents(
    subject_agent_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get all shared documents enabled for a specific agent."""
    try:
        documents = shared_knowledge_manager.get_agent_enabled_documents(subject_agent_id)
        return {
            "status": "success",
            "documents": documents,
            "subject_agent_id": subject_agent_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
