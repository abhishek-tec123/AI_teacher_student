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
    Uses PromptBuilder + Pydantic schema enforcement.
    """
    from common.prompts import PromptBuilder, EvaluationScores

    builder = PromptBuilder(student_profile=profile)
    prompt = builder.build_evaluation_prompt(
        query=query,
        response=response,
        subject=subject,
        confusion_type=confusion_type,
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

        # Try strict Pydantic validation first
        try:
            validated = EvaluationScores.model_validate_json(raw_output)
            scores = validated.model_dump()
        except Exception:
            # Fallback to manual JSON parsing if LLM wraps JSON in markdown
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
