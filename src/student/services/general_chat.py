import re
from student.services.generate_response import generate_response_with_groq
from student.repositories.conversation_repository import ConversationManager  # ✅ Import dynamic agent ID mapping
from common.utils.prompt_templates import detect_formal_communication
from student.agents.main_agent import get_agent_metadata
from student.utils.agent_utils import get_dynamic_agent_id_for_subject
from common.prompts import PromptBuilder
import logging
logger = logging.getLogger(__name__)

from student.utils.chat_utils import is_greeting, is_general_chat

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
    
    # Build dynamic greeting prompt via PromptBuilder
    builder = PromptBuilder(
        agent_id=agent_id,
        language=language,
    )
    system_prompt = builder.build_greeting_prompt(is_formal=is_formal and bool(agent_intro))
    logger.info(f"🔍 DEBUG: Using dynamic greeting prompt (formal: {is_formal}, lang: {language})")
    
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
    
    # Build dynamic general chat prompt via PromptBuilder
    builder = PromptBuilder(
        agent_id=get_dynamic_agent_id_for_subject(student_manager, payload.student_id, payload.subject),
        language=language,
    )
    system_prompt = builder.build_general_chat_prompt()

    response = generate_response_with_groq(
        query=payload.query,
        context=context_text,
        system_prompt=system_prompt,
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
