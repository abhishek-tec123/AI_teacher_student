"""
Language Detection Module
Detects if a query is in English, Hindi (Devanagari), or Hinglish (Roman Hindi)
Uses hybrid approach: rule-based for clear cases, LLM fallback for ambiguous cases
"""

import re
from typing import Dict, Any
from student.services.conversation_summarizer import summarize_text_with_groq
import logging
logger = logging.getLogger(__name__)

# =====================================================
# LANGUAGE PATTERNS
# =====================================================

# Common Hinglish words and patterns (Romanized Hindi)
HINGLISH_COMMON_WORDS = [
    # Question words
    "kya", "kaise", "kyun", "kyon", "kahan", "kaha", "kidhar", "kab", "kitna", "kitne",
    # Common verbs
    "hai", "ho", "hoga", "hogi", "hain", "hoga", "kar", "karo", "kare", "karta", "karti",
    "do", "de", "dekh", "dekho", "batao", "bata", "samajh", "samjho", "samajha", "samajhi",
    "banate", "banata", "banati", "kaam", "karta", "karti", "aaya", "aayi", "gaya", "gayi",
    # Pronouns
    "mera", "meri", "mere", "tera", "teri", "tere", "aap", "tum", "main", "tu",
    "mujhe", "tujhe", "usko", "isko", "unhe", "inhe", "unse", "isse", "inse",
    # Common words
    "nahi", "na", "haan", "han", "bhi", "aur", "ya", "ke", "ki", "ka",
    "se", "mein", "me", "par", "liye", "baad", "pehle", "ab", "phir",
    "toh", "thi", "tha", "the", "matlab", "chahiye", "sakta", "sakti",
    "bahut", "zyaada", "kum", "thora", "acha", "bura", "galat", "sahi",
    # Educational terms
    "samajh", "doubt", "question", "answer", "batao", "sikhao", "padh", "padhta", "padhti",
    "explain", "karo", "hota", "hoti", "kaise", "kyon", "kyun", "jawab", "sawal",
    # Food/Plant terms
    "bhojan", "khana", "paudhe", "paude", "poudhe", "podhe",
    # Time-related
    "din", "raat", "subah", "shaam", "kal", "aaj", "abhi"
]

# Suffixes common in Hinglish
HINGLISH_SUFFIXES = ["hai", "ho", "ge", "gi", "ta", "ti", "na", "ne", "kar"]

# =====================================================
# RULE-BASED DETECTION
# =====================================================

def contains_devanagari(text: str) -> bool:
    """Check if text contains Devanagari Unicode characters (Hindi script)"""
    # Devanagari Unicode range: \u0900-\u097F
    devanagari_pattern = re.compile(r'[\u0900-\u097F]')
    return bool(devanagari_pattern.search(text))

def count_hinglish_words(text: str) -> int:
    """Count common Hinglish words in text"""
    text_lower = text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    
    hinglish_count = 0
    for word in words:
        if word in HINGLISH_COMMON_WORDS:
            hinglish_count += 1
    
    return hinglish_count

def has_hinglish_suffixes(text: str) -> bool:
    """Check if words have common Hinglish suffixes"""
    text_lower = text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    
    for word in words:
        for suffix in HINGLISH_SUFFIXES:
            if word.endswith(suffix) and len(word) > len(suffix):
                return True
    return False

def calculate_hinglish_score(text: str) -> float:
    """Calculate a Hinglish probability score (0.0 to 1.0)"""
    text_lower = text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    
    if not words:
        return 0.0
    
    score = 0.0
    
    # Count Hinglish common words
    hinglish_word_count = count_hinglish_words(text)
    score += (hinglish_word_count / len(words)) * 0.6  # 60% weight
    
    # Check for Hinglish suffixes
    if has_hinglish_suffixes(text):
        score += 0.3  # 30% weight
    
    # Check for mixed language indicators (English words + Hindi structure)
    english_common = ["what", "how", "why", "when", "where", "is", "are", "the", "a", "an"]
    english_count = sum(1 for word in words if word in english_common)
    if english_count > 0 and hinglish_word_count > 0:
        score += 0.1  # 10% weight for mixed patterns
    
    return min(score, 1.0)

# =====================================================
# LLM FALLBACK DETECTION
# =====================================================

def llm_detect_language(query: str) -> str:
    """
    Use LLM to detect language for ambiguous cases
    Returns: 'english', 'hindi', or 'hinglish'
    """
    prompt = f"""Analyze the following text and classify its language.

Text: "{query}"

Classify as ONE of:
- "english": Pure English text
- "hindi": Hindi written in Devanagari script (e.g., "नमस्ते")
- "hinglish": Hindi written in Roman/English script (e.g., "namaste", "kya hai")

Rules:
- "kya hai" or "kyon" patterns = hinglish
- "नमस्ते" or "क्या" = hindi  
- "what is" or standard English = english
- Mixed sentences like "what is photosynthesis in Hindi" = english (student is asking about language, not speaking it)

Return ONLY the classification word: english, hindi, or hinglish"""

    try:
        result = summarize_text_with_groq(text=query, prompt=prompt)
        result = result.strip().lower()
        
        # Extract just the language word
        if "hinglish" in result or "hinglish" in result:
            return "hinglish"
        elif "hindi" in result:
            return "hindi"
        elif "english" in result:
            return "english"
        else:
            return "english"  # Default fallback
    except Exception as e:
        logger.info(f"LLM language detection failed: {e}")
        return "english"  # Safe fallback

# =====================================================
# MAIN DETECTION FUNCTION
# =====================================================

def detect_language(query: str, use_llm_fallback: bool = True) -> str:
    """
    Detect language of query: 'english', 'hindi', or 'hinglish'
    
    Uses rule-based detection first, LLM fallback for ambiguous cases
    
    Args:
        query: The student's query text
        use_llm_fallback: Whether to use LLM for ambiguous cases
    
    Returns:
        'english', 'hindi', or 'hinglish'
    """
    if not query or not query.strip():
        return "english"
    
    query = query.strip()
    
    # Rule 1: Check for Devanagari (Hindi script)
    if contains_devanagari(query):
        return "hindi"
    
    # Rule 2: Check Hinglish score
    hinglish_score = calculate_hinglish_score(query)
    
    # High confidence Hinglish detection
    if hinglish_score >= 0.5:
        return "hinglish"
    
    # Rule 3: Check for pure English patterns
    # If no Hinglish words and looks like English, return English
    if hinglish_score < 0.1:
        # Very low Hinglish probability = likely English
        return "english"
    
    # Ambiguous case: use LLM if enabled
    if use_llm_fallback and 0.1 <= hinglish_score < 0.5:
        return llm_detect_language(query)
    
    # Default to English for ambiguous cases without LLM
    return "english"

def get_language_instruction(language: str) -> str:
    """
    Get the prompt instruction for responding in a specific language
    
    Args:
        language: 'english', 'hindi', or 'hinglish'
    
    Returns:
        Instruction string to add to the prompt
    """
    instructions = {
        "hindi": """
LANGUAGE INSTRUCTION: Respond in Hindi using Devanagari script.
- Use natural Hindi phrasing and sentence structure
- Write entirely in Devanagari (e.g., "आप", "समझ", "बताएं")
- Explain concepts clearly in Hindi
- Example response style: "फोटोसिंथेसिस एक प्रक्रिया है जिसमें पौधे..."
""",
        "hinglish": """
LANGUAGE INSTRUCTION: Respond in Hinglish (Hindi in Roman/English script).
- Use Roman alphabet with Hindi grammar and words
- Mix Hindi and English naturally as people do in casual conversation
- Use common Hinglish patterns like "hai", "kya", "kaise", "matlab"
- Example response style: "Photosynthesis ek process hai jisme plants..."
""",
        "english": """
LANGUAGE INSTRUCTION: Respond in English.
- Use clear, natural English
- Keep explanations simple and appropriate for the student's level
"""
    }
    
    return instructions.get(language, instructions["english"])

def get_language_display_name(language: str) -> str:
    """Get human-readable language name"""
    display_names = {
        "hindi": "Hindi (Devanagari)",
        "hinglish": "Hinglish (Roman Hindi)",
        "english": "English"
    }
    return display_names.get(language, "English")

# =====================================================
# BATCH DETECTION (for analytics)
# =====================================================

def detect_language_batch(queries: list) -> Dict[str, Any]:
    """
    Detect languages for multiple queries (useful for analytics)
    
    Returns:
        Dict with counts and percentages for each language
    """
    results = {"hindi": 0, "hinglish": 0, "english": 0, "total": len(queries)}
    
    for query in queries:
        lang = detect_language(query, use_llm_fallback=False)  # Fast mode
        results[lang] += 1
    
    # Calculate percentages
    if results["total"] > 0:
        results["percentages"] = {
            "hindi": round(results["hindi"] / results["total"] * 100, 1),
            "hinglish": round(results["hinglish"] / results["total"] * 100, 1),
            "english": round(results["english"] / results["total"] * 100, 1)
        }
    
    return results
