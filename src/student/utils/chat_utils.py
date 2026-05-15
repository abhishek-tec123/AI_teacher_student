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
