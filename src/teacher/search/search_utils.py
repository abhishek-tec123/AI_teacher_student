import logging

# -----------------------------
# Importing necessary libraries
# -----------------------------
# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
# -----------------------------
# Query extraction helper
# -----------------------------
def extract_core_question(query: str) -> str:
    """
    Extracts the core question from a formatted query string.
    Looks for patterns like "Current Question:" or just uses the query if no pattern found.
    """
    import re
    
    # ---------------------------------------------------------
    # RL/Conversational Extraction (High Priority)
    # If the query is likely a conversational response from an LLM (e.g. RL rewrite)
    # try to extract just the core suggestion inside quotes.
    # ---------------------------------------------------------
    lower_query = query.lower()
    if any(keyword in lower_query for keyword in ["rewrit", "option", "alternative", "suggested"]):
        quoted = re.findall(r'"([^"]*)"', query)
        if quoted:
            # Prefer the longest quoted string if multiple exist (to avoid single words)
            best_chunk = max(quoted, key=len)
            if len(best_chunk) > 10: # Only if it's a meaningful phrase
                return best_chunk[:500]

    # Pattern 0: "Search Query (RL Optimized):\n<query>"
    # This comes from mainAgent.py after RL optimization
    # Using re.DOTALL and a more flexible pattern to catch the content before the next section
    match = re.search(r"Search Query \(RL Optimized\):\s*\n\s*(.+?)(?:\n\n|\n[A-Z][a-z]+:|$)", query, re.DOTALL | re.IGNORECASE)
    if match:
        core = match.group(1).strip()
        if core:
            # print(f"DEBUG: Extracted via Pattern 0: {core[:100]}...")
            return core

    # Pattern 0.1: "Original Student Question:\n<question>"
    match = re.search(r"Original Student Question:\s*\n\s*(.+?)(?:\n\n|\nSearch Query|$)", query, re.DOTALL | re.IGNORECASE)
    if match:
        core = match.group(1).strip()
        if core:
            return core

    # Pattern 1: "Current Question:\n<question>"
    match = re.search(r"Current Question:\s*\n\s*(.+?)(?:\n\n|\nClass:|\nStudent preferences:|$)", query, re.DOTALL | re.IGNORECASE)
    if match:
        core = match.group(1).strip()
        if core:
            return core
    
    # Pattern 2: "Previous conversation:...\n\nCurrent Question:\n<question>"
    match = re.search(r"Current Question:\s*\n\s*(.+?)(?:\n\n|\nClass:|$)", query, re.DOTALL | re.IGNORECASE)
    if match:
        core = match.group(1).strip()
        if core:
            return core
    
    # Pattern 3: If query starts with "Q:" or "Question:"
    match = re.search(r"^(?:Q:|Question:)\s*(.+?)(?:\n|$)", query, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    
    # Fallback: use first line or first 200 chars if query is very long
    lines = query.strip().split('\n')
    if len(lines) > 0:
        # Avoid systemic lines in fallbacks
        systemic_prefixes = (
            'Class:', 'Subject:', 'Student', 'Rules:', 'Previous', 
            'You are an expert', 'IMPORTANT INSTRUCTIONS', 'Target student', 'Use a friendly'
        )
        
        # If first line is very short and looks like a question, use it
        first_line = lines[0].strip()
        if len(first_line) < 200 and '?' in first_line and not first_line.startswith(systemic_prefixes):
            return first_line
            
        # Otherwise, if query is very long (>500 chars), use first meaningful line
        if len(query) > 500:
            for line in lines:  
                line = line.strip()
                if line and 10 < len(line) < 300 and not line.startswith(systemic_prefixes):
                    # Check if it contains labels we might have missed
                    if "Question:" in line or "Query:" in line:
                        continue
                    return line
    
    return query[:500] if len(query) > 500 else query


# -----------------------------
# Vector Search Config
# -----------------------------
VECTOR_INDEX_NAME = "vector_index"
# In the current schema, the embedding vector is stored under `embedding.vector`
VECTOR_PATH = "embedding.vector"
TOP_K = 10
MIN_SCORE_THRESHOLD = 0.3  # Threshold for chunk selection - balanced with content validation
import numpy as np
# -----------------------------
# Embedding helper
# -----------------------------
def embed_query(query: str, embedding_model) -> list:
    """Generate embedding vector for a query using the provided model."""
    return embedding_model.embed_query(query)

# -----------------------------
# Content relevance validation
# -----------------------------
def validate_content_relevance(query: str, chunk_text: str, min_keyword_matches: int = 2) -> bool:
    """
    Validates that retrieved chunk content is actually relevant to the query.
    Prevents false positives by checking keyword presence and semantic relevance.
    Slightly relaxed for very short, profile-style questions so that
    teacher resume/profile chunks can be used when appropriate.
    """
    if not query or not chunk_text:
        return False
    
    # Extract key terms from query (remove common words)
    query_lower = query.lower()
    query_words = [word.strip("?.,!;:()[]{}\"'") for word in query_lower.split() 
                   if len(word) > 2 and word not in ['the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'is', 'are', 'was', 'were', 'what', 'how', 'when', 'where', 'why', 'tell', 'me', 'explain', 'describe']]
    
    chunk_lower = chunk_text.lower()
    
    # Count keyword matches
    keyword_matches = 0
    for word in query_words:
        if word in chunk_lower:
            keyword_matches += 1
    
    # Dynamically relax requirement for very short/profile-style queries
    effective_min_matches = min_keyword_matches
    if len(query_words) <= 3:
        effective_min_matches = 1
    
    # Require minimum keyword matches
    if keyword_matches < effective_min_matches:
        logger.info(f"[ContentValidation] Rejected chunk: only {keyword_matches}/{len(query_words)} keywords matched (required {effective_min_matches})")
        return False
    
    # Additional check: chunk should not be too generic
    generic_phrases = ['this is a', 'this is an', 'it is a', 'it is an', 'here is', 'there is', 'the following', 'as follows']
    for phrase in generic_phrases:
        if chunk_lower.strip().startswith(phrase):
            logger.info(f"[ContentValidation] Rejected chunk: starts with generic phrase '{phrase}'")
            return False
    
    logger.info(f"[ContentValidation] Accepted chunk: {keyword_matches}/{len(query_words)} keywords matched (required {effective_min_matches})")
    return True

# -----------------------------
# Vector search helpers
# -----------------------------
def find_similar_chunks(query_embedding, collection, query="", num_candidates=100, limit=TOP_K, index_name=VECTOR_INDEX_NAME):
    """Cosine similarity search with NO fallback - balanced threshold with content validation."""
    logger.info(f"[CosineSearch] Using in-memory cosine similarity search ONLY")
    
    # ONLY use cosine similarity - NO FALLBACKS ALLOWED
    cosine_results = find_similar_chunks_in_memory(query_embedding, collection, top_k=limit, similarity_threshold=0.3, query_text=query)
    
    if cosine_results:
        logger.info(f"[CosineSearch] Cosine similarity returned {len(cosine_results)} results")
        return cosine_results
    else:
        # ABSOLUTE RULE: No results = NO FALLBACK - return empty list
        logger.error(f"🚫 COSINE SEARCH FAILED: No results found and NO fallbacks allowed. Returning empty list.")
        return []

def find_similar_chunks_in_memory(query_embedding, collection, top_k=TOP_K, similarity_threshold=0.3, query_text=""):
    """In-memory cosine similarity search with balanced threshold and content validation."""
    logger.info(f"[InMemorySearch] Starting in-memory cosine similarity search with threshold {similarity_threshold}")
    # Match the current nested schema used when storing documents
    docs = list(
        collection.find(
            {},
            {
                "embedding.vector": 1,
                "chunk.text": 1,
                "chunk.unique_chunk_id": 1,
                "document.doc_unique_id": 1,
                "subject_agent_id": 1,
                "document_id": 1,
                "agent_metadata": 1,
            },
        )
    )
    
    logger.info(f"[InMemorySearch] Found {len(docs)} documents with embeddings")

    def cosine_similarity(a, b):
        a = np.array(a)
        b = np.array(b)
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

    scored = []
    for doc in docs:
        # Safely extract nested fields according to the current schema
        embedding_container = doc.get("embedding") or {}
        embedding_vector = embedding_container.get("vector")
        if embedding_vector is None:
            # Skip documents without an embedding vector
            continue

        chunk_container = doc.get("chunk") or {}
        document_container = doc.get("document") or {}

        unique_id = document_container.get("doc_unique_id") if document_container else None
        unique_chunk_id = chunk_container.get("unique_chunk_id", "N/A")
        chunk_text = chunk_container.get("text", "")

        similarity_score = cosine_similarity(query_embedding, embedding_vector)
        
        # FIRST check similarity threshold
        if similarity_score >= similarity_threshold:
            # THEN validate content relevance if query text is provided
            if query_text and not validate_content_relevance(query_text, chunk_text):
                logger.info(f"[InMemorySearch] Skipping chunk {unique_chunk_id} due to failed content validation")
                continue
                
            scored.append(
                {
                    # Normalize into the flat structure expected downstream
                    "unique_id": unique_id,
                    "unique_chunk_id": unique_chunk_id,
                    "chunk_text": chunk_text,
                    "score": similarity_score,
                    "subject_agent_id": doc.get("subject_agent_id"),
                    "document_id": doc.get("document_id"),
                    "document": document_container,
                    "chunk": doc.get("chunk"),
                    "agent_metadata": doc.get("agent_metadata"),
                }
            )

    scored.sort(key=lambda x: x["score"], reverse=True)
    top_results = scored[:top_k]
    logger.info(f"[InMemorySearch] Returning {len(top_results)} results above threshold {similarity_threshold}, top score: {top_results[0]['score'] if top_results else 0:.4f}")
    return top_results