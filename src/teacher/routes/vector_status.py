"""
Vector status routes
Handles database status, environment info, and collection metadata
"""

from fastapi import APIRouter, Request
import os
from config.settings import settings

router = APIRouter()

# -------------------------------------------------
# Health / Env / DB Meta
# -------------------------------------------------
@router.get("/status")
def health():
    return {"status": "ok"}

@router.get("/env_info")
def env_info(request: Request):
    return {
        "mongodb_uri_set": bool(settings.mongodb_uri),
        "groq_api_key_set": bool(settings.groq_api_key),
        "embedding_model_loaded": hasattr(
            request.app.state, "embedding_model"
        ),
    }

@router.get("/db_status/{class_}/{subject}")
def db_status(class_: str, subject: str):
    from teacher.repositories.dbstatus import check_db_status
    
    return check_db_status(class_, subject)

# -------------------------------------------------
# Classes / Subjects / Collections
# -------------------------------------------------
@router.get("/classes")
def classes():
    from teacher.repositories.classes_and_subject import list_all_classes
    
    return list_all_classes()

@router.get("/subjects")
def subjects(selected_class: str):
    from teacher.repositories.classes_and_subject import get_subjects_by_class
    
    return get_subjects_by_class(selected_class)

@router.get("/all_collections")
def collections():
    from teacher.repositories.collections import list_all_collections
    
    return list_all_collections()
