from student.services.conversation_summarizer import summarize_text_with_groq

# -----------------------------
# Topic Extraction (LLM-based)
# -----------------------------
def extract_topic_from_sentence(sentence: str) -> str:
    """
    Extracts the main learning topic from a student's sentence.
    """

    prompt = """
Extract ONLY the main learning topic from the sentence.

Rules:
- Return only the topic
- No explanation
- No punctuation
- 1 to 3 words maximum

Examples:
"I want to learn friction" -> friction
"Teach me Newton's laws" -> Newton's laws
"I want help with algebra equations" -> algebra equations
"""

    topic = summarize_text_with_groq(
        text=sentence,
        prompt=prompt
    )

    return topic.strip()


# -----------------------------
# Study Plan Generator
# -----------------------------
def generate_study_plan_with_subtopics(
    student_sentence: str,
    student_profile: dict | None = None,
    explicit_topic: str | None = None,
    session_summary: str = "",
) -> str:
    """
    Generates a structured beginner-friendly study plan
    with clear sections, topics, and bullet points.
    """

    # 🔑 Decide topic source
    if explicit_topic:
        topic = explicit_topic.strip()
    elif session_summary:
        # Extract topic from session summary if available
        topic = extract_topic_from_sentence(session_summary[:500])
    else:
        topic = extract_topic_from_sentence(student_sentence)

    # 🧠 Student profile hint
    profile_hint = ""
    if student_profile:
        profile_hint = "Student Profile:\n"
        for k, v in student_profile.items():
            profile_hint += f"- {k}: {v}\n"

    # Add session summary context if available
    session_context = ""
    if session_summary:
        session_context = f"""
STUDENT SESSION CONTEXT (what the student has already discussed and learned):
{session_summary}

Use this context to:
- Avoid repeating topics already covered
- Build upon concepts the student already knows
- Address any confusion points mentioned in the session
"""

    prompt = f"""
You are an experienced and student-friendly teacher.

Create a structured step-by-step study plan for:

TOPIC: {topic}

{session_context}

IMPORTANT RULES:
- Assume the student is a complete beginner
- Organize the plan in logical learning order
- Use clear section headings
- Use bullet points for subtopics
- Each subtopic must include a short explanation
- Do NOT jump to advanced concepts early
- Keep explanations simple and clear

STRUCTURE FORMAT:

Main Topic: {topic}

1. Basics and Foundations
- Subtopic
  Short explanation
- Subtopic
  Short explanation

2. Core Concepts
- Subtopic
  Short explanation
- Subtopic
  Short explanation

3. Rules or Principles
- Subtopic
  Short explanation

4. Practice Level
- Beginner practice
  What type of problems to solve

5. Applications
- Real-life use
  How it applies in real situations

6. Mastery and Review
- Revision strategy
  How to review
- What the student will be able to do after completing this topic

{profile_hint}
"""

    response = summarize_text_with_groq(
        text=topic,
        prompt=prompt
    )
    logger.info("=== study plan ===", response)
    return response.strip()

from student.services.student_agent import StudentAgent
from student.agents.study_plan import extract_topic_from_sentence
import logging
logger = logging.getLogger(__name__)

def plan_aware_chat(
    student_agent: StudentAgent,
    query: str,
    existing_plan: str | None,
    class_name: str,
    subject: str,
    student_profile: dict
) -> str:
    """
    Handles plan-aware chat: 
    - Uses study plan if question topic exists in plan
    - Otherwise, falls back to normal teacher chat
    """
    use_plan = False

    if existing_plan:
        question_topic = extract_topic_from_sentence(query).lower()
        if question_topic and question_topic in existing_plan.lower():
            use_plan = True

    if use_plan:
        prompt = f"""
You are a teacher strictly following a step-by-step study plan.

STUDY PLAN:
{existing_plan}

RULES:
- Answer ONLY what is required
- Do NOT introduce future topics
- Explain only the current topic in detail
- Be student-friendly
- Assume student is at the beginning

Student question:
{query}
"""
    else:
        prompt = query

    response = student_agent.ask(
        query=prompt,
        class_name=class_name,
        subject=subject,
        student_profile=student_profile
    )

    return response
