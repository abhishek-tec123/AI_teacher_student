import os, json
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage


def summarize_text_with_groq(
    text: str,
    prompt: str = """Summarize the following text into clear, concise bullet points.
- Focus on key concepts
- Keep it short
- Avoid repetition
- Use simple language
"""
) -> str:
    """
    Summarizes the given text using Groq LLM based on the provided prompt.
    """

    if not text.strip():
        raise ValueError("Input text cannot be empty")

    groq_api_key = settings.groq_api_key
    if not groq_api_key:
        raise ValueError("GROQ_API_KEY is not set in environment variables.")

    # Final input sent to LLM
    full_input = f"""
{prompt}

TEXT:
{text}
""".strip()

    from common.llm.groq_client import sync_invoke_with_limiters

    response = sync_invoke_with_limiters(
        messages=[HumanMessage(content=full_input)],
        model_name=settings.groq_llm,
        api_key=groq_api_key,
        retry_on_429=True,
    )

    summary = getattr(response, "content", str(response)).strip()

    logger.info("Text summarized successfully")

    return summary

def extract_text_from_history(history):
    """
    Converts conversation history into a plain text string for summarization.
    Handles cases where 'response' might be a dict or string.
    """
    texts = []
    for item in history:
        # Extract both query and response for better context
        query = item.get("query", "")
        resp = item.get("response", "")
        
        if isinstance(resp, dict):
            # Convert dict to string safely (e.g., JSON)
            resp = json.dumps(resp)
        elif not isinstance(resp, str):
            resp = str(resp)
            
        # Format as conversation pair
        if query and resp:
            texts.append(f"Q: {query.strip()}\nA: {resp.strip()}")
        elif resp:  # Fallback to just response if no query
            texts.append(resp.strip())
            
    return "\n\n".join(texts)

import json
from typing import Any, Dict



import json
from config.settings import settings
import logging
logger = logging.getLogger(__name__)



def update_session_summary(
    *,
    chat_session_id: str,
    query: str = "",
    response: str = "",
    conversation_batch: list = None,
    student_manager,
    student_id: str = "",
) -> str:
    """
    Updates a detailed session summary in MongoDB under session_summaries array.
    This detailed summary is used by notes and quiz agents.
    """
    if not chat_session_id:
        logger.warning("No chat_session_id provided, skipping session summary update")
        return ""

    # -----------------------------
    # 1️⃣ Resolve student_id if not provided directly
    # -----------------------------
    if not student_id:
        # Try to find student by chat_session_id in chat_sessions metadata
        doc = student_manager.students.find_one(
            {f"chat_sessions.active_chat_sessions.chat_session_id": chat_session_id},
            {"student_id": 1}
        )
        if not doc:
            # Fallback: search in session_summaries array
            doc = student_manager.students.find_one(
                {"session_summaries.chat_session_id": chat_session_id},
                {"student_id": 1}
            )
        if doc:
            student_id = doc.get("student_id")

    if not student_id:
        logger.warning(f"No student found for chat_session_id {chat_session_id}")
        return ""

    # -----------------------------
    # 2️⃣ Get Previous Session Summary
    # -----------------------------
    student_doc = student_manager.students.find_one(
        {"student_id": student_id},
        {"session_summaries": 1}
    )

    previous_summary = ""
    if student_doc:
        summaries = student_doc.get("session_summaries", [])
        for s in summaries:
            if s.get("chat_session_id") == chat_session_id:
                previous_summary = s.get("summary", "")
                break

    # -----------------------------
    # 2️⃣ Prepare Updated Text
    # -----------------------------
    if isinstance(response, dict):
        response_text = json.dumps(response)
    elif not isinstance(response, str):
        response_text = str(response)
    else:
        response_text = response

    if conversation_batch:
        # Format multiple conversation turns
        batch_lines = []
        for i, turn in enumerate(conversation_batch, 1):
            turn_response = turn.get("response", "")
            if isinstance(turn_response, dict):
                turn_response = json.dumps(turn_response)
            elif not isinstance(turn_response, str):
                turn_response = str(turn_response)
            batch_lines.append(f"Turn {i}:\nStudent: {turn.get('query', '')}\nTeacher: {turn_response}")
        conversation_text = "\n\n".join(batch_lines)
    else:
        conversation_text = f"Student: {query}\nTeacher: {response_text}"

    combined_text = f"""
PREVIOUS SESSION SUMMARY:
{previous_summary}

NEW CONVERSATION:
{conversation_text}
""".strip()

    # -----------------------------
    # 3️⃣ Generate Detailed Session Summary
    # -----------------------------
    try:
        prompt = """You are creating a learning session summary for a student.

RULES:
- CRITICAL: Preserve ALL topics from the previous summary. Do NOT drop earlier topics.
- Add new concepts and topics from the new conversation.
- Keep it concise but comprehensive — cover every topic discussed so far.
- Write in plain text (no bullet points, no markdown, no emojis).
- Update the previous summary with the new conversation, integrating it naturally.
- The final summary must include everything from the previous summary plus the new topics."""

        updated_summary = summarize_text_with_groq(
            text=combined_text,
            prompt=prompt
        )

        # -----------------------------
        # 4️⃣ Save to MongoDB (upsert into session_summaries array)
        # -----------------------------
        # Remove old entry if exists
        student_manager.students.update_one(
            {"student_id": student_id},
            {
                "$pull": {
                    "session_summaries": {"chat_session_id": chat_session_id}
                }
            }
        )

        # Add updated entry
        student_manager.students.update_one(
            {"student_id": student_id},
            {
                "$push": {
                    "session_summaries": {
                        "chat_session_id": chat_session_id,
                        "summary": updated_summary,
                        "updated_at": __import__('datetime').datetime.utcnow()
                    }
                }
            }
        )

        logger.info(f"Session summary updated for chat_session {chat_session_id}")
        return updated_summary

    except Exception as e:
        logger.error(f"Session summary update failed: {e}")
        return previous_summary


def get_session_summary(
    *,
    chat_session_id: str,
    student_manager,
    student_id: str = "",
) -> str:
    """
    Retrieves the detailed session summary for a given chat session.
    Returns empty string if not found.
    """
    if not chat_session_id:
        return ""

    try:
        query = {"student_id": student_id} if student_id else {"session_summaries.chat_session_id": chat_session_id}
        projection = {"session_summaries": 1} if student_id else {"session_summaries.$": 1}
        student_doc = student_manager.students.find_one(query, projection)

        if student_doc:
            summaries = student_doc.get("session_summaries", [])
            for s in summaries:
                if s.get("chat_session_id") == chat_session_id:
                    return s.get("summary", "")
    except Exception as e:
        logger.error(f"Failed to get session summary: {e}")

    return ""
