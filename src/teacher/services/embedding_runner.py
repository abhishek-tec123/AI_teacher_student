from langchain_huggingface import HuggingFaceEmbeddings
from teacher.embeddings.utility import (
    load_documents,
    split_documents,
    embed_chunks,
    build_embedding_json_for_db
)
import logging
logger = logging.getLogger(__name__)

def get_vectors_and_details(
    file_inputs,
    embedding_model=None,
    original_filenames=None,
    subject_agent_id: str | None = None,
    agent_metadata: dict | None = None,
    file_storage_paths: list | None = None  # New parameter for file storage paths
):
    # 📂 Step 1: Load documents
    logger.info("[*] Loading documents...")
    docs = load_documents(file_inputs)

    # 📏 Step 2: Split documents
    logger.info(f"[*] Splitting {len(docs)} documents into chunks...")
    chunks = split_documents(docs, chunk_size=1000, chunk_overlap=200)

    # 🤖 Step 3: Embed chunks
    if embedding_model is None:
        raise ValueError("No embedding model provided.")
    model_name = getattr(embedding_model, 'model_name', 'provided_model')

    logger.info(f"[*] Embedding {len(chunks)} chunks...")
    embeddings = embed_chunks(chunks, embedding_model)

    # 🧱 Step 4: Build JSON for DB
    embedding_json, doc_ids = build_embedding_json_for_db(
        chunks, embeddings, embedding_model_name=model_name, original_filenames=original_filenames, subject_agent_id=subject_agent_id, file_storage_paths=file_storage_paths
    )

    # ✅ Step 5: Attach subject_agent_id and agent_metadata if provided
    if subject_agent_id:
        for entry in embedding_json:
            entry["subject_agent_id"] = subject_agent_id
    if agent_metadata:
        for entry in embedding_json:
            entry["agent_metadata"] = agent_metadata

    logger.info(f"[✅] Processed {len(embedding_json)} embeddings from {len(doc_ids)} documents.")
    return embedding_json, doc_ids

# # Example usage
# if __name__ == "__main__":
#     import json
#     file_inputs = [
#         "/Users/abhishek/Desktop/tutorAi/data/jemh1dd/jemh1a1.pdf",
#         "/Users/abhishek/Desktop/tutorAi/data/jemh1dd/jemh1a2.pdf"
#     ]
#     vector = get_vectors_and_details(file_inputs)
#     print(json.dumps(vector, indent=3, ensure_ascii=False))  # Just for visualization
