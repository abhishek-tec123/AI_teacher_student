# update_agent_data.py
import os
from typing import List, Optional
from fastapi import UploadFile, HTTPException
from pymongo import MongoClient
from config.settings import settings
import logging
logger = logging.getLogger(__name__)

async def update_agent_data(
    subject_agent_id: str,
    class_: Optional[str],
    subject: Optional[str],
    agent_type: Optional[str],
    agent_name: Optional[str],
    description: Optional[str],
    teaching_tone: Optional[str],
    global_prompt_enabled: bool,
    global_rag_enabled: bool,
    files: Optional[List[UploadFile]],
    embedding_model,
    create_vectors_service,
):
    """Update agent metadata and optionally replace documents."""

    MONGODB_URI = settings.mongodb_uri
    if not MONGODB_URI:
        raise HTTPException(status_code=500, detail="MongoDB URI not configured")

    client = MongoClient(MONGODB_URI)

    found_collection = None
    found_db_name = None
    found_collection_name = None

    # -------------------------------
    # Search agent across all DBs
    # -------------------------------
    for db_name in client.list_database_names():
        if db_name in ["admin", "local", "config"]:
            continue

        db = client[db_name]

        for collection_name in db.list_collection_names():
            collection = db[collection_name]

            existing = collection.find_one({"subject_agent_id": subject_agent_id})
            if existing is not None:
                found_collection = collection
                found_db_name = db_name
                found_collection_name = collection_name
                break

        if found_collection is not None:
            break

    if found_collection is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    # -------------------------------
    # Update agent metadata
    # -------------------------------
    update_fields = {
        k: v for k, v in {
            "agent_metadata.agent_type": agent_type,
            "agent_metadata.agent_name": agent_name,
            "agent_metadata.description": description,
            "agent_metadata.teaching_tone": teaching_tone,
            "agent_metadata.global_prompt_enabled": global_prompt_enabled,
            "agent_metadata.global_rag_enabled": global_rag_enabled,
        }.items() if v is not None or k in [
            "agent_metadata.global_prompt_enabled",
            "agent_metadata.global_rag_enabled"
        ]
    }

    if update_fields:
        found_collection.update_many(
            {"subject_agent_id": subject_agent_id},
            {"$set": update_fields}
        )
    
    # ✅ Auto-enable/disable shared documents based on global_rag_enabled setting
    auto_result = {"auto_enabled_shared_documents": 0, "auto_disabled_shared_documents": 0, "shared_documents": []}
    
    try:
        from admin.repositories.shared_knowledge_repository import shared_knowledge_manager
        
        # Get all available shared documents
        shared_docs_result = shared_knowledge_manager.list_shared_documents()
        
        if shared_docs_result.get("status") == "success" and shared_docs_result.get("documents"):
            if global_rag_enabled:
                # Enable shared documents for this agent
                enabled_count = 0
                for doc in shared_docs_result["documents"]:
                    try:
                        # Get agent details from updated metadata or existing data
                        agent_doc = found_collection.find_one({"subject_agent_id": subject_agent_id})
                        agent_metadata = agent_doc.get("agent_metadata", {}) if agent_doc else {}
                        agent_name_from_db = agent_metadata.get("agent_name", "")
                        class_name_from_db = found_db_name
                        subject_name_from_db = found_collection_name
                        
                        success = shared_knowledge_manager.enable_document_for_agent(
                            doc["document_id"], 
                            subject_agent_id,
                            agent_name=agent_name_from_db,
                            class_name=class_name_from_db,
                            subject=subject_name_from_db
                        )
                        if success:
                            enabled_count += 1
                            logger.info(f"✅ Auto-enabled shared document '{doc['document_name']}' for agent {subject_agent_id}")
                    except Exception as e:
                        logger.warning(f"Failed to enable document {doc['document_id']} for agent {subject_agent_id}: {e}")
                
                # Get the updated list of enabled documents
                try:
                    enabled_docs = shared_knowledge_manager.get_agent_enabled_documents(subject_agent_id)
                    auto_result["shared_documents"] = enabled_docs
                except Exception as e:
                    logger.warning(f"Failed to get enabled documents list: {e}")
                    auto_result["shared_documents"] = []
                
                if enabled_count > 0:
                    auto_result["auto_enabled_shared_documents"] = enabled_count
                    auto_result["shared_documents_status"] = "enabled"
                    
            else:
                # Disable shared documents for this agent
                disabled_count = 0
                for doc in shared_docs_result["documents"]:
                    try:
                        # Check if this agent is using this document
                        if any(agent.get("agent_id") == subject_agent_id for agent in doc.get("used_by_agents", [])):
                            success = shared_knowledge_manager.disable_document_for_agent(
                                doc["document_id"], 
                                subject_agent_id
                            )
                            if success:
                                disabled_count += 1
                                logger.info(f"✅ Auto-disabled shared document '{doc['document_name']}' for agent {subject_agent_id}")
                    except Exception as e:
                        logger.warning(f"Failed to disable document {doc['document_id']} for agent {subject_agent_id}: {e}")
                
                # Get the updated list of enabled documents (should be empty)
                try:
                    enabled_docs = shared_knowledge_manager.get_agent_enabled_documents(subject_agent_id)
                    auto_result["shared_documents"] = enabled_docs
                except Exception as e:
                    logger.warning(f"Failed to get enabled documents list: {e}")
                    auto_result["shared_documents"] = []
                
                if disabled_count > 0:
                    auto_result["auto_disabled_shared_documents"] = disabled_count
                    auto_result["shared_documents_status"] = "disabled"
                    
    except Exception as e:
        logger.warning(f"Failed to auto-enable/disable shared documents for agent {subject_agent_id}: {e}")
        auto_result["shared_documents_status"] = "error"

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
                    class_name=found_db_name or "Sample Class",
                    subject=found_collection_name,
                    confusion_type="NO_CONFUSION",
                    session_context="Previous Q: What is biology?\nPrevious A: Biology is the study of living organisms.",
                    current_query="What is photosynthesis?",
                    agent_metadata={"global_prompt_enabled": True}
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
                class_name=found_db_name or "Sample Class",
                subject=found_collection_name,
                confusion_type="NO_CONFUSION",
                session_context="Previous Q: What is biology?\nPrevious A: Biology is the study of living organisms.",
                current_query="What is photosynthesis?",
                agent_metadata={"global_prompt_enabled": False}
            )
            
            prompt_info["full_prompt"] = full_prompt
        except ImportError:
            # If modules are not available, skip
            pass
    
    auto_result["prompt"] = prompt_info

    # Log activity for agent update
    try:
        from student.services.activity_tracker import log_agent_updated
        
        # Determine what was changed
        changes = []
        if agent_type:
            changes.append("agent_type")
        if agent_name:
            changes.append("agent_name")
        if description:
            changes.append("description")
        if teaching_tone:
            changes.append("teaching_tone")
        if files:
            changes.append("documents")
        # Always include global settings in changes since they're always updated
        changes.extend(["global_prompt_enabled", "global_rag_enabled"])
        
        # Get the agent name for logging
        agent_doc = found_collection.find_one({"subject_agent_id": subject_agent_id})
        agent_metadata = agent_doc.get("agent_metadata", {}) if agent_doc else {}
        agent_name_for_log = agent_metadata.get("agent_name") or agent_name or found_collection_name
        
        if changes:
            log_agent_updated(
                agent_id=subject_agent_id,
                agent_name=agent_name_for_log,
                subject=found_collection_name,
                class_name=found_db_name,
                changes=changes
            )
            logger.info(f"✅ Logged agent update activity for {subject_agent_id}")
        
    except Exception as e:
        logger.info(f"❌ Failed to log agent update activity: {e}")

    # -------------------------------
    # Replace documents if new files uploaded
    # -------------------------------
    if files:
        summary = await create_vectors_service(
            class_=found_db_name,
            subject=found_collection_name,
            files=files,
            embedding_model=embedding_model,
            agent_metadata={
                "agent_type": agent_type,
                "agent_name": agent_name,
                "description": description,
                "teaching_tone": teaching_tone,
            },
            subject_agent_id=subject_agent_id,
        )

        if not summary:
            raise HTTPException(status_code=500, detail="Failed to create new embeddings")

        # Check if summary contains vector_unique_ids (only present when files are actually processed)
        if "vector_unique_ids" not in summary:
            # No new vectors were created, nothing to delete
            return {
                "message": "Agent updated but no new documents were processed",
                "new_chunks": 0,
                "deleted_old_chunks": 0,
                "subject_agent_id": subject_agent_id,
                **auto_result
            }

        # ✅ Update student's subject_agent field to include the actual agent_id
        try:
            from student.repositories.student_repository import StudentManager
            student_manager = StudentManager()
            
            # Find students who might be using this agent based on subject name
            # This is a simple approach - in production, you'd have proper enrollment tracking
            if subject and found_db_name:
                # Get students from the class who have this subject
                students = student_manager.get_students_by_class(found_db_name)
                
                for student in students:
                    student_details = student.get("student_details", {})
                    student_subjects = student_details.get("subject_agent", [])
                    
                    # Check if this student has this subject
                    subject_found = False
                    updated_subjects = []
                    
                    for subj in student_subjects:
                        if isinstance(subj, dict) and subj.get("subject") == subject:
                            # Update this subject entry to include the agent_id
                            updated_subjects.append({
                                "subject": subject,
                                "agent_id": subject_agent_id  # Add the actual agent ID
                            })
                            subject_found = True
                        else:
                            updated_subjects.append(subj)
                    
                    # Update student record if we found and updated the subject
                    if subject_found:
                        student_manager.update_student(
                            student_id=student.get("student_id"),
                            subject_agent=updated_subjects
                        )
                        logger.info(f"✅ Updated student {student.get('student_id')} subject_agent with agent_id {subject_agent_id}")
                        
        except Exception as e:
            logger.info(f"⚠️  Failed to update student subject_agent: {e}")

        delete_result = found_collection.delete_many(
            {
                "subject_agent_id": subject_agent_id,
                "chunk.unique_chunk_id": {"$nin": summary["vector_unique_ids"]}
            }
        )

        return {
            "message": "Agent updated and documents replaced successfully",
            "new_chunks": summary.get("num_chunks", 0),
            "deleted_old_chunks": delete_result.deleted_count,
            "subject_agent_id": subject_agent_id,
            **auto_result
        }

    return {
        "message": "Agent metadata updated successfully",
        "subject_agent_id": subject_agent_id,
        **auto_result
    }

async def delete_vectors(subject_agent_id: str):
    """
    Delete all vector documents in MongoDB for a given subject_agent_id.
    """
    MONGODB_URI = settings.mongodb_uri
    if not MONGODB_URI:
        raise HTTPException(status_code=500, detail="MongoDB URI not configured")

    client = MongoClient(MONGODB_URI)

    deleted_count_total = 0

    # Search all databases for the agent
    for db_name in client.list_database_names():
        if db_name in ["admin", "local", "config"]:
            continue
        db = client[db_name]

        for collection_name in db.list_collection_names():
            collection = db[collection_name]

            delete_result = collection.delete_many({"subject_agent_id": subject_agent_id})
            deleted_count_total += delete_result.deleted_count

    logger.info(f"Deleted {deleted_count_total} vector documents for agent {subject_agent_id}")
    return {
        "deleted": True,
        "deleted_chunks": deleted_count_total
    }

async def delete_agent_data(subject_agent_id: str) -> dict:
    """
    Delete an agent and all its vectors/documents from MongoDB.
    Enhanced to drop the entire collection if it contains only the target agent's data
    and delete all local storage files associated with the agent.
    """
    MONGODB_URI = settings.mongodb_uri
    if not MONGODB_URI:
        raise HTTPException(status_code=500, detail="MongoDB URI not configured")

    client = MongoClient(MONGODB_URI)
    
    deleted_chunks = 0
    dropped_collections = []
    collections_with_multiple_agents = []
    
    # Storage deletion statistics
    storage_deletion_stats = {
        'agent_storage': {'deleted': False, 'files_deleted': 0, 'bytes_freed': 0},
        'shared_documents': {'documents_updated': 0, 'files_deleted': 0, 'bytes_freed': 0}
    }
    
    # Search all databases for the agent
    for db_name in client.list_database_names():
        if db_name in ["admin", "local", "config"]:
            continue
        db = client[db_name]

        for collection_name in db.list_collection_names():
            collection = db[collection_name]
            
            # Check if this collection contains the target agent
            agent_docs = list(collection.find({"subject_agent_id": subject_agent_id}))
            if not agent_docs:
                continue
                
            # Count total documents and unique agents in this collection
            total_docs = collection.count_documents({})
            unique_agents = collection.distinct("subject_agent_id")
            
            logger.info(f"Collection {db_name}.{collection_name}: {total_docs} total docs, {len(unique_agents)} unique agents")
            
            if len(unique_agents) == 1 and unique_agents[0] == subject_agent_id:
                # Safe to drop the entire collection - it only contains our target agent
                try:
                    logger.info(f"Dropping collection {db_name}.{collection_name} as it only contains agent {subject_agent_id}")
                    db.drop_collection(collection_name)
                    dropped_collections.append(f"{db_name}.{collection_name}")
                    deleted_chunks += len(agent_docs)
                    logger.info(f"✅ Dropped collection {db_name}.{collection_name} with {len(agent_docs)} documents")
                except Exception as e:
                    logger.info(f"❌ Failed to drop collection {db_name}.{collection_name}: {e}")
                    # Fallback to document-level deletion
                    delete_result = collection.delete_many({"subject_agent_id": subject_agent_id})
                    deleted_chunks += delete_result.deleted_count
                    logger.info(f"Fallback: Deleted {delete_result.deleted_count} documents from {db_name}.{collection_name}")
            else:
                # Collection contains multiple agents - only delete this agent's documents
                collections_with_multiple_agents.append(f"{db_name}.{collection_name}")
                delete_result = collection.delete_many({"subject_agent_id": subject_agent_id})
                deleted_chunks += delete_result.deleted_count
                logger.info(f"Deleted {delete_result.deleted_count} documents from multi-agent collection {db_name}.{collection_name}")

    # Delete agent local storage
    try:
        from teacher.services.file_storage import document_storage
        storage_deletion_stats['agent_storage'] = document_storage.delete_agent_storage(subject_agent_id)
        logger.info(f"✅ Agent storage deletion: {storage_deletion_stats['agent_storage']['message']}")
    except Exception as e:
        logger.info(f"❌ Failed to delete agent storage: {e}")
        storage_deletion_stats['agent_storage'] = {
            'deleted': False,
            'message': f'Failed to delete agent storage: {str(e)}',
            'files_deleted': 0,
            'bytes_freed': 0
        }
    
    # Remove agent from shared documents
    try:
        from admin.repositories.shared_knowledge_repository import shared_knowledge_manager
        shared_result = shared_knowledge_manager.remove_agent_from_shared_documents(subject_agent_id)
        storage_deletion_stats['shared_documents'] = shared_result
        logger.info(f"✅ Shared document cleanup: {shared_result['message']}")
    except Exception as e:
        logger.info(f"❌ Failed to remove agent from shared documents: {e}")
        storage_deletion_stats['shared_documents'] = {
            'documents_updated': 0,
            'files_deleted': 0,
            'bytes_freed': 0,
            'message': f'Failed to remove agent from shared documents: {str(e)}'
        }

    # Log activity for agent deletion
    try:
        from student.services.activity_tracker import log_agent_deleted
        
        log_agent_deleted(
            agent_id=subject_agent_id,
            dropped_collections=dropped_collections,
            collections_with_multiple_agents=collections_with_multiple_agents,
            deleted_chunks=deleted_chunks
        )
        logger.info(f"✅ Logged agent deletion activity for {subject_agent_id}")
        
    except Exception as e:
        logger.info(f"❌ Failed to log agent deletion activity: {e}")

    # Calculate total storage freed
    total_files_deleted = storage_deletion_stats['agent_storage']['files_deleted'] + storage_deletion_stats['shared_documents']['files_deleted']
    total_bytes_freed = storage_deletion_stats['agent_storage']['bytes_freed'] + storage_deletion_stats['shared_documents']['bytes_freed']

    logger.info(f"Agent {subject_agent_id} deletion summary:")
    logger.info(f"  - Total chunks deleted: {deleted_chunks}")
    logger.info(f"  - Collections dropped: {len(dropped_collections)}")
    logger.info(f"  - Storage files deleted: {total_files_deleted}")
    logger.info(f"  - Storage space freed: {total_bytes_freed} bytes ({round(total_bytes_freed / (1024*1024), 2)} MB)")
    if dropped_collections:
        logger.info(f"    Dropped: {', '.join(dropped_collections)}")
    if collections_with_multiple_agents:
        logger.info(f"  - Multi-agent collections cleaned: {len(collections_with_multiple_agents)}")
        logger.info(f"    Cleaned: {', '.join(collections_with_multiple_agents)}")

    if deleted_chunks == 0 and total_files_deleted == 0:
        return {"deleted": False, "deleted_chunks": 0}

    return {
        "deleted": True, 
        "deleted_chunks": deleted_chunks, 
        "subject_agent_id": subject_agent_id,
        "dropped_collections": dropped_collections,
        "collections_with_multiple_agents": collections_with_multiple_agents,
        "storage_deletion": storage_deletion_stats,
        "total_files_deleted": total_files_deleted,
        "total_bytes_freed": total_bytes_freed
    }