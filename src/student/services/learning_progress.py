# -----------------------------
# Progressive / Degressive: update and store ALL subject-preference keys that change from queries.
# - level, learning_style, response_length, include_example updated and persisted.
# - New subject gets defaults first; then these keys update based on query streaks.
# -----------------------------
from student.repositories.conversation_repository import ConversationManager

def _print_profile(label: str, profile: dict):
    keys = ("level", "tone", "learning_style", "response_length", "include_example", "common_mistakes", "confusion_counter")
    logger.info(f"\n--- {label} ---")
    for k in keys:
        v = profile.get(k, "<missing>")
        logger.info(f"  {k}: {v}")
    logger.info("---\n")


def print_profile(label: str, profile: dict):
    """Print subject preference key-value (e.g. existing from DB)."""
    _print_profile(label, profile)


def update_progress_and_regression(student_manager, student_id, subject, profile, preference_manager=None):
    # Snapshot current preference (before) so we only print if model updates it
    _keys = ("level", "tone", "learning_style", "response_length", "include_example", "common_mistakes", "confusion_counter", "quiz_score_history", "consecutive_low_scores", "consecutive_perfect_scores")
    _defaults = {"level": "basic", "tone": "friendly", "learning_style": "step-by-step", "response_length": "long", "include_example": True, "common_mistakes": [], "confusion_counter": {}, "quiz_score_history": [], "consecutive_low_scores": 0, "consecutive_perfect_scores": 0}
    before_snapshot = {k: profile.get(k, _defaults.get(k)) for k in _keys}

    # Use ConversationManager for conversation history
    conversation_manager = ConversationManager()
    history = conversation_manager.get_conversation_history(
        student_id, subject, limit=8
    )

    correct_streak = 0
    wrong_streak = 0
    confusion_counts = {}
    degradation_triggered = False

    for h in history:
        c = h.get("confusion_type", "NO_CONFUSION")
        if c != "NO_CONFUSION":
            confusion_counts[c] = confusion_counts.get(c, 0) + 1

        # Check for correct/wrong patterns
        if h.get("feedback") == "correct":
            correct_streak += 1
            wrong_streak = 0
        elif h.get("feedback") == "wrong":
            wrong_streak += 1
            correct_streak = 0

    # ------------------
    # CHECK CONFUSION_COUNTER THRESHOLDS (NEW LOGIC)
    # ------------------
    confusion_counter = profile.get("confusion_counter", {})
    for confusion_type, count in confusion_counter.items():
        if confusion_type == "FORMULA_CONFUSION" and count >= 2:
            degradation_triggered = True
            logger.info(f"📉 Formula confusion threshold reached: {count} occurrences")
            break
        elif confusion_type != "FORMULA_CONFUSION" and count >= 3:
            degradation_triggered = True
            logger.info(f"📉 Confusion threshold reached for {confusion_type}: {count} occurrences")
            break

    # ------------------
    # CHECK QUIZ SCORE THRESHOLDS (NEW LOGIC)
    # ------------------
    consecutive_low_scores = profile.get("consecutive_low_scores", 0)
    consecutive_perfect_scores = profile.get("consecutive_perfect_scores", 0)
    
    if consecutive_low_scores >= 2:
        degradation_triggered = True
        logger.info(f"📉 Quiz degradation triggered: {consecutive_low_scores} consecutive low scores")
    elif consecutive_perfect_scores >= 2:
        logger.info(f"📈 Quiz progression triggered: {consecutive_perfect_scores} consecutive perfect scores")

    # ------------------
    # LEVEL (3 correct → level up; 3 wrong → level down)
    # ------------------
    level = profile.get("level", "basic")

    if correct_streak >= 3:
        if level == "basic":
            level = "intermediate"
        elif level == "intermediate":
            level = "advanced"

    if wrong_streak >= 3:
        if level == "advanced":
            level = "intermediate"
        elif level == "intermediate":
            level = "basic"

    # ------------------
    # RESPONSE_LENGTH (simplified logic: 3-level system - short, medium, very long)
    # ------------------
    response_length = profile.get("response_length", "very long")  # Default to very long for detailed responses
    degradation_include_example = False

    # Define response length hierarchy for progression
    response_hierarchy = ["short", "medium", "very long"]
    
    # PERFECT PERFORMANCE: Maintain or enhance detailed responses
    if consecutive_perfect_scores >= 2:
        current_index = response_hierarchy.index(response_length) if response_length in response_hierarchy else 2
        # For good performers, maintain current level or upgrade
        if current_index >= 2:  # very long - keep at maximum
            response_length = "very long"
        elif current_index >= 1:  # medium - upgrade to very long
            response_length = "very long"
        else:  # short - upgrade to medium
            response_length = "medium"
        logger.info(f"📈 Perfect performance: maintaining detailed responses ({response_length})")
    
    # POOR PERFORMANCE: Ensure maximum detail for struggling students
    elif consecutive_low_scores >= 2:
        response_length = "very long"  # Maximum detail for struggling students
        logger.info(f"📉 Poor performance: response_length set to {response_length} for better support")
        degradation_include_example = True
    
    # REGULAR STREAK-BASED LOGIC (progressive enhancement)
    elif correct_streak >= 3 and not degradation_triggered:
        current_index = response_hierarchy.index(response_length) if response_length in response_hierarchy else 2
        # Progress to next level if not at maximum
        if current_index < 2:
            response_length = response_hierarchy[current_index + 1]
        logger.info(f"📈 Good performance: enhanced to {response_length}")
    
    # CONFUSION-BASED DEGRADATION (increase detail for clarity)
    elif degradation_triggered or wrong_streak >= 3:
        current_index = response_hierarchy.index(response_length) if response_length in response_hierarchy else 2
        # Increase detail level for confused students
        if current_index < 2:
            response_length = response_hierarchy[min(current_index + 1, 2)]  # Jump to next level for clarity
        else:
            response_length = "very long"
        logger.info(f"📉 Confusion-based degradation: response_length increased to {response_length}")
        degradation_include_example = True
    else:
        degradation_include_example = False

    # ------------------
    # LEARNING STYLE (degressive: more examples when repeatedly confused)
    # ------------------
    learning_style = profile.get("learning_style", "step-by-step")
    for k, v in confusion_counts.items():
        if v >= 3:
            learning_style = "examples"
            break

    # ------------------
    # INCLUDE_EXAMPLE (updated logic: quiz performance has absolute priority over confusion)
    # ------------------
    include_example = profile.get("include_example", True)
    
    # PERFECT PERFORMANCE: Disable examples (ABSOLUTE PRIORITY - overrides confusion)
    if consecutive_perfect_scores >= 2:
        include_example = False
        logger.info(f"📈 Perfect performance: examples disabled")
    # POOR PERFORMANCE: Enable examples (ABSOLUTE PRIORITY - overrides confusion)
    elif consecutive_low_scores >= 2:
        include_example = True
        logger.info(f"📉 Poor performance: examples enabled")
    # REGULAR LOGIC (only if no quiz performance)
    elif degradation_triggered or degradation_include_example:
        include_example = True
        logger.info(f"📉 Confusion-based degradation: examples enabled")
    elif level == "advanced" and not degradation_triggered:
        include_example = False
        logger.info(f"📈 Advanced level: examples disabled")
    elif learning_style == "examples":
        include_example = True
    else:
        include_example = True

    # Update profile in memory with all computed values
    profile["level"] = level
    profile["learning_style"] = learning_style
    profile["response_length"] = response_length
    profile["include_example"] = include_example

    # ------------------
    # STORE ALL KEYS IN DB (full subject preference with defaults/current values every time)
    # ------------------
    SUBJECT_PREFERENCE_KEYS = (
        "level", "tone", "learning_style", "response_length",
        "include_example", "common_mistakes", "confusion_counter",
        "quiz_score_history", "consecutive_low_scores", "consecutive_perfect_scores"
    )
    full_preference = {k: profile.get(k) for k in SUBJECT_PREFERENCE_KEYS if k in profile}
    # Ensure we have all keys with defaults if missing
    defaults = {
        "level": "basic", "tone": "friendly", "learning_style": "step-by-step",
        "response_length": "long", "include_example": True,
        "common_mistakes": [], "confusion_counter": {},
        "quiz_score_history": [], "consecutive_low_scores": 0, "consecutive_perfect_scores": 0
    }
    for k, v in defaults.items():
        full_preference.setdefault(k, v)

    # Use PreferenceManager for updating subject preference
    preference_manager.update_subject_preference(
        student_id, subject, full_preference
    )

    # Only print before/after if preference was actually updated (level, learning_style, response_length, include_example, or common_mistakes/confusion_counter from wrong question)
    updatable = ("level", "learning_style", "response_length", "include_example", "common_mistakes", "confusion_counter", "quiz_score_history", "consecutive_low_scores", "consecutive_perfect_scores")
    changed = any(full_preference.get(k) != before_snapshot.get(k) for k in updatable)
    if changed:
        _print_profile("BEFORE (subject preference)", before_snapshot)
        _print_profile("AFTER (subject preference)", full_preference)
        direction = "📈 progressive" if (correct_streak >= 3 and wrong_streak == 0 and not degradation_triggered) else ("📉 degressive" if degradation_triggered or wrong_streak >= 3 else "📊")
        logger.info(f"{direction} Learning state updated (correct_streak={correct_streak}, wrong_streak={wrong_streak})")
    else:
        logger.info("Preference not updated (no change).")

    return profile


import json
import logging
logger = logging.getLogger(__name__)

# -----------------------------
# Preference Normalizer: all subject-preference keys with defaults. New subject gets these; then updated from queries.
# -----------------------------
def normalize_student_preference(pref: dict) -> dict:
    defaults = {
        "level": "basic",
        "tone": "friendly",
        "learning_style": "step-by-step",
        "response_length": "long",
        "include_example": True,
        "common_mistakes": [],
        "confusion_counter": {},
        "quiz_score_history": [],
        "consecutive_low_scores": 0,
        "consecutive_perfect_scores": 0
    }

    for k, v in defaults.items():
        pref.setdefault(k, v)

    if isinstance(pref.get("common_mistakes"), str):
        try:
            pref["common_mistakes"] = json.loads(pref["common_mistakes"]) if pref["common_mistakes"] else []
        except Exception:
            pref["common_mistakes"] = []

    if isinstance(pref.get("confusion_counter"), str):
        try:
            pref["confusion_counter"] = json.loads(pref["confusion_counter"]) if pref["confusion_counter"] else {}
        except Exception:
            pref["confusion_counter"] = {}

    return pref