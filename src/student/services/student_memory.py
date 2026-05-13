import logging
import os
import json
from typing import Optional
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from student.repositories.student_repository import StudentManager
from config.settings import settings
logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO)


def clean_llm_json_output(raw_output: str) -> str:
    """
    Removes markdown code fences like ```json ... ```
    """
    raw_output = raw_output.strip()

    if raw_output.startswith("```"):
        # Remove first ```json or ```
        raw_output = raw_output.split("```")[1]
        raw_output = raw_output.replace("json", "", 1).strip()

    return raw_output.strip()


def student_memory_generate_response_with_groq(
    *,
    student_id: str,
    query: str,
    student_manager: StudentManager,
    context: Optional[str] = None,
    system_prompt: str = "Provide a clear, short, and simple response."
) -> dict:
    """
    Generates response, detects student_core_memory info,
    and updates MongoDB automatically.
    """

    if not query.strip():
        raise ValueError("Query cannot be empty")

    groq_api_key = settings.groq_api_key
    if not groq_api_key:
        raise ValueError("GROQ_API_KEY is not set.")

    memory_detection_prompt = f"""
You are an intelligent assistant.

Detect if USER MESSAGE contains personal memory info
for student_core_memory.

Keys:
- self_description
- study_preferences
- motivation_statement
- background_context
- current_focus_struggle

Rules:
- If sentence describes academic weakness like "I am weak in X"
  classify as self_description.
- If sentence describes temporary difficulty like distraction or focus issues
  classify as current_focus_struggle.

- If sentence describes learning style → use study_preferences.
- If sentence describes life/school background → use background_context.
- If sentence describes goal/dream → use motivation_statement.
- If no memory info → memory_key must be null.

Return strictly valid JSON (no markdown, no explanation):

{{
  "memory_key": "<one of above or null>",
  "memory_value": "<clean extracted sentence or null>",
  "response": "<assistant reply>"
}}

SYSTEM PROMPT:
{system_prompt}

USER MESSAGE:
{query}
"""

    from common.llm.groq_client import sync_invoke_with_limiters
    response = sync_invoke_with_limiters(
        messages=[HumanMessage(content=memory_detection_prompt)],
        model_name=settings.default_llm_model,
        api_key=groq_api_key,
        retry_on_429=True,
    )
    raw_output = getattr(response, "content", str(response)).strip()

    # Clean markdown if present
    cleaned_output = clean_llm_json_output(raw_output)

    try:
        parsed = json.loads(cleaned_output)
    except Exception as e:
        logger.warning(f"Failed to parse JSON from LLM: {e}")
        parsed = {
            "memory_key": None,
            "memory_value": None,
            "response": raw_output
        }

    memory_key = parsed.get("memory_key")
    memory_value = parsed.get("memory_value")

    # ✅ Update MongoDB if memory detected
    if memory_key and memory_value:
        try:
            student_manager.students.update_one(
                {"_id": student_id},
                {
                    "$set": {
                        f"student_core_memory.{memory_key}": memory_value
                    }
                }
            )
            logger.info(f"Updated memory key: {memory_key}")
        except Exception as e:
            logger.error(f"Failed to update student memory: {e}")

    logger.info("Response + memory detection completed")

    return parsed


# ===============================
# Standalone Testing
# ===============================

def main():
    student_manager = StudentManager()

    # Use an existing student_id from your MongoDB
    student_id = "std_EOWRC"

    test_queries = [
        "I am very weak in mathematics."
    ]

    for query in test_queries:
        logger.info("\n-----------------------------------")
        logger.info(f"Query: {query}")

        result = student_memory_generate_response_with_groq(
            student_id=student_id,
            query=query,
            student_manager=student_manager
        )

        logger.info("Memory Key:", result.get("memory_key"))
        logger.info("Memory Value:", result.get("memory_value"))
        logger.info("Response:", result.get("response"))


if __name__ == "__main__":
    main()
