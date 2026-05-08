import json
from typing import Optional
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from config.settings import settings


# Lazy-loaded evaluator LLM
_evaluator_llm = None


def _get_evaluator_llm():
    global _evaluator_llm
    if _evaluator_llm is None:
        api_key = settings.groq_api_key
        if not api_key:
            raise ValueError("GROQ_API_KEY is not set in environment variables.")
        _evaluator_llm = ChatGroq(
            model_name="llama-3.1-8b-instant",
            api_key=api_key,
            temperature=0.1,
            max_tokens=400,
        )
    return _evaluator_llm


def _evaluate_with_limiter(messages):
    """Evaluate using centralized rate limiter when possible, fallback to direct LLM."""
    try:
        from common.llm.groq_client import sync_invoke_with_limiters
        return sync_invoke_with_limiters(
            messages=messages,
            model_name="llama-3.1-8b-instant",
            temperature=0.1,
            max_tokens=400,
            retry_on_429=True,
        )
    except Exception:
        # Fallback to direct LLM if centralized client fails
        return _get_evaluator_llm().invoke(messages)


EVALUATION_PROMPT = """
You are a STRICT educational response evaluator.

IMPORTANT:
- You did NOT generate the assistant response.
- You are an external reviewer.
- Do NOT default to mid-range scores.
- Use the FULL score range when justified.
- Penalize mismatches with the student profile.
- If the response is TOO BASIC for an ADVANCED student,
  personalization MUST be BELOW 0.4.
- Be fair, but do not be lenient.

Return ONLY valid JSON. No extra text.

--------------------------------------------------
SCORING GUIDELINES (0.0 – 1.0)
--------------------------------------------------

clarity:
- Is the explanation easy to follow and well-structured?
- Is it concise and aligned with desired response length?

correctness:
- Is the response factually correct?
- Simplified explanations are OK IF NOT misleading.

personalization:
- Does the response match the student's level, tone,
  learning style, and length constraints?
- Penalize generic or beginner-level explanations
  given to advanced students.

pedagogical_value:
- Does the response meaningfully help learning?
- Does it provide insight, structure, or conceptual clarity?
- Generic encouragement without substance should score LOW.

critical_confidence:
- Is the answer confident and decisive when appropriate?
- Penalize unnecessary hedging.

model_certainty:
- Is certainty justified by content?
- Penalize unjustified confidence or excessive doubt.

rag_relevance:
- If external context or retrieval is implied, is it used meaningfully?
- Penalize generic answers when context-specific grounding is expected.

answer_completeness:
- Does the response fully address all parts of the query?
- Penalize partial or shallow answers.

hallucination_risk:
- Likelihood of fabricated facts or unsupported claims.
- 1.0 = very low risk, 0.0 = high risk.

--------------------------------------------------
CONTEXT
--------------------------------------------------

Student Query:
{query}

Subject:
{subject}

Student Profile:
- Level: {level}
- Learning Style: {learning_style}
- Prefers Examples: {include_example}
- Tone Preference: {tone}
- Desired Response Length: {response_length}

Detected Confusion Type:
{confusion_type}

Assistant Response:
{response}

--------------------------------------------------
OUTPUT FORMAT (STRICT)
--------------------------------------------------

Return JSON EXACTLY in this format:

{{
  "pedagogical_value": float,
  "critical_confidence": float,
  "rag_relevance": float,
  "answer_completeness": float,
  "hallucination_risk": float
}}

Rules:
- Scores must be between 0.0 and 1.0
- Use decimals like 0.35, 0.60, 0.85
- Do NOT add any text outside the JSON
"""


def evaluate_response(
    *,
    query: str,
    response: str,
    subject: str,
    profile: dict,
    confusion_type: Optional[str] = None,
):
    """
    Evaluates a generated tutoring response and returns ONLY scores.
    """

    prompt = EVALUATION_PROMPT.format(
        query=query,
        subject=subject,
        level=profile.get("level", "unknown"),
        learning_style=profile.get("learning_style", "unknown"),
        include_example=profile.get("include_example", False),
        tone=profile.get("tone", "neutral"),
        response_length=profile.get("response_length", "unspecified"),
        confusion_type=confusion_type or "None",
        response=response,
    )

    message = HumanMessage(content=prompt)

    EXPECTED_KEYS = {
        "pedagogical_value",
        "critical_confidence",
        "rag_relevance",
        "answer_completeness",
        "hallucination_risk",
    }

    try:
        result = _evaluate_with_limiter([message])
        raw_output = result.content.strip()
        scores = json.loads(raw_output)

        if not isinstance(scores, dict):
            raise ValueError("Scores is not a dict")

        missing = EXPECTED_KEYS - scores.keys()
        extra = scores.keys() - EXPECTED_KEYS

        if missing:
            raise ValueError(f"Missing score keys: {missing}")
        if extra:
            raise ValueError(f"Unexpected score keys: {extra}")

        scores = {k: float(v) for k, v in scores.items()}

        percentage_scores = {k: round(v * 100, 1) for k, v in scores.items()}

        if "hallucination_risk" in percentage_scores:
            percentage_scores["hallucination_risk"] = round(100 - percentage_scores["hallucination_risk"], 1)

        overall_score = round(sum(scores.values()) / len(scores), 3)
        overall_percentage = round(overall_score * 100, 1)

        percentage_scores["overall_score"] = overall_percentage

        return percentage_scores

    except Exception:
        fallback_scores = {
            "pedagogical_value": 0.4,
            "critical_confidence": 0.4,
            "rag_relevance": 0.3,
            "answer_completeness": 0.4,
            "hallucination_risk": 0.1,
        }

        percentage_fallback = {k: round(v * 100, 1) for k, v in fallback_scores.items()}

        if "hallucination_risk" in percentage_fallback:
            percentage_fallback["hallucination_risk"] = round(100 - percentage_fallback["hallucination_risk"], 1)

        overall_score = round(sum(fallback_scores.values()) / len(fallback_scores), 3)
        overall_percentage = round(overall_score * 100, 1)

        percentage_fallback["overall_score"] = overall_percentage

        return percentage_fallback
