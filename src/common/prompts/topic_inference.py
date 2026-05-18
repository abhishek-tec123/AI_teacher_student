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
    
    # Clean up punctuation and common stop words to analyze core content
    clean_q = re.sub(r"[^\w\s]", "", q).strip()
    if not clean_q:
        return None
    
    # Action words/patterns that indicate a formatting/action request rather than a topic
    action_patterns = [
        r"^(?:give\s+me|show|make|create|generate|write|provide)?\s*(?:\d+|five|three|ten|one|two|four|six|seven|eight|nine)?\s*(?:practice\s+|long\s+|short\s+|open\s*ended\s+)?(?:questions?|problems?|tasks?|exercises?|sums?|notes?|quizzes?|quiz|test|mcqs?)\b",
        r"\b(?:practice\s+|long\s+|short\s+|open\s*ended\s+)?(?:questions?|problems?|tasks?|exercises?|sums?|notes?|quizzes?|quiz|test|mcqs?)\s*(?:on|about|for)?$",
    ]
    
    # If the entire query is just an action request, check for "on/about/for <topic>" clause
    is_action_only = False
    for pattern in action_patterns:
        if re.match(pattern, clean_q):
            is_action_only = True
            break
            
    if is_action_only or clean_q in {"why", "how", "what", "explain", "more", "again", "yes", "no", "ok", "okay"}:
        # Check if there is an "on/about/for/of <topic>" part at the end
        on_match = re.search(r"\b(?:on|about|for|of)\s+(.+)$", q)
        if on_match:
            topic_candidate = on_match.group(1).strip()
            # If topic candidate is just vague or action, return None
            if topic_candidate not in {"questions", "problems", "notes", "quiz", "mcqs", "sums"}:
                return topic_candidate
        return None
            
    # Also ignore very short vague queries
    words = clean_q.split()
    if len(words) <= 1 and words[0] in {"why", "how", "what", "explain", "more", "again", "yes", "no", "ok", "okay"}:
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
