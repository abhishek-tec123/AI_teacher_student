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
    Detects short conversational acknowledgments, vague continuations, and
    context-dependent requests (like explaining problems/questions/sums or asking why/how)
    that should NOT trigger the academic no-chunks bypass.
    """
    q = query.lower().strip()

    # Single-word or very short acknowledgments
    short_acknowledgments = {
        "yes", "yeah", "yep", "yup", "sure", "okay", "ok", "alright",
        "fine", "good", "great", "cool", "nice", "thanks", "thank you",
        "no", "nope", "nah", "hmm", "ah", "oh", "wow", "really",
        "ok then", "sure thing", "go ahead", "why not", "let's do it",
        "why", "how", "why not", "how so", "explain", "explain more",
    }
    if q in short_acknowledgments:
        return True

    # Pattern-based vague continuations and context-dependent requests
    patterns = [
        # Existing acknowledgments and basic continuations
        r"^(yes|yeah|yep|yup|sure|okay|ok|alright|all right|fine|good|great|cool|nice|thanks|thank you)\b",
        r"^(tell me|show me|what topics|suggest topics|what can you teach|anything|go on|continue|next|proceed)\b",
        r"^(i want to learn|i want to know|i would like to learn|i would like to know)\b",
        r"^(what next|what now|where do we start|let's start|let us start)\b",
        r"^(okay then|alright then|so what|and then|what about that)\b",
        r"^(sounds good|sounds great|that works|perfect|awesome)\b",
        
        # Conversational questions referring back (e.g. why?, why not explain?, why didn't you?)
        r"^(why|how|why\s+not|how\s+so|explain\s+why|why\s+is\s+that|what\s+about)\b",
        r"\b(why\s+not\s+explain|why\s+didn't\s+you|why\s+not)\b",
        
        # Explanations of problems/questions/sums/exercises/tasks
        # e.g., "explain problem 1", "explain question 3", "how to solve the DNA one", "walk me through the first sum"
        r"\b(explain|solve|walkthrough|breakdown|do|answer|show|discuss|help|clarify|explain\s+more|understand|walk\s+me\s+through)\b.*\b(problem|question|sum|task|exercise|activity|one|first|second|third|last|dna)\b",
        r"\b(problem|question|sum|task|exercise|activity|number|no\.?)\s*\d+\b",
        r"\b(explain|solve|walkthrough|breakdown|do|answer|show|discuss|help)\s+(it|this|that|them|these|those|more)\b",

        # Active learning requests (practice, quiz, test, mcq, question, problem, exercise, task, sum, assignment, activity, note, lesson, summary, explanation)
        # e.g., "practice question on RNA", "give me some practice question on DNA", "quiz me on science"
        r"\b(practi[sc]e|pratice|quiz|test|mcq|q[ue]stion|problem|ex[er]cise|task|sum|assign|activit|note|lesson|summar[iy]se|explain|exaplain|expalin|explan|breakdown|walkthrough|solve|do|answer|show|discuss|help|clarify|understand|walk\s+me\s+through)\b",
    ]
    return any(re.search(p, q) for p in patterns)
