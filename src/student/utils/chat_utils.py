import re

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


def is_conversational_followup(query: str) -> bool:
    """
    Detects short conversational acknowledgments and vague continuations
    that should NOT trigger the academic no-chunks bypass.
    Examples: 'yes', 'ok', 'sure', 'tell me', 'what topics?', 'anything'
    """
    q = query.lower().strip()

    # Single-word or very short acknowledgments
    short_acknowledgments = {
        "yes", "yeah", "yep", "yup", "sure", "okay", "ok", "alright",
        "fine", "good", "great", "cool", "nice", "thanks", "thank you",
        "no", "nope", "nah", "hmm", "ah", "oh", "wow", "really",
        "ok then", "sure thing", "go ahead", "why not", "let's do it",
    }
    if q in short_acknowledgments:
        return True

    # Pattern-based vague continuations
    patterns = [
        r"^(yes|yeah|yep|yup|sure|okay|ok|alright|all right|fine|good|great|cool|nice|thanks|thank you)\b",
        r"^(tell me|show me|what topics|suggest topics|what can you teach|anything|go on|continue|next|proceed)\b",
        r"^(i want to learn|i want to know|i would like to learn|i would like to know)\b",
        r"^(what next|what now|where do we start|let's start|let us start)\b",
        r"^(okay then|alright then|so what|and then|what about that)\b",
        r"^(sounds good|sounds great|that works|perfect|awesome)\b",
    ]
    return any(re.search(p, q) for p in patterns)
