from fastapi.responses import JSONResponse
from student.services.learning_progress import normalize_student_preference
from student.services.quiz_helper import create_quiz_session, get_current_question, handle_quiz_mode, get_last_completed_quiz, generate_quiz_explanation
from student.services.intent_handlers import handle_chat_intent, handle_study_plan_intent
from student.agents.main_agent import detect_intent_and_topic
from student.agents.quiz_generator import generate_quiz_from_history
from student.agents.notes_agent import generate_notes, generate_summary
from student.services.conversation_summarizer import update_session_summary, get_session_summary
from student.utils.agent_utils import get_dynamic_agent_id_for_subject
from student.repositories.conversation_repository import ConversationManager
from student.repositories.preference_repository import PreferenceManager
import time
import threading
import logging
logger = logging.getLogger(__name__)

# Simple in-memory cache for student preferences
student_preference_cache = {}
student_existence_cache = {}
cache_lock = threading.Lock()

def get_cached_preference(student_id, subject, preference_manager):
    """Get student preference with caching for faster response."""
    cache_key = f"{student_id}_{subject}"
    
    # Check cache first
    with cache_lock:
        if cache_key in student_preference_cache:
            cached_entry = student_preference_cache[cache_key]
            if time.time() - cached_entry["timestamp"] < 300:  # 5 minutes cache
                logger.info(f"📂 Using cached preference for {cache_key}")
                return cached_entry["preference"]
    
    # If not in cache or expired, fetch from database
    logger.info(f"📂 Fetching preference from database for {cache_key}")
    preference = preference_manager.get_or_create_subject_preference(student_id, subject)
    
    # Update cache
    with cache_lock:
        student_preference_cache[cache_key] = {
            "preference": preference,
            "timestamp": time.time()
        }
    
    return preference

def check_student_exists_cached(student_id, student_manager):
    """Check if student exists with caching."""
    with cache_lock:
        if student_id in student_existence_cache:
            cached_exists, timestamp = student_existence_cache[student_id]
            # Cache for 10 minutes
            if time.time() - timestamp < 600:
                logger.info(f"🎯 Using cached existence check for {student_id}")
                return cached_exists
    
    # If not in cache or expired, check database
    logger.info(f"📂 Checking student existence in database for {student_id}")
    exists = student_manager.students.find_one({"student_id": student_id}) is not None
    
    # Update cache
    with cache_lock:
        student_existence_cache[student_id] = (exists, time.time())
    
    return exists

def update_performance_background(student_manager, student_id, subject, query, response, evolution_scores):
    """Background function to update performance metrics asynchronously."""
    try:
        from student.repositories.conversation_repository import ConversationManager
        conversation_manager = ConversationManager()
        
        agent_id = get_dynamic_agent_id_for_subject(student_manager, student_id, subject)
        additional_data = {}
        if agent_id:
            additional_data["subject_agent_id"] = agent_id
            
        conversation_manager.add_conversation(
            student_id=student_id,
            subject=subject,
            query=query,
            response=response,
            evaluation=evolution_scores,
            quality_scores=evolution_scores,
            feedback=evolution_scores.get("feedback", "like"),
            confusion_type=evolution_scores.get("confusion_type", "NO_CONFUSION"),
            additional_data=additional_data
        )
        
        if agent_id:
            logger.info(f"🔄 Background performance update completed for agent: {agent_id}")
            
            # Clear preference cache when student data is updated
            with cache_lock:
                cache_key = f"{student_id}_{subject}"
                if cache_key in student_preference_cache:
                    del student_preference_cache[cache_key]
                    logger.info(f"🗑️ Cleared preference cache for {cache_key}")
        else:
            logger.info(f"⚠️ Background update skipped - Agent not found for subject '{subject}'")
    except Exception as e:
        logger.info(f"❌ Background performance update failed: {e}")

def queryRouter(
    *,
    payload,
    student_agent,
    student_manager,
    context_store
):
    # Create preference manager instance for preference operations
    preference_manager = PreferenceManager()

    conversation_id = None  # ✅ local variable (thread-safe)
    context_summary = None
    evolution_scores = {}

    # Ensure student exists (with caching)
    if not check_student_exists_cached(payload.student_id, student_manager):
        return JSONResponse(
            status_code=404,
            content={"error": "Student not found. Please create student first."}
        )

    # Initialize context if not exists
    if payload.student_id not in context_store:
        context_store[payload.student_id] = []

    session_context = context_store[payload.student_id]

    # -----------------------------
    # QUIZ MODE OVERRIDE
    # -----------------------------
    quiz_response = handle_quiz_mode(
        student_id=payload.student_id,
        query=payload.query,
        student_manager=student_manager,
        preference_manager=preference_manager
    )

    if quiz_response:
        return quiz_response

    # -----------------------------
    # NORMAL MODE
    # -----------------------------
    profile = normalize_student_preference(
        get_cached_preference(
            payload.student_id, payload.subject, preference_manager
        )
    )

    intent_result = detect_intent_and_topic(payload.query, payload.subject)
    intent = intent_result["intent"]
    topic = intent_result.get("topic")

    # Initialize conversation_manager for use across all intents
    conversation_manager = ConversationManager()
    response = None

    # =============================
    # CHAT (� PRIORITY: Immediate Response)
    # =============================
    if intent == "CHAT":
        result = handle_chat_intent(
            student_agent=student_agent,
            student_manager=student_manager,
            payload=payload,
            profile=profile,
            context=session_context,
            preference_manager=preference_manager,  # Pass preference_manager parameter
            chat_session_id=getattr(payload, 'chat_session_id', None)  # Pass chat_session_id
        )

        response = result["response"]
        conversation_id = result.get("conversation_id")  # May be None (set in background)
        evolution_scores = result.get("evaluation", {})

        # 🚀 IMMEDIATE RESPONSE: Return to user immediately
        immediate_response = {
            "response": response,
            "conversation_id": conversation_id,
            "evaluation": evolution_scores,
            # "profile": result.get("profile", profile),  # Use returned profile or original
            # "context_summary": result.get("context_summary"),  # Fetch stored summary
            "status": "success"
        }

        # 🚀 BACKGROUND: Update session context and summary (non-blocking)
        def background_session_update():
            try:
                new_entry = {
                    "conversation_id": str(conversation_id) if conversation_id else None,
                    "query": payload.query,
                    "response": response,
                    "evolution": evolution_scores
                }

                session_context.append(new_entry)
                # Keep only last 10 raw messages
                context_store[payload.student_id] = session_context[-10:]

                # Update session summary in background
                chat_session_id = getattr(payload, 'chat_session_id', None)
                if chat_session_id:
                    update_session_summary(
                        chat_session_id=chat_session_id,
                        query=payload.query,
                        response=response,
                        student_manager=student_manager,
                    )
                    logger.info(f"🔄 Background session summary updated for session: {chat_session_id}")
                else:
                    logger.info(f"⚠️ Skipping session summary update - no chat_session_id")
            except Exception as e:
                logger.info(f"❌ Background session update failed: {e}")

        # Start background processing
        session_thread = threading.Thread(target=background_session_update, daemon=True)
        session_thread.start()
        logger.info(f"🚀 Session update moved to background for faster response")

        return immediate_response

    # =============================
    # QUIZ
    # =============================
    elif intent == "QUIZ":
        # Fetch session summary for quiz generation (more efficient than raw history)
        chat_session_id = getattr(payload, 'chat_session_id', None)
        session_summary_text = ""
        if chat_session_id:
            session_summary_text = get_session_summary(
                chat_session_id=chat_session_id,
                student_manager=student_manager,
                student_id=payload.student_id,
            )
            logger.info(f"📝 Using session summary for quiz generation")

        # Fallback to raw history if no session summary available
        if not session_summary_text:
            conversation_manager = ConversationManager()
            stored_history = conversation_manager.get_chat_history_by_agent(
                student_id=payload.student_id,
                subject=payload.subject,
                limit=20
            )
            formatted_stored_history = []
            for item in stored_history:
                formatted_stored_history.append({
                    "query": item.get("query", ""),
                    "response": item.get("response", ""),
                    "evolution": item.get("evaluation", {})
                })
            combined_history = formatted_stored_history + session_context
        else:
            combined_history = []

        num_questions = intent_result.get("num_questions", 3)
        quiz_data = generate_quiz_from_history(
            history=combined_history if not session_summary_text else None,
            subject=payload.subject,
            topic=topic,
            num_questions=num_questions,
            session_summary=session_summary_text,
        )

        if not quiz_data["quiz"]:
            response = "Sorry, I couldn't generate a quiz right now."
        else:
            create_quiz_session(payload.student_id, quiz_data, payload.subject)
            
            # Record quiz start in conversation history
            first_question = quiz_data['quiz'][0] if quiz_data['quiz'] else None
            quiz_start_response = f"Started quiz about {topic or payload.subject} with {len(quiz_data['quiz'])} questions"
            
            if first_question:
                quiz_start_response += f"\n\nQ1: {first_question['question']}\nOptions: A) {first_question['options'][0]}, B) {first_question['options'][1]}, C) {first_question['options'][2]}, D) {first_question['options'][3]}"
            
            quiz_start_entry = {
                "query": payload.query,
                "response": quiz_start_response,
                "quiz_metadata": {
                    "topic": topic,
                    "subject": payload.subject,
                    "question_count": len(quiz_data["quiz"]),
                    "quiz_id": f"quiz_{payload.student_id}_{int(time.time())}"
                }
            }
            
            # 🚀 Start background conversation storage for quiz
            def store_quiz_background():
                try:
                    # Get agent ID for performance tracking
                    agent_id = get_dynamic_agent_id_for_subject(student_manager, payload.student_id, payload.subject)
                    
                    additional_data = {
                        **quiz_start_entry.get("quiz_metadata", {}),
                        "quiz_session": True,
                        "quality_scores": {
                            "overall_score": 80.0,  # Default score for quiz start
                        }
                    }
                    if agent_id:
                        additional_data["subject_agent_id"] = agent_id
                        
                    conversation_manager.add_conversation(
                        student_id=payload.student_id,
                        subject=payload.subject,
                        query=quiz_start_entry["query"],
                        response=quiz_start_entry["response"],
                        additional_data=additional_data,
                        chat_session_id=getattr(payload, 'chat_session_id', None)  # Add chat_session_id if available
                    )
                    
                    if agent_id:
                        logger.info(f"🔄 Background quiz storage completed for: {payload.student_id} (agent: {agent_id})")
                    else:
                        logger.info(f"⚠️ Quiz storage completed - Agent not found")
                except Exception as e:
                    logger.info(f"❌ Background quiz storage failed: {e}")
            
            quiz_thread = threading.Thread(target=store_quiz_background, daemon=True)
            quiz_thread.start()
            logger.info(f"🚀 Quiz storage started in background for faster response")
            
            response = {
                "message": "Quiz started!",
                "question": get_current_question(payload.student_id),
                "quiz_metadata": {
                    "topic": topic,
                    "subject": payload.subject,
                    "question_count": len(quiz_data["quiz"]),
                    "history_used": len(combined_history)
                }
            }

    # =============================
    # STUDY PLAN
    # =============================
    elif intent == "STUDY_PLAN":
        response = handle_study_plan_intent(
            student_manager=student_manager,
            payload=payload,
            profile=profile,
            topic=topic,
            chat_session_id=getattr(payload, 'chat_session_id', None)
        )
        
        # 🚀 Start background conversation storage for study plan
        def store_study_plan_background():
            try:
                from student.repositories.conversation_repository import ConversationManager
                conversation_manager = ConversationManager()
                
                # Get agent ID for performance tracking
                agent_id = get_dynamic_agent_id_for_subject(student_manager, payload.student_id, payload.subject)
                
                additional_data = {
                    "study_plan_action": "generated",
                    "topic": topic,
                    "study_plan": response.get("study_plan", "")
                }
                if agent_id:
                    additional_data["subject_agent_id"] = agent_id
                    
                conversation_manager.add_conversation(
                    student_id=payload.student_id,
                    subject=payload.subject,
                    query=payload.query,
                    response=response.get("study_plan", ""),  # Store actual study plan content
                    additional_data=additional_data
                )
                logger.info(f"🔄 Background study plan storage completed for: {payload.student_id}")
            except Exception as e:
                logger.info(f"❌ Background study plan storage failed: {e}")
        
        study_plan_thread = threading.Thread(target=store_study_plan_background, daemon=True)
        study_plan_thread.start()
        logger.info(f"🚀 Study plan storage started in background for faster response")

    # =============================
    # NOTES (🚫 no summary update)
    # =============================
    elif intent == "NOTES":
        # Fetch session summary for notes generation (more efficient than raw history)
        chat_session_id = getattr(payload, 'chat_session_id', None)
        session_summary_text = ""
        if chat_session_id:
            session_summary_text = get_session_summary(
                chat_session_id=chat_session_id,
                student_manager=student_manager,
                student_id=payload.student_id,
            )
            logger.info(f"📝 Using session summary for notes generation")

        # Fallback to raw history if no session summary available
        if not session_summary_text:
            stored_history = conversation_manager.get_chat_history_by_agent(
                student_id=payload.student_id,
                subject=payload.subject,
                limit=None
            )
            formatted_stored_history = []
            for item in stored_history:
                formatted_stored_history.append({
                    "query": item.get("query", ""),
                    "response": item.get("response", ""),
                    "evolution": item.get("evaluation", {})
                })
            combined_history = formatted_stored_history + session_context
        else:
            combined_history = []

        notes = generate_notes(
            topic=topic,
            chat_history=combined_history if not session_summary_text else None,
            student_profile=profile,
            session_summary=session_summary_text,
        )

        response = {
            "topic": topic,
            "notes": notes,
            "metadata": {
                "history_used": len(combined_history),
                "stored_history": len(formatted_stored_history),
                "session_context": len(session_context)
            }
        }

        # 🚀 Start background conversation storage for notes
        def store_notes_background():
            try:
                from student.repositories.conversation_repository import ConversationManager
                conversation_manager = ConversationManager()
                
                # Get agent ID for performance tracking
                agent_id = get_dynamic_agent_id_for_subject(student_manager, payload.student_id, payload.subject)
                
                additional_data = {
                    "notes_action": "generated",
                    "topic": topic,
                    "history_sources": len(combined_history)
                }
                if agent_id:
                    additional_data["subject_agent_id"] = agent_id
                    
                conversation_manager.add_conversation(
                    student_id=payload.student_id,
                    subject=payload.subject,
                    query=payload.query,
                    response=notes,  # Store actual notes content
                    additional_data=additional_data
                )
                logger.info(f"🔄 Background notes storage completed for: {payload.student_id}")
            except Exception as e:
                logger.info(f"❌ Background notes storage failed: {e}")
        
        notes_thread = threading.Thread(target=store_notes_background, daemon=True)
        notes_thread.start()
        logger.info(f"🚀 Notes storage started in background for faster response")

        session_context.append({
            "query": payload.query,
            "response": notes
        })

        context_store[payload.student_id] = session_context[-10:]

    # =============================
    # SUMMARY (🚫 no summary update)
    # =============================
    elif intent == "SUMMARY":
        # Fetch session summary for summary generation (more efficient than raw history)
        chat_session_id = getattr(payload, 'chat_session_id', None)
        session_summary_text = ""
        if chat_session_id:
            session_summary_text = get_session_summary(
                chat_session_id=chat_session_id,
                student_manager=student_manager,
                student_id=payload.student_id,
            )
            logger.info(f"📝 Using session summary for summary generation")

        # Fallback to raw history if no session summary available
        if not session_summary_text:
            stored_history = conversation_manager.get_chat_history_by_agent(
                student_id=payload.student_id,
                subject=payload.subject,
                limit=None
            )
            formatted_stored_history = []
            for item in stored_history:
                formatted_stored_history.append({
                    "query": item.get("query", ""),
                    "response": item.get("response", ""),
                    "evolution": item.get("evaluation", {})
                })
            combined_history = formatted_stored_history + session_context
        else:
            combined_history = []

        summary = generate_summary(
            topic=topic,
            chat_history=combined_history if not session_summary_text else None,
            student_profile=profile,
            session_summary=session_summary_text,
        )

        response = {
            "topic": topic,
            "summary": summary,
            "metadata": {
                "history_used": len(combined_history),
                "stored_history": len(formatted_stored_history),
                "session_context": len(session_context)
            }
        }

        # 🚀 Start background conversation storage for summary
        def store_summary_background():
            try:
                from student.repositories.conversation_repository import ConversationManager
                conversation_manager = ConversationManager()
                
                # Get agent ID for performance tracking
                agent_id = get_dynamic_agent_id_for_subject(student_manager, payload.student_id, payload.subject)
                
                additional_data = {
                    "summary_action": "generated",
                    "topic": topic,
                    "history_sources": len(combined_history)
                }
                if agent_id:
                    additional_data["subject_agent_id"] = agent_id
                    
                conversation_manager.add_conversation(
                    student_id=payload.student_id,
                    subject=payload.subject,
                    query=payload.query,
                    response=summary,  # Store actual summary content
                    additional_data=additional_data
                )
                logger.info(f"🔄 Background summary storage completed for: {payload.student_id}")
            except Exception as e:
                logger.info(f"❌ Background summary storage failed: {e}")
        
        summary_thread = threading.Thread(target=store_summary_background, daemon=True)
        summary_thread.start()
        logger.info(f"🚀 Summary storage started in background for faster response")

        session_context.append({
            "query": payload.query,
            "response": summary
        })

        context_store[payload.student_id] = session_context[-10:]

    # =============================
    # QUIZ_EXPLAIN (post-quiz explanation)
    # =============================
    elif intent == "QUIZ_EXPLAIN":
        completed = get_last_completed_quiz(payload.student_id)
        if not completed:
            response = "You don't have a recent quiz to explain. Start a quiz first!"
        else:
            question_number = intent_result.get("question_number")
            explanation = generate_quiz_explanation(
                completed_quiz=completed,
                question_number=question_number,
                student_query=payload.query,
            )
            response = explanation

    return JSONResponse(
        content={
            "query": payload.query,
            "response": response,
            "conversation_id": str(conversation_id) if conversation_id else None,
            "evolution": evolution_scores,
            "context_history": context_store[payload.student_id],
        }
    )
