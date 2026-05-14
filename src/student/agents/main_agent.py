import re
import json
from threading import Lock
from student.services.conversation_summarizer import summarize_text_with_groq
from student.agents.study_plan import extract_topic_from_sentence
from student.agents.rl_optimizer import RLOptimizer
from admin.services.global_settings_service import get_global_rag_settings
from common.utils.prompt_templates import get_base_prompt as get_template_base_prompt, build_teacher_prompt
from common.llm.groq_rate_limiter import is_daily_budget_low

# =====================================================
# 🔐 IN-MEMORY PROMPT CACHE (GLOBAL, NO DB)
# =====================================================

_PROMPT_LOCK = Lock()

PROMPT_CACHE = {
    "BASE_TEACHER_PROMPT": get_template_base_prompt()
}

def get_base_prompt() -> str:
    with _PROMPT_LOCK:
        return PROMPT_CACHE["BASE_TEACHER_PROMPT"]


def update_base_prompt(new_prompt: str):
    with _PROMPT_LOCK:
        PROMPT_CACHE["BASE_TEACHER_PROMPT"] = new_prompt.strip()

# =====================================================
# 🚀 RESPONSE CACHE FOR SPEED (5-minute TTL)
# =====================================================
import hashlib
import time

_RESPONSE_CACHE = {}
_RESPONSE_LOCK = Lock()

def _get_response_cache_key(query: str, subject: str, profile_hash: str, language: str = "english") -> str:
    """Generate cache key for response caching."""
    content = f"{query}_{subject}_{profile_hash}_{language}"
    return hashlib.md5(content.encode()).hexdigest()

def _get_profile_hash(profile: dict) -> str:
    """Generate hash of relevant profile fields for caching."""
    relevant_fields = {
        "level": profile.get("level", "basic"),
        "tone": profile.get("tone", "friendly"),
        "response_length": profile.get("response_length", "medium"),
        "include_example": profile.get("include_example", True)
    }
    return hashlib.md5(str(relevant_fields).encode()).hexdigest()[:16]

def get_cached_response(query: str, subject: str, profile: dict, language: str = "english") -> str:
    """Get cached response if available and not expired."""
    profile_hash = _get_profile_hash(profile)
    cache_key = _get_response_cache_key(query, subject, profile_hash, language)
    
    with _RESPONSE_LOCK:
        if cache_key in _RESPONSE_CACHE:
            cached_data, timestamp = _RESPONSE_CACHE[cache_key]
            # Cache for 5 minutes (300 seconds)
            if time.time() - timestamp < 300:
                logger.info(f"📂 Using cached response for query: {query[:30]}... (lang: {language})")
                return cached_data
            else:
                # Remove expired entry
                del _RESPONSE_CACHE[cache_key]
    return None

def cache_response(query: str, subject: str, profile: dict, response: str, language: str = "english"):
    """Cache a response for future use."""
    profile_hash = _get_profile_hash(profile)
    cache_key = _get_response_cache_key(query, subject, profile_hash, language)
    
    with _RESPONSE_LOCK:
        _RESPONSE_CACHE[cache_key] = (response, time.time())
        # Limit cache size to prevent memory issues
        if len(_RESPONSE_CACHE) > 100:
            # Remove oldest entry (simple FIFO)
            oldest_key = min(_RESPONSE_CACHE.keys(), key=lambda k: _RESPONSE_CACHE[k][1])
            del _RESPONSE_CACHE[oldest_key]
        logger.info(f"💾 Cached response for query: {query[:30]}... (lang: {language})")


# =====================================================
# 🎯 INTENT DETECTION
# =====================================================

# Mapping for word-based numbers (e.g., "ten questions")
_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
}


def _extract_num_questions(q: str) -> int:
    """Extract requested question count from a quiz query. Defaults to 3, clamps 1-20."""
    # Numeric patterns: "10 questions", "5 q", "generate 12"
    num_match = re.search(r"(\d+)\s*(?:question|questions|q|mcq|mcqs|problem|problems)", q)
    if num_match:
        return max(1, min(int(num_match.group(1)), 20))

    # Word-based numbers: "ten questions"
    for word, value in _WORD_NUMBERS.items():
        if re.search(rf"\b{word}\b\s*(?:question|questions|q|mcq|mcqs|problem|problems)", q):
            return max(1, min(value, 20))

    return 3  # default when student doesn't specify


def detect_intent_and_topic(query: str, current_subject: str = None) -> dict:
    q = query.lower()

    if any(x in q for x in ["quiz", "test me", "start quiz"]):
        match = re.search(r"(?:on|from|of)\s+(.*)", q)
        return {
            "intent": "QUIZ",
            "topic": match.group(1) if match else None,
            "num_questions": _extract_num_questions(q),
        }

    # Post-quiz explanation intent — requires quiz-related context words
    quiz_context_words = ["question", "q", "answer", "quiz", "test"]
    has_quiz_context = any(w in q for w in quiz_context_words)
    has_explain_words = any(w in q for w in ["why", "explain", "wrong", "mistake", "correct"])
    if has_quiz_context and has_explain_words:
        # Check for "last question" / "final question" before digit regex
        if re.search(r"\b(last|final)\b.*\b(question|q)\b|\b(question|q)\b.*\b(last|final)\b", q):
            return {
                "intent": "QUIZ_EXPLAIN",
                "question_number": -1,  # sentinel for "last question"
            }

        q_num_match = re.search(r"(?:question|q)\s*(\d+)|#(\d+)", q)
        question_number = None
        if q_num_match:
            question_number = int(q_num_match.group(1) or q_num_match.group(2))
        return {
            "intent": "QUIZ_EXPLAIN",
            "question_number": question_number,
        }

    if any(x in q for x in ["study plan", "how to learn", "start learning"]):
        match = re.search(r"(?:learn|study)\s+(.*)", q)
        return {"intent": "STUDY_PLAN", "topic": match.group(1) if match else None}

    if any(word in q for word in ["notes", "make notes", "revision"]):
        # Check if it's a generic request or specific topic request
        if any(word in q for word in ["notes on", "make notes on", "revision on"]):
            # Specific topic request - extract the topic
            return {
                "intent": "NOTES",
                "topic": extract_topic_from_sentence(query)
            }
        else:
            # Generic request - use current subject
            return {
                "intent": "NOTES",
                "topic": current_subject or "General"
            }

    if any(word in q for word in ["summary", "summarize", "give summary", "what i have learned"]):
        # Check if it's a generic summary request or specific topic request
        if any(word in q for word in ["summary of", "give summary of"]) or re.search(r"summarize\s+\w+", q):
            # Specific topic request - extract topic
            return {
                "intent": "SUMMARY",
                "topic": extract_topic_from_sentence(query)
            }
        else:
            # Generic request - use current subject
            return {
                "intent": "SUMMARY",
                "topic": current_subject or "General"
            }

    return {"intent": "CHAT", "query": q, "topic": None}


# =====================================================
# 🔍 DEEP-DIVE INTENT DETECTION
# =====================================================

_DEEP_DIVE_KEYWORDS = [
    "explain more", "go deeper", "tell me more", "elaborate",
    "expand on", "in more detail", "can you clarify", "i don't understand",
    "make it clearer", "why is that", "how does that work", "more detail",
    "deeper explanation", "can you break it down further", "in depth",
    "more about", "explain further", "clarify", "detailed explanation",
    "step by step", "more depth", "simplify", "i am confused",
    "don't understand", "not clear", "can you explain again"
]

_DEEP_DIVE_SHORT_FOLLOWUPS = {
    "more", "deeper", "clarify", "again", "detail", "explain",
    "how", "why", "what", "elaborate", "expand", "further",
    "simplify", "confused", "unclear", "examples", "example"
}


def _extract_sub_topic(query: str) -> str or None:
    """Extract a specific sub-topic from follow-up phrases like 'more about X'."""
    q = query.lower().strip()
    patterns = [
        r"more about\s+(.+)",
        r"go deeper on\s+(.+)",
        r"tell me more about\s+(.+)",
        r"elaborate on\s+(.+)",
        r"focus on\s+(.+)",
        r"what about\s+(.+)",
        r"explain\s+(.+)\s+in detail",
        r"explain\s+(.+)\s+more",
        r"explain more about\s+(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            topic = match.group(1).strip().rstrip("?.")
            # Validate: must be at least 1 word and at most 6 words
            words = topic.split()
            if 1 <= len(words) <= 6:
                return topic
    return None


def detect_deep_dive_intent(query: str, last_query: str = None, last_response: str = None) -> dict:
    """
    Detect if the student wants a deeper explanation about the previous response.

    Returns:
        {
            "is_deep_dive": bool,
            "deep_dive_topic": str or None,
        }
    """
    q = query.lower().strip()

    # Direct keyword match
    has_keyword = any(kw in q for kw in _DEEP_DIVE_KEYWORDS)

    # Short follow-up (single word or very short phrase) when there is a last topic
    is_short_followup = (
        last_query is not None
        and len(q.split()) <= 3
        and any(word in q for word in _DEEP_DIVE_SHORT_FOLLOWUPS)
    )

    # Vague follow-up referencing previous topic (pronouns)
    vague_pronouns = ["it", "this", "that", "the above", "the topic"]
    is_vague_reference = (
        last_query is not None
        and any(pronoun in q for pronoun in vague_pronouns)
        and len(q.split()) <= 6
    )

    is_deep_dive = has_keyword or is_short_followup or is_vague_reference

    # Infer deep-dive topic
    deep_dive_topic = None
    if is_deep_dive:
        # Try to extract a specific sub-topic from the query first
        extracted_topic = _extract_sub_topic(query)
        if extracted_topic:
            deep_dive_topic = extracted_topic
        elif last_query:
            deep_dive_topic = last_query.strip()
        else:
            deep_dive_topic = query.strip()

    return {
        "is_deep_dive": is_deep_dive,
        "deep_dive_topic": deep_dive_topic,
    }


# =====================================================
# 🛡 SAFE JSON LOADER
# =====================================================

def safe_json_load(raw: str) -> dict:
    match = re.search(r"\{[\s\S]*?\}", raw)
    if not match:
        return {}

    json_str = match.group(0)
    json_str = json_str.replace("'", '"')
    json_str = re.sub(r",\s*}", "}", json_str)

    try:
        return json.loads(json_str)
    except Exception:
        return {}


# =====================================================
# 🧠 CONFUSION DIAGNOSIS
# =====================================================

def diagnose_student_confusion(question: str, subject: str, class_name: str) -> dict:
    prompt = f"""
Return ONLY valid JSON.

Class: {class_name}
Subject: {subject}
Question: "{question}"

Rules:
- Use NO_CONFUSION when the question is neutral or correct
- Use CONCEPT_GAP / FORMULA_CONFUSION / PROCEDURAL_ERROR only if misconception is explicit
- If unsure, choose NO_CONFUSION

JSON:
{{
  "confusion_type": "NO_CONFUSION | CONCEPT_GAP | FORMULA_CONFUSION | PROCEDURAL_ERROR",
  "reason": "short reason",
  "teaching_strategy": "how to explain"
}}
"""

    raw = summarize_text_with_groq(text=question, prompt=prompt)

    try:
        return json.loads(raw)
    except Exception:
        return safe_json_load(raw) or {
            "confusion_type": "NO_CONFUSION",
            "reason": "",
            "teaching_strategy": ""
        }


# =====================================================
# � AGENT METADATA HELPER
# =====================================================

def get_agent_metadata(subject_agent_id: str) -> dict:
    """
    Get agent metadata from database using subject_agent_id
    """
    try:
        from teacher.repositories.get_agent_data import get_agent_data
        agent_data = get_agent_data(subject_agent_id)
        return agent_data.get("agent_metadata", {})
    except Exception as e:
        logger.info(f"Error getting agent metadata: {e}")
        return {}

# =====================================================
# �‍🏫 TEACHER CHAT (MAIN ENTRY)
# =====================================================

def diagnosis_chat(
    student_agent,
    query,
    class_name,
    subject,
    student_profile,
    context=None,
    subject_agent_id=None,
    language=None,
    is_deep_dive=False,
    deep_dive_topic=None,
    chunk_context=None,
    deep_dive_count=0,
):
    """
    Preference-aware, session-aware teacher response

    Args:
        language: Response language ('english', 'hindi', 'hinglish' or None for auto-detect)
        is_deep_dive: If True, bypass retrieval and reuse stored chunk_context
        deep_dive_topic: Topic string for deep-dive prompt instructions
        chunk_context: Pre-built chunk context string from previous turn (for deep-dive)
        deep_dive_count: Number of consecutive deep-dives so far (0 = first/normal)
    """
    # Use provided language or default to english
    detected_language = language or "english"
    logger.info(f"🌐 Using language: {detected_language}")

    # Store detected language in profile for continuity
    student_profile["last_detected_language"] = detected_language

    # -----------------------------
    # 🚀 RESPONSE CACHE: Check for cached response first (skip for deep-dive)
    # -----------------------------
    if not is_deep_dive:
        cached_response = get_cached_response(query, subject, student_profile, language=detected_language)
        if cached_response:
            return {
                "response": cached_response,
                "confusion_type": "NO_CONFUSION",  # Cached responses assumed non-confused
                "rl_metadata": {
                    "trajectory": ["cached_response"],
                    "optimized_query": query,
                    "top_k": 5,
                    "cache_hit": True
                },
                "detected_language": detected_language,  # Include detected language
                "debug_info": {
                    "cache_hit": True,
                    "response_time": "cached",
                    "language": detected_language
                }
            }

    # -----------------------------
    # Get global RAG settings for debug info
    # -----------------------------
    global_rag_settings = get_global_rag_settings()

    # -----------------------------
    # Confusion diagnosis disabled to save LLM tokens
    # Will be re-enabled with a more efficient approach in the future
    # -----------------------------
    confusion_type = "NO_CONFUSION"
    diagnosis = {"confusion_type": "NO_CONFUSION", "reason": "Disabled for token efficiency", "teaching_strategy": ""}

    # -----------------------------
    # Get agent metadata for introduction
    # -----------------------------
    agent_metadata = None
    if subject_agent_id:
        agent_metadata = get_agent_metadata(subject_agent_id)

    student_profile.setdefault("confusion_counter", {})
    student_profile.setdefault("common_mistakes", [])

    if confusion_type != "NO_CONFUSION":
        student_profile["confusion_counter"][confusion_type] = (
            student_profile["confusion_counter"].get(confusion_type, 0) + 1
        )
        if confusion_type not in student_profile["common_mistakes"]:
            student_profile["common_mistakes"].append(confusion_type)

    # -----------------------------
    # Build session context
    # -----------------------------
    session_history_text = ""
    personal_info_summary = ""

    if context:
        # Limit to last 5 turns for the teacher's final prompt
        limited_context = context[-5:]

        # Extract personal information for easy access
        personal_info = []
        for turn in limited_context:
            if isinstance(turn, dict):
                query_text = turn.get('query', '').lower()
                # Handle both string responses and dict responses
                response_data = turn.get('response', '')
                if isinstance(response_data, dict):
                    response = response_data.get('response', '')
                else:
                    response = response_data

                # Look for personal information sharing
                if any(phrase in query_text for phrase in ['my name is', 'i am', 'i\'m', 'my favorite', 'i like', 'i dislike']):
                    personal_info.append(f"Student shared: {turn.get('query','')}")

                session_history_text += (
                    f"Previous Q: {turn.get('query','')}\n"
                    f"Previous A: {response}\n"
                )
            elif isinstance(turn, str):
                session_history_text += f"{turn}\n"

        # Add personal info summary at the beginning for emphasis
        if personal_info:
            personal_info_summary = "\nIMPORTANT PERSONAL INFORMATION SHARED BY STUDENT:\n" + "\n".join(personal_info) + "\n\n"

    # -----------------------------
    # Build final prompt context
    # -----------------------------
    full_context = personal_info_summary + session_history_text

    # -----------------------------
    # RL-based Query Optimization (skip for deep-dive, short queries, or low budget)
    # -----------------------------
    query_word_count = len(query.split())
    budget_low = is_daily_budget_low(threshold=10000)
    skip_rl = is_deep_dive or budget_low or query_word_count < 5

    if skip_rl:
        top_k = 5
        skip_reason = "deep_dive" if is_deep_dive else ("low_budget" if budget_low else "short_query")
        state = {"current_query": query, "previous_actions": [f"skip_rl:{skip_reason}"]}
        if budget_low:
            logger.info("⏭️ RL rewrite skipped: daily token budget low")
        elif query_word_count < 5:
            logger.info("⏭️ RL rewrite skipped: query too short")
    else:
        optimizer = RLOptimizer()
        state = optimizer.define_state(query=query, context_chunks=[], student_profile=student_profile)
        top_k = 5

        # Small RL loop to refine query/retrieval (max 2 steps for latency)
        for _ in range(2):
            action = optimizer.select_action(state)
            state["previous_actions"].append(action)

            if action == "rewrite_query":
                # Only pass the last 2 turns of context for rewriting to avoid "sticky topics"
                recent_context = ""
                if context:
                    last_turns = context[-2:]
                    for turn in last_turns:
                        if isinstance(turn, dict):
                            recent_context += f"Q: {turn.get('query','')}\nA: {turn.get('response','')}\n"
                        elif isinstance(turn, str):
                            recent_context += f"{turn}\n"

                state["current_query"] = optimizer.rewrite_query(state["current_query"], context_text=recent_context)
            elif action == "expand_context":
                top_k = min(top_k + 2, 5)
            elif action == "generate_response":
                break

    # Final prompt still uses session context and diagnosis
    full_prompt = build_teacher_prompt(
        student_profile=student_profile,
        class_name=class_name,
        subject=subject,
        confusion_type=confusion_type,
        session_context=full_context,
        current_query=query,
        agent_metadata=agent_metadata,
        base_prompt=get_base_prompt(),  # Use the cached base prompt
        language=detected_language,  # Pass detected language
        is_deep_dive=is_deep_dive,
        deep_dive_topic=deep_dive_topic,
        deep_dive_count=deep_dive_count,
    )

    full_prompt += f"\nOriginal Student Question:\n{query}\n"
    if not is_deep_dive:
        full_prompt += f"\nSearch Query (RL Optimized):\n{state['current_query']}\n"

    # -----------------------------
    # Ask LLM (with RL-optimized parameters) or deep-dive direct call
    # -----------------------------
    if is_deep_dive and chunk_context:
        logger.info("🔍 DEEP-DIVE MODE: Bypassing retriever, reusing stored chunk context")
        result = student_agent.ask(
            query=full_prompt,
            class_name=class_name,
            subject=subject,
            student_profile=student_profile,
            subject_agent_id=subject_agent_id,
            top_k=top_k,
            is_deep_dive=True,
            chunk_context=chunk_context,
        )
    else:
        result = student_agent.ask(
            query=full_prompt,
            class_name=class_name,
            subject=subject,
            student_profile=student_profile,
            subject_agent_id=subject_agent_id,  # Pass for shared knowledge
            top_k=top_k
        )

    if isinstance(result, dict):
        response = result.get("response", "")
        quality_scores = result.get("quality_scores", {})
        chunk_context = result.get("chunk_context", chunk_context)
    else:
        response = result or ""
        quality_scores = {}

    # -----------------------------
    # Attach RL Metadata
    # -----------------------------
    rl_metadata = {
        "trajectory": state["previous_actions"],
        "optimized_query": state["current_query"],
        "top_k": top_k
    }

    # -----------------------------
    # 🚀 CACHE RESPONSE for future speed (skip for deep-dive)
    # -----------------------------
    if not is_deep_dive:
        cache_response(query, subject, student_profile, response, language=detected_language)

    return {
        "response": response,
        "confusion_type": confusion_type,
        "profile": student_profile,
        "quality_scores": quality_scores,
        "rl_metadata": rl_metadata,
        "detected_language": detected_language,  # Include detected language in response
        "chunk_context": chunk_context,
        "deep_dive_count": deep_dive_count,
        "debug_info": {
            "actual_prompt": full_prompt,
            "prompt_length": len(full_prompt),
            "rag_enabled": global_rag_settings.get("enabled", False),
            "rag_content_length": len(global_rag_settings.get("content", "")) if global_rag_settings.get("enabled", False) else 0,
            "base_prompt": full_prompt.replace(f"\n\n--- GLOBAL RAG CONTEXT ---\n{global_rag_settings.get('content', '')}\n--- END GLOBAL RAG CONTEXT ---\n", "") if global_rag_settings.get("enabled", False) else full_prompt
        }
    }

def set_base_prompt(new_prompt: str):
    with _PROMPT_LOCK:
        PROMPT_CACHE["BASE_TEACHER_PROMPT"] = new_prompt.strip()
# =====================================================
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from config.settings import settings
import logging
logger = logging.getLogger(__name__)

class UpdatePromptRequest(BaseModel):
    prompt: str

def update_base_prompt_handler(payload: UpdatePromptRequest):
    """
    Admin-only route logic.
    """

    if not payload.prompt or len(payload.prompt.strip()) < 20:
        return JSONResponse(
            status_code=400,
            content={"error": "Prompt is too short or empty"}
        )

    # ✅ CALL REAL SETTER
    set_base_prompt(payload.prompt)

    return {
        "status": "success",
        "message": "Base prompt updated successfully",
        "active_prompt_preview": get_base_prompt()[:300]
    }
