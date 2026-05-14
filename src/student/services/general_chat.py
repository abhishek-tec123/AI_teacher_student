import re
from student.services.generate_response import generate_response_with_groq
from student.repositories.conversation_repository import ConversationManager  # ✅ Import dynamic agent ID mapping
from common.utils.prompt_templates import detect_formal_communication  # ✅ Import formal detection from modular templates
from student.agents.main_agent import get_agent_metadata  # ✅ Import agent metadata from mainAgent
from student.utils.agent_utils import get_dynamic_agent_id_for_subject
from common.utils.language_detector import get_language_instruction
import logging
logger = logging.getLogger(__name__)

def is_greeting(query: str) -> bool:
    q = query.lower().strip()
    patterns = [
        r"^hi\b",
        r"^hello\b",
        r"^hey\b",
        r"^good (morning|afternoon|evening)\b",
        # Hindi/Hinglish greetings
        r"^namaste\b",
        r"^namaskar\b",
        r"^pranam\b",
        r"^kaise\b",
        r"^kya\s+haal\b",
    ]
    return any(re.search(p, q) for p in patterns)


def is_general_chat(query: str) -> bool:
    q = query.lower().strip()
    patterns = [
        r"\bmy name is\b",
        r"\bi am\b",
        r"\bi'm\b",
        r"\bhow are you\b",
        r"\bwhat is my name\b",
        r"\bwhat's my name\b",
        r"\btell me about\b",
        r"\bdo you remember\b",
    ]
    return any(re.search(p, q) for p in patterns)

# -------------------------------------------------
# Context Builder
# -------------------------------------------------
def build_context_text(context):
    if not context:
        return None

    text = "Previous conversation:\n"
    for turn in context:
        query = turn.get("query", "")
        response_data = turn.get("response", "")

        if isinstance(response_data, dict):
            response_text = response_data.get("response", "")
        else:
            response_text = response_data

        text += f"Q: {query}\nA: {response_text}\n"

    return text
# -------------------------------------------------
# Greeting Handler
# -------------------------------------------------
def handle_greeting_chat(
    *,
    payload,
    student_manager,
    profile,
    chat_session_id=None,  # Add chat_session_id parameter
    language="english",  # Add language parameter
):
    # Get agent ID for potential introduction
    agent_id = get_dynamic_agent_id_for_subject(student_manager, payload.student_id, payload.subject)
    logger.info(f"🔍 DEBUG: agent_id for subject '{payload.subject}': {agent_id}")
    
    # Create conversation manager instance
    conversation_manager = ConversationManager()
    
    # Check if this is a formal greeting
    is_formal = detect_formal_communication(payload.query)
    logger.info(f"🔍 DEBUG: is_formal greeting '{payload.query}': {is_formal}")
    
    # Get agent metadata for formal greetings
    agent_intro = ""
    if is_formal and agent_id:
        logger.info(f"🔍 DEBUG: Attempting to get metadata for agent_id: {agent_id}")
        agent_metadata = get_agent_metadata(agent_id)
        logger.info(f"🔍 DEBUG: agent_metadata retrieved: {agent_metadata}")
        if agent_metadata:
            agent_name = agent_metadata.get("agent_name", "")
            description = agent_metadata.get("description", "")
            logger.info(f"🔍 DEBUG: agent_name: '{agent_name}', description: '{description}'")
            if agent_name:
                agent_intro = f" I'm {agent_name}. {description}"
                logger.info(f"🔍 DEBUG: Generated agent_intro: '{agent_intro}'")
    
    # Get language instruction
    language_instruction = get_language_instruction(language)
    
    # Build response with potential introduction
    if is_formal and agent_intro:
        # Formal greeting with introduction - use agent identity
        system_prompt = (
            "You are a teacher assistant.\n"
            f"Your identity: {agent_intro.strip()}\n"
            f"{language_instruction}\n"
            "Respond warmly to greetings and introduce yourself using your identity.\n"
            "Start your response with a warm greeting followed by your introduction.\n"
            "Example: 'Hello! I'm Diljit manjhi sir. This is diljit here of home science teacher of class 12th. How can I help you today?'\n"
            "Keep it brief and welcoming."
        )
        logger.info(f"🔍 DEBUG: Using formal greeting with intro (lang: {language})")
    else:
        # Simple greeting
        system_prompt = (
            "You are a friendly student assistant.\n"
            f"{language_instruction}\n"
            "Respond warmly and briefly to greetings.\n"
            "Do not ask academic questions unless student does."
        )
        logger.info(f"🔍 DEBUG: Using simple greeting (formal: {is_formal}, intro: '{agent_intro}', lang: {language})")
    
    response = generate_response_with_groq(
        query=payload.query,
        system_prompt=system_prompt,
    )

    additional_data = {}
    if agent_id:
        additional_data["subject_agent_id"] = agent_id

    conversation_id = conversation_manager.add_conversation(
        student_id=payload.student_id,
        subject=payload.subject,
        query=payload.query,
        response=response,
        confusion_type="NO_CONFUSION",
        evaluation=None,
        additional_data=additional_data,
        chat_session_id=chat_session_id
    )
    return {
        "response": response,
        "profile": profile,
        "evaluation": None,
        "conversation_id": str(conversation_id),
        "detected_language": language,
    }
# -------------------------------------------------
# General (Non-academic) Chat Handler – LLM ONLY
# -------------------------------------------------
def handle_general_chat_llm(
    *, payload, student_manager, profile, context, chat_session_id=None, language="english"
):
    context_text = build_context_text(context)
    
    # Get language instruction
    language_instruction = get_language_instruction(language)

    response = generate_response_with_groq(
        query=payload.query,
        context=context_text,
        system_prompt=(
            "You are a friendly student assistant.\n"
            f"{language_instruction}\n"
            "Rules:\n"
            "- Answer naturally and briefly\n"
            "- Use conversation history for personal info\n"
            "- Do NOT mention systems, databases, or tools\n"
            "- Do NOT teach unless asked\n"
        ),
    )

    agent_id = get_dynamic_agent_id_for_subject(student_manager, payload.student_id, payload.subject)
    
    additional_data = {}
    if agent_id:
        additional_data["subject_agent_id"] = agent_id

    conversation_id = ConversationManager().add_conversation(
        student_id=payload.student_id,
        subject=payload.subject,
        query=payload.query,
        response=response,
        confusion_type="NO_CONFUSION",
        evaluation=None,
        additional_data=additional_data,
        chat_session_id=chat_session_id
    )
    return {
        "response": response,
        "profile": profile,
        "evaluation": None,
        "conversation_id": str(conversation_id),
        "detected_language": language,
    }
