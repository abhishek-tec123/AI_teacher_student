"""
Admin system configuration routes
Handles shared knowledge documents, agent settings, and system configuration
"""

from fastapi import APIRouter, Depends, UploadFile, File, Form, Request, HTTPException
import os
import mimetypes
from common.auth.dependencies import require_role
from pydantic import BaseModel
from admin.repositories.shared_knowledge_repository import shared_knowledge_manager
from config.settings import settings
import logging
logger = logging.getLogger(__name__)

# Configure logging

router = APIRouter()

# =====================================================
# SHARED KNOWLEDGE DOCUMENTS MANAGEMENT
# =====================================================

class SharedDocumentRequest(BaseModel):
    document_name: str
    description: str = ""

class AgentDocumentRequest(BaseModel):
    agent_id: str
    agent_name: str = ""
    class_name: str = ""
    subject: str = ""

class AgentGlobalSettingsRequest(BaseModel):
    agent_id: str
    global_prompt_enabled: bool = False
    global_rag_enabled: bool = False

@router.post("/shared-knowledge/upload")
async def upload_shared_document(
    request: Request,
    document_name: str = Form(...),
    description: str = Form(""),
    files: list[UploadFile] = File(...),
    current_user: dict = Depends(require_role("admin"))
):
    """Upload shared knowledge documents accessible by all agents."""
    try:
        result = shared_knowledge_manager.upload_shared_document(
            files=files,
            document_name=document_name,
            description=description,
            embedding_model=request.app.state.embedding_model
        )
        return result
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/shared-knowledge")
def list_shared_documents(current_user: dict = Depends(require_role("admin"))):
    """List all shared knowledge documents with their status and usage."""
    return shared_knowledge_manager.list_shared_documents()

@router.delete("/shared-knowledge/{document_id}")
def delete_shared_document(
    document_id: str,
    current_user: dict = Depends(require_role("admin"))
):
    """Delete a shared knowledge document."""
    try:
        return shared_knowledge_manager.delete_shared_document(document_id)
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=e.status_code if hasattr(e, 'status_code') else 500, detail=str(e))

@router.post("/shared-knowledge/{document_id}/enable")
def enable_document_for_agent(
    document_id: str,
    payload: AgentDocumentRequest,
    current_user: dict = Depends(require_role("admin"))
):
    """Enable a shared document for a specific agent."""
    try:
        return shared_knowledge_manager.enable_document_for_agent(
            document_id=document_id,
            agent_id=payload.agent_id,
            agent_name=payload.agent_name,
            class_name=payload.class_name,
            subject=payload.subject
        )
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=e.status_code if hasattr(e, 'status_code') else 500, detail=str(e))

@router.post("/shared-knowledge/{document_id}/disable")
def disable_document_for_agent(
    document_id: str,
    payload: AgentDocumentRequest,
    current_user: dict = Depends(require_role("admin"))
):
    """Disable a shared document for a specific agent."""
    try:
        return shared_knowledge_manager.disable_document_for_agent(
            document_id=document_id,
            agent_id=payload.agent_id
        )
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=e.status_code if hasattr(e, 'status_code') else 500, detail=str(e))

@router.get("/shared-knowledge/agent/{agent_id}")
def get_agent_enabled_documents(
    agent_id: str,
    current_user: dict = Depends(require_role("admin"))
):
    """Get all shared documents enabled for a specific agent."""
    return {
        "status": "success",
        "documents": shared_knowledge_manager.get_agent_enabled_documents(agent_id)
    }

@router.get("/shared-knowledge/{document_id}")
def get_shared_document_metadata(
    document_id: str,
    current_user: dict = Depends(require_role("admin"))
):
    """Get detailed metadata for a specific shared document."""
    try:
        # Try to find document by document_id first, then by doc_unique_id
        metadata = shared_knowledge_manager.get_shared_document_metadata(document_id)
        
        # If not found by document_id, try by doc_unique_id
        if not metadata:
            from pymongo import MongoClient
            
            mongodb_uri = settings.mongodb_uri
            if not mongodb_uri:
                raise HTTPException(status_code=500, detail="MongoDB URI not configured")
            
            client = MongoClient(mongodb_uri)
            db = client[settings.db_name]
            collection = db["shared_knowledge"]
            
            # Find document by doc_unique_id
            doc = collection.find_one({"document.doc_unique_id": document_id})
            if doc:
                actual_document_id = doc.get("document_id")
                metadata = shared_knowledge_manager.get_shared_document_metadata(actual_document_id)
            
            client.close()
        
        if not metadata:
            raise HTTPException(status_code=404, detail="Shared document not found")
        
        return {
            "status": "success",
            "document": metadata
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get shared document metadata: {str(e)}")

@router.get("/shared-knowledge/{document_id}/preview")
def preview_shared_document(
    document_id: str,
    current_user: dict = Depends(require_role("admin"))
):
    """Preview/download a shared document file."""
    try:
        # Try to find document by document_id first, then by doc_unique_id
        storage_path = shared_knowledge_manager.get_shared_document_file_path(document_id)
        
        # If not found by document_id, try by doc_unique_id
        if not storage_path:
            # Look for document by doc_unique_id
            from pymongo import MongoClient
            
            mongodb_uri = settings.mongodb_uri
            if not mongodb_uri:
                raise HTTPException(status_code=500, detail="MongoDB URI not configured")
            
            client = MongoClient(mongodb_uri)
            db = client[settings.db_name]
            collection = db["shared_knowledge"]
            
            # Find document by doc_unique_id
            doc = collection.find_one({"document.doc_unique_id": document_id})
            if doc:
                actual_document_id = doc.get("document_id")
                storage_path = shared_knowledge_manager.get_shared_document_file_path(actual_document_id)
            
            client.close()
        
        if not storage_path:
            raise HTTPException(status_code=404, detail="Document file not found or not available for preview")
        
        if not os.path.exists(storage_path):
            raise HTTPException(status_code=404, detail="Document file not found on disk")
        
        # Get document metadata for filename - try both IDs
        metadata = shared_knowledge_manager.get_shared_document_metadata(document_id)
        if not metadata:
            # Try to find metadata by doc_unique_id
            from pymongo import MongoClient
            mongodb_uri = settings.mongodb_uri
            client = MongoClient(mongodb_uri)
            db = client[settings.db_name]
            collection = db["shared_knowledge"]
            
            doc = collection.find_one({"document.doc_unique_id": document_id})
            if doc:
                actual_document_id = doc.get("document_id")
                metadata = shared_knowledge_manager.get_shared_document_metadata(actual_document_id)
            
            client.close()
        
        filename = metadata.get("document_name", f"shared_document_{document_id}") if metadata else f"shared_document_{document_id}"
        
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
        from fastapi.responses import FileResponse
        return FileResponse(
            path=storage_path,
            filename=filename,
            media_type=mime_type
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to preview shared document: {str(e)}")

@router.get("/global-rag-knowledge")
def list_global_rag_knowledge(current_user: dict = Depends(require_role("admin"))):
    """List all global RAG knowledge including settings and shared documents."""
    try:
        from admin.services.global_settings_service import get_global_rag_settings
        
        # Get global RAG settings
        global_settings = get_global_rag_settings()
        
        # Get shared knowledge documents
        shared_documents_result = shared_knowledge_manager.list_shared_documents()
        
        # Prepare response
        response = {
            "status": "success",
            "global_settings": {
                "enabled": global_settings["enabled"],
                "content_length": len(global_settings["content"]) if global_settings["enabled"] else 0,
                "content_preview": global_settings["content"][:200] + "..." if global_settings["enabled"] and len(global_settings["content"]) > 200 else global_settings["content"] if global_settings["enabled"] else "",
                "last_updated": "N/A"  # Could add timestamp tracking if needed
            },
            "shared_documents": {
                "total_documents": shared_documents_result.get("total_documents", 0),
                "total_chunks": sum(doc.get("indexed_chunks", 0) for doc in shared_documents_result.get("documents", [])),
                "total_agents_using": sum(doc.get("used_by_count", 0) for doc in shared_documents_result.get("documents", [])),
                "documents": shared_documents_result.get("documents", [])
            },
            "summary": {
                "total_knowledge_sources": (1 if global_settings["enabled"] else 0) + shared_documents_result.get("total_documents", 0),
                "active_sources": (1 if global_settings["enabled"] else 0) + len([doc for doc in shared_documents_result.get("documents", []) if doc.get("status") == "indexed"]),
                "total_content_size": len(global_settings["content"]) if global_settings["enabled"] else 0
            }
        }
        
        return response
        
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Failed to list global RAG knowledge: {str(e)}")

# =====================================================
# AGENT GLOBAL SETTINGS MANAGEMENT
# =====================================================

@router.post("/agents/{agent_id}/global-settings")
def update_agent_global_settings(
    agent_id: str,
    payload: AgentGlobalSettingsRequest,
    current_user: dict = Depends(require_role("admin"))
):
    """Update global settings for a specific agent."""
    try:
        from teacher.repositories.get_agent_data import get_agent_data
        from pymongo import MongoClient
        
        # Get agent data to find the database and collection
        agent_data = get_agent_data(agent_id)
        if not agent_data:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        # Update agent metadata with global settings
        mongodb_uri = settings.mongodb_uri
        if not mongodb_uri:
            raise HTTPException(status_code=500, detail="MongoDB URI not configured")
        
        client = MongoClient(mongodb_uri)
        db = client[agent_data["class"]]
        collection = db[agent_data["subject"]]
        
        # Update all documents for this agent with new global settings
        result = collection.update_many(
            {"subject_agent_id": agent_id},
            {
                "$set": {
                    "agent_metadata.global_prompt_enabled": payload.global_prompt_enabled,
                    "agent_metadata.global_rag_enabled": payload.global_rag_enabled
                }
            }
        )
        
        # ✅ Auto-enable/disable shared documents based on new global_rag_enabled setting
        auto_result = {"auto_enabled_shared_documents": 0, "auto_disabled_shared_documents": 0}
        
        try:
            # Get all available shared documents
            shared_docs_result = shared_knowledge_manager.list_shared_documents()
            
            if shared_docs_result.get("status") == "success" and shared_docs_result.get("documents"):
                if payload.global_rag_enabled:
                    # Enable shared documents for this agent
                    enabled_count = 0
                    for doc in shared_docs_result["documents"]:
                        try:
                            # Get agent details from updated payload or agent data
                            agent_name = agent_data.get("agent_metadata", {}).get("agent_name", "")
                            class_name = agent_data.get("class", "")
                            subject_name = agent_data.get("subject", "")
                            
                            success = shared_knowledge_manager.enable_document_for_agent(
                                doc["document_id"], 
                                agent_id,
                                agent_name=agent_name,
                                class_name=class_name,
                                subject=subject_name
                            )
                            if success:
                                enabled_count += 1
                        except Exception as e:
                            logger.warning(f"Failed to enable document {doc['document_id']} for agent {agent_id}: {e}")
                    
                    if enabled_count > 0:
                        auto_result["auto_enabled_shared_documents"] = enabled_count
                        auto_result["shared_documents_status"] = "enabled"
                        
                else:
                    # Disable shared documents for this agent
                    disabled_count = 0
                    for doc in shared_docs_result["documents"]:
                        try:
                            # Check if this agent is using this document
                            if any(agent.get("agent_id") == agent_id for agent in doc.get("used_by_agents", [])):
                                success = shared_knowledge_manager.disable_document_for_agent(
                                    doc["document_id"], 
                                    agent_id
                                )
                                if success:
                                    disabled_count += 1
                        except Exception as e:
                            logger.warning(f"Failed to disable document {doc['document_id']} for agent {agent_id}: {e}")
                    
                    if disabled_count > 0:
                        auto_result["auto_disabled_shared_documents"] = disabled_count
                        auto_result["shared_documents_status"] = "disabled"
                        
        except Exception as e:
            logger.warning(f"Failed to auto-enable/disable shared documents for agent {agent_id}: {e}")
            auto_result["shared_documents_status"] = "error"
        
        return {
            "status": "success",
            "message": f"Updated global settings for agent {agent_id}",
            "matched_documents": result.matched_count,
            "modified_documents": result.modified_count,
            "global_prompt_enabled": payload.global_prompt_enabled,
            "global_rag_enabled": payload.global_rag_enabled,
            **auto_result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update agent global settings: {str(e)}")

@router.get("/agents/{agent_id}/global-settings")
def get_agent_global_settings(
    agent_id: str,
    current_user: dict = Depends(require_role("admin"))
):
    """Get current global settings for a specific agent."""
    try:
        from teacher.repositories.get_agent_data import get_agent_data
        
        # Get agent data
        agent_data = get_agent_data(agent_id)
        if not agent_data:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        # Extract global settings from agent metadata
        agent_metadata = agent_data.get("agent_metadata", {})
        
        return {
            "status": "success",
            "agent_id": agent_id,
            "global_prompt_enabled": agent_metadata.get("global_prompt_enabled", False),
            "global_rag_enabled": agent_metadata.get("global_rag_enabled", False),
            "agent_metadata": agent_metadata
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get agent global settings: {str(e)}")
