from student.services.conversation_summarizer import summarize_text_with_groq
from common.prompts import PromptBuilder
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

    builder = PromptBuilder()
    prompt = builder.build_summary_prompt(
        topic=topic,
        history_text=history_text if history_text else "No previous conversations about this topic",
        profile_hint=profile_hint,
    )

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

    builder = PromptBuilder()
    prompt = builder.build_notes_prompt(
        topic=topic,
        history_text=history_text if history_text else "No previous conversations about this topic",
        profile_hint=profile_hint,
    )

    response = summarize_text_with_groq(
        text=topic,
        prompt=prompt
    )
    logger.info(response)
    return response.strip()
