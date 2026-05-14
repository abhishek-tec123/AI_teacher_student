# import os
# import tempfile
# from typing import List, Optional
# from fastapi import UploadFile, HTTPException

# from teacher.services.vector_store_atlas import create_vector_and_store_in_atlas
# from teacher.embeddings.utility import generate_subject_agent_id

# def map_to_db_and_collection(class_: str, subject: str):
#     return class_.strip(), subject.strip()


# async def create_vectors_service(
#     class_: str,
#     subject: str,
#     files: Optional[List[UploadFile]] = None,
#     embedding_model=None,
#     agent_metadata: dict | None = None,
#     subject_agent_id: str | None = None,
# ):
#     db_name, collection_name = map_to_db_and_collection(class_, subject)

#     # Handle: no files OR empty list
#     if not files:
#         return {
#             "status": "skipped",
#             "message": "No files provided",
#             "db": db_name,
#             "collection": collection_name,
#         }

#     file_inputs: List[str] = []
#     original_filenames: List[str] = []

#     for file in files:
#         # Extra safety: skip invalid uploads
#         if not file or not file.filename:
#             continue

#         suffix = os.path.splitext(file.filename)[-1] or ".tmp"

#         with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
#             content = await file.read()

#             # Skip empty file content
#             if not content:
#                 continue

#             tmp.write(content)
#             file_inputs.append(tmp.name)
#             original_filenames.append(file.filename)

#     # After filtering, still nothing usable
#     if not file_inputs:
#         return {
#             "status": "skipped",
#             "message": "No valid files to process",
#             "db": db_name,
#             "collection": collection_name,
#         }

#     # ✅ Generate ID only if new agent
#     if not subject_agent_id:
#         subject_agent_id = generate_subject_agent_id()

#     return create_vector_and_store_in_atlas(
#         subject_agent_id=subject_agent_id,
#         file_inputs=file_inputs,
#         db_name=db_name,
#         collection_name=collection_name,
#         embedding_model=embedding_model,
#         original_filenames=original_filenames,
#         agent_metadata=agent_metadata,
#     )


import os
import tempfile
from typing import List, Optional
from fastapi import UploadFile

from teacher.services.vector_store_atlas import create_vector_and_store_in_atlas
from teacher.embeddings.utility import generate_subject_agent_id
from teacher.services.file_storage import document_storage
from config.settings import settings
import logging
logger = logging.getLogger(__name__)

# Configure logging

def map_to_db_and_collection(class_: Optional[str], subject: str):
    """
    Return db_name and collection_name based on mode:
    - teacher-agent mode: use class + subject
    - subject-only mode: use 'general' db + subject collection
    """
    if class_:
        db_name = class_.strip()
    else:
        db_name = "general"  # fallback for subject-only mode

    collection_name = subject.strip()
    return db_name, collection_name


async def create_vectors_service(
    subject: str,
    class_: Optional[str] = None,
    files: Optional[List[UploadFile]] = None,
    embedding_model=None,
    agent_metadata: dict | None = None,
    subject_agent_id: str | None = None,
    global_prompt_enabled: bool = False,
    global_rag_enabled: bool = False,
):
    db_name, collection_name = map_to_db_and_collection(class_, subject)

    # Handle: no files OR empty list
    if not files:
        return {
            "status": "skipped",
            "message": "No files provided",
            "db": db_name,
            "collection": collection_name,
        }

    file_inputs: List[str] = []
    original_filenames: List[str] = []
    file_storage_paths: List[str] = []  # Track storage paths for each file

    # ✅ Generate ID only if new agent
    if not subject_agent_id:
        subject_agent_id = generate_subject_agent_id()
        logger.info(f"Generated new agent ID: {subject_agent_id}")
    else:
        logger.info(f"Using existing agent ID: {subject_agent_id}")
    
    # Process files and save them immediately for preview
    for file in files:
        # Extra safety: skip invalid uploads
        if not file or not file.filename:
            continue

        suffix = os.path.splitext(file.filename)[-1] or ".tmp"

        # Read file content first
        content = await file.read()
        
        # Skip empty file content
        if not content:
            continue
        
        # Generate document ID and save to storage immediately
        from teacher.embeddings.utility import generate_custom_id
        document_id = generate_custom_id(file.filename, 5)
        
        try:
            # Save file to permanent storage
            storage_path = document_storage.save_uploaded_file(
                file_content=content,
                agent_id=subject_agent_id,
                document_id=document_id,
                filename=file.filename
            )
            file_storage_paths.append(storage_path)
            logger.info(f"Saved original file for preview: {file.filename} -> {storage_path}")
        except Exception as e:
            logger.error(f"Failed to save file {file.filename} for preview: {e}")
            file_storage_paths.append(None)  # Mark as failed
        
        # Create temporary file for vector processing
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            file_inputs.append(tmp.name)
            original_filenames.append(file.filename)

    # After filtering, still nothing usable
    if not file_inputs:
        return {
            "status": "skipped",
            "message": "No valid files to process",
            "db": db_name,
            "collection": collection_name,
        }

    # ✅ Check if agent with same parameters already exists
    if not subject_agent_id:
        from pymongo import MongoClient
        mongodb_uri = settings.mongodb_uri
        if mongodb_uri:
            try:
                client = MongoClient(mongodb_uri)
                db = client[db_name]
                collection = db[collection_name]
                
                # Simple search by agent name first
                existing_agent = collection.find_one({
                    "agent_metadata.agent_name": agent_metadata.get("agent_name", "") if agent_metadata else ""
                })
                
                if existing_agent:
                    subject_agent_id = existing_agent.get("subject_agent_id")
                    logger.info(f"✅ Reusing existing agent ID: {subject_agent_id}")
                else:
                    subject_agent_id = generate_subject_agent_id()
                    logger.info(f"✅ Generated new agent ID: {subject_agent_id}")
                    
                client.close()
            except Exception as e:
                logger.warning(f"Failed to check existing agent: {e}")
                subject_agent_id = generate_subject_agent_id()
        else:
            subject_agent_id = generate_subject_agent_id()
    
    # Now that we have the final agent_id, update storage paths if needed
    # (This is already done above since we save files immediately now)

    # Add global settings to agent metadata
    if agent_metadata is None:
        agent_metadata = {}
    
    agent_metadata.update({
        "global_prompt_enabled": global_prompt_enabled,
        "global_rag_enabled": global_rag_enabled
    })
    
    result = create_vector_and_store_in_atlas(
        subject_agent_id=subject_agent_id,
        file_inputs=file_inputs,
        db_name=db_name,
        collection_name=collection_name,
        embedding_model=embedding_model,
        original_filenames=original_filenames,
        agent_metadata=agent_metadata,
        file_storage_paths=file_storage_paths,  # Pass storage paths
    )

    # Add full prompt information to response
    prompt_info = {
        "enabled": global_prompt_enabled,
        "global_prompt_content": None,
        "full_prompt": None
    }
    
    if global_prompt_enabled:
        try:
            from admin.services.global_prompts_service import get_highest_priority_enabled_prompt
            from common.utils.prompt_templates import build_teacher_prompt
            
            global_prompt = get_highest_priority_enabled_prompt()
            if global_prompt:
                prompt_info["global_prompt_content"] = global_prompt.get("content", "")
                
                # Build the full prompt that will be used by the agent
                sample_student_profile = {
                    "level": "intermediate",
                    "tone": "friendly", 
                    "learning_style": "step-by-step",
                    "response_length": "long",
                    "include_example": True,
                    "common_mistakes": []
                }
                
                full_prompt = build_teacher_prompt(
                    student_profile=sample_student_profile,
                    class_name=class_ or "Sample Class",
                    subject=subject,
                    confusion_type="NO_CONFUSION",
                    session_context="Previous Q: What is biology?\nPrevious A: Biology is the study of living organisms.",
                    current_query="What is photosynthesis?",
                    agent_metadata=agent_metadata
                )
                
                prompt_info["full_prompt"] = full_prompt
        except ImportError:
            # If modules are not available, skip
            pass
    else:
        # When disabled, show the regular prompt without global content
        try:
            from common.utils.prompt_templates import build_teacher_prompt
            
            sample_student_profile = {
                "level": "intermediate",
                "tone": "friendly",
                "learning_style": "step-by-step", 
                "response_length": "long",
                "include_example": True,
                "common_mistakes": []
            }
            
            full_prompt = build_teacher_prompt(
                student_profile=sample_student_profile,
                class_name=class_ or "Sample Class",
                subject=subject,
                confusion_type="NO_CONFUSION",
                session_context="Previous Q: What is biology?\nPrevious A: Biology is the study of living organisms.",
                current_query="What is photosynthesis?",
                agent_metadata=agent_metadata
            )
            
            prompt_info["full_prompt"] = full_prompt
        except ImportError:
            # If modules are not available, skip
            pass
    
    result["prompt"] = prompt_info

    # ✅ Auto-enable shared documents for agent if global_rag_enabled
    if global_rag_enabled and subject_agent_id:
        try:
            # Import here to avoid circular import issues
            from admin.repositories.shared_knowledge_repository import shared_knowledge_manager
            
            # Get all available shared documents
            shared_docs_result = shared_knowledge_manager.list_shared_documents()
            
            if shared_docs_result.get("status") == "success" and shared_docs_result.get("documents"):
                enabled_count = 0
                for doc in shared_docs_result["documents"]:
                    try:
                        # Extract agent info from metadata
                        agent_name = agent_metadata.get("agent_name", "") if agent_metadata else ""
                        class_name = class_ if class_ else ""
                        subject_name = subject if subject else ""
                        
                        # Enable each shared document for this agent with full details
                        success = shared_knowledge_manager.enable_document_for_agent(
                            doc["document_id"], 
                            subject_agent_id,
                            agent_name=agent_name,
                            class_name=class_name,
                            subject=subject_name
                        )
                        if success:
                            enabled_count += 1
                            logger.info(f"✅ Auto-enabled shared document '{doc['document_name']}' for agent {subject_agent_id}")
                    except Exception as e:
                        logger.warning(f"Failed to enable document {doc['document_id']} for agent {subject_agent_id}: {e}")
                
                if enabled_count > 0:
                    logger.info(f"✅ Auto-enabled {enabled_count} shared documents for new agent {subject_agent_id}")
                    
                    # Get the updated list of enabled documents for this agent
                    try:
                        enabled_docs = shared_knowledge_manager.get_agent_enabled_documents(subject_agent_id)
                        result["shared_documents"] = enabled_docs
                    except Exception as e:
                        logger.warning(f"Failed to get enabled documents list: {e}")
                        result["shared_documents"] = []
                    
                    # Add this info to result
                    result["auto_enabled_shared_documents"] = enabled_count
                    result["shared_documents_status"] = "enabled"
                else:
                    logger.info(f"No shared documents available to enable for agent {subject_agent_id}")
                    result["auto_enabled_shared_documents"] = 0
                    result["shared_documents_status"] = "no_documents_available"
                    result["shared_documents"] = []
            else:
                logger.info(f"No shared documents found in system for agent {subject_agent_id}")
                result["auto_enabled_shared_documents"] = 0
                result["shared_documents_status"] = "no_shared_documents"
                result["shared_documents"] = []
                
        except Exception as e:
            logger.error(f"Failed to auto-enable shared documents for agent {subject_agent_id}: {e}")
            result["auto_enabled_shared_documents"] = 0
            result["shared_documents_status"] = "error"
            result["shared_documents"] = []
    
    # ✅ Auto-disable shared documents for agent if global_rag_enabled is false
    elif not global_rag_enabled and subject_agent_id:
        try:
            # Import here to avoid circular import issues
            from admin.repositories.shared_knowledge_repository import shared_knowledge_manager
            
            # Get all available shared documents
            shared_docs_result = shared_knowledge_manager.list_shared_documents()
            
            if shared_docs_result.get("status") == "success" and shared_docs_result.get("documents"):
                disabled_count = 0
                for doc in shared_docs_result["documents"]:
                    try:
                        # Check if this agent is using this document
                        if any(agent.get("agent_id") == subject_agent_id for agent in doc.get("used_by_agents", [])):
                            # Disable this shared document for this agent
                            success = shared_knowledge_manager.disable_document_for_agent(
                                doc["document_id"], 
                                subject_agent_id
                            )
                            if success:
                                disabled_count += 1
                                logger.info(f"✅ Auto-disabled shared document '{doc['document_name']}' for agent {subject_agent_id}")
                    except Exception as e:
                        logger.warning(f"Failed to disable document {doc['document_id']} for agent {subject_agent_id}: {e}")
                
                if disabled_count > 0:
                    logger.info(f"✅ Auto-disabled {disabled_count} shared documents for agent {subject_agent_id}")
                    
                    # Get the updated list of enabled documents for this agent (should be empty)
                    try:
                        enabled_docs = shared_knowledge_manager.get_agent_enabled_documents(subject_agent_id)
                        result["shared_documents"] = enabled_docs
                    except Exception as e:
                        logger.warning(f"Failed to get enabled documents list: {e}")
                        result["shared_documents"] = []
                    
                    # Add this info to result
                    result["auto_disabled_shared_documents"] = disabled_count
                    result["shared_documents_status"] = "disabled"
                else:
                    logger.info(f"No shared documents to disable for agent {subject_agent_id}")
                    result["auto_disabled_shared_documents"] = 0
                    result["shared_documents_status"] = "none_to_disable"
                    result["shared_documents"] = []
            else:
                logger.info(f"No shared documents found in system for agent {subject_agent_id}")
                result["auto_disabled_shared_documents"] = 0
                result["shared_documents_status"] = "no_shared_documents"
                result["shared_documents"] = []
                
        except Exception as e:
            logger.error(f"Failed to auto-disable shared documents for agent {subject_agent_id}: {e}")
            result["auto_disabled_shared_documents"] = 0
            result["shared_documents_status"] = "error"
            result["shared_documents"] = []

    return result
