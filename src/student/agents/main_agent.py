import re
import json
import os
from threading import Lock
from student.services.conversation_summarizer import summarize_text_with_groq
from student.agents.study_plan import extract_topic_from_sentence
from student.agents.rl_optimizer import RLOptimizer
from admin.services.global_settings_service import get_global_rag_settings
from common.utils.prompt_templates import get_base_prompt as get_template_base_prompt, build_teacher_prompt
from common.prompts.topic_inference import infer_topic_from_history
from common.llm.groq_rate_limiter import is_daily_budget_low
from student.utils.chat_utils import is_greeting, is_general_chat, is_conversational_followup

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

# Mapping for ordinal words (e.g., "second question", "2nd question")
_ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5,
    "6th": 6, "7th": 7, "8th": 8, "9th": 9, "10th": 10,
}


def _extract_question_number_from_ordinals(q: str) -> int | None:
    """Extract question number from ordinal words like 'second question' or '2nd q'."""
    # Pattern: ordinal near question/q (e.g., "second question", "the 2nd q")
    for ordinal, num in _ORDINAL_WORDS.items():
        pattern = rf"\b{re.escape(ordinal)}\b.*\b(question|q)\b|\b(question|q)\b.*\b{re.escape(ordinal)}\b"
        if re.search(pattern, q, re.IGNORECASE):
            return num

    # Pattern: "question number two", "q number 2nd"
    number_word_match = re.search(
        rf"(?:question|q)\s+(?:number|no|#)?\s*(\d+|{'|'.join(_ORDINAL_WORDS.keys())})",
        q, re.IGNORECASE
    )
    if number_word_match:
        matched = number_word_match.group(1).lower()
        if matched in _ORDINAL_WORDS:
            return _ORDINAL_WORDS[matched]
        if matched.isdigit():
            return int(matched)

    return None


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

        # Try digit regex first (e.g., "question 2", "#3")
        q_num_match = re.search(r"(?:question|q)\s*(\d+)|#(\d+)", q)
        question_number = None
        if q_num_match:
            question_number = int(q_num_match.group(1) or q_num_match.group(2))
        else:
            # Fallback: try ordinal words (e.g., "second question", "2nd q")
            question_number = _extract_question_number_from_ordinals(q)

        return {
            "intent": "QUIZ_EXPLAIN",
            "question_number": question_number,
        }

    if any(x in q for x in ["study plan", "how to learn", "start learning", "make plan", "create plan", "plan on", "plan for", "plan about"]):
        # Try multiple patterns for topic extraction
        match = re.search(r"(?:learn|study|plan)\s+(?:on|for|about)?\s*(.*)", q)
        if not match:
            match = re.search(r"(?:plan|learn|study)\s+(.*)", q)
        return {"intent": "STUDY_PLAN", "topic": match.group(1).strip() if match else None}

    if any(word in q for word in ["notes", "make notes", "revision"]):
        # Check if it's a generic request or specific topic request
        if any(word in q for word in ["notes on", "make notes on", "revision on"]):
            # Specific topic request - extract the topic
            return {
                "intent": "NOTES",
                "topic": extract_topic_from_sentence(query)
            }
        else:
            # Generic request - let _resolve_topic() infer from session history
            return {
                "intent": "NOTES",
                "topic": None
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
            # Generic request - let _resolve_topic() infer from session history
            return {
                "intent": "SUMMARY",
                "topic": None
            }

    # PRACTICE / PROBLEMS check (simple rule before LLM fallback)
    practice_keywords = ["problem", "exercise", "practice", "solve", "test me", "task", "assignment", "activity", "sum", "example", "question"]
    if any(word in q for word in practice_keywords):
        return {
            "intent": "CHAT", # Handled by the dynamic prompt rule we added
            "topic": extract_topic_from_sentence(query),
            "is_practice": True
        }

    # If no rules match, use LLM-based classification for "anything else"
    llm_intent = classify_intent_with_prompt(query, current_subject)
    if llm_intent.get("confidence", 0) > 0.6:
        return llm_intent

    return {"intent": "CHAT", "query": q, "topic": None}

def classify_intent_with_prompt(query: str, current_subject: str = None) -> dict:
    """
    LLM-based intent detection for complex queries that don't match rules.
    This handles the "anything" a student can ask.
    """
    from student.services.generate_response import generate_response_with_groq
    
    classifier_prompt = f"""
Analyze the student query and classify the primary intent and topic.
Subject Context: {current_subject or "Academic Studies"}

Intents:
- QUIZ: Start a formal multiple-choice test.
- STUDY_PLAN: Create a roadmap or learning schedule.
- NOTES: Generate structured study notes.
- SUMMARY: Summarize recent conversation or a topic.
- CHAT: Ask a question, request practice problems, deep-dive into a concept, or general conversation.

Return ONLY a JSON object:
{{
  "intent": "QUIZ|STUDY_PLAN|NOTES|SUMMARY|CHAT",
  "topic": "extracted main topic or null",
  "confidence": 0.0-1.0
}}
"""
    try:
        response = generate_response_with_groq(
            query=f"Classify this query: '{query}'",
            system_prompt=classifier_prompt,
            model_name="llama-3.1-8b-instant" # Fast model for classification
        )
        # Parse JSON from response
        import json
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            result = json.loads(match.group(0))
            return result
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Intent classification failed: {e}")
    
    return {"intent": "CHAT", "topic": None}


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

_STRONG_FOLLOWUP_WORDS = {
    "more", "deeper", "clarify", "again", "detail",
    "elaborate", "expand", "further", "simplify", "confused",
    "unclear", "example", "examples"
}

_WEAK_FOLLOWUP_WORDS = {"how", "why", "what", "where", "who"}


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
    q_words = [w.strip("?.,!") for w in q.split()]
    q_words = [w for w in q_words if w]
    
    is_short_followup = False
    if last_query is not None:
        if len(q_words) <= 4 and any(w in q_words for w in _STRONG_FOLLOWUP_WORDS):
            is_short_followup = True
        elif len(q_words) <= 2 and any(w in q_words for w in _WEAK_FOLLOWUP_WORDS):
            is_short_followup = True
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


def suggest_topic_from_agent_knowledge(
    class_name: str,
    subject: str,
    subject_agent_id: str | None,
) -> str | None:
    """
    Suggest a topic from agent knowledge when no chat history exists.
    Tries agent metadata first, then falls back to a sample chunk.
    """
    # 1. Try agent metadata
    try:
        metadata = get_agent_metadata(subject_agent_id) if subject_agent_id else {}
        for key in ("description", "subject", "agent_name"):
            val = metadata.get(key, "").strip()
            if val and len(val) > 2:
                return val
    except Exception:
        pass

    # 2. Try fetching a sample chunk from the collection
    try:
        from pymongo import MongoClient
        from config.settings import settings

        client = MongoClient(settings.mongodb_uri)
        db = client[class_name]
        collection = db[subject]
        sample = collection.find_one(
            {"subject_agent_id": subject_agent_id} if subject_agent_id else {},
            {"chunk.text": 1, "document.file_name": 1}
        )
        client.close()

        if sample:
            text = sample.get("chunk", {}).get("text", "")
            if text:
                # Extract first sentence as topic hint
                first_sentence = text.split(".")[0].strip()
                if len(first_sentence) > 3:
                    return first_sentence[:120]
            file_name = sample.get("document", {}).get("file_name", "")
            if file_name:
                name = os.path.splitext(file_name)[0].replace("_", " ").replace("-", " ").strip()
                if name:
                    return name
    except Exception:
        pass

    return None


# Cache for LLM-extracted topics to avoid repeated calls
_TOPIC_CACHE = {}
_TOPIC_CACHE_TTL = 300  # 5 minutes
_TOPIC_CACHE_LOCK = Lock()


def _get_topic_cache_key(subject_agent_id: str, max_topics: int) -> str:
    import hashlib
    return hashlib.md5(f"{subject_agent_id}_{max_topics}".encode()).hexdigest()


def _get_cached_topics(cache_key: str):
    import time
    with _TOPIC_CACHE_LOCK:
        if cache_key in _TOPIC_CACHE:
            result, timestamp = _TOPIC_CACHE[cache_key]
            if time.time() - timestamp < _TOPIC_CACHE_TTL:
                logger.info(f"🎯 Using cached topics for key: {cache_key[:8]}...")
                return result
            del _TOPIC_CACHE[cache_key]
    return None


def _cache_topics(cache_key: str, topics: list):
    import time
    with _TOPIC_CACHE_LOCK:
        _TOPIC_CACHE[cache_key] = (topics, time.time())
        if len(_TOPIC_CACHE) > 50:
            oldest = min(_TOPIC_CACHE.keys(), key=lambda k: _TOPIC_CACHE[k][1])
            del _TOPIC_CACHE[oldest]


def get_available_topics_from_agent(
    class_name: str,
    subject: str,
    subject_agent_id: str | None,
    max_topics: int = 10,
) -> list[str]:
    """
    Extract clean topic names from the agent's knowledge base.
    Samples random chunks and uses LLM to extract meaningful topics.
    """
    import random

    if not subject_agent_id:
        return [subject] if subject else []

    # Check cache first (we cache a larger pool of topics, e.g., 20)
    cache_key = _get_topic_cache_key(subject_agent_id, 20)
    cached_pool = _get_cached_topics(cache_key)
    
    if cached_pool and len(cached_pool) >= max_topics:
        # Return a random sample from the cached pool to ensure variety
        return random.sample(cached_pool, min(max_topics, len(cached_pool)))
    elif cached_pool:
        return cached_pool

    sampled_docs = []
    try:
        from pymongo import MongoClient
        from config.settings import settings

        client = MongoClient(settings.mongodb_uri)
        db = client[class_name]
        collection = db[subject]

        filter_query = {"subject_agent_id": subject_agent_id}

        # Sample random chunks
        pipeline = [
            {"$match": filter_query},
            {"$sample": {"size": 20}},
            {"$project": {"chunk.text": 1}}
        ]
        sampled_docs = list(collection.aggregate(pipeline))
        client.close()
    except Exception as e:
        logger.warning(f"Failed to sample chunks for topic extraction: {e}")

    # Extract raw texts from sampled chunks
    raw_texts = []
    for doc in sampled_docs:
        text = doc.get("chunk", {}).get("text", "")
        if text and len(text.strip()) > 20:
            raw_texts.append(text.strip()[:800])  # limit each chunk

    topics = []

    if raw_texts:
        # Use LLM to extract clean topics from raw chunk texts (request up to 20)
        combined_text = "\n---\n".join(raw_texts[:20])
        prompt = f"""Extract 20 clean, meaningful topic names from the following text excerpts.
Each topic should be 2-5 words, descriptive, and suitable for a student syllabus.
Return ONLY a JSON array of strings. No markdown, no explanation.

Text excerpts:
{combined_text[:6000]}

JSON output:"""

        try:
            from student.services.generate_response import generate_response_with_groq
            raw = generate_response_with_groq(
                query="Extract topics",
                system_prompt=prompt,
                model_name="llama-3.1-8b-instant",
            )
            # Parse JSON array from response
            match = re.search(r'\[[\s\S]*?\]', raw)
            if match:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, list):
                    for topic in parsed:
                        t = str(topic).strip()
                        if t and len(t) > 2 and len(t) < 80 and t not in topics:
                            topics.append(t)
        except Exception as e:
            logger.warning(f"LLM topic extraction failed: {e}")

    # Fallback: regex-based extraction from chunks if LLM failed
    if not topics and raw_texts:
        for text in raw_texts:
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
            for line in lines[:3]:
                if re.fullmatch(r"\d+|\d+\.\d+|CHAPTER|Chapter|Page \d+", line, re.IGNORECASE):
                    continue
                clean = re.sub(r"\s*\d+$|\s*[IVXivx]+$", "", line).strip()
                if clean and len(clean) > 3 and len(clean) < 80 and clean not in topics:
                    topics.append(clean)
                    break
            if len(topics) >= max_topics * 2:
                break

    # Fallback: document file names
    if len(topics) < max_topics:
        try:
            from pymongo import MongoClient
            from config.settings import settings
            client = MongoClient(settings.mongodb_uri)
            db = client[class_name]
            collection = db[subject]
            filter_query = {"subject_agent_id": subject_agent_id}
            file_names = collection.distinct("document.file_name", filter_query)
            for file_name in file_names:
                if not file_name:
                    continue
                name = os.path.splitext(file_name)[0].replace("_", " ").replace("-", " ").strip()
                if name and name not in topics:
                    topics.append(name)
                if len(topics) >= max_topics * 2:
                    break
            client.close()
        except Exception:
            pass

    # Fallback: agent metadata
    if not topics:
        try:
            metadata = get_agent_metadata(subject_agent_id) if subject_agent_id else {}
            for key in ("agent_name", "description", "subject"):
                val = metadata.get(key, "").strip()
                if val and len(val) > 2 and val not in topics:
                    topics.append(val)
        except Exception:
            pass

    # Last resort: subject name
    if not topics and subject:
        topics.append(subject)

    # Cache the large pool of topics
    _cache_topics(cache_key, topics)
    
    # Return a random sample of max_topics for this specific request
    import random
    return random.sample(topics, min(max_topics, len(topics)))


# =====================================================
# 🛡 OFF-SUBJECT CLASSIFIER (deterministic enforcement)
# =====================================================

_CLASSIFIER_LOCK = Lock()
_CLASSIFIER_CACHE = {}
_CLASSIFIER_CACHE_TTL = 300  # 5 minutes


def _get_classifier_cache_key(query: str, subject: str) -> str:
    import hashlib
    return hashlib.md5(f"{query.lower().strip()}_{subject.lower().strip()}".encode()).hexdigest()


def _get_cached_classification(cache_key: str):
    import time
    with _CLASSIFIER_LOCK:
        if cache_key in _CLASSIFIER_CACHE:
            result, timestamp = _CLASSIFIER_CACHE[cache_key]
            if time.time() - timestamp < _CLASSIFIER_CACHE_TTL:
                logger.info(f"🎯 Using cached classification for key: {cache_key[:8]}...")
                return result
            del _CLASSIFIER_CACHE[cache_key]
    return None


def _cache_classification(cache_key: str, result: dict):
    import time
    with _CLASSIFIER_LOCK:
        _CLASSIFIER_CACHE[cache_key] = (result, time.time())
        if len(_CLASSIFIER_CACHE) > 100:
            oldest = min(_CLASSIFIER_CACHE.keys(), key=lambda k: _CLASSIFIER_CACHE[k][1])
            del _CLASSIFIER_CACHE[oldest]


def classify_subject_boundary(query: str, subject: str) -> dict:
    """
    Lightweight classifier to determine if a query is academic AND off-subject.
    Uses a fast LLM (llama-3.1-8b-instant) with temperature=0.
    Returns: {"is_off_subject": bool, "category": str, "reason": str}
    """
    cache_key = _get_classifier_cache_key(query, subject)
    cached = _get_cached_classification(cache_key)
    if cached is not None:
        return cached

    classifier_prompt = f"""You are a strict subject-boundary checker.
Subject: {subject}
Student query: "{query}"

Task: Determine if this query is academic AND clearly NOT about {subject}.
- "Academic" = requires structured teaching (math, physics, history, grammar, etc.)
- "Non-academic" = greetings, personal chat, weather, capitals, casual conversation

Return ONLY a JSON object (no markdown, no explanation):
{{
  "is_off_subject": true or false,
  "category": "math|science|history|geography|language|general_knowledge|greeting|personal_chat|other",
  "reason": "one-sentence explanation"
}}
"""

    try:
        from student.services.generate_response import generate_response_with_groq
        raw = generate_response_with_groq(
            query=f"Classify this query: '{query}'",
            system_prompt=classifier_prompt,
            model_name="llama-3.1-8b-instant",
        )
        match = re.search(r"\{{[\s\S]*?\}}", raw)
        if match:
            result = json.loads(match.group(0))
            # Normalize
            result["is_off_subject"] = bool(result.get("is_off_subject", False))
            result["category"] = result.get("category", "other")
            result["reason"] = result.get("reason", "")
        else:
            result = {"is_off_subject": False, "category": "unknown", "reason": "Parse failed"}
    except Exception as e:
        logger.error(f"Subject boundary classification failed: {e}")
        result = {"is_off_subject": False, "category": "unknown", "reason": f"Error: {e}"}

    _cache_classification(cache_key, result)
    logger.info(f"🛡 Classification result: {result}")
    return result


def generate_redirect_response(query: str, subject: str, available_topics: list[str]) -> str:
    """
    Simple, direct redirect when no chunks are found.
    NO LLM calls — fast, deterministic, no off-subject explanations.
    Uses bullet points for topic list.
    """
    if not available_topics:
        return (
            f"That's an interesting question! In our {subject} class, we explore many exciting topics. "
            f"What would you like to learn about?"
        )

    topic_bullets = "\n".join(f"- {topic}" for topic in available_topics)

    # Simple, natural redirect templates with bullet points
    templates = [
        (
            f"That's an interesting question! In our {subject} class, we focus on these topics:\n\n"
            f"{topic_bullets}\n\n"
            f"Which of these would you like to explore?"
        ),
        (
            f"Great curiosity! Right now in {subject}, we're learning about:\n\n"
            f"{topic_bullets}\n\n"
            f"What would you like to dive into?"
        ),
        (
            f"I love your curiosity! For our {subject} lessons, we cover:\n\n"
            f"{topic_bullets}\n\n"
            f"Which one sounds exciting to you?"
        ),
    ]

    # Deterministic selection based on query length
    idx = len(query.strip()) % len(templates)
    return templates[idx]


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
    is_practice=False,
):
    """
    Preference-aware, session-aware teacher response

    Args:
        language: Response language ('english', 'hindi', 'hinglish' or None for auto-detect)
        is_deep_dive: If True, bypass retrieval and reuse stored chunk_context
        deep_dive_topic: Topic string for deep-dive prompt instructions
        chunk_context: Pre-built chunk context string from previous turn (for deep-dive)
        deep_dive_count: Number of consecutive deep-dives so far (0 = first/normal)
        is_practice: If True, student is requesting practice problems
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
        # Limit to last 20 turns for the teacher's final prompt
        limited_context = context[-20:]

        # Extract personal information for easy access
        personal_info = []
        for turn in limited_context:
            query_text = ""
            response_text = ""

            if isinstance(turn, dict):
                query_text = turn.get('query', '')
                response_data = turn.get('response', '')
                if isinstance(response_data, dict):
                    response_text = response_data.get('response', '')
                else:
                    response_text = str(response_data)
            elif isinstance(turn, str):
                query_text = turn
                # Try to parse Q: and A:
                match = re.match(r"^Q:\s*(.*?)\s*\nA:\s*(.*?)$", turn, re.DOTALL | re.IGNORECASE)
                if match:
                    query_text = match.group(1)
                    response_text = match.group(2)

            if query_text:
                query_lower = query_text.lower()
                # Look for personal information sharing
                if any(phrase in query_lower for phrase in ['my name is', 'i am', 'i\'m', 'my favorite', 'i like', 'i dislike']):
                    personal_info.append(f"Student shared: {query_text}")

                if isinstance(turn, dict):
                    session_history_text += (
                        f"Previous Q: {query_text}\n"
                        f"Previous A: {response_text}\n"
                    )
                else:
                    session_history_text += f"{turn}\n"

        # Add personal info summary at the beginning for emphasis
        if personal_info:
            personal_info_summary = "\nIMPORTANT PERSONAL INFORMATION SHARED BY STUDENT:\n" + "\n".join(personal_info) + "\n\n"

    # -----------------------------
    # Build final prompt context
    # -----------------------------
    full_context = personal_info_summary + session_history_text

    # Infer topic from history for vague queries
    inferred_topic = None
    if not is_deep_dive:
        history_for_inference = []
        if context:
            for turn in context[-20:]:
                if isinstance(turn, dict):
                    history_for_inference.append(turn)
                elif isinstance(turn, str):
                    match = re.match(r"^Q:\s*(.*?)\s*\nA:\s*(.*?)$", turn, re.DOTALL | re.IGNORECASE)
                    if match:
                        history_for_inference.append({
                            "query": match.group(1),
                            "response": match.group(2)
                        })
                    else:
                        history_for_inference.append({
                            "query": turn,
                            "response": ""
                        })
        inferred_topic = infer_topic_from_history(history_for_inference, current_query=query)
        if inferred_topic:
            logger.info(f"📍 Inferred topic from history: '{inferred_topic}'")

    # RL-based Query Optimization (skip for deep-dive or low budget)
    budget_low = is_daily_budget_low(threshold=10000)
    skip_rl = is_deep_dive or budget_low

    if skip_rl:
        top_k = 5
        skip_reason = "deep_dive" if is_deep_dive else "low_budget"
        state = {"current_query": query, "previous_actions": [f"skip_rl:{skip_reason}"]}
        if budget_low:
            logger.info("⏭️ RL rewrite skipped: daily token budget low")
    else:
        optimizer = RLOptimizer()
        state = optimizer.define_state(query=query, context_chunks=[], student_profile=student_profile)
        top_k = 5

        # Small RL loop to refine query/retrieval (max 2 steps for latency)
        for _ in range(2):
            action = optimizer.select_action(state)
            state["previous_actions"].append(action)

            if action == "rewrite_query":
                recent_context = ""
                last_topic = ""
                if context:
                    last_turns = context[-2:]
                    for turn in last_turns:
                        if isinstance(turn, dict):
                            q_text = turn.get('query','')
                            r_text = turn.get('response','')
                            if isinstance(r_text, dict): r_text = r_text.get('response', '')
                            recent_context += f"Q: {q_text}\nA: {r_text}\n"
                            topic_match = re.search(r"Topic: \*\*(.+?)\*\*", str(r_text))
                            if topic_match:
                                last_topic = topic_match.group(1)

                state["current_query"] = optimizer.rewrite_query(state["current_query"], context_text=recent_context[:2000])
                if last_topic and any(vague in state["current_query"].lower() for vague in ["problem", "it", "this", "that", "the first", "the second", "explain more"]):
                    if last_topic.lower() not in state["current_query"].lower():
                        state["current_query"] = f"{state['current_query']} related to {last_topic}"
                        logger.info(f"📍 Topic Bias applied: {state['current_query']}")
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
        base_prompt=get_base_prompt(),
        language=detected_language,
        is_deep_dive=is_deep_dive,
        deep_dive_topic=deep_dive_topic,
        deep_dive_count=deep_dive_count,
        is_practice=is_practice,
        inferred_topic=inferred_topic,
    )

    full_prompt += f"\nOriginal Student Question:\n{query}\n"
    if not is_deep_dive:
        full_prompt += f"\nSearch Query (RL Optimized):\n{state['current_query']}\n"

    # -----------------------------
    # Ask LLM
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
            custom_prompt=full_prompt,
        )
    else:
        # NORMAL CHAT:
        # 1. CHECK HISTORY FIRST (Crude check for topic continuity)
        is_in_history = False
        if full_context.strip():
            stop_words = {"what", "is", "the", "how", "why", "who", "where", "when", "tell", "explain", "more", "about"}
            query_words = [w.lower() for w in query.split() if w.lower() not in stop_words and len(w) > 2]
            if any(word in full_context.lower() for word in query_words):
                is_in_history = True
                logger.info("💬 Topic continuity detected in history.")

        if subject_agent_id:
            logger.info("💬 NORMAL CHAT: Attempting retriever for knowledge grounding")
            # Use the RL-optimized query if available, otherwise the original query
            search_query = state.get("current_query", query)
            
            result = student_agent.ask(
                query=search_query,
                class_name=class_name,
                subject=subject,
                student_profile=student_profile,
                subject_agent_id=subject_agent_id,
                top_k=top_k,
                is_deep_dive=False,
                chunk_context=None,
                custom_prompt=full_prompt,
            )
            
            has_chunks = False
            if isinstance(result, dict):
                chunk_ctx = result.get("chunk_context", "")
                response_text = result.get("response", "")
                # Check if we actually got relevant chunks
                has_chunks = bool(chunk_ctx and len(chunk_ctx) > 50 and response_text and len(response_text) > 20)
                
            if has_chunks:
                logger.info("✅ Retriever found relevant chunks, using its response")
                # result is already set and has response + chunks
            else:
                logger.info("💬 No relevant chunks found in knowledge base. Checking for alternatives.")
                # We didn't find chunks, so we'll try to fallback
                result = None

        if not result:
            # No retriever result (either no chunks or no agent_id)
            suggested_topic = inferred_topic
            is_personal = is_greeting(query) or is_general_chat(query)
            is_followup = is_conversational_followup(query)

            if is_personal or is_followup:
                # Personal / follow-up queries: call main LLM with conversation flow guidance
                logger.info("💬 Personal/follow-up query: calling main LLM")
                graceful_instruction = (
                    "\n\nCONVERSATION FLOW GUIDANCE:\n"
                    "You are a friendly, real teacher. The student's query may be vague, off-subject, "
                    "or not directly covered in the syllabus materials.\n"
                    "- NEVER say 'I don't have specific information' or mention missing documents.\n"
                    "- NEVER say 'I can only answer from uploaded documents' or similar.\n"
                    "- ALWAYS maintain a smooth, natural conversation flow.\n"
                )
                if is_followup:
                    graceful_instruction += (
                        "- The student sent a short follow-up. Continue the conversation naturally "
                        "based on the conversation history above. If no clear topic was being discussed, "
                        "gently suggest what to learn next.\n"
                    )
                elif is_personal:
                    graceful_instruction += (
                        "- The student asked a personal or general question. Answer naturally and warmly.\n"
                    )
                full_prompt += graceful_instruction
            elif subject_agent_id:
                # Academic query with no chunks: simply suggest topics from agent knowledge
                # NO extra LLM calls — fast, deterministic, no off-subject explanations
                logger.info("💬 No chunks found. Simply suggesting topics from agent knowledge.")
                available_topics = get_available_topics_from_agent(
                    class_name, subject, subject_agent_id, max_topics=10
                )
                response_text = generate_redirect_response(query, subject, available_topics)
                result = {
                    "response": response_text,
                    "quality_scores": {},
                    "chunk_context": "",
                    "is_fallback": True,
                }
            else:
                # No agent_id — call main LLM with graceful fallback
                logger.info("💬 No agent_id. Calling main LLM with graceful fallback.")
                graceful_instruction = (
                    "\n\nCONVERSATION FLOW GUIDANCE:\n"
                    "You are a friendly, real teacher. The student's query may be vague, off-subject, "
                    "or not directly covered in the syllabus materials.\n"
                    "- NEVER say 'I don't have specific information' or mention missing documents.\n"
                    "- NEVER say 'I can only answer from uploaded documents' or similar.\n"
                    "- ALWAYS maintain a smooth, natural conversation flow.\n"
                )
                full_prompt += graceful_instruction

            if not result:
                if suggested_topic:
                    full_prompt += (
                        f"\n\nINFERRED/SUGGESTED TOPIC: {suggested_topic}\n"
                        "If the student's query is vague, assume they are asking about this topic. "
                    )

                from student.services.generate_response import generate_response_with_groq
                response_text = generate_response_with_groq(
                    query=query,
                    system_prompt=full_prompt,
                )
                result = {
                    "response": response_text,
                    "quality_scores": {},
                    "chunk_context": chunk_ctx if 'chunk_ctx' in locals() else "",
                    "is_fallback": True,
                }

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
        "is_fallback": result.get("is_fallback", False) if isinstance(result, dict) else False,
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
