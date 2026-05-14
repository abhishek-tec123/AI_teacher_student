from typing import List, Union
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
import hashlib
import os
from datetime import datetime
from teacher.services.text_collection import MixedFileTypeLoader

def load_documents(file_paths: Union[str, List[str]], verbose: bool = True) -> List[Document]:
    loader = MixedFileTypeLoader(file_paths, verbose=verbose)
    return loader.load()

def split_documents(docs: List[Document], chunk_size: int = 1000, chunk_overlap: int = 200) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return splitter.split_documents(docs)

def embed_chunks(chunks: List[Document], embedding_model) -> List[List[float]]:
    texts = [chunk.page_content for chunk in chunks]
    return embedding_model.embed_documents(texts)

import random
import string

def generate_subject_agent_id():
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"agent_{random_part}"

# def build_embedding_json(chunks: List[Document], embeddings: List[List[float]]) -> List[dict]:
#     result = []
#     for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
#         entry = {
#             "index": idx,
#             "source": chunk.metadata.get("source", None),
#             "embedding": emb,
#             "embedding_size": len(emb),
#             "chunk_text": chunk.page_content,
#             "metadata": chunk.metadata
#         }
#         result.append(entry)
#     return result

def generate_custom_id(file_name, length=5):
    # Deterministically generate a 5-char alphanumeric string from the file name
    hash_digest = hashlib.sha256(file_name.encode('utf-8')).hexdigest()
    return hash_digest[:length]

def build_embedding_json_for_db(chunks: List[Document], embeddings: List[List[float]], embedding_model_name: str, original_filenames: List[str] = None, agent_metadata: dict | None = None, subject_agent_id: str = None, file_storage_paths: List[str] | None = None):
    result = []
    unique_ids = set()
    
    # Create a mapping from temporary file paths to original filenames
    temp_to_original_mapping = {}
    if original_filenames:
        # Group chunks by their source file
        source_files = {}
        for chunk in chunks:
            source = chunk.metadata.get("source", None)
            if source:
                temp_filename = os.path.basename(source)
                if temp_filename not in source_files:
                    source_files[temp_filename] = []
                source_files[temp_filename].append(chunk)
        
        # Map each unique temp file to an original filename
        temp_files = list(source_files.keys())
        for i, temp_file in enumerate(temp_files):
            if i < len(original_filenames):
                temp_to_original_mapping[temp_file] = original_filenames[i]
    
    # Assign a unique_id (5-char custom alphanumeric) for each document (by file_name)
    file_name_to_unique_id = {}
    for chunk in chunks:
        source = chunk.metadata.get("source", None)
        file_name = os.path.basename(source) if source else None
        
        # Use original filename if available, otherwise use temp filename
        if file_name and file_name in temp_to_original_mapping:
            file_name = temp_to_original_mapping[file_name]
        
        if file_name and file_name not in file_name_to_unique_id:
            file_name_to_unique_id[file_name] = generate_custom_id(file_name, 5)
    
    for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        source = chunk.metadata.get("source")
        file_type = os.path.splitext(source)[1] if source else None
        file_name = os.path.basename(source) if source else None

        if file_name in temp_to_original_mapping:
            file_name = temp_to_original_mapping[file_name]

        unique_id = file_name_to_unique_id.get(file_name)
        unique_ids.add(unique_id)

        unique_chunk_id = f"{unique_id}_{idx}"

        entry = {
            "subject_agent_id": subject_agent_id,
            "document": {
                "file_name": file_name,
                "file_type": file_type,
                "doc_unique_id": unique_id,
                "storage_path": None,  # Will be set below if available
                "preview_available": False,  # Will be set below if available
                "file_size": None,  # Will be set below if available
                "upload_date": datetime.now().isoformat() if file_name else None,
            },
            "chunk": {
                "unique_chunk_id": unique_chunk_id,
                "text": chunk.page_content,
            },
            "embedding": {
                "model": embedding_model_name,
                "vector": emb,
                "size": len(emb),
            },
            "metadata": chunk.metadata,
        }

        # ✅ Attach agent metadata ONLY if provided
        if agent_metadata:
            entry["agent_metadata"] = agent_metadata
        
        # ✅ Attach file storage information if available
        if file_storage_paths and file_name:
            # Find the corresponding storage path for this file
            file_index = list(file_name_to_unique_id.keys()).index(file_name) if file_name in list(file_name_to_unique_id.keys()) else None
            if file_index is not None and file_index < len(file_storage_paths) and file_storage_paths[file_index]:
                storage_path = file_storage_paths[file_index]
                try:
                    # Get file size
                    file_size = os.path.getsize(storage_path) if os.path.exists(storage_path) else None
                    
                    # Update document info with storage details
                    entry["document"].update({
                        "storage_path": storage_path,
                        "preview_available": True,
                        "file_size": file_size
                    })
                except Exception as e:
                    # If we can't get file info, keep defaults
                    pass

        result.append(entry)

    return result, list(unique_ids)