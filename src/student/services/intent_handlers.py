import re
import threading
from student.services.learning_progress import (
    normalize_student_preference,
    update_progress_and_regression,
)
from student.agents.main_agent import diagnosis_chat, detect_deep_dive_intent
from student.agents.quiz_generator import generate_quiz_from_history
from student.agents.study_plan import generate_study_plan_with_subtopics
from student.agents.evaluation_agent import evaluate_response
from student.agents.vector_performance_updater import update_vector_performance
from student.utils.agent_utils import get_dynamic_agent_id_for_subject  # ✅ Import dynamic agent ID mapping
from student.services.general_chat import is_greeting, handle_greeting_chat, handle_general_chat_llm, is_general_chat
from student.repositories.conversation_repository import ConversationManager
from student.repositories.preference_repository import PreferenceManager
import logging
logger = logging.getLogger(__name__)
# -------------------------------------------------
# Main Chat Intent Handler
# -------------------------------------------------

def handle_chat_intent(
    *,
    student_agent,
    student_manager,
    payload,
    profile,
    context,
    preference_manager,  # Add preference_manager parameter
    chat_session_id=None,  # Add chat_session_id parameter
):
    # Use explicit language from request, default to english
    detected_language = getattr(payload, 'language', None) or "english"
    logger.info(f"🌐 Using language: {detected_language}")

    # Store in profile for continuity
    profile["last_detected_language"] = detected_language
    # -----------------------------------------
    # Greeting
    # -----------------------------------------
    if is_greeting(payload.query):
        return handle_greeting_chat(
            payload=payload,
            student_manager=student_manager,
            profile=profile,
            chat_session_id=chat_session_id,
            language=detected_language
        )

    # -----------------------------------------
    # General / Personal Chat (NO VECTOR DB)
    # -----------------------------------------
    if is_general_chat(payload.query):
        return handle_general_chat_llm(
            payload=payload,
            student_manager=student_manager,
            profile=profile,
            context=context,
            chat_session_id=chat_session_id,
            language=detected_language
        )

    # -----------------------------------------
    # Academic Tutor Flow (Vector DB + Agent) - PRIORITY #1
    # -----------------------------------------
    # Get subject_agent_id for agent introduction
    subject_agent_id = get_dynamic_agent_id_for_subject(student_manager, payload.student_id, payload.subject)

    # Detect deep-dive intent
    last_query = None
    last_response = None
    if context:
        last_turn = context[-1]
        if isinstance(last_turn, dict):
            last_query = last_turn.get("query", "")
            last_response_data = last_turn.get("response", "")
            if isinstance(last_response_data, dict):
                last_response = last_response_data.get("response", "")
            else:
                last_response = last_response_data

    deep_dive_check = detect_deep_dive_intent(payload.query, last_query=last_query, last_response=last_response)
    is_deep_dive = deep_dive_check["is_deep_dive"]
    deep_dive_topic = deep_dive_check["deep_dive_topic"]

    chunk_context = None
    deep_dive_count = 0
    if is_deep_dive:
        logger.info(f"🔍 Deep-dive detected: topic='{deep_dive_topic}'")
        conversation_manager = ConversationManager()
        last_convo = conversation_manager.get_last_conversation_with_data(
            student_id=payload.student_id,
            subject=payload.subject,
            chat_session_id=chat_session_id,
        )
        if last_convo:
            chunk_context = last_convo.get("additional_data", {}).get("chunk_context", "")
            if chunk_context:
                logger.info(f"🔍 Reusing chunk_context from conversation {last_convo.get('_id')}")
                # Compute deep-dive count from previous conversation
                if last_convo.get("additional_data", {}).get("is_deep_dive"):
                    deep_dive_count = last_convo.get("additional_data", {}).get("deep_dive_count", 0) + 1
                else:
                    deep_dive_count = 1
                logger.info(f"🔍 Deep-dive count set to: {deep_dive_count}")
            else:
                logger.info("⚠️ Deep-dive detected but no chunk_context found in last conversation")
                is_deep_dive = False
        else:
            logger.info("⚠️ Deep-dive detected but no previous conversation found")
            is_deep_dive = False

    # Prepare academic history
    history_context = [
        f"Q: {turn['query']}\nA: {turn['response']}"
        for turn in context
    ]

    chat = diagnosis_chat(
        student_agent,
        payload.query,
        payload.class_name,
        payload.subject,
        profile,
        context=history_context,
        subject_agent_id=subject_agent_id,
        language=detected_language,
        is_deep_dive=is_deep_dive,
        deep_dive_topic=deep_dive_topic,
        chunk_context=chunk_context,
        deep_dive_count=deep_dive_count,
    )

    response = chat["response"]
    confusion_type = chat.get("confusion_type")
    rl_metadata = chat.get("rl_metadata", {})
    result_chunk_context = chat.get("chunk_context", chunk_context)

    # -----------------------------------------
    # STORE CONVERSATION IMMEDIATELY for conversation_id
    # -----------------------------------------
    conversation_manager = ConversationManager()

    # Build additional_data including chunk_context for future deep-dives
    additional_data = {}
    if result_chunk_context:
        additional_data["chunk_context"] = result_chunk_context
    if is_deep_dive:
        additional_data["is_deep_dive"] = True
        additional_data["deep_dive_count"] = deep_dive_count
        additional_data["deep_dive_topic"] = deep_dive_topic

    # Store conversation immediately to get conversation_id
    conversation_id = conversation_manager.add_conversation(
        student_id=payload.student_id,
        subject=payload.subject,
        query=payload.query,
        response=response,  # Store actual response
        feedback="neutral",  # Default feedback
        confusion_type=confusion_type or "NO_CONFUSION",
        evaluation=None,
        additional_data=additional_data,
        chat_session_id=chat_session_id  # Add chat_session_id
    )
    
    logger.info(f"📝 Conversation stored immediately with ID: {conversation_id}")
    
    # -----------------------------------------
    # IMMEDIATE RESPONSE PRIORITY: Return LLM response first
    # -----------------------------------------
    
    immediate_result = {
        "response": response,
        "profile": profile,  # Return original profile for speed
        "evaluation": {"status": "processing"},  # Placeholder evaluation
        "conversation_id": conversation_id,  # Now has actual ID
        "detected_language": detected_language,  # Include detected language
    }

    # -----------------------------------------
    # BACKGROUND PROCESSING: Handle all non-critical operations
    # -----------------------------------------
    def background_processing():
        try:
            # 1️⃣ Update progression (moved to background for speed)
            updated_profile = update_progress_and_regression(
                student_manager,
                payload.student_id,
                payload.subject,
                profile,
                preference_manager
            )
            logger.info("📊 Background profile update completed")
            
            # 2️⃣ Update conversation with additional data
            agent_id = get_dynamic_agent_id_for_subject(student_manager, payload.student_id, payload.subject)
            
            # Prepare additional data - evaluation and agent_id go directly to conversation level
            conversation_updates = {}
            if agent_id:
                conversation_updates["subject_agent_id"] = agent_id
            if rl_metadata:
                conversation_updates["rl_metadata"] = rl_metadata
            if chat_session_id:
                conversation_updates["chat_session_id"] = chat_session_id
            
            # Update the existing conversation with evaluation and agent data
            if conversation_updates:
                conversation_manager.update_conversation(
                    conversation_id=conversation_id,
                    additional_data=conversation_updates
                )
            
            if agent_id:
                logger.info(f"📝 Background conversation updated with agent: {agent_id}")
            else:
                logger.info(f"⚠️ Background conversation updated - Agent not found for subject '{payload.subject}'")
            
            # 3️⃣ Evaluate academic response (moved to background)
            evaluation = evaluate_response(
                query=payload.query,
                response=response,
                subject=payload.subject,
                profile=updated_profile,
            )
            logger.info("🧠 Background evaluation completed")
            
            # 4️⃣ Store evaluation scores in conversation
            if evaluation:
                conversation_manager.update_conversation(
                    conversation_id=conversation_id,
                    additional_data={"evaluation": evaluation}
                )
                logger.info(f"📊 Evaluation scores stored for conversation: {conversation_id}")
            
            # Performance tracking (moved to background)
            if agent_id:
                performance_update_result = update_vector_performance(
                    subject_agent_id=agent_id,
                    quality_scores=evaluation,
                    feedback=evaluation.get("feedback", "like") if isinstance(evaluation, dict) else "like",
                    confusion_type=confusion_type,
                    student_id=payload.student_id
                )
                logger.info(f"🔥 PERFORMANCE UPDATE TRIGGERED")
                logger.info(f"   - Agent ID: {agent_id}")
                logger.info(f"   - Quality Scores: {evaluation}")
                logger.info(f"   - Student ID: {payload.student_id}")
                logger.info(f"   - Performance Update Result: {performance_update_result}")
            
            # Update session summary in background
            if chat_session_id:
                from student.services.conversation_summarizer import update_session_summary
                update_session_summary(
                    chat_session_id=chat_session_id,
                    query=payload.query,
                    response=response,
                    student_manager=student_manager,
                    student_id=payload.student_id,
                )
                logger.info("📝 Background session summary update completed")
            else:
                logger.info("⚠️ Skipping session summary update - no chat_session_id")
            
            # Update student profile with new preferences (moved to background)
            try:
                # Use existing preference_manager or create new one if needed (thread safety)
                pm = preference_manager if preference_manager is not None else PreferenceManager()
                
                pm.update_subject_preference(
                    student_id=payload.student_id,
                    subject=payload.subject,
                    updates={
                        "learning_style": updated_profile["learning_style"],
                        "level": updated_profile["level"],
                        "tone": updated_profile["tone"],
                        "response_length": updated_profile["response_length"],
                        "include_example": updated_profile["include_example"],
                    },
                )
                logger.info("💾 Background profile persistence completed")
            except Exception as e:
                logger.info(f"❌ Background profile persistence failed: {e}")
                import traceback
                traceback.print_exc()
            
            # Second progression update (non-critical)
            final_profile = update_progress_and_regression(
                student_manager,
                payload.student_id,
                payload.subject,
                updated_profile,
                preference_manager=pm,
            )
            logger.info("📈 Background final progression update completed")
            
            logger.info("✅ All background processing completed successfully")
            
        except Exception as e:
            logger.info(f"❌ Background processing failed: {e}")
    
    # Start background processing for non-critical operations
    background_thread = threading.Thread(target=background_processing, daemon=True)
    background_thread.start()
    logger.info(f"🚀 Non-critical operations moved to background")
    
    return immediate_result


# -------------------------------------------------
# Quiz Intent
# -------------------------------------------------

def handle_quiz_intent(*, student_manager, payload, topic, chat_session_id=None):
    # Try to use session summary first (more efficient)
    session_summary_text = ""
    if chat_session_id:
        from student.services.conversation_summarizer import get_session_summary
        session_summary_text = get_session_summary(
            chat_session_id=chat_session_id,
            student_manager=student_manager,
            student_id=payload.student_id,
        )
        if session_summary_text:
            logger.info(f"📝 Using session summary for quiz generation")

    # Fallback to raw history if no session summary
    if not session_summary_text:
        conversation_manager = ConversationManager()
        history = conversation_manager.get_conversation_history(
            payload.student_id,
            payload.subject,
            limit=20,
        )
    else:
        history = []

    return generate_quiz_from_history(
        history=history if not session_summary_text else None,
        subject=payload.subject,
        topic=topic,
        num_questions=3,
        session_summary=session_summary_text,
    )

# -------------------------------------------------
# Study Plan Intent
# -------------------------------------------------

def handle_study_plan_intent(*, student_manager, payload, profile, topic, chat_session_id=None):
    # Try to use session summary for study plan context
    session_summary_text = ""
    if chat_session_id:
        from student.services.conversation_summarizer import get_session_summary
        session_summary_text = get_session_summary(
            chat_session_id=chat_session_id,
            student_manager=student_manager,
            student_id=payload.student_id,
        )
        if session_summary_text:
            logger.info(f"📝 Using session summary for study plan generation")

    plan_text = generate_study_plan_with_subtopics(
        student_sentence=payload.query,
        student_profile=profile,
        explicit_topic=topic,
        session_summary=session_summary_text,
    )

    return {
        "study_plan": plan_text,
        "subject": payload.subject,
        "topic": topic,
    }
