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
- Be clear, calm, and encouraging. Never shame the student.
- Prefer intuitive explanations before formulas. Do not hallucinate facts.
- Student inputs may be questions or general information — acknowledge both.
- Use conversation history directly; do NOT say information is unavailable if it appears earlier.
- For personal questions (name, preferences, info shared), search history first and answer directly.
- Match student preferences strictly (level, tone, learning style, length).
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
1. Answer ONLY what was asked, at the student's level, following their tone and learning style.
2. Do NOT introduce unrelated topics or use markdown labels like "Subtopics:".
3. Use clean plain text starting with "Topic: **<Main topic>**" then bullet explanations.
4. Include one example if include_example is True, and one brief common-mistake correction if provided.
5. End with a short encouraging sentence.

CRITICAL: Use Unicode subscripts (₀₁₂₃₄₅₆₇₈₉) and superscripts (⁰¹²³⁴⁵⁶⁷⁸⁹) for ALL scientific notation.
- Chemistry: H₂O, CO₂, C₆H₁₂O₆.
- Physics: vᵢ, aₙ, 10² m/s.
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
    language: str = "english",
    is_deep_dive: bool = False,
    deep_dive_topic: str = None,
    deep_dive_count: int = 0,
    is_practice: bool = False,
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
        is_deep_dive: If True, append deep-dive instructions
        deep_dive_topic: Topic for deep-dive focus
        deep_dive_count: Number of consecutive deep-dives (0 = first/normal)
        is_practice: If True, student is requesting practice problems

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
1. Answer ONLY what was asked, at the student's level, following their tone ({tone}) and learning style ({learning_style}).
2. Do NOT introduce unrelated topics or use markdown labels like "Subtopics:".
3. Use clean plain text starting with "Topic: **<Main topic>**" then bullet explanations.
4. Include one example if include_example is True, and one brief common-mistake correction if provided.
5. End with a short encouraging sentence.
6. NEVER provide unsolicited practice problems, exercises, or tasks. Only provide them if is_practice is True or if specifically requested.

DYNAMIC QUERY ADAPTATION:
- PRACTICE PROBLEMS: If the student asks for NEW practice problems, exercises, or tasks to solve:
  * Provide exactly 5 diverse problems.
  * LABEL each problem with a descriptive theme or concept in brackets, e.g., "Problem 1 [DNA Copying]: ...".
  * CRITICAL [STRICT FOCUS]: If is_practice is True, skip ALL conceptual explanations, analogies, real-world connections, and deeper insights. Provide ONLY the problems and a brief intro.
  * Range difficulty from basic conceptual to advanced application.
  * Do not show answers immediately unless they ask.
- ANSWERS/EXPLANATIONS TO PROBLEMS: If the student asks for an ANSWER, EXPLANATION, BREAKDOWN, WALKTHROUGH, or CLARIFICATION of a specific problem/task/sum (e.g., "explain problem 1", "how to solve the DNA one", "walk me through the first sum"):
  * Provide a clear, detailed walkthrough and the solution to THAT specific problem only.
  * Focus on the logic and steps required to solve it.
  * Do NOT provide a new set of 5 problems.
- TOPIC STICKINESS: Maintain the current topic from the conversation history unless the student explicitly asks to switch subjects.
- BRIEF QUERIES: If the query is very short (e.g., "why?", "explain more"), override "long" length preferences and be concise.
- DETAILED QUERIES: If the query is long or multi-part, provide a comprehensive response regardless of "short" preferences.
- GREETINGS: If the student greets you (e.g., "Hi", "Hello"), acknowledge it warmly and introduce yourself naturally.

CRITICAL: Use Unicode subscripts (₀₁₂₃₄₅₆₇₈₉) and superscripts (⁰¹²³⁴⁵⁶⁷⁸⁹) for ALL scientific notation.
- Chemistry: H₂O, CO₂, C₆H₁₂O₆.
- Physics: vᵢ, aₙ, 10² m/s.
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
    if is_deep_dive:
        # Adaptive length based on deep-dive count
        if deep_dive_count == 1:
            prompt += "\nProvide a MUCH LONGER and MORE DETAILED response than before (4+ paragraphs). Include multiple examples, detailed breakdowns, and broader context.\n"
        elif deep_dive_count == 2:
            prompt += "\nProvide a VERY LONG and DETAILED response (6+ paragraphs). Go deep using your knowledge. Bring genuinely NEW insights and depth.\n"
        else:
            prompt += "\nProvide a DETAILED response (4+ paragraphs) with new angles and insights. Keep it fresh with minor changes in angle.\n"
    elif response_length == "short":
        prompt += "\nProvide SHORT response (3-4 paragraphs). Key concept and basic explanation with minimal examples.\n"
    elif response_length == "medium":
        prompt += "\nProvide MEDIUM response (2-3 paragraphs). Main concept, explanation, and one clear example.\n"
    elif response_length == "very long":
        prompt += "\nProvide VERY LONG response (5+ paragraphs). Comprehensive explanation, multiple examples, context, and deeper insights.\n"
    else:
        prompt += "\nProvide VERY LONG response (5+ paragraphs). Comprehensive explanation, multiple examples, context, and deeper insights.\n"

    # Deep-dive instructions
    if is_deep_dive:
        topic = deep_dive_topic or current_query
        if deep_dive_count == 1:
            prompt += f"""
DEEP-DIVE MODE (Level 1):
- The student wants a deeper, more detailed explanation about: {topic}.
- Use the retrieved chunks as your factual anchor. The facts in the chunks are non-negotiable.
- Draw FREELY on your teaching expertise to add analogies, step-by-step breakdowns, real-world connections, and deeper conceptual clarity.
- Your goal is to make the student truly understand at a deeper level, not to restate the same surface explanation.
- Keep the tone encouraging and appropriate for the student's level.
"""
        elif deep_dive_count == 2:
            prompt += f"""
DEEP-DIVE MODE (Level 2):
- The student wants an even deeper explanation about: {topic}.
- CRITICAL: You have already explained this once before. Do NOT repeat the same points, examples, or analogies.
- Try a completely DIFFERENT teaching angle: use a new analogy, connect to a different real-world domain, or explain the "why" behind the mechanisms.
- The chunks are still your factual anchor; do not contradict them.
- Bring genuinely NEW insights and depth that were not in your previous explanation.
"""
        else:
            prompt += f"""
DEEP-DIVE MODE (Level 3):
- The student has asked for even more depth about: {topic}.
- CRITICAL: Do NOT repeat the same explanations or examples you have already given. Keep it fresh with minor changes in angle.
- Use a slightly different teaching approach: focus on a narrower sub-aspect, use a fresh analogy, or connect to a new real-world example.
- Continue to draw on your teaching expertise alongside the chunk facts. Keep going deep.
"""

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
