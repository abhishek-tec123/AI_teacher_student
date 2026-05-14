"""
Student document preview routes
Handles document listing, preview, and metadata for agent knowledge base
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from typing import List, Optional
import os
import mimetypes

from common.auth.dependencies import get_current_user
from teacher.services.file_storage import document_storage
from pydantic import BaseModel
from .utils import get_student_agent_ids, validate_student_agent_access, get_agent_documents_from_db
import logging
logger = logging.getLogger(__name__)
router = APIRouter()

# Pydantic models
class DocumentInfo(BaseModel):
    document_id: str
    file_name: str
    file_type: str
    file_size: Optional[int] = None
    upload_date: Optional[str] = None
    preview_available: bool
    chunk_count: Optional[int] = None

class DocumentListResponse(BaseModel):
    documents: List[DocumentInfo]
    total: int
    page: int
    limit: int
    total_pages: int
    agent_id: str

class AgentDocumentRequest(BaseModel):
    agent_id: str

class AgentDocumentIdsResponse(BaseModel):
    agent_id: str
    doc_unique_ids: List[str]
    total_count: int

@router.get("/{student_id}/agents/{agent_id}/documents", response_model=DocumentListResponse)
def get_student_agent_documents(
    student_id: str,
    agent_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Number of documents per page"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get list of documents available for a student's agent
    Students can only access documents from agents they have access to
    """
    # Security: Students can only access their own documents
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Access denied: You can only access your own documents")
    
    # Validate student has access to this agent
    if not validate_student_agent_access(student_id, agent_id):
        raise HTTPException(status_code=403, detail="Access denied: You don't have access to this agent")
    
    try:
        # Get documents from database
        all_documents = get_agent_documents_from_db(agent_id)
        
        # Apply pagination
        total = len(all_documents)
        total_pages = (total + limit - 1) // limit
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_documents = all_documents[start_idx:end_idx]
        
        # Convert to response model
        document_list = []
        for doc in paginated_documents:
            document_list.append(DocumentInfo(
                document_id=doc.get("document_id", ""),
                file_name=doc.get("file_name", ""),
                file_type=doc.get("file_type", ""),
                file_size=doc.get("file_size"),
                upload_date=doc.get("upload_date"),
                preview_available=doc.get("preview_available", False),
                chunk_count=doc.get("chunk_count", 0)
            ))
        
        return DocumentListResponse(
            documents=document_list,
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages,
            agent_id=agent_id
        )
        
    except Exception as e:
        logger.info(f"Error getting documents: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve documents")

@router.get("/{student_id}/agents/{agent_id}/documents/{document_id}")
def get_document_metadata(
    student_id: str,
    agent_id: str,
    document_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get detailed metadata for a specific document
    """
    # Security: Students can only access their own documents
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Access denied: You can only access your own documents")
    
    # Validate student has access to this agent
    if not validate_student_agent_access(student_id, agent_id):
        raise HTTPException(status_code=403, detail="Access denied: You don't have access to this agent")
    
    try:
        # Get all documents for the agent
        all_documents = get_agent_documents_from_db(agent_id)
        
        # Find the specific document
        target_doc = None
        for doc in all_documents:
            if doc.get("document_id") == document_id:
                target_doc = doc
                break
        
        if not target_doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Get additional details from storage if available
        storage_info = None
        if target_doc.get("preview_available") and target_doc.get("storage_path"):
            try:
                file_path = target_doc["storage_path"]
                if os.path.exists(file_path):
                    file_stat = os.stat(file_path)
                    storage_info = {
                        "file_exists": True,
                        "file_size": file_stat.st_size,
                        "last_modified": file_stat.st_mtime,
                        "mime_type": mimetypes.guess_type(file_path)[0] or "application/octet-stream"
                    }
                else:
                    storage_info = {"file_exists": False}
            except Exception as e:
                storage_info = {"file_exists": False, "error": str(e)}
        
        return {
            "document": target_doc,
            "storage_info": storage_info,
            "agent_id": agent_id,
            "student_id": student_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.info(f"Error getting document metadata: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve document metadata")

@router.get("/{student_id}/agents/{agent_id}/documents/{document_id}/preview")
def preview_document(
    student_id: str,
    agent_id: str,
    document_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Preview/download the original document file
    """
    # Security: Students can only access their own documents
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Access denied: You can only access your own documents")
    
    # Validate student has access to this agent
    if not validate_student_agent_access(student_id, agent_id):
        raise HTTPException(status_code=403, detail="Access denied: You don't have access to this agent")
    
    try:
        # Get document metadata to find storage path
        all_documents = get_agent_documents_from_db(agent_id)
        
        target_doc = None
        for doc in all_documents:
            if doc.get("document_id") == document_id:
                target_doc = doc
                break
        
        if not target_doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        if not target_doc.get("preview_available", False):
            raise HTTPException(status_code=400, detail="Document preview not available")
        
        storage_path = target_doc.get("storage_path")
        if not storage_path or not os.path.exists(storage_path):
            raise HTTPException(status_code=404, detail="Document file not found")
        
        # Determine MIME type
        mime_type = mimetypes.guess_type(storage_path)[0]
        if not mime_type:
            # Default based on file extension
            ext = os.path.splitext(storage_path)[1].lower()
            mime_map = {
                '.pdf': 'application/pdf',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                '.doc': 'application/msword',
                '.txt': 'text/plain',
                '.html': 'text/html',
                '.htm': 'text/html',
                '.csv': 'text/csv',
                '.json': 'application/json'
            }
            mime_type = mime_map.get(ext, 'application/octet-stream')
        
        # Return file for preview/download
        return FileResponse(
            path=storage_path,
            filename=target_doc.get("file_name", f"document_{document_id}"),
            media_type=mime_type
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.info(f"Error previewing document: {e}")
        raise HTTPException(status_code=500, detail="Failed to preview document")

@router.get("/{student_id}/shared-documents/{document_id}")
def get_shared_document_metadata(
    student_id: str,
    document_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get metadata for a shared document (if accessible by student's agents)
    """
    # Security: Students can only access their own data
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Access denied: You can only access your own data")
    
    try:
        from admin.repositories.shared_knowledge_repository import shared_knowledge_manager
        
        # Get the shared document metadata
        metadata = shared_knowledge_manager.get_shared_document_metadata(document_id)
        if not metadata:
            raise HTTPException(status_code=404, detail="Shared document not found")
        
        # Check if student has access to any agent that uses this shared document
        student_agents = get_student_agent_ids(student_id)
        has_access = any(
            agent_id in metadata.get("used_by_agents", []) 
            for agent_id in student_agents
        )
        
        if not has_access and current_user["role"] == "student":
            raise HTTPException(status_code=403, detail="Access denied: This shared document is not available to your agents")
        
        return {
            "status": "success",
            "document": metadata,
            "student_id": student_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.info(f"Error getting shared document metadata: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve shared document metadata")

@router.get("/{student_id}/shared-documents/{document_id}/preview")
def preview_shared_document(
    student_id: str,
    document_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Preview/download a shared document file (if accessible by student's agents)
    """
    # Security: Students can only access their own data
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Access denied: You can only access your own data")
    
    try:
        from admin.repositories.shared_knowledge_repository import shared_knowledge_manager
        
        # Get the shared document metadata to check access
        metadata = shared_knowledge_manager.get_shared_document_metadata(document_id)
        if not metadata:
            raise HTTPException(status_code=404, detail="Shared document not found")
        
        # Check if student has access to any agent that uses this shared document
        student_agents = get_student_agent_ids(student_id)
        has_access = any(
            agent_id in metadata.get("used_by_agents", []) 
            for agent_id in student_agents
        )
        
        if not has_access and current_user["role"] == "student":
            raise HTTPException(status_code=403, detail="Access denied: This shared document is not available to your agents")
        
        # Get file path for the shared document
        storage_path = shared_knowledge_manager.get_shared_document_file_path(document_id)
        if not storage_path:
            raise HTTPException(status_code=404, detail="Document file not found or not available for preview")
        
        if not os.path.exists(storage_path):
            raise HTTPException(status_code=404, detail="Document file not found on disk")
        
        # Determine MIME type
        mime_type = mimetypes.guess_type(storage_path)[0]
        if not mime_type:
            # Default based on file extension
            ext = os.path.splitext(storage_path)[1].lower()
            mime_map = {
                '.pdf': 'application/pdf',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                '.doc': 'application/msword',
                '.txt': 'text/plain',
                '.html': 'text/html',
                '.htm': 'text/html',
                '.csv': 'text/csv',
                '.json': 'application/json'
            }
            mime_type = mime_map.get(ext, 'application/octet-stream')
        
        # Return file for preview/download
        filename = metadata.get("document_name", f"shared_document_{document_id}")
        return FileResponse(
            path=storage_path,
            filename=filename,
            media_type=mime_type
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.info(f"Error previewing shared document: {e}")
        raise HTTPException(status_code=500, detail="Failed to preview shared document")

@router.post("/documents/agent-documents", response_model=AgentDocumentIdsResponse)
def get_agent_document_ids(
    request: AgentDocumentRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Get all doc_unique_id values for a specific agent
    Accepts agent_id in request body and returns list of document IDs
    """
    agent_id = request.agent_id
    
    # Basic validation
    if not agent_id or not agent_id.strip():
        raise HTTPException(status_code=400, detail="agent_id is required")
    
    try:
        # Get all documents for the agent using existing function
        all_documents = get_agent_documents_from_db(agent_id)
        
        # Extract only the doc_unique_id values
        doc_unique_ids = []
        for doc in all_documents:
            document_id = doc.get("document_id")
            if document_id:
                doc_unique_ids.append(document_id)
        
        return AgentDocumentIdsResponse(
            agent_id=agent_id,
            doc_unique_ids=doc_unique_ids,
            total_count=len(doc_unique_ids)
        )
        
    except Exception as e:
        logger.info(f"Error getting agent document IDs: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve document IDs")

@router.get("/{student_id}/documents/storage-info")
def get_storage_info(
    student_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get storage information (for admin/debugging purposes)
    """
    # Security: Students can only access their own info
    if current_user["role"] == "student" and current_user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Only allow admins or the student themselves
    if current_user["role"] not in ["admin", "teacher"] and current_user["user_id"] != student_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        storage_info = document_storage.get_storage_info()
        
        # Add student-specific info
        student_agents = get_student_agent_ids(student_id)
        student_documents = []
        
        for agent_id in student_agents:
            agent_docs = get_agent_documents_from_db(agent_id)
            for doc in agent_docs:
                if doc.get("preview_available"):
                    student_documents.append({
                        "agent_id": agent_id,
                        "document_id": doc.get("document_id"),
                        "file_name": doc.get("file_name"),
                        "file_size": doc.get("file_size")
                    })
        
        return {
            "global_storage": storage_info,
            "student_documents": student_documents,
            "accessible_agents": student_agents
        }
        
    except Exception as e:
        logger.info(f"Error getting storage info: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve storage info")
