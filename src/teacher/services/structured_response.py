import logging
# groq chat with text string input ---------------------------------------------------------------------
import json
import os
import re
from pydantic import BaseModel, Field, ValidationError
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
import tiktoken
from config.settings import settings
logger = logging.getLogger(__name__)

# Load environment variables
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# -----------------------------
# Pydantic model for student profile (subject_preferences schema; all keys stored in DB, used in prompt)
# -----------------------------
class StudentProfile(BaseModel):
    level: str = Field(default="basic")
    tone: str = Field(default="friendly")
    learning_style: str = Field(default="step-by-step")
    response_length: str = Field(default="long")
    include_example: bool = Field(default=True)
    language: str = "English"
    common_mistakes: list = Field(default_factory=list)

# -----------------------------
# Main Groq response function
# -----------------------------
def generate_response_from_groq(
    input_text: str,
    query: str = "",
    student_profile: dict = None,
    custom_prompt: str = None
) -> str:
    """
    Generates a response from the Groq LLM using optional dynamic system prompts
    based on student profile/preferences.
    """

    # Validate or create student profile (subject_preferences schema)
    try:
        # Only pass keys that StudentProfile knows; ignore confusion_counter etc.
        _fields = getattr(StudentProfile, "model_fields", None) or getattr(StudentProfile, "__fields__", {})
        safe_profile = {k: v for k, v in (student_profile or {}).items() if k in _fields}
        profile = StudentProfile(**safe_profile)
    except ValidationError as e:
        logger.warning(f"Student profile validation failed, using defaults: {e}")
        profile = StudentProfile()  # fallback to defaults

    # Construct dynamic prompt from full subject preferences (all keys from DB used in prompt)
    profile_instructions = []
    profile_instructions.append(f"Target student level: {profile.level}.")
    profile_instructions.append(f"Use a {profile.tone} tone.")
    profile_instructions.append(f"Adapt explanation to a {profile.learning_style} learning style.")
    # Enhanced response length instructions with 3 levels (short, medium, very long)
    if profile.response_length == "short":
        profile_instructions.append("Keep response SHORT (2-3 paragraphs). Include key concept and basic explanation with minimal examples.")
    elif profile.response_length == "medium":
        profile_instructions.append("Provide MEDIUM length response (3-4 paragraphs). Include main concept, explanation, and one clear example.")
    elif profile.response_length == "very long":
        profile_instructions.append("Provide VERY LONG response (5+ paragraphs). Include comprehensive explanation, multiple examples, context, and deeper insights.")
    else:
        profile_instructions.append("Provide VERY LONG response (5+ paragraphs). Include comprehensive explanation, multiple examples, context, and deeper insights.")
    if profile.include_example:
        profile_instructions.append("Include an example to illustrate the concept.")
    if profile.common_mistakes:
        profile_instructions.append(
            f"Student often has these gaps; address gently and avoid reinforcing: {profile.common_mistakes}."
        )

    profile_prompt = "Student preferences (use in your answer):\n" + " ".join(profile_instructions)
    system_prompt = custom_prompt or "Answer the user query concisely and accurately."
    full_input = f"{system_prompt}\n\n{profile_prompt}\n\nUser Query: {query}\n\nJSON Data:\n{input_text}"

    # Log what's being sent to LLM
    logger.info("📤 SENDING TO LLM:")
    logger.info("=" * 80)
    logger.info(f"System Prompt: {system_prompt}")
    logger.info(f"Profile Instructions: {profile_prompt}")
    logger.info(f"User Query: {query[:500]}{'...' if len(query) > 500 else ''}")
    # logger.info(f"Retrieved Context (chunks): {len(input_text)} chars")
    # logger.info("-" * 80)
    # logger.info("Full LLM Input (first 1000 chars):")
    # logger.info(full_input[:1000] + ("..." if len(full_input) > 1000 else ""))
    logger.info("=" * 80)

    # Token count helper
    def count_tokens(text):
        if tiktoken:
            enc = tiktoken.encoding_for_model("gpt-3.5-turbo")
            return len(enc.encode(text))
        return len(text) // 4  # approximate

    # Initialize LLM
    groq_api_key = settings.groq_api_key
    if not groq_api_key:
        raise ValueError("GROQ_API_KEY is not set in environment variables.")

    from common.llm.groq_client import sync_invoke_with_limiters

    messages = [HumanMessage(content=full_input)]

    input_tokens = count_tokens(full_input)
    logger.info(f"[Token Log] Input tokens: {input_tokens}")

    response = sync_invoke_with_limiters(
        messages=messages,
        model_name=settings.default_llm_model,
        api_key=groq_api_key,
        temperature=0.3,
        retry_on_429=True,
    )

    response_text = getattr(response, "content", str(response))
    output_tokens = count_tokens(response_text)
    logger.info(f"[Token Log] Output tokens: {output_tokens}")
    logger.info("=" * 80)
    # logger.info("📥 LLM RESPONSE:")
    # logger.info("=" * 80)
    # logger.info(response_text[:500] + ("..." if len(response_text) > 500 else ""))
    # logger.info("=" * 80)

    return response_text


# -----------------------------
# Quality Score Analysis
# -----------------------------
def compute_quality_scores(
    query: str,
    response_text: str,
    retrieved_chunks: list,
    context_string: str,
) -> dict:
    """
    Computes Quality Score Analysis for a RAG response.

    Returns dict with:
      - critical_confidence: Model's certainty in its answer (0-100)
      - model_certainty: Same as critical_confidence (alias)
      - rag_relevance: How relevant the retrieved chunks are (0-100)
      - answer_completeness: How fully the answer addresses the query (0-100)
      - hallucination_risk: Risk of fabricated content (0-100, lower = safer)
    """
    scores = {
        "critical_confidence": 0,
        "model_certainty": 0,
        "rag_relevance": 0,
        "answer_completeness": 0,
        "hallucination_risk": 100,
    }

    # RAG Relevance: derive from chunk similarity scores (0-1 -> 0-100%)
    if retrieved_chunks:
        chunk_scores = [c.get("score", 0) for c in retrieved_chunks if "score" in c]
        logger.info(f"🔍 RAG Relevance Debug:")
        logger.info(f"   - Total chunks: {len(retrieved_chunks)}")
        logger.info(f"   - Chunks with scores: {len(chunk_scores)}")
        logger.info(f"   - Chunk scores: {chunk_scores}")
        if chunk_scores:
            avg_score = sum(chunk_scores) / len(chunk_scores)
            # Fixed RAG relevance calculation: 
            # Scores 0.0-0.2 = 0%, 0.2-0.4 = 25%, 0.4-0.6 = 50%, 0.6-0.8 = 75%, 0.8-1.0 = 100%
            if avg_score >= 0.8:
                rag_relevance = 100
            elif avg_score >= 0.6:
                rag_relevance = 75
            elif avg_score >= 0.4:
                rag_relevance = 50
            elif avg_score >= 0.2:
                rag_relevance = 25
            else:
                rag_relevance = 0
            
            scores["rag_relevance"] = rag_relevance
            logger.info(f"   - Average score: {avg_score}")
            logger.info(f"   - RAG relevance: {rag_relevance}%")
        else:
            logger.info(f"   - No chunk scores found, RAG relevance remains 0%")

    # LLM-based scores: model_certainty, answer_completeness, hallucination_risk
    groq_api_key = settings.groq_api_key
    if groq_api_key and query and response_text and context_string:
        prompt = f"""Evaluate this RAG response. Return ONLY valid JSON.

Query: "{query}"

Retrieved Context:
{context_string[:2000]}

Generated Response:
{response_text[:1500]}

Score each metric 0-100 (integers):
- model_certainty: How confident is the model in this answer? (100 = very confident)
- answer_completeness: Does the answer fully address the query? (100 = fully complete)
- hallucination_risk: Risk of fabricated/unsupported content (0 = none, 100 = high risk)

Return ONLY this JSON (no other text):
{{"model_certainty": N, "answer_completeness": N, "hallucination_risk": N}}"""

        try:
            from common.llm.groq_client import sync_invoke_with_limiters
            out = sync_invoke_with_limiters(
                messages=[HumanMessage(content=prompt)],
                model_name=settings.default_llm_model,
                api_key=groq_api_key,
                retry_on_429=True,
            )
            raw = getattr(out, "content", str(out))
            # Parse JSON from response
            match = re.search(r"\{[\s\S]*?\}", raw)
            if match:
                parsed = json.loads(match.group(0).replace("'", '"'))
                scores["model_certainty"] = int(parsed.get("model_certainty", 50))
                scores["critical_confidence"] = scores["model_certainty"]
                scores["answer_completeness"] = int(parsed.get("answer_completeness", 50))
                scores["hallucination_risk"] = int(parsed.get("hallucination_risk", 50))
                # Clamp 0-100
                for k in ["model_certainty", "critical_confidence", "answer_completeness", "hallucination_risk"]:
                    scores[k] = max(0, min(100, scores[k]))
        except Exception as e:
            logger.warning(f"Quality score LLM evaluation failed: {e}")

    return scores
