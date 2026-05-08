from student.services.conversation_summarizer import summarize_text_with_groq
import logging
logger = logging.getLogger(__name__)

def generate_summary(
    topic: str,
    chat_history: list[dict[str, str]] | None = None,
    student_profile: dict | None = None,
    session_summary: str = "",
) -> str:
    history_text = ""

    if session_summary:
        history_text = session_summary
        logger.info(f"📝 Using session summary for summary generation ({len(session_summary)} chars)")
    elif chat_history:
        # Use ALL conversations for comprehensive summary (no topic filtering)
        for turn in chat_history:
            history_text += f"Student: {turn['query']}\nTeacher: {turn['response']}\n"

        logger.info(f"📝 Using all {len(chat_history)} conversations for comprehensive summary")

    profile_hint = ""
    if student_profile:
        for k, v in student_profile.items():
            profile_hint += f"- {k}: {v}\n"

    prompt = f"""
You are an intelligent teacher creating a comprehensive learning summary based on student learning conversations.

RULES:
- Create a concise summary of what the student has learned
- Focus on key concepts, understanding, and progress made
- Use clear, accessible language
- Highlight important insights and breakthrough moments
- Address any confusion points that were resolved
- No markdown formatting
- No emojis
- No bullet points or numbering
- Write in paragraph form for easy reading

TOPIC:
{topic}

STUDENT LEARNING CONVERSATIONS:
{history_text if history_text else "No previous conversations about this topic"}

STUDENT LEARNING PROFILE:
{profile_hint}

INSTRUCTIONS:
- Summarize the student's learning journey on this topic
- Include key concepts understood and skills developed
- Note any areas of confusion that were clarified
- Highlight the student's progress and current understanding level
- Keep the summary comprehensive but concise
- Write as if explaining to the student what they have accomplished
- CRITICAL: Use Unicode subscripts (₀₁₂₃₄₅₆₇₈₉) and superscripts (⁰¹²³⁴⁵⁶⁷⁸⁹) for ALL scientific notation (e.g., H₂O, x², vᵢ).
"""

    response = summarize_text_with_groq(
        text=topic,
        prompt=prompt
    )
    logger.info(response)
    return response.strip()

def generate_notes(
    topic: str,
    chat_history: list[dict[str, str]] | None = None,
    student_profile: dict | None = None,
    session_summary: str = "",
) -> str:
    history_text = ""

    if session_summary:
        history_text = session_summary
        logger.info(f"📝 Using session summary for notes generation ({len(session_summary)} chars)")
    elif chat_history:
        topic_relevant_history = []

        # Filter history to focus on topic-relevant conversations
        topic_keywords = topic.lower().split()

        for turn in chat_history:
            item_text = f"{turn.get('query', '')} {turn.get('response', '')}".lower()
            # Check if any topic keywords appear in the conversation
            if any(keyword in item_text for keyword in topic_keywords if len(keyword) > 2):
                topic_relevant_history.append(turn)

        # Use topic-relevant history if available, otherwise use all history
        history_to_use = topic_relevant_history if topic_relevant_history else chat_history

        for turn in history_to_use:
            history_text += f"Student: {turn['query']}\nTeacher: {turn['response']}\n"

        if topic_relevant_history:
            logger.info(f"📝 Using {len(topic_relevant_history)} topic-relevant conversations for notes out of {len(chat_history)} total")

    profile_hint = ""
    if student_profile:
        for k, v in student_profile.items():
            profile_hint += f"- {k}: {v}\n"

    prompt = f"""
You are an intelligent teacher creating comprehensive study notes based on student learning conversations.

RULES:
- Bullet points only using "-"
- No numbering
- No markdown
- Beginner friendly but comprehensive
- Short clear points that build understanding
- No emojis
- Focus strictly on the requested topic
- Use insights from student conversations to address common confusion points

TOPIC:
{topic}

STUDENT LEARNING CONVERSATIONS:
{history_text if history_text else "No previous conversations about this topic"}

STUDENT LEARNING PROFILE:
{profile_hint}

INSTRUCTIONS:
- Create notes that address concepts the student has discussed
- Include examples that might clarify confusion points from conversations
- Structure points logically based on how the student learned the topic
- Keep explanations simple but thorough
- FORMATTING: Use `**Header**: *Explanation text*` on the same line for all points.
- CRITICAL: Use Unicode subscripts (₀₁₂₃₄₅₆₇₈₉) and superscripts (⁰¹²³⁴⁵⁶⁷⁸⁹) for ALL scientific notation (e.g., H₂O, x², vᵢ).
"""

    response = summarize_text_with_groq(
        text=topic,
        prompt=prompt
    )
    logger.info(response)
    return response.strip()
