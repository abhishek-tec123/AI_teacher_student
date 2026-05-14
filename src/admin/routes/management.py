"""
Admin management routes
Handles user management, dashboard stats, and admin operations
"""

from fastapi import APIRouter, Depends
from common.auth.dependencies import require_role
from admin.repositories.admin_repository import AdminManager
from student.repositories.student_repository import StudentManager
from teacher.repositories.collections import list_all_collections

# Configure logging

router = APIRouter()

@router.get("/list-admins")
def list_admins(current_user: dict = Depends(require_role("admin"))):
    """List all admins (admin only)."""
    admin_manager = AdminManager()
    admins = admin_manager.list_admins()
    return {
        "total": len(admins),
        "admins": admins
    }

@router.get("/dashboard-counts")
def get_dashboard_stats(current_user: dict = Depends(require_role("admin"))):
    """Get dashboard statistics: all students, total agents, and total conversations."""
    # Get all students
    student_manager = StudentManager()
    students = student_manager.list_students()
    
    # Get all agents with their conversation counts
    agents_data = list_all_collections()
    total_agents = 0
    total_conversations = 0
    
    if agents_data["status"] == "success":
        agents = agents_data.get("agents", [])
        total_agents = len(agents)
        total_conversations = sum(agent.get("total_conversations", 0) for agent in agents)
    
    return {
        "students": {
            "total": len(students)
        },
        "agents": {
            "total": total_agents,
            "total_conversations": total_conversations
        }
    }


@router.get("/global-rag-knowledge")
def legacy_global_rag_knowledge(current_user: dict = Depends(require_role("admin"))):
    """
    Backwards-compatible alias for /api/v1/admin/system/global-rag-knowledge.
    Keeps existing frontend route /api/v1/admin/global-rag-knowledge working.
    """
    from admin.services.global_settings_service import get_global_rag_settings
    from admin.repositories.shared_knowledge_repository import shared_knowledge_manager

    global_settings = get_global_rag_settings()
    shared_documents_result = shared_knowledge_manager.list_shared_documents()

    return {
        "status": "success",
        "global_settings": {
            "enabled": global_settings["enabled"],
            "content_length": len(global_settings["content"]) if global_settings["enabled"] else 0,
            "content_preview": global_settings["content"][:200] + "..." if global_settings["enabled"] and len(global_settings["content"]) > 200 else global_settings["content"] if global_settings["enabled"] else "",
            "last_updated": "N/A",
        },
        "shared_documents": {
            "total_documents": shared_documents_result.get("total_documents", 0),
            "total_chunks": sum(doc.get("indexed_chunks", 0) for doc in shared_documents_result.get("documents", [])),
            "total_agents_using": sum(doc.get("used_by_count", 0) for doc in shared_documents_result.get("documents", [])),
            "documents": shared_documents_result.get("documents", []),
        },
        "summary": {
            "total_knowledge_sources": (1 if global_settings["enabled"] else 0) + shared_documents_result.get("total_documents", 0),
            "active_sources": (1 if global_settings["enabled"] else 0) + len(
                [doc for doc in shared_documents_result.get("documents", []) if doc.get("status") == "indexed"]
            ),
            "total_content_size": len(global_settings["content"]) if global_settings["enabled"] else 0,
        },
    }


@router.get("/global-prompts")
def legacy_list_global_prompts(current_user: dict = Depends(require_role("admin"))):
    """
    Backwards-compatible alias for /api/v1/admin/prompts/global-prompts/.
    Keeps existing frontend route /api/v1/admin/global-prompts working.
    """
    from admin.services.global_prompts_service import get_all_prompts, get_enabled_prompts

    prompts = get_all_prompts()
    enabled_prompts = get_enabled_prompts()

    return {
        "status": "success",
        "total_prompts": len(prompts),
        "enabled_prompts": len(enabled_prompts),
        "prompts": prompts,
    }
