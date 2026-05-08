# -----------------------------
# Quiz Helpers
# -----------------------------
quiz_sessions: dict[str, dict] = {}

import logging
logger = logging.getLogger(__name__)

from student.services.learning_progress import update_progress_and_regression
from student.repositories.preference_repository import PreferenceManager

def create_quiz_session(student_id: str, quiz_data: dict, subject: str = "General"):
    quiz_sessions[student_id] = {
        "current_index": 0,
        "score": 0,
        "quiz": quiz_data["quiz"],
        "answers": [],
        "subject": subject
    }

def get_current_question(student_id: str):
    session = quiz_sessions.get(student_id)
    if not session:
        return None

    idx = session["current_index"]
    quiz = session["quiz"]

    if idx >= len(quiz):
        return None

    q = quiz[idx]
    return {
        "question_number": idx + 1,
        "total_questions": len(quiz),
        "question": q["question"],
        "options": q["options"],
        "answer": q["answer"]
    }

def submit_quiz_answer(student_id: str, user_input: str, student_manager=None, preference_manager=None):
    session = quiz_sessions.get(student_id)
    if not session:
        return {"error": "No active quiz"}

    idx = session["current_index"]
    quiz = session["quiz"]

    if idx >= len(quiz):
        return {"error": "Quiz already finished"}

    choice = user_input.upper().strip()
    if choice not in ["A", "B", "C", "D"]:
        return {"error": "Invalid option"}

    q = quiz[idx]
    selected = q["options"][ord(choice) - 65]
    correct = q["answer"]
    is_correct = selected == correct

    if is_correct:
        session["score"] += 1

    session["answers"].append({
        "question": q["question"],
        "selected": selected,
        "correct": correct,
        "is_correct": is_correct
    })

    # Store quiz question and answer in conversation history
    if student_manager:
        try:
            actual_subject = session.get("subject", "General")
            question_text = f"Q{idx + 1}: {q['question']}\nOptions: A) {q['options'][0]}, B) {q['options'][1]}, C) {q['options'][2]}, D) {q['options'][3]}"
            answer_text = f"Your answer: {choice} ({selected})\nCorrect answer: {correct}\n{'✅ Correct!' if is_correct else '❌ Incorrect!'}"
            
            # Use ConversationManager for adding conversations
            conversation_manager = ConversationManager()
            
            agent_id = get_dynamic_agent_id_for_subject(student_manager, student_id, actual_subject)
            additional_data = {
                "quiz_action": "question_answered",
                "question_number": idx + 1,
                "is_correct": is_correct,
                "selected_answer": choice,
                "correct_answer": correct
            }
            if agent_id:
                additional_data["subject_agent_id"] = agent_id
                
            conversation_id = conversation_manager.add_conversation(
                student_id=student_id,
                subject=actual_subject,
                query=question_text,
                response=answer_text,
                additional_data=additional_data
            )
        except Exception as e:
            logger.info(f"Failed to store quiz Q&A: {e}")

    session["current_index"] += 1

    return {
        "is_correct": is_correct,
        "correct_answer": correct,
        "quiz_completed": session["current_index"] >= len(quiz)
    }

# Add debug function to check quiz state
def debug_quiz_state(student_id: str):
    session = quiz_sessions.get(student_id)
    if not session:
        logger.info(f"❌ No session found for {student_id}")
        return
    logger.info(f"🔍 Quiz state: index={session['current_index']}, total={len(session['quiz'])}, completed={session['current_index'] >= len(session['quiz'])}")


def get_final_quiz_result(student_id: str):
    session = quiz_sessions.get(student_id)
    if not session:
        return None

    return {
        "score": session["score"],
        "total": len(session["quiz"]),
        "answers": session["answers"]
    }

from fastapi.responses import JSONResponse

def handle_quiz_mode(student_id: str, query: str, student_manager=None, preference_manager=None):
    """
    Handles quiz flow if the student is currently in quiz mode.
    Returns a JSONResponse if quiz mode is active, otherwise None.
    """

    # Ensure consistent student_id type
    student_id = str(student_id)

    # Not in quiz mode → let normal flow continue
    if student_id not in quiz_sessions:
        return None

    # Normalize input
    normalized_query = query.strip().upper()

    # Exit quiz
    if normalized_query in {"EXIT", "QUIT", "STOP QUIZ"}:
        session = quiz_sessions.get(student_id)

        if session and student_manager:
            try:
                actual_subject = session.get("subject", "General")
                student_manager.add_conversation(
                    student_id=student_id,
                    subject=actual_subject,
                    query=query,
                    response="Quiz cancelled by user",
                    additional_data={"quiz_action": "cancelled"}
                )
            except Exception:
                pass

        quiz_sessions.pop(student_id, None)

        return JSONResponse(content={
            "intent": "QUIZ",
            "response": {
                "message": "Quiz cancelled. Back to normal chat 🙂"
            }
        })

    # Submit answer
    result = submit_quiz_answer(student_id, normalized_query, student_manager, preference_manager)
    
    # Debug quiz state
    debug_quiz_state(student_id)
    logger.info(f"📊 Quiz result: is_correct={result.get('is_correct')}, quiz_completed={result.get('quiz_completed')}")

    if not result or "error" in result:
        return JSONResponse(content={
            "intent": "QUIZ",
            "response": {
                "message": "Please reply with A, B, C, or D."
            }
        })

    # ----------------------------
    # Quiz finished
    # ----------------------------
    if result["quiz_completed"]:
        logger.info("🎯 Quiz completion block reached")
        # Capture session before popping
        session = quiz_sessions.get(student_id)
        final = get_final_quiz_result(student_id)

        # Prepare final feedback safely
        if result["is_correct"]:
            last_feedback = "✅ Correct!"
        else:
            correct = result["correct_answer"]
            last_feedback = f"❌ Incorrect. Correct answer: {correct}"

        # Record completion and update quiz tracking
        if student_manager:
            try:
                actual_subject = session.get("subject", "General")
                score = final["score"]
                total = final["total"]
                
                # Get current profile to update quiz tracking
                if preference_manager:
                    current_profile = preference_manager.get_or_create_subject_preference(student_id, actual_subject)
                else:
                    # Fallback to student_manager if preference_manager not provided
                    current_profile = student_manager.get_or_create_subject_preference(student_id, actual_subject)
                
                # Update quiz score tracking
                quiz_score_history = current_profile.get("quiz_score_history", [])
                consecutive_low_scores = current_profile.get("consecutive_low_scores", 0)
                consecutive_perfect_scores = current_profile.get("consecutive_perfect_scores", 0)
                
                # Add current score to history (keep last 5)
                quiz_score_history.append(score)
                if len(quiz_score_history) > 5:
                    quiz_score_history = quiz_score_history[-5:]
                
                # Update consecutive counters
                logger.info(f"🔢 Score analysis: score={score}, total={total}, current_consecutive_perfect={consecutive_perfect_scores}")
                
                # Calculate percentage for better threshold logic
                score_percentage = (score / total) if total > 0 else 0
                
                if score_percentage < 0.6:  # Less than 60% = low score
                    consecutive_low_scores += 1
                    consecutive_perfect_scores = 0
                    logger.info(f"📉 Low score ({score_percentage:.1%}): consecutive_low_scores={consecutive_low_scores}")
                elif score_percentage >= 0.8:  # 80% or above = good performance
                    consecutive_perfect_scores += 1
                    consecutive_low_scores = 0
                    if score_percentage == 1.0:
                        logger.info(f"📈 Perfect score (100%): consecutive_perfect_scores={consecutive_perfect_scores}")
                    else:
                        logger.info(f"📈 Good performance ({score_percentage:.1%}): consecutive_perfect_scores={consecutive_perfect_scores}")
                else:
                    # Score between 60-79% = still considered low performance (not mixed)
                    consecutive_low_scores += 1
                    consecutive_perfect_scores = 0
                    logger.info(f"� Low-mid performance ({score_percentage:.1%}): consecutive_low_scores={consecutive_low_scores}")
                
                # Update profile with quiz tracking data
                updated_profile = current_profile.copy()
                updated_profile.update({
                    "quiz_score_history": quiz_score_history,
                    "consecutive_low_scores": consecutive_low_scores,
                    "consecutive_perfect_scores": consecutive_perfect_scores
                })
                
                # Use PreferenceManager for updating subject preference
                if preference_manager:
                    preference_manager.update_subject_preference(student_id, actual_subject, updated_profile)
                else:
                    # Fallback to student_manager if preference_manager not provided
                    student_manager.update_subject_preference(student_id, actual_subject, updated_profile)
                
                # Update preferences based on quiz performance
                if update_progress_and_regression:
                    try:
                        updated_profile = update_progress_and_regression(
                            student_manager, student_id, actual_subject, updated_profile, preference_manager
                        )
                        logger.info(f"📊 Quiz-based preference update: response_length={updated_profile.get('response_length')}, include_example={updated_profile.get('include_example')}")
                    except Exception as e:
                        logger.info(f"Failed to update preferences after quiz: {e}")
                
                # Get agent ID for performance tracking
                from .utils.agent_utils import get_dynamic_agent_id_for_subject
                agent_id = get_dynamic_agent_id_for_subject(student_manager, student_id, actual_subject)
                
                # Calculate quality scores based on quiz performance
                score_percentage = (final["score"] / final["total"]) * 100
                quality_scores = {
                    "overall_score": score_percentage,
                    "quiz_performance": score_percentage,
                    "engagement": 85.0 if score_percentage >= 60 else 70.0,
                    "participation": 90.0,  # High for completing quiz
                    "accuracy": score_percentage
                }
                
                # Use ConversationManager for adding conversations
                conversation_manager.add_conversation(
                    student_id=student_id,
                    subject=actual_subject,
                    query=query,
                    response=f"Quiz completed! Score: {final['score']}/{final['total']}",
                    quality_scores=quality_scores,  # Add quality scores for performance tracking
                    additional_data={
                        "quiz_action": "completed",
                        "final_score": final["score"],
                        "total_questions": final["total"],
                        "answers": final["answers"],
                        "subject_agent_id": agent_id,  
                        "quiz_tracking": {
                            "consecutive_low_scores": consecutive_low_scores,
                            "consecutive_perfect_scores": consecutive_perfect_scores,
                            "score_history": quiz_score_history
                        }
                    },
                    agent_id=get_dynamic_agent_id_for_subject(student_manager, student_id, actual_subject)
                )
                logger.info(f"🔄 Quiz completion stored with performance tracking (score: {score_percentage:.1f}%)")
            except Exception as e:
                logger.info(f"Failed to update quiz tracking: {e}")

        # Remove session AFTER computing everything
        quiz_sessions.pop(student_id, None)

        return JSONResponse(content={
            "intent": "QUIZ",
            "response": {
                # Keep structure simple to avoid frontend breaking
                "message": (
                    f"{last_feedback}\n\n"
                    f"🎉 Quiz Complete!\n"
                    f"Final Score: {final['score']} / {final['total']}"
                )
            }
        })

    # ----------------------------
    # Continue quiz
    # ----------------------------
    next_question = get_current_question(student_id)

    if result["is_correct"]:
        feedback = "✅ Correct!"
    else:
        feedback = f"❌ Incorrect. Correct answer: {result['correct_answer']}"

    return JSONResponse(content={
        "intent": "QUIZ",
        "response": {
            "feedback": feedback,
            "question": next_question
        }
    })
