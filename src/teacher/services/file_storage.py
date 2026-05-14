"""
File storage utilities for document preview system
Handles saving and retrieving original documents for preview functionality
"""

import os
import shutil
import hashlib
from typing import Optional, List
from pathlib import Path
import logging
logger = logging.getLogger(__name__)


class DocumentStorage:
    """Manages storage of original documents for preview functionality"""
    
    def __init__(self, base_storage_path: str = "storage"):
        self.base_storage_path = Path(base_storage_path)
        self.agents_path = self.base_storage_path / "agents"
        self.shared_path = self.base_storage_path / "shared"
        
        # Ensure directories exist
        self.base_storage_path.mkdir(exist_ok=True)
        self.agents_path.mkdir(exist_ok=True)
        self.shared_path.mkdir(exist_ok=True)
    
    def get_agent_storage_path(self, agent_id: str) -> Path:
        """Get storage path for a specific agent"""
        agent_path = self.agents_path / agent_id
        agent_path.mkdir(exist_ok=True)
        return agent_path
    
    def get_document_storage_path(self, agent_id: str, document_id: str) -> Path:
        """Get storage path for a specific document"""
        agent_path = self.get_agent_storage_path(agent_id)
        doc_path = agent_path / document_id
        doc_path.mkdir(exist_ok=True)
        return doc_path
    
    def save_uploaded_file(self, file_content: bytes, agent_id: str, document_id: str, filename: str) -> str:
        """
        Save an uploaded file to storage
        
        Args:
            file_content: Binary content of the file
            agent_id: Agent identifier
            document_id: Document unique identifier
            filename: Original filename
            
        Returns:
            Relative storage path for the file
        """
        try:
            doc_storage_path = self.get_document_storage_path(agent_id, document_id)
            file_path = doc_storage_path / filename
            
            # Write file content
            with open(file_path, 'wb') as f:
                f.write(file_content)
            
            # Return relative path from project root
            try:
                relative_path = str(file_path.relative_to(Path.cwd()))
            except ValueError:
                # If paths are on different drives, use absolute path
                relative_path = str(file_path)
            logger.info(f"Saved file: {filename} to {relative_path}")
            
            return relative_path
            
        except Exception as e:
            logger.error(f"Failed to save file {filename}: {e}")
            raise
    
    def save_temp_file(self, temp_file_path: str, agent_id: str, document_id: str, filename: str) -> str:
        """
        Save a temporary file to permanent storage
        
        Args:
            temp_file_path: Path to temporary file
            agent_id: Agent identifier
            document_id: Document unique identifier
            filename: Original filename
            
        Returns:
            Relative storage path for the file
        """
        try:
            doc_storage_path = self.get_document_storage_path(agent_id, document_id)
            file_path = doc_storage_path / filename
            
            # Copy file from temp location
            shutil.copy2(temp_file_path, file_path)
            
            # Return relative path from project root
            relative_path = str(file_path.relative_to(Path.cwd()))
            logger.info(f"Saved temp file: {filename} to {relative_path}")
            
            return relative_path
            
        except Exception as e:
            logger.error(f"Failed to save temp file {temp_file_path}: {e}")
            raise
    
    def get_file_path(self, agent_id: str, document_id: str, filename: str) -> Optional[str]:
        """
        Get the full path to a stored file
        
        Args:
            agent_id: Agent identifier
            document_id: Document unique identifier
            filename: Original filename
            
        Returns:
            Full path to the file or None if not found
        """
        try:
            file_path = self.get_document_storage_path(agent_id, document_id) / filename
            
            if file_path.exists():
                return str(file_path)
            return None
            
        except Exception as e:
            logger.error(f"Failed to get file path: {e}")
            return None
    
    def delete_document_files(self, agent_id: str, document_id: str) -> bool:
        """
        Delete all files for a specific document
        
        Args:
            agent_id: Agent identifier
            document_id: Document unique identifier
            
        Returns:
            True if deletion was successful
        """
        try:
            doc_path = self.get_document_storage_path(agent_id, document_id)
            
            if doc_path.exists():
                shutil.rmtree(doc_path)
                logger.info(f"Deleted document files: {agent_id}/{document_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to delete document files: {e}")
            return False
    
    def list_agent_documents(self, agent_id: str) -> List[dict]:
        """
        List all documents stored for an agent
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            List of document information dicts
        """
        try:
            agent_path = self.get_agent_storage_path(agent_id)
            documents = []
            
            if not agent_path.exists():
                return documents
            
            for doc_dir in agent_path.iterdir():
                if doc_dir.is_dir():
                    # Get all files in this document directory
                    files = list(doc_dir.glob('*'))
                    if files:
                        # Get the first file as the main document
                        main_file = files[0]
                        file_size = main_file.stat().st_size
                        
                        documents.append({
                            'document_id': doc_dir.name,
                            'filename': main_file.name,
                            'file_path': str(main_file.relative_to(Path.cwd())),
                            'file_size': file_size,
                            'file_count': len(files)
                        })
            
            return documents
            
        except Exception as e:
            logger.error(f"Failed to list agent documents: {e}")
            return []
    
    def delete_agent_storage(self, agent_id: str) -> dict:
        """
        Delete all storage for a specific agent
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            Dict with deletion statistics
        """
        try:
            agent_path = self.get_agent_storage_path(agent_id)
            
            if not agent_path.exists():
                return {
                    'deleted': False,
                    'message': f'Agent storage directory not found: {agent_id}',
                    'files_deleted': 0,
                    'directories_deleted': 0,
                    'bytes_freed': 0
                }
            
            # Count files and directories before deletion
            files_deleted = 0
            directories_deleted = 0
            bytes_freed = 0
            
            for root, dirs, files in os.walk(agent_path, topdown=False):
                # Count files
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        file_size = os.path.getsize(file_path)
                        bytes_freed += file_size
                        files_deleted += 1
                    except OSError:
                        pass
                
                # Count directories
                for dir in dirs:
                    directories_deleted += 1
            
            # Add the root directory itself
            directories_deleted += 1
            
            # Delete the entire agent directory
            shutil.rmtree(agent_path)
            logger.info(f"Deleted agent storage: {agent_id} - {files_deleted} files, {directories_deleted} dirs, {bytes_freed} bytes")
            
            return {
                'deleted': True,
                'message': f'Successfully deleted agent storage for {agent_id}',
                'files_deleted': files_deleted,
                'directories_deleted': directories_deleted,
                'bytes_freed': bytes_freed
            }
            
        except Exception as e:
            logger.error(f"Failed to delete agent storage {agent_id}: {e}")
            return {
                'deleted': False,
                'message': f'Failed to delete agent storage: {str(e)}',
                'files_deleted': 0,
                'directories_deleted': 0,
                'bytes_freed': 0
            }
    
    def get_storage_info(self) -> dict:
        """Get information about storage usage"""
        try:
            total_size = 0
            total_files = 0
            total_agents = 0
            
            if self.agents_path.exists():
                for agent_dir in self.agents_path.iterdir():
                    if agent_dir.is_dir():
                        total_agents += 1
                        for doc_dir in agent_dir.iterdir():
                            if doc_dir.is_dir():
                                for file_path in doc_dir.iterdir():
                                    if file_path.is_file():
                                        total_files += 1
                                        total_size += file_path.stat().st_size
            
            return {
                'total_agents': total_agents,
                'total_files': total_files,
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'storage_path': str(self.base_storage_path)
            }
            
        except Exception as e:
            logger.error(f"Failed to get storage info: {e}")
            return {
                'total_agents': 0,
                'total_files': 0,
                'total_size_bytes': 0,
                'total_size_mb': 0,
                'storage_path': str(self.base_storage_path)
            }

# Global instance for use across the application
document_storage = DocumentStorage()
