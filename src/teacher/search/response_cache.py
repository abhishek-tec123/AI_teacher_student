import logging
# -----------------------------
# Response Caching System
# -----------------------------
import time
import hashlib
import re
from teacher.search.search_utils import extract_core_question
logger = logging.getLogger(__name__)

# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
# -----------------------------
# Response Cache Class
# -----------------------------
class ResponseCache:
    def __init__(self):
        self.cache = {}
        self.question_frequency = {}
        self.cache_ttl = 3600  # 1 hour cache TTL
    
    def _get_question_hash(self, question):
        """Generate a hash for the question to use as cache key."""
        # Extract core question first to handle variations
        core_question = extract_core_question(question)
        
        # Normalize question: lowercase, remove extra whitespace, remove punctuation
        normalized = re.sub(r'[^\w\s]', '', core_question.lower().strip())
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Remove common question words that don't affect the core meaning
        stop_words = ['what', 'is', 'are', 'the', 'a', 'an', 'tell', 'me', 'explain', 'describe']
        words = normalized.split()
        filtered_words = [word for word in words if word not in stop_words and len(word) > 2]
        normalized = ' '.join(filtered_words)
        
        logger.info(f"[ResponseCache] Normalized question: '{normalized}'")
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def get_cached_response(self, question, student_id=None):
        """Get cached response if available and not expired."""
        question_hash = self._get_question_hash(question)
        current_time = time.time()
        
        if question_hash in self.cache:
            cached_data = self.cache[question_hash]
            
            # Check if cache is still valid
            if current_time - cached_data['timestamp'] < self.cache_ttl:
                # Update frequency count
                self.question_frequency[question_hash] = self.question_frequency.get(question_hash, 0) + 1
                
                frequency = self.question_frequency[question_hash]
                logger.info(f"[ResponseCache] Question repeated {frequency} times, using cached response")
                
                # Return longer response for repeated questions
                response = cached_data['response']
                if frequency > 1:
                    response = self._make_response_longer(response, frequency)
                
                return {
                    'response': response,
                    'quality_scores': cached_data['quality_scores'],
                    'from_cache': True,
                    'repeat_count': frequency
                }
            else:
                # Cache expired, remove it
                del self.cache[question_hash]
                if question_hash in self.question_frequency:
                    del self.question_frequency[question_hash]
        
        return None
    
    def cache_response(self, question, response, quality_scores, student_id=None):
        """Cache a response for future use."""
        question_hash = self._get_question_hash(question)
        
        self.cache[question_hash] = {
            'response': response,
            'quality_scores': quality_scores,
            'timestamp': time.time(),
            'student_id': student_id
        }
        
        # Initialize frequency count
        if question_hash not in self.question_frequency:
            self.question_frequency[question_hash] = 1
        
        logger.info(f"[ResponseCache] Cached response for question (hash: {question_hash[:8]}...)")
    
    def _make_response_longer(self, original_response, repeat_count):
        """Make response longer for repeated questions."""
        # Add more detailed explanations for repeated questions
        longer_prefixes = [
            "Since you've asked about this topic again, let me provide you with a more comprehensive explanation:\n\n",
            "Building on our previous discussion, here's a more detailed response:\n\n",
            "As this is an important topic you're revisiting, I'll elaborate further:\n\n",
            "Let me expand on the previous answer with additional details and context:\n\n"
        ]
        
        longer_suffixes = [
            "\n\nIf you need even more specific information about any aspect of this topic, please let me know!",
            "\n\nFeel free to ask follow-up questions if you'd like me to dive deeper into any particular area.",
            "\n\nI hope this expanded explanation helps you better understand this concept.",
            "\n\nWould you like me to provide examples or clarify any specific points in more detail?"
        ]
        
        prefix = longer_prefixes[min(repeat_count - 2, len(longer_prefixes) - 1)]
        suffix = longer_suffixes[min(repeat_count - 2, len(longer_suffixes) - 1)]
        
        return prefix + original_response + suffix
    
    def clear_cache(self):
        """Clear all cached responses."""
        self.cache.clear()
        self.question_frequency.clear()
        logger.info("[ResponseCache] Cache cleared")