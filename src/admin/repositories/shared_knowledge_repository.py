import os
import tempfile
import mimetypes
import glob
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import UploadFile, HTTPException
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from teacher.services.vector_store_atlas import create_vector_and_store_in_atlas
from teacher.services.embedding_runner import get_vectors_and_details
from config.settings import settings
import logging
logger = logging.getLogger(__name__)


class SharedKnowledgeManager:
    """Manages shared knowledge documents accessible by all agents."""

    def __init__(self):
        self.mongodb_uri = settings.mongodb_uri
        self.client = MongoClient(self.mongodb_uri)
        self.db = self.client[settings.db_name]
        self.collection = self.db["shared_knowledge"]
    
    def upload_shared_document(
        self,
        files: List[UploadFile],
        document_name: str,
        description: str = "",
        embedding_model=None
    ) -> Dict[str, Any]:
        """Upload and process shared knowledge documents."""
        
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")
        
        if not document_name:
            raise HTTPException(status_code=400, detail="Document name is required")
        
        # Check if document name already exists
        existing = self.collection.find_one({"document_name": document_name})
        if existing:
            # Return existing document instead of creating duplicate
            logger.info(f"Document '{document_name}' already exists, returning existing document")
            return {
                "status": "success",
                "message": f"Document '{document_name}' already exists",
                "document_id": existing.get("document_id"),
                "document_name": existing.get("document_name"),
                "description": existing.get("description", ""),
                "upload_date": existing.get("upload_date"),
                "status": existing.get("status", "indexed"),
                "indexed_chunks": existing.get("indexed_chunks", 0),
                "total_chunks": existing.get("total_chunks", 0),
                "file_count": len(existing.get("file_names", [])),
                "file_names": existing.get("file_names", []),
                "estimated_size": existing.get("estimated_size", "Unknown"),
                "used_by_count": len(existing.get("used_by_agents", [])),
                "used_by_agents": existing.get("used_by_agents", []),
                "is_existing": True
            }
        
        # Process files
        file_inputs = []
        original_filenames = []
        storage_paths = []  # Add storage paths tracking
        
        # Generate unique document ID first so we can use it for filename
        document_id = f"shared_doc_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{len(files)}"
        
        for file in files:
            if not file or not file.filename:
                continue
            
            suffix = os.path.splitext(file.filename)[-1] or ".tmp"
            
            # Create permanent storage file (not temporary)
            storage_dir = os.path.join("storage", "shared")
            os.makedirs(storage_dir, exist_ok=True)
            
            # Use document_id for filename (clean version)
            clean_filename = f"{document_id}{suffix}"
            storage_path = os.path.join(storage_dir, clean_filename)
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                content = file.file.read()
                
                if not content:
                    continue
                
                tmp.write(content)
                file_inputs.append(tmp.name)
                original_filenames.append(file.filename)
                
                # Also save permanent copy for preview
                with open(storage_path, 'wb') as permanent_file:
                    permanent_file.write(content)
                storage_paths.append(storage_path)
        
        if not file_inputs:
            raise HTTPException(status_code=400, detail="No valid files to process")
        
        # Create vectors and store in shared collection
        try:
            result = create_vector_and_store_in_atlas(
                file_inputs=file_inputs,
                db_name=settings.db_name,
                collection_name="shared_knowledge",
                embedding_model=embedding_model,
                original_filenames=original_filenames,
                agent_metadata={
                    "document_type": "shared_knowledge",
                    "document_name": document_name,
                    "description": description,
                    "upload_date": datetime.utcnow().isoformat(),
                    "document_id": document_id
                },
                subject_agent_id=document_id
            )
            
            # Update document metadata
            self.collection.update_many(
                {"subject_agent_id": document_id},
                {
                    "$set": {
                        "document_name": document_name,
                        "description": description,
                        "upload_date": datetime.utcnow().isoformat(),
                        "document_id": document_id,
                        "status": "indexed",
                        "indexed_chunks": result.get("inserted_chunks", 0),
                        "total_chunks": result.get("num_chunks", 0),
                        "file_names": result.get("file_names", []),
                        "used_by_agents": [],
                        "storage_path": storage_paths[0] if storage_paths else None,  # Save first file path for preview
                        "preview_available": len(storage_paths) > 0
                    }
                }
            )
            
            # Clean up temporary files (but keep permanent storage files)
            for file_path in file_inputs:
                try:
                    os.unlink(file_path)
                except Exception as e:
                    logger.warning(f"Failed to delete temporary file {file_path}: {e}")
            
            logger.info(f"Successfully uploaded shared document: {document_name}")
            
            return {
                "status": "success",
                "document_id": document_id,
                "document_name": document_name,
                "description": description,
                "upload_date": datetime.utcnow().isoformat(),
                "total_chunks": result.get("num_chunks", 0),
                "indexed_chunks": result.get("inserted_chunks", 0),
                "file_names": result.get("file_names", []),
                "status": "indexed"
            }
            
        except Exception as e:
            # Clean up temporary files on error
            for file_path in file_inputs:
                try:
                    os.unlink(file_path)
                except Exception:
                    pass
            
            logger.error(f"Failed to upload shared document: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")
    
    def list_shared_documents(self) -> Dict[str, Any]:
        """List all shared knowledge documents with their status and usage."""
        try:
            documents = []
            
            # Get unique documents by document_id
            pipeline = [
                {"$match": {"document_id": {"$exists": True}}},
                {"$group": {
                    "_id": "$document_id",
                    "document_name": {"$first": "$document_name"},
                    "description": {"$first": "$description"},
                    "upload_date": {"$first": "$upload_date"},
                    "status": {"$first": "$status"},
                    "indexed_chunks": {"$first": "$indexed_chunks"},
                    "total_chunks": {"$first": "$total_chunks"},
                    "file_names": {"$first": "$file_names"},
                    "used_by_agents": {"$first": "$used_by_agents"},
                    "subject_agent_id": {"$first": "$subject_agent_id"}
                }},
                {"$sort": {"upload_date": -1}}
            ]
            
            for doc in self.collection.aggregate(pipeline):
                # Calculate file sizes (approximate)
                total_size = 0
                for file_name in doc.get("file_names", []):
                    # Estimate size based on file type
                    if file_name.endswith('.pdf'):
                        total_size += 4.2 * 1024 * 1024  # ~4.2 MB average
                    elif file_name.endswith('.docx'):
                        total_size += 2.8 * 1024 * 1024  # ~2.8 MB average
                    else:
                        total_size += 1.5 * 1024 * 1024  # ~1.5 MB average
                
                # Format file size
                if total_size >= 1024 * 1024:
                    size_str = f"{total_size / (1024 * 1024):.1f} MB"
                else:
                    size_str = f"{total_size / 1024:.1f} KB"
                
                documents.append({
                    "document_id": str(doc["_id"]),  # Convert ObjectId to string
                    "document_name": doc["document_name"],
                    "description": doc.get("description", ""),
                    "upload_date": doc["upload_date"],
                    "status": doc.get("status", "pending"),
                    "indexed_chunks": doc.get("indexed_chunks", 0),
                    "total_chunks": doc.get("total_chunks", 0),
                    "file_count": len(doc.get("file_names", [])),
                    "file_names": doc.get("file_names", []),
                    "estimated_size": size_str,
                    "used_by_count": len(doc.get("used_by_agents", [])),
                    "used_by_agents": doc.get("used_by_agents", [])
                })
            
            return {
                "status": "success",
                "total_documents": len(documents),
                "documents": documents
            }
            
        except Exception as e:
            logger.error(f"Failed to list shared documents: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def delete_shared_document(self, document_id: str) -> Dict[str, Any]:
        """Delete a shared knowledge document."""
        try:
            # Store the original input for logging
            original_input = document_id
            
            # Check if document exists - try both _id and doc_unique_id
            doc = self.collection.find_one({"_id": document_id})
            
            # If not found by _id, try by document_id field
            if not doc:
                doc = self.collection.find_one({"document_id": document_id})
                if doc:
                    # Use the actual document_id field value for deletion
                    document_id = doc["document_id"]
            
            # If still not found, try by doc_unique_id
            if not doc:
                doc = self.collection.find_one({"document.doc_unique_id": original_input})
                if doc:
                    # Use the actual document_id field value for deletion
                    document_id = doc["document_id"]
            
            if not doc:
                # Debug: log what we're looking for
                logger.error(f"Document not found. Tried _id={original_input}, document_id={original_input}, doc_unique_id={original_input}")
                raise HTTPException(status_code=404, detail="Document not found")
            
            # Delete ALL chunks for this document using document_id field (not _id)
            # All chunks share the same document_id, so we delete by that field
            result = self.collection.delete_many({"document_id": document_id})
            
            # If no chunks found by document_id, try doc_unique_id
            if result.deleted_count == 0:
                result = self.collection.delete_many({"document.doc_unique_id": original_input})
            
            # Clean up storage files if they exist
            if doc and doc.get("storage_path") and os.path.exists(doc["storage_path"]):
                try:
                    os.remove(doc["storage_path"])
                    logger.info(f"Deleted storage file: {doc['storage_path']}")
                except Exception as e:
                    logger.warning(f"Failed to delete storage file {doc['storage_path']}: {e}")
            
            logger.info(f"Deleted shared document {document_id}: {result.deleted_count} chunks")
            
            return {
                "status": "success",
                "message": f"Document '{doc.get('document_name', document_id)}' deleted successfully",
                "deleted_chunks": result.deleted_count,
                "document_id": str(document_id)  # Convert ObjectId to string
            }
            
        except Exception as e:
            logger.error(f"Failed to delete shared document {document_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")
    
    def enable_document_for_agent(
        self, 
        document_id: str, 
        agent_id: str,
        agent_name: str = "",
        class_name: str = "",
        subject: str = ""
    ) -> Dict[str, Any]:
        """Enable a shared document for a specific agent."""
        try:
            # Check if document exists
            doc = self.collection.find_one({"document_id": document_id})
            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")
            
            # Add agent to used_by list if not already present
            agent_info = {
                "agent_id": agent_id,
                "agent_name": agent_name,
                "class_name": class_name,
                "subject": subject,
                "enabled_date": datetime.utcnow().isoformat()
            }
            
            # Check if agent is already enabled
            existing_agents = doc.get("used_by_agents", [])
            agent_already_enabled = any(
                agent.get("agent_id") == agent_id for agent in existing_agents
            )
            
            if agent_already_enabled:
                return {
                    "status": "success",
                    "message": "Document already enabled for this agent",
                    "document_id": document_id,
                    "agent_id": agent_id
                }
            
            # Add agent to used_by list
            result = self.collection.update_many(
                {"document_id": document_id},
                {
                    "$push": {"used_by_agents": agent_info}
                }
            )
            
            logger.info(f"Enabled shared document {document_id} for agent {agent_id}")
            
            return {
                "status": "success",
                "message": f"Document '{doc.get('document_name')}' enabled for agent",
                "document_id": document_id,
                "agent_id": agent_id,
                "document_name": doc.get("document_name")
            }
            
        except Exception as e:
            logger.error(f"Failed to enable document {document_id} for agent {agent_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to enable document: {str(e)}")
    
    def disable_document_for_agent(self, document_id: str, agent_id: str) -> Dict[str, Any]:
        """Disable a shared document for a specific agent."""
        try:
            # Check if document exists
            doc = self.collection.find_one({"document_id": document_id})
            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")
            
            # Remove agent from used_by list
            result = self.collection.update_many(
                {"document_id": document_id},
                {
                    "$pull": {"used_by_agents": {"agent_id": agent_id}}
                }
            )
            
            logger.info(f"Disabled shared document {document_id} for agent {agent_id}")
            
            return {
                "status": "success",
                "message": f"Document '{doc.get('document_name')}' disabled for agent",
                "document_id": document_id,
                "agent_id": agent_id,
                "document_name": doc.get("document_name")
            }
            
        except Exception as e:
            logger.error(f"Failed to disable document {document_id} for agent {agent_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to disable document: {str(e)}")
    
    def get_agent_enabled_documents(self, agent_id: str) -> List[Dict[str, Any]]:
        """Get all shared documents enabled for a specific agent."""
        try:
            pipeline = [
                {"$match": {"used_by_agents.agent_id": agent_id}},
                {"$unwind": "$used_by_agents"},
                {"$match": {"used_by_agents.agent_id": agent_id}},
                {"$group": {
                    "_id": "$document_id",
                    "document_name": {"$first": "$document_name"},
                    "description": {"$first": "$description"},
                    "upload_date": {"$first": "$upload_date"},
                    "status": {"$first": "$status"},
                    "indexed_chunks": {"$first": "$indexed_chunks"},
                    "total_chunks": {"$first": "$total_chunks"},
                    "enabled_date": {"$first": "$used_by_agents.enabled_date"}
                }},
                {"$sort": {"enabled_date": -1}}
            ]
            
            documents = []
            for doc in self.collection.aggregate(pipeline):
                # Use the _id field which is the document_id in this aggregation
                doc_id = doc["_id"]
                logger.debug(f"Found enabled document for agent {agent_id}: {doc['document_name']} (ID: {doc_id})")
                
                documents.append({
                    "document_id": doc_id,  # This is the correct document_id
                    "document_name": doc["document_name"],
                    "description": doc.get("description", ""),
                    "upload_date": doc["upload_date"],
                    "status": doc.get("status", "pending"),
                    "indexed_chunks": doc.get("indexed_chunks", 0),
                    "total_chunks": doc.get("total_chunks", 0),
                    "enabled_date": doc["enabled_date"]
                })
            
            logger.info(f"Returning {len(documents)} enabled shared documents for agent {agent_id}")
            return documents
            
        except Exception as e:
            logger.error(f"Failed to get enabled documents for agent {agent_id}: {e}")
            return []
    
    def get_shared_document_file_path(self, document_id: str) -> Optional[str]:
        """Get the file path for a shared document for preview."""
        try:
            # First try to find by document_id field (most common case)
            doc = self.collection.find_one({"document_id": document_id})
            
            # If not found, try by _id field (some cases)
            if not doc:
                doc = self.collection.find_one({"_id": document_id})
            
            # If still not found, try by doc_unique_id in the document object
            if not doc:
                doc = self.collection.find_one({"document.doc_unique_id": document_id})
            
            if not doc:
                return None
            
            # Check if storage path is available in document metadata
            storage_path = doc.get("storage_path")
            if storage_path and os.path.exists(storage_path):
                return storage_path
            
            # If no direct storage path, try to find file by pattern matching
            storage_dir = os.path.join("storage", "shared")
            if os.path.exists(storage_dir):
                # Try to find exact file with document_id + extension
                
                # First try exact match with document_id
                for ext in ['.pdf', '.docx', '.doc', '.txt', '.html', '.csv', '.json']:
                    pattern = os.path.join(storage_dir, f"{document_id}{ext}")
                    if os.path.exists(pattern):
                        logger.info(f"Found exact file: {pattern}")
                        return pattern
                
                # Then try pattern matching with document_id
                pattern = os.path.join(storage_dir, f"{document_id}*")
                matching_files = glob.glob(pattern)
                
                if matching_files:
                    logger.info(f"Found file by pattern matching: {matching_files[0]}")
                    return matching_files[0]
                
                # If not found, try to find the most recent shared document file
                # This handles cases where there might be timestamp mismatches
                all_shared_files = glob.glob(os.path.join(storage_dir, "shared_doc_*.pdf"))
                if all_shared_files:
                    # Sort by modification time, get the most recent
                    all_shared_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                    logger.info(f"Using most recent shared document file: {all_shared_files[0]}")
                    return all_shared_files[0]
                
                # Also try with doc_unique_id if available
                doc_unique_id = doc.get("document", {}).get("doc_unique_id", "")
                if doc_unique_id:
                    pattern = os.path.join(storage_dir, f"*{doc_unique_id}*")
                    matching_files = glob.glob(pattern)
                    if matching_files:
                        logger.info(f"Found file by doc_unique_id pattern: {matching_files[0]}")
                        return matching_files[0]
            
            # If no direct storage path, we need to reconstruct from file storage
            # This is a fallback - in practice, shared documents might not store original files
            # Only the embedded chunks
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get file path for shared document {document_id}: {e}")
            return None
    
    def get_shared_document_metadata(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed metadata for a specific shared document."""
        try:
            # First try to find by document_id field (most common case)
            doc = self.collection.find_one({"document_id": document_id})
            
            # If not found, try by _id field (some cases)
            if not doc:
                doc = self.collection.find_one({"_id": document_id})
            
            # If still not found, try by doc_unique_id in the document object
            if not doc:
                doc = self.collection.find_one({"document.doc_unique_id": document_id})
            
            if not doc:
                return None
            
            # Get file path for additional info
            storage_path = self.get_shared_document_file_path(document_id)
            storage_info = None
            
            if storage_path:
                try:
                    file_stat = os.stat(storage_path)
                    storage_info = {
                        "file_exists": True,
                        "file_size": file_stat.st_size,
                        "last_modified": file_stat.st_mtime,
                        "mime_type": mimetypes.guess_type(storage_path)[0] or "application/octet-stream"
                    }
                except Exception as e:
                    storage_info = {"file_exists": False, "error": str(e)}
            else:
                storage_info = {"file_exists": False, "message": "Original file not stored"}
            
            return {
                "document_id": str(doc["_id"]),  # Convert ObjectId to string
                "doc_unique_id": doc.get("document", {}).get("doc_unique_id", ""),
                "document_name": doc["document_name"],
                "description": doc.get("description", ""),
                "upload_date": doc["upload_date"],
                "status": doc.get("status", "pending"),
                "indexed_chunks": doc.get("indexed_chunks", 0),
                "total_chunks": doc.get("total_chunks", 0),
                "file_names": doc.get("file_names", []),
                "used_by_agents": doc.get("used_by_agents", []),
                "storage_path": storage_path,
                "storage_info": storage_info,
                "preview_available": storage_path is not None
            }
            
        except Exception as e:
            logger.error(f"Failed to get metadata for shared document {document_id}: {e}")
            return None
    
    def remove_agent_from_shared_documents(self, agent_id: str) -> dict:
        """
        Remove an agent from all shared documents and optionally clean up unused shared files
        
        Args:
            agent_id: Agent identifier to remove
            
        Returns:
            Dict with removal statistics
        """
        try:
            # Find all shared documents that use this agent
            shared_docs = list(self.collection.find({"used_by_agents.agent_id": agent_id}))
            
            documents_updated = 0
            documents_with_no_agents = 0
            files_deleted = 0
            bytes_freed = 0
            
            for doc in shared_docs:
                # Remove agent from used_by_agents list
                used_by_agents = doc.get("used_by_agents", [])
                original_count = len(used_by_agents)
                
                # Filter out the target agent
                used_by_agents = [agent for agent in used_by_agents if agent.get("agent_id") != agent_id]
                
                if len(used_by_agents) < original_count:
                    # Update the document
                    self.collection.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {"used_by_agents": used_by_agents}}
                    )
                    documents_updated += 1
                    
                    # Check if no agents are using this document anymore
                    if len(used_by_agents) == 0:
                        documents_with_no_agents += 1
                        
                        # Optionally delete the shared file
                        try:
                            storage_path = self.get_shared_document_file_path(doc["document_id"])
                            if storage_path and os.path.exists(storage_path):
                                file_size = os.path.getsize(storage_path)
                                os.remove(storage_path)
                                files_deleted += 1
                                bytes_freed += file_size
                                logger.info(f"Deleted unused shared document file: {storage_path}")
                        except Exception as e:
                            logger.warning(f"Failed to delete shared document file: {e}")
                    
                    logger.info(f"Removed agent {agent_id} from shared document {doc['document_name']}")
            
            return {
                'documents_updated': documents_updated,
                'documents_with_no_agents': documents_with_no_agents,
                'files_deleted': files_deleted,
                'bytes_freed': bytes_freed,
                'message': f'Removed agent {agent_id} from {documents_updated} shared documents'
            }
            
        except Exception as e:
            logger.error(f"Failed to remove agent {agent_id} from shared documents: {e}")
            return {
                'documents_updated': 0,
                'documents_with_no_agents': 0,
                'files_deleted': 0,
                'bytes_freed': 0,
                'message': f'Failed to remove agent from shared documents: {str(e)}'
            }

# Global instance
shared_knowledge_manager = SharedKnowledgeManager()
