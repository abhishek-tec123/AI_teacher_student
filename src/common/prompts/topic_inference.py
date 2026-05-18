"""
Topic inference from conversation history.

When a student asks something vague ("quiz me", "make notes", "why?"),
this module extracts the most likely current topic from previous turns.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _extract_topic_from_header(text: str) -> Optional[str]:
    """Look for 'Topic: **X**' or 'Topic: X' in response text."""
    if not text:
        return None
    patterns = [
        r"Topic:\s*\*\*(.+?)\*\*",
        r"Topic:\s*(.+?)(?:\n|$)",
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            topic = match.group(1).strip()
            if topic and len(topic) < 100:
                return topic
    return None


def _extract_topic_from_query(query: str) -> Optional[str]:
    """If the query itself is a clear topic request, extract it."""
    if not query:
        return None
    q = query.lower().strip()
    # Skip vague words
    vague_words = {"why", "how", "what", "explain", "more", "again", "yes", "no", "ok", "okay"}
    if q in vague_words or len(q.split()) <= 1 and q in vague_words:
        return None
    return query.strip()


def infer_topic_from_history(
    history: list[dict],
    current_query: str = "",
) -> Optional[str]:
    """
    Returns the most relevant topic from chat history.

    Strategy (fastest to slowest):
    1. Check previous assistant responses for 'Topic: **X**' headers.
    2. Check last 3 student queries for explicit topic words.
    3. Return None if truly empty.
    """
    if not history and not current_query:
        return None

    # 1. Try current query itself (highest priority)
    topic = _extract_topic_from_query(current_query)
    if topic:
        logger.info(f"📍 Topic inferred from current query: '{topic}'")
        return topic

    # 2. Search backwards through history for Topic headers in assistant responses
    for turn in reversed(history):
        if not isinstance(turn, dict):
            continue
        response_data = turn.get("response", "")
        response_text = ""
        if isinstance(response_data, dict):
            response_text = response_data.get("response", "")
        else:
            response_text = str(response_data)

        topic = _extract_topic_from_header(response_text)
        if topic:
            logger.info(f"📍 Topic inferred from header: '{topic}'")
            return topic

    # 3. Check last 3 student queries for explicit topic words
    query_count = 0
    for turn in reversed(history):
        if not isinstance(turn, dict):
            continue
        query_text = turn.get("query", "")
        if query_text:
            topic = _extract_topic_from_query(query_text)
            if topic:
                logger.info(f"📍 Topic inferred from query: '{topic}'")
                return topic
            query_count += 1
            if query_count >= 3:
                break

    logger.info("📍 No topic could be inferred from history")
    return None
