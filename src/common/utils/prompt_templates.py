"""
Prompt Templates Module
Contains all prompt templates and related utilities for the AI teacher system.
This makes prompts modular and reusable across different components.
"""

from typing import Dict, Any, Optional
from config.settings import settings

# =====================================================
# 🔐 BASE TEACHER PROMPT
# =====================================================

from common.prompts.builder import PromptBuilder
from common.prompts.registry import PromptRegistry

BASE_TEACHER_PROMPT = PromptRegistry.get_template("base_teacher")

# =====================================================
# 📋 SAMPLE DATA FOR PROMPT DEMONSTRATION
# =====================================================

SAMPLE_STUDENT_PROFILE = {
    "level": "intermediate",
    "tone": "friendly",
    "learning_style": "step-by-step",
    "response_length": "long",
    "include_example": True,
    "common_mistakes": ["confusion between photosynthesis and respiration"]
}

SAMPLE_CLASS_INFO = {
    "class_name": "10th Grade",
    "subject": "Biology",
    "confusion_type": "NO_CONFUSION"
}

SAMPLE_QUERY = "What is photosynthesis?"

SAMPLE_SESSION_CONTEXT = "Previous Q: What is biology?\nPrevious A: Biology is the study of living organisms and their interactions with the environment."

# =====================================================
# 🎯 FALLBACK PROMPT TEMPLATES
# =====================================================

FALLBACK_BASE_PROMPT = PromptRegistry.get_template("base_teacher")

# =====================================================
# 🔧 PROMPT UTILITY FUNCTIONS
# =====================================================

def get_sample_student_profile() -> Dict[str, Any]:
    """Get sample student profile for prompt demonstration."""
    return SAMPLE_STUDENT_PROFILE.copy()

def get_sample_class_info() -> Dict[str, str]:
    """Get sample class information for prompt demonstration."""
    return SAMPLE_CLASS_INFO.copy()

def get_sample_query() -> str:
    """Get sample query for prompt demonstration."""
    return SAMPLE_QUERY

def get_sample_session_context() -> str:
    """Get sample session context for prompt demonstration."""
    return SAMPLE_SESSION_CONTEXT

def create_fallback_prompt_with_rag(rag_content: str) -> str:
    """Create fallback prompt with RAG content injected."""
    if rag_content:
        return FALLBACK_BASE_PROMPT.replace(
            "Previous conversation (Last 5 turns for context only):",
            f"--- GLOBAL RAG CONTEXT ---\n{rag_content}\n--- END GLOBAL RAG CONTEXT ---\n\nPrevious conversation (Last 5 turns for context only):"
        )
    return FALLBACK_BASE_PROMPT

def get_base_prompt() -> str:
    """Get the base teacher prompt."""
    return BASE_TEACHER_PROMPT

def get_fallback_base_prompt() -> str:
    """Get the fallback base prompt."""
    return FALLBACK_BASE_PROMPT

# =====================================================
# 🎯 TEACHER PROMPT BUILDER FUNCTION
# =====================================================

def detect_formal_communication(query: str) -> bool:
    """
    Detect if student is using formal communication or greeting that should trigger introduction
    """
    formal_indicators = [
        "sir", "ma'am", "teacher", "professor", "respected", "honored",
        "please", "thank you", "excuse me", "pardon", "would you", "could you",
        "may i", "can you please", "kindly", "appreciate", "grateful"
    ]
    
    greeting_indicators = ["hello", "hi", "hey", "good morning", "good afternoon", "good evening"]
    
    query_lower = query.lower()
    
    # Check for formal indicators
    formal_count = sum(1 for indicator in formal_indicators if indicator in query_lower)
    
    # Check for greeting indicators
    greeting_count = sum(1 for indicator in greeting_indicators if indicator in query_lower)
    
    # Check for proper capitalization and punctuation
    has_proper_capitalization = query[0].isupper() if query else False
    has_proper_punctuation = query.endswith(('.', '?', '!')) if query else False
    
    # Consider it formal/introduction-worthy if:
    # - At least 2 formal indicators, OR
    # - 1 formal indicator + proper capitalization/punctuation, OR
    # - Contains high-formality indicators like "sir", "ma'am", "teacher", "professor", "respected", OR
    # - Any greeting indicator (hello, hi, etc.) - ALWAYS trigger introduction for greetings
    high_formality_indicators = ["sir", "ma'am", "teacher", "professor", "respected", "honored"]
    has_high_formality = any(indicator in query_lower for indicator in high_formality_indicators)
    has_greeting = greeting_count >= 1
    
    return (formal_count >= 2) or (formal_count >= 1 and (has_proper_capitalization or has_proper_punctuation)) or has_high_formality or has_greeting

def build_teacher_prompt(
    *,
    student_profile: dict,
    class_name: str,
    subject: str,
    confusion_type: str,
    session_context: str,
    current_query: str = "Current Question",
    agent_metadata: dict = None,
    base_prompt: str = None,
    language: str = "english",
    is_deep_dive: bool = False,
    deep_dive_topic: str = None,
    deep_dive_count: int = 0,
    is_practice: bool = False,
    inferred_topic: str = None,
) -> str:
    """
    Build complete teacher prompt with all components.
    Now delegates to PromptBuilder for dynamic, persona-driven prompts.
    """
    # Resolve agent_id from agent_metadata if provided
    agent_id = None
    if agent_metadata and agent_metadata.get("subject_agent_id"):
        agent_id = agent_metadata.get("subject_agent_id")

    builder = PromptBuilder(
        agent_id=agent_id,
        student_profile=student_profile,
        language=language,
    )

    return builder.build_teacher_prompt(
        class_name=class_name,
        subject=subject,
        confusion_type=confusion_type,
        session_context=session_context,
        current_query=current_query,
        is_deep_dive=is_deep_dive,
        deep_dive_topic=deep_dive_topic,
        deep_dive_count=deep_dive_count,
        is_practice=is_practice,
        inferred_topic=inferred_topic,
    )

# =====================================================
# 📊 PROMPT COMPONENTS FOR RESPONSES
# =====================================================

def get_prompt_components_for_response() -> Dict[str, Any]:
    """Get prompt components structure for API responses."""
    return {
        "student_profile": get_sample_student_profile(),
        "session_context": get_sample_session_context()
    }

# =====================================================
# 🎯 PROMPT VALIDATION
# =====================================================

def validate_prompt_components(student_profile: Dict[str, Any], 
                              class_info: Optional[Dict[str, str]] = None,
                              session_context: Optional[str] = None) -> bool:
    """Validate prompt components are properly structured."""
    
    # Check student profile
    required_profile_keys = ["level", "tone", "learning_style", "response_length", "include_example"]
    for key in required_profile_keys:
        if key not in student_profile:
            return False
    
    # Check class info if provided
    if class_info:
        required_class_keys = ["class_name", "subject", "confusion_type"]
        for key in required_class_keys:
            if key not in class_info:
                return False
    
    # Check session context if provided
    if session_context and not isinstance(session_context, str):
        return False
    
    return True
