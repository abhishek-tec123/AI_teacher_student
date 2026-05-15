import json
import re
from typing import List, Dict, Any

from student.services.conversation_summarizer import summarize_text_with_groq, extract_text_from_history
import logging
logger = logging.getLogger(__name__)

# -------------------------------------------------
# JSON Extraction (robust against bad LLM output)
# -------------------------------------------------
def _strip_markdown_code_blocks(text: str) -> str:
    """Remove markdown code fences (```json ... ```)."""
    text = re.sub(r"```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```\s*", "", text)
    return text.strip()


def extract_json_from_text(text: str) -> dict:
    """
    Extracts the first valid JSON object or array from LLM output.
    Always returns a dict with a 'quiz' key.
    """
    cleaned = _strip_markdown_code_blocks(text)

    # 1️⃣ Direct JSON parse
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict) and "quiz" in parsed:
            return parsed
        if isinstance(parsed, list):
            return {"quiz": parsed}
    except json.JSONDecodeError:
        pass

    # 2️⃣ Try extracting JSON array (non-greedy, then progressively smaller)
    array_match = re.search(r"\[\s*\{.*?\}\s*\]", cleaned, re.DOTALL)
    if array_match:
        try:
            parsed = json.loads(array_match.group())
            if isinstance(parsed, list):
                return {"quiz": parsed}
        except json.JSONDecodeError:
            pass

    # 3️⃣ Try extracting JSON object with balanced braces
    # Start from the first '{' and try to find a valid JSON by counting braces
    start = cleaned.find("{")
    while start != -1:
        depth = 0
        for i, ch in enumerate(cleaned[start:], start=start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = cleaned[start:i + 1]
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, dict):
                            return parsed
                    except json.JSONDecodeError:
                        pass
                    break
        start = cleaned.find("{", start + 1)

    logger.warning("Failed to extract JSON from LLM output. Raw text (first 500 chars): %s", cleaned[:500])
    return {"quiz": []}

# -------------------------------------------------
# Validation & Cleanup
# -------------------------------------------------
def _resolve_answer(answer_raw: Any, options: List[str]) -> str | None:
    """
    Resolve an answer value to an actual option string.
    Supports:
      - exact string match (case-insensitive)
      - single-letter A-D / a-d (mapped to options[0-3])
      - integer index 0-3
    """
    if not options:
        return None

    # 1️⃣ Exact string match (case-insensitive)
    answer_str = str(answer_raw).strip()
    for opt in options:
        if opt.strip().lower() == answer_str.lower():
            return opt.strip()

    # 2️⃣ Letter match A-D / a-d
    if len(answer_str) == 1 and answer_str.upper() in "ABCD":
        idx = ord(answer_str.upper()) - ord("A")
        if 0 <= idx < len(options):
            return options[idx].strip()

    # 3️⃣ Integer index 0-3
    try:
        idx = int(answer_raw)
        if 0 <= idx < len(options):
            return options[idx].strip()
    except (ValueError, TypeError):
        pass

    return None


def normalize_quiz_items(
    quiz: List[Dict[str, Any]],
    expected_count: int
) -> List[Dict[str, Any]]:
    """
    Ensures:
    - exactly expected_count questions
    - 4 options
    - answer exists in options
    """

    valid_questions = []

    for q in quiz:
        if not isinstance(q, dict):
            logger.debug("Quiz item rejected: not a dict (%s)", type(q))
            continue

        if not all(k in q for k in ["question", "options", "answer"]):
            logger.debug("Quiz item rejected: missing required keys (%s)", list(q.keys()))
            continue

        if not isinstance(q["options"], list) or len(q["options"]) != 4:
            logger.debug("Quiz item rejected: options not a list of length 4 (%s)", q.get("options"))
            continue

        resolved_answer = _resolve_answer(q["answer"], q["options"])
        if resolved_answer is None:
            logger.debug(
                "Quiz item rejected: answer '%s' not found in options %s",
                q["answer"], q["options"]
            )
            continue

        valid_questions.append({
            "question": q["question"].strip(),
            "options": [opt.strip() for opt in q["options"]],
            "answer": resolved_answer
        })

        if len(valid_questions) == expected_count:
            break

    return valid_questions

# -------------------------------------------------
# Main Quiz Generator
# -------------------------------------------------
def generate_quiz_from_history(
    history: list = None,
    subject: str = "",
    topic: str | None = None,
    num_questions: int = 3,
    session_summary: str = "",
) -> dict:
    """
    Generates a multiple-choice quiz ONCE.

    Returns:
    {
        "subject": str,
        "topic": str | None,
        "quiz": [ {question, options, answer} ],
        "current_question": {
            "question_number": int,
            "total_questions": int,
            "question": str,
            "options": list[str],
            "answer": str
        }
    }
    """

    # Safety fallback: only bail if we have absolutely no content to work with
    if not history and not topic and not session_summary:
        return {
            "subject": subject,
            "topic": topic,
            "quiz": [],
            "current_question": None
        }

    # Use session summary if available, otherwise extract from raw history
    if session_summary:
        conversation_text = session_summary
        logger.info(f"📝 Using session summary for quiz generation ({len(session_summary)} chars)")
    else:
        conversation_text = extract_text_from_history(history) if history else ""

        # Filter history to focus on topic-relevant conversations if topic is specified
        if topic and history:
            topic_keywords = topic.lower().split()
            topic_relevant_history = []

            for item in history:
                item_text = f"{item.get('query', '')} {item.get('response', '')}".lower()
                # Check if any topic keywords appear in the conversation
                if any(keyword in item_text for keyword in topic_keywords if len(keyword) > 2):
                    topic_relevant_history.append(item)

            # If we found topic-relevant history, use it; otherwise use all history
            if topic_relevant_history:
                conversation_text = extract_text_from_history(topic_relevant_history)
                logger.info(f"🎯 Using {len(topic_relevant_history)} topic-relevant conversations out of {len(history)} total")

    from common.prompts import PromptBuilder

    builder = PromptBuilder()
    prompt = builder.build_quiz_prompt(
        conversation_text=conversation_text,
        topic=topic,
        num_questions=num_questions,
    )

    raw_output = summarize_text_with_groq(
        text="Generate the quiz JSON now.",
        prompt=prompt
    )

    parsed = extract_json_from_text(raw_output)

    quiz_raw = parsed.get("quiz", [])
    quiz_clean = normalize_quiz_items(quiz_raw, num_questions)

    # Hard safety check
    if len(quiz_clean) != num_questions:
        logger.warning(
            "Expected %d questions, got %d",
            num_questions, len(quiz_clean)
        )

        # If we got no questions, try a simpler approach with better prompt
        if len(quiz_clean) == 0:
            logger.info("Retrying with simplified quiz generation...")

            # Retry with simpler prompt
            retry_prompt = builder.build_quiz_prompt(
                conversation_text=conversation_text[:1000] if conversation_text else (topic or subject),
                topic=topic or subject,
                num_questions=num_questions,
                is_retry=True,
            )

            retry_output = summarize_text_with_groq(
                text="Generate the quiz JSON now.",
                prompt=retry_prompt
            )
            
            retry_parsed = extract_json_from_text(retry_output)
            retry_quiz = retry_parsed.get("quiz", [])
            quiz_clean = normalize_quiz_items(retry_quiz, num_questions)
            
            logger.info(f"🔄 Retry result: Got {len(quiz_clean)} questions")
        
        # If we still have fewer questions but at least 1, use them as-is
        # Don't generate fake questions - it's better to have fewer real questions

    # Prepare current question (first question)
    current_question = None
    if quiz_clean:
        first_q = quiz_clean[0]
        current_question = {
            "question_number": 1,
            "total_questions": len(quiz_clean),
            "question": first_q["question"],
            "options": first_q["options"],
            "answer": first_q["answer"]  # ✅ Included answer
        }

    return {
        "subject": subject,
        "topic": topic,
        "quiz": quiz_clean,
        "current_question": current_question
    }
