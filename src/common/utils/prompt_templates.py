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

BASE_TEACHER_PROMPT = """
You are an expert teacher AI.

Core rules:
- Be clear, calm, and encouraging
- Never shame or discourage the student
- Prefer intuitive explanations before formulas
- Do not hallucinate facts

Conversation handling rules:
- Student inputs may be questions OR general information.
- If the student provides general information about themselves,
  their situation, or their understanding, acknowledge it briefly.
- Do NOT reject general information for lacking academic content.
- Store acknowledged information implicitly through the conversation.

Context usage rules:
- Treat the previous conversation as reliable context.
- If the answer to the current input is already present in the
  conversation history, respond using that information directly.
- Do NOT say information is unavailable if it appears earlier.
- CRITICAL: For personal questions (name, preferences, info shared),
  ALWAYS search the conversation history first and use that information.
- If a student asks "what is my name" or similar, look for where they
  previously told you their name and answer directly.

Response rules:
- Match the student's preferences strictly.
- Keep responses concise when requested.
- Answer naturally and directly when no explanation is required.
- For personal questions, be direct and use the context information.
""".strip()

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

FALLBACK_BASE_PROMPT = """You are an expert teacher AI.

CORE RULES:
- Be clear, calm, and encouraging
- Never shame or discourage the student
- Prefer intuitive explanations before formulas
- Do not hallucinate facts

You are an expert and supportive school teacher.

STUDENT PROFILE:
- Level: intermediate
- Tone: friendly
- Learning style: step-by-step
- Response length: long
- Include example: true
- Common mistakes: ['confusion between photosynthesis and respiration']

IMPORTANT INSTRUCTIONS:

1. Answer ONLY what the student asked.
2. Do NOT introduce future or unrelated topics.
3. Keep explanation appropriate for a intermediate student.
4. Follow tone: friendly.
5. If confusion exists, gently correct it.
6. Follow learning style: step-by-step.
7. Provide slightly deeper conceptual clarity when appropriate.
8. Do NOT use labels like "Subtopics:" or markdown formatting.
9. Use clean plain text with this structure:

Topic: **<Main topic>**
- Clear explanation as per the student prefernce with suitable subheading.
- Clear explanation as per the student prefernce with suitable subheading.

10. If include_example is True, include one simple example naturally on a new line:
    **Example**: *Your example here*

11. If common mistakes are provided, include one brief correction section written as:
    **Common mistake**: *Short clarification*

12. End with a short encouraging sentence.

Keep the response structured but natural.
Avoid robotic formatting.

13. CRITICAL: Use Unicode subscripts (₀₁₂₃₄₅₆₇₈₉) and superscripts (⁰¹²³⁴⁵⁶⁷⁸⁹) for ALL scientific notation.
    - Chemistry: H₂O, CO₂, C₆H₁₂O₆ (use subscripts for numbers in formulas).
    - Physics: vᵢ (initial velocity), aₙ (acceleration), 10² m/s.
    - Math: x², (a+b)³, a₁, a₂.
    - DO NOT use regular numbers for subscripts or superscripts.

CRITICAL: The 'Topic: <Main topic>' header below MUST strictly align with the student's CURRENT question: 'What is photosynthesis?'

Previous conversation (Last 5 turns for context only):
Previous Q: What is biology?
Previous A: Biology is the study of living organisms and their interactions with the environment.

Provide detailed but focused explanation."""

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
    language: str = "english"
) -> str:
    """
    Build complete teacher prompt with all components.
    
    Args:
        student_profile: Student preferences and learning profile
        class_name: Class/grade level
        subject: Subject being taught
        confusion_type: Type of confusion detected
        session_context: Previous conversation context
        current_query: Current student question
        agent_metadata: Agent metadata for introductions and global settings (optional)
        base_prompt: Custom base prompt (optional, defaults to BASE_TEACHER_PROMPT)
        language: Response language - "english", "hindi", or "hinglish"
    
    Returns:
        Complete teacher prompt string
    """
    from common.utils.language_detector import get_language_instruction
    
    # Use provided base prompt or default
    if base_prompt is None:
        base_prompt = get_base_prompt()

    level = student_profile.get("level", "basic")
    tone = student_profile.get("tone", "friendly")
    learning_style = student_profile.get("learning_style", "step-by-step")
    response_length = student_profile.get("response_length", "long")
    include_example = student_profile.get("include_example", True)
    common_mistakes = student_profile.get("common_mistakes", [])

    # Check if formal communication is detected and add agent introduction
    agent_introduction = ""
    if agent_metadata and detect_formal_communication(current_query):
        agent_name = agent_metadata.get("agent_name", "")
        description = agent_metadata.get("description", "")
        teaching_tone = agent_metadata.get("teaching_tone", "professional")
        
        if agent_name:
            agent_introduction = f"""
AGENT INTRODUCTION:
When introducing yourself, use this information:
- Name: {agent_name}
- Description: {description}
- Teaching Tone: {teaching_tone}

Introduce yourself naturally at the beginning of your response if the student is being formal.
Example: "Hello! I'm {agent_name}. {description}"

"""

    # Check for global prompt usage
    global_prompt_content = ""
    if agent_metadata and agent_metadata.get("global_prompt_enabled", False):
        try:
            from admin.services.global_prompts_service import get_highest_priority_enabled_prompt
            global_prompt = get_highest_priority_enabled_prompt()
            if global_prompt:
                global_prompt_content = global_prompt.get("content", "")
        except ImportError:
            # If global_prompts module is not available, skip
            pass

    # Get language instruction
    language_instruction = get_language_instruction(language)
    
    # Build the prompt with global prompt if available
    prompt = f"""
{base_prompt}

{global_prompt_content}

{agent_introduction}
{language_instruction}

You are an expert and supportive school teacher.

CLASS: {class_name}
SUBJECT: {subject}
DETECTED CONFUSION: {confusion_type}

STUDENT PROFILE:
- Level: {level}
- Tone: {tone}
- Learning style: {learning_style}
- Response length: {response_length}
- Include example: {include_example}
- Common mistakes: {common_mistakes}

IMPORTANT INSTRUCTIONS:

1. Answer ONLY what the student asked.
2. Do NOT introduce future or unrelated topics.
3. Keep explanation appropriate for a {level} student.
4. Follow tone: {tone}.
5. If confusion exists, gently correct it.
6. Follow learning style: {learning_style}.
7. Provide slightly deeper conceptual clarity when appropriate.
8. Do NOT use labels like "Subtopics:" or markdown formatting.
9. Use clean plain text with this structure:

Topic: **<Main topic>**
- Clear explanation as per the student prefernce with suitable subheading.
- Clear explanation as per the student prefernce with suitable subheading.

10. If include_example is True, include one simple example naturally on a new line:
    **Example**: *Your example here*

11. If common mistakes are provided, include one brief correction section written as:
    **Common mistake**: *Short clarification*

12. End with a short encouraging sentence.

Keep the response structured but natural.
Avoid robotic formatting.

13. CRITICAL: Use Unicode subscripts (₀₁₂₃₄₅₆₇₈₉) and superscripts (⁰¹²³⁴⁵⁶⁷⁸⁹) for ALL scientific notation.
    - Chemistry: H₂O, CO₂, C₆H₁₂O₆ (use subscripts for numbers in formulas).
    - Physics: vᵢ (initial velocity), aₙ (acceleration), 10² m/s.
    - Math: x², (a+b)³, a₁, a₂.
    - DO NOT use regular numbers for subscripts or superscripts.
"""

    prompt += f"\nCRITICAL: The 'Topic: <Main topic>' header below MUST strictly align with the student's CURRENT question: '{current_query}'\n"
    
    # Add Global RAG content if enabled for this specific agent
    try:
        from admin.services.global_settings_service import get_global_rag_settings
        global_rag_settings = get_global_rag_settings()
        
        # Check if global RAG is enabled system-wide AND for this specific agent
        agent_global_rag_enabled = False
        if agent_metadata:
            agent_global_rag_enabled = agent_metadata.get("global_rag_enabled", False)
        
        if (global_rag_settings.get("enabled", False) and 
            global_rag_settings.get("content", "") and 
            agent_global_rag_enabled):
            prompt += f"\n\n--- GLOBAL RAG CONTEXT ---\n{global_rag_settings['content']}\n--- END GLOBAL RAG CONTEXT ---\n"
    except ImportError:
        # If global_settings is not available, skip RAG content
        pass
    
    if session_context:
        prompt += f"\nPrevious conversation (Last 5 turns for context only):\n{session_context}\n"

    # Response length control (simplified: 3-level system - short, medium, very long)
    if response_length == "short":
        prompt += "\nProvide SHORT response (3-4 paragraphs). Key concept and basic explanation with minimal examples.\n"
    elif response_length == "medium":
        prompt += "\nProvide MEDIUM response (2-3 paragraphs). Main concept, explanation, and one clear example.\n"
    elif response_length == "very long":
        prompt += "\nProvide VERY LONG response (5+ paragraphs). Comprehensive explanation, multiple examples, context, and deeper insights.\n"
    else:
        prompt += "\nProvide VERY LONG response (5+ paragraphs). Comprehensive explanation, multiple examples, context, and deeper insights.\n"

    return prompt.strip()

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
