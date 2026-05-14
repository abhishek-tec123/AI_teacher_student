"""
Admin prompt management routes
Handles base prompts, global prompts, and RAG settings
"""

from fastapi import APIRouter, Depends, HTTPException
import os
from student.agents.main_agent import (
    get_base_prompt,
    update_base_prompt_handler,
    UpdatePromptRequest,
)
from common.auth.dependencies import require_role
from pydantic import BaseModel
from typing import Optional
from admin.services.global_settings_service import (
    get_global_rag_settings,
    enable_global_rag as enable_global_rag_setting,
    disable_global_rag as disable_global_rag_setting
)
from common.utils.prompt_templates import (
    get_sample_student_profile,
    get_sample_session_context,
    get_fallback_base_prompt,
    create_fallback_prompt_with_rag,
    get_prompt_components_for_response,
    build_teacher_prompt
)
from admin.services.global_prompts_service import (
    create_global_prompt,
    get_all_prompts,
    get_prompt_by_id,
    update_prompt,
    delete_prompt,
    enable_prompt,
    disable_prompt,
    get_enabled_prompts,
    get_highest_priority_enabled_prompt
)

# Configure logging

router = APIRouter()

# Dummy data constants for prompt demonstration
DUMMY_CLASS_NAME = "Sample Class"
DUMMY_SUBJECT = "Sample Subject"
DUMMY_QUERY = "What is photosynthesis?"

class GlobalRagRequest(BaseModel):
    content: str

class GlobalPromptRequest(BaseModel):
    name: str
    content: str
    priority: int = 1
    version: str = "v1"

class GlobalPromptUpdateRequest(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    priority: Optional[int] = None
    version: Optional[str] = None

@router.post("/update-base-prompt")
def update_base_prompt(
    payload: UpdatePromptRequest,
    current_user: dict = Depends(require_role("admin"))
):
    return update_base_prompt_handler(payload)

@router.get("/current-base-prompt")
def get_current_prompt(current_user: dict = Depends(require_role("admin"))):
    return {
        "base_prompt": get_base_prompt()
    }

# Global prompt management routes
@router.post("/global-prompt/enable")
def enable_global_rag(
    payload: GlobalRagRequest,
    current_user: dict = Depends(require_role("admin"))
):
    """Enable global RAG with custom content and show complete prompt examples."""
    enable_global_rag_setting(payload.content)
    
    settings = get_global_rag_settings()
    
    # Import the build_teacher_prompt function to create realistic full prompts
    try:
        # Get sample data from templates
        sample_student_profile = get_sample_student_profile()
        sample_session_context = get_sample_session_context()
        
        # Build the complete base prompt (without RAG)
        base_prompt = build_teacher_prompt(
            student_profile=sample_student_profile,
            class_name=DUMMY_CLASS_NAME,
            subject=DUMMY_SUBJECT,
            confusion_type="NO_CONFUSION",
            session_context=sample_session_context,
            current_query=DUMMY_QUERY,
            agent_metadata=None
        )
        
        # Build the complete enhanced prompt (with RAG)
        enhanced_prompt = build_teacher_prompt(
            student_profile=sample_student_profile,
            class_name=DUMMY_CLASS_NAME,
            subject=DUMMY_SUBJECT,
            confusion_type="NO_CONFUSION",
            session_context=sample_session_context,
            current_query=DUMMY_QUERY,
            agent_metadata=None
        )
            
    except Exception:
        # Fallback to modular prompts if import fails
        base_prompt = get_fallback_base_prompt()
        enhanced_prompt = create_fallback_prompt_with_rag(settings["content"]) if settings["enabled"] else None
    
    return {
        "status": "success",
        "message": "Global RAG enabled successfully",
        "enabled": True,
        "content_preview": settings["content"][:200] + "..." if len(settings["content"]) > 200 else settings["content"],
        "rag_content_length": len(settings["content"]),
        "prompts": {
            "base_prompt": base_prompt,
            "rag_enhanced_prompt": enhanced_prompt
        },
        "prompt_components": get_prompt_components_for_response()
    }

@router.post("/global-prompt/disable")
def disable_global_rag(current_user: dict = Depends(require_role("admin"))):
    """Disable global RAG and show complete prompt examples."""
    disable_global_rag_setting()
    
    # Import the build_teacher_prompt function to create realistic full prompts
    try:
        # Get sample data from templates
        sample_student_profile = get_sample_student_profile()
        sample_session_context = get_sample_session_context()
        
        # Build the complete base prompt (without RAG)
        base_prompt = build_teacher_prompt(
            student_profile=sample_student_profile,
            class_name=DUMMY_CLASS_NAME,
            subject=DUMMY_SUBJECT,
            confusion_type="NO_CONFUSION",
            session_context=sample_session_context,
            current_query=DUMMY_QUERY,
            agent_metadata=None
        )
            
    except Exception:
        # Fallback to modular prompts if import fails
        base_prompt = get_fallback_base_prompt()
    
    return {
        "status": "success",
        "message": "Global RAG disabled successfully",
        "enabled": False,
        "rag_content_length": 0,
        "prompts": {
            "base_prompt": base_prompt,
            "rag_enhanced_prompt": None
        },
        "prompt_components": get_prompt_components_for_response()
    }

@router.get("/global-prompt/status")
def get_global_rag_status(current_user: dict = Depends(require_role("admin"))):
    """Get current global RAG status and content with full prompt examples."""
    settings = get_global_rag_settings()
    
    # Import the build_teacher_prompt function to create realistic full prompts
    try:
        # Get sample data from templates
        sample_student_profile = get_sample_student_profile()
        sample_session_context = get_sample_session_context()
        
        # Build the complete base prompt (without RAG)
        base_prompt = build_teacher_prompt(
            student_profile=sample_student_profile,
            class_name=DUMMY_CLASS_NAME,
            subject=DUMMY_SUBJECT,
            confusion_type="NO_CONFUSION",
            session_context=sample_session_context,
            current_query=DUMMY_QUERY,
            agent_metadata=None
        )
        
        # Build the complete enhanced prompt (with RAG if enabled)
        if settings["enabled"]:
            enhanced_prompt = build_teacher_prompt(
                student_profile=sample_student_profile,
                class_name=DUMMY_CLASS_NAME,
                subject=DUMMY_SUBJECT,
                confusion_type="NO_CONFUSION",
                session_context=sample_session_context,
                current_query=DUMMY_QUERY,
                agent_metadata=None
            )
        else:
            enhanced_prompt = None
            
    except ImportError:
        # Fallback to modular prompts if import fails
        base_prompt = get_fallback_base_prompt()
        enhanced_prompt = create_fallback_prompt_with_rag(settings["content"]) if settings["enabled"] else None
    
    return {
        "enabled": settings["enabled"],
        "content": settings["content"] if settings["enabled"] else "",
        "content_length": len(settings["content"]) if settings["enabled"] else 0,
        "rag_content_length": len(settings["content"]) if settings["enabled"] else 0,
        "prompts": {
            "base_prompt": base_prompt,
            "rag_enhanced_prompt": enhanced_prompt
        },
        "prompt_components": get_prompt_components_for_response()
    }

# =====================================================
# GLOBAL PROMPTS MANAGEMENT
# =====================================================

@router.post("/global-prompts/")
def create_global_prompt_endpoint(
    payload: GlobalPromptRequest,
    current_user: dict = Depends(require_role("admin"))
):
    """Create a new global prompt."""
    try:
        prompt = create_global_prompt(
            name=payload.name,
            content=payload.content,
            priority=payload.priority,
            version=payload.version
        )
        return {
            "status": "success",
            "message": f"Global prompt '{payload.name}' created successfully",
            "prompt": prompt
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create global prompt: {str(e)}")

@router.get("/global-prompts/")
def list_global_prompts(current_user: dict = Depends(require_role("admin"))):
    """List all global prompts."""
    try:
        prompts = get_all_prompts()
        enabled_prompts = get_enabled_prompts()
        
        return {
            "status": "success",
            "total_prompts": len(prompts),
            "enabled_prompts": len(enabled_prompts),
            "prompts": prompts
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list global prompts: {str(e)}")

@router.get("/global-prompts/{prompt_id}")
def get_global_prompt(
    prompt_id: str,
    current_user: dict = Depends(require_role("admin"))
):
    """Get a specific global prompt."""
    try:
        prompt = get_prompt_by_id(prompt_id)
        if not prompt:
            raise HTTPException(status_code=404, detail="Global prompt not found")
        
        return {
            "status": "success",
            "prompt": prompt
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get global prompt: {str(e)}")

@router.put("/global-prompts/{prompt_id}")
def update_global_prompt_endpoint(
    prompt_id: str,
    payload: GlobalPromptUpdateRequest,
    current_user: dict = Depends(require_role("admin"))
):
    """Update a global prompt."""
    try:
        # Filter out None values
        update_data = {k: v for k, v in payload.dict().items() if v is not None}
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No valid fields to update")
        
        prompt = update_prompt(prompt_id, **update_data)
        if not prompt:
            raise HTTPException(status_code=404, detail="Global prompt not found")
        
        return {
            "status": "success",
            "message": f"Global prompt '{prompt.get('name')}' updated successfully",
            "prompt": prompt
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update global prompt: {str(e)}")

@router.delete("/global-prompts/{prompt_id}")
def delete_global_prompt_endpoint(
    prompt_id: str,
    current_user: dict = Depends(require_role("admin"))
):
    """Delete a global prompt."""
    try:
        prompt = get_prompt_by_id(prompt_id)
        if not prompt:
            raise HTTPException(status_code=404, detail="Global prompt not found")
        
        success = delete_prompt(prompt_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete global prompt")
        
        return {
            "status": "success",
            "message": f"Global prompt '{prompt.get('name')}' deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete global prompt: {str(e)}")

@router.post("/global-prompts/{prompt_id}/enable")
def enable_global_prompt_endpoint(
    prompt_id: str,
    current_user: dict = Depends(require_role("admin"))
):
    """Enable a global prompt."""
    try:
        prompt = enable_prompt(prompt_id)
        if not prompt:
            raise HTTPException(status_code=404, detail="Global prompt not found")
        
        return {
            "status": "success",
            "message": f"Global prompt '{prompt.get('name')}' enabled successfully",
            "prompt": prompt
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to enable global prompt: {str(e)}")

@router.post("/global-prompts/{prompt_id}/disable")
def disable_global_prompt_endpoint(
    prompt_id: str,
    current_user: dict = Depends(require_role("admin"))
):
    """Disable a global prompt."""
    try:
        prompt = disable_prompt(prompt_id)
        if not prompt:
            raise HTTPException(status_code=404, detail="Global prompt not found")
        
        return {
            "status": "success",
            "message": f"Global prompt '{prompt.get('name')}' disabled successfully",
            "prompt": prompt
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to disable global prompt: {str(e)}")

@router.get("/global-prompts/enabled/highest-priority")
def get_highest_priority_enabled_prompt_endpoint(current_user: dict = Depends(require_role("admin"))):
    """Get the highest priority enabled global prompt."""
    try:
        prompt = get_highest_priority_enabled_prompt()
        
        return {
            "status": "success",
            "prompt": prompt
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get highest priority enabled prompt: {str(e)}")
