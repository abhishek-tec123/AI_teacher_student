import logging
"""
Topic Extraction Utils - Utility functions for LLM calls and topic processing
"""

import os
import json
import re
from typing import Dict, List, Optional, Any

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from config.settings import settings
logger = logging.getLogger(__name__)
# -----------------------------
# Global cache
# -----------------------------
_model_cache = None

# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)



# -----------------------------
# Initialize utils
# -----------------------------
def initialize_utils(model_cache=None):
    """Initialize utils with centralized model cache."""
    global _model_cache
    _model_cache = model_cache


# -----------------------------
# Get embedding model
# -----------------------------
def get_embedding_model(model_name: str) -> Optional[Any]:
    """
    Get embedding model ONLY from centralized model cache.
    No manual loading allowed.
    """

    if _model_cache is None:
        logger.error("❌ Model cache not initialized")
        return None

    try:
        logger.info(f"📦 Loading embedding model from cache: {model_name}")
        return _model_cache.get_embedding_model(model_name)

    except Exception as e:
        logger.error(f"❌ Failed to load embedding model from cache: {e}")
        return None


# -----------------------------
# LLM Call
# -----------------------------
def call_llm_direct(prompt: str, content: str = "") -> str:
    """Call Groq LLM directly."""

    try:
        groq_api_key = settings.groq_api_key

        if not groq_api_key:
            logger.error("❌ GROQ_API_KEY not set")
            return ""

        if content:
            full_input = f"{prompt}\n\nCONTENT:\n{content}"
        else:
            full_input = prompt

        from common.llm.groq_client import sync_invoke_with_limiters
        response = sync_invoke_with_limiters(
            messages=[HumanMessage(content=full_input)],
            model_name=settings.groq_llm,
            api_key=groq_api_key,
            retry_on_429=True,
        )

        result = getattr(response, "content", str(response)).strip()

        logger.info("✅ LLM call successful")

        return result

    except Exception as e:
        logger.error(f"❌ LLM call failed: {e}")
        return ""


# -----------------------------
# Parse JSON from LLM
# -----------------------------
def parse_json_from_llm_response(response_text: str) -> Dict[str, Any]:

    if not response_text:
        return {}

    try:
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)

        if not json_match:
            logger.warning("⚠️ No JSON found in response")
            return {}

        json_str = json_match.group(0)

        parsed = json.loads(json_str)

        logger.info("✅ JSON parsed successfully")

        return parsed

    except Exception as e:
        logger.error(f"❌ JSON parsing failed: {e}")
        return {}


# -----------------------------
# Topic similarity
# -----------------------------
def are_topics_similar(topic1: str, topic2: str, threshold: float = 0.8) -> bool:

    topic1 = topic1.lower().strip()
    topic2 = topic2.lower().strip()

    if topic1 == topic2:
        return True

    if topic1 in topic2 or topic2 in topic1:
        return True

    words1 = set(topic1.split())
    words2 = set(topic2.split())

    if not words1 or not words2:
        return False

    similarity = len(words1 & words2) / len(words1 | words2)

    return similarity >= threshold


# -----------------------------
# MongoDB chunk retrieval
# -----------------------------
def get_agent_chunks_from_mongodb(
    subject_agent_id: str,
    db_name: str,
    collection_name: str
) -> List[Dict[str, Any]]:

    from pymongo import MongoClient

    try:
        mongodb_uri = settings.mongodb_uri

        if not mongodb_uri:
            raise ValueError("MONGODB_URI not set")

        client = MongoClient(mongodb_uri)

        db = client[db_name]
        collection = db[collection_name]

        query = {"subject_agent_id": subject_agent_id}

        projection = {
            "chunk.text": 1,
            "chunk.unique_chunk_id": 1,
            "document.file_name": 1,
            "document.page_number": 1
        }

        chunks = list(collection.find(query, projection))

        processed_chunks = []

        for chunk in chunks:

            chunk_data = chunk.get("chunk", {})
            doc_data = chunk.get("document", {})

            processed_chunks.append({
                "text": chunk_data.get("text", ""),
                "unique_chunk_id": chunk_data.get("unique_chunk_id", ""),
                "source_file": doc_data.get("file_name", ""),
                "page_number": doc_data.get("page_number", 0)
            })

        client.close()

        logger.info(f"📚 Retrieved {len(processed_chunks)} chunks")

        return processed_chunks

    except Exception as e:
        logger.error(f"❌ MongoDB retrieval failed: {e}")
        raise


# -----------------------------
# Prompt creation
# -----------------------------
def create_topic_extraction_prompt(include_subtopics: bool = True) -> str:
    """Create the prompt for topic extraction."""
    return f"""
Analyze the following educational content and extract the main topics and subtopics.

Instructions:
1. Identify the main topics covered in this content
2. For each main topic, identify relevant subtopics if requested
3. **IMPORTANT**: Extract 1-2 line descriptions directly from the content for each topic and subtopic
   - Find actual sentences or phrases in the text that describe the topic/subtopic
   - Do NOT generate descriptions from general knowledge - they must come from the content
   - Keep descriptions concise (1-2 lines maximum)
4. Return the results in a structured JSON format
5. Focus on academic/educational topics that would be part of a syllabus
6. Assign confidence scores (0.0-1.0) based on how clearly the topic is covered

Format your response as valid JSON:
{{
  "topics": [
    {{
      "topic": "Main Topic Name",
      "description": "1-2 line description extracted directly from the content text",
      "confidence": 0.95,
      "subtopics": [
        {{
          "subtopic": "Subtopic Name", 
          "description": "1-2 line description extracted directly from the content",
          "confidence": 0.88
        }}
      ] if include_subtopics else []
    }}
  ]
}}

If no clear topics are found, return: {{"topics": []}}
"""

# -----------------------------
# Topic organization
# -----------------------------
def organize_topics_hierarchy(
    extracted_topics: List[Dict[str, Any]],
    max_topics: int
) -> List[Dict[str, Any]]:

    if not extracted_topics:
        return []

    topic_groups = {}

    for topic_data in extracted_topics:

        topic_name = topic_data.get("topic", "").strip()

        if not topic_name:
            continue

        confidence = topic_data.get("confidence", 0)
        description = topic_data.get("description", "")
        subtopics = topic_data.get("subtopics", [])

        found = False

        for existing_topic in topic_groups:

            if are_topics_similar(topic_name, existing_topic):

                existing = topic_groups[existing_topic]

                existing["confidence"] = max(existing["confidence"], confidence)
                
                # Merge descriptions - keep the most detailed one from content
                if description and (not existing.get("description") or len(description) > len(existing.get("description", ""))):
                    existing["description"] = description

                for sub in subtopics:
                    sub_name = sub.get("subtopic", "").strip()
                    if sub_name:
                        # Check if subtopic already exists
                        existing_sub_found = False
                        for existing_sub in existing["subtopics"]:
                            if are_topics_similar(sub_name, existing_sub.get("subtopic", "")):
                                # Merge subtopic descriptions
                                sub_desc = sub.get("description", "")
                                if sub_desc and (not existing_sub.get("description") or len(sub_desc) > len(existing_sub.get("description", ""))):
                                    existing_sub["description"] = sub_desc
                                existing_sub["confidence"] = max(existing_sub["confidence"], sub.get("confidence", 0))
                                existing_sub_found = True
                                break
                        
                        if not existing_sub_found:
                            existing["subtopics"].append(sub)

                found = True
                break

        if not found:

            topic_groups[topic_name] = {
                "topic": topic_name,
                "description": description,
                "confidence": confidence,
                "subtopics": subtopics
            }

    topics = list(topic_groups.values())

    topics.sort(key=lambda x: x["confidence"], reverse=True)

    return topics[:max_topics]