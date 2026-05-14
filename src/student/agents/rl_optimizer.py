import os
import random
import json
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from student.services.generate_response import generate_response_with_groq
import logging
logger = logging.getLogger(__name__)


class RLOptimizer:
    """
    RL-based optimizer for refining query processing and retrieval.
    """
    
    ACTION_SPACE = ["rewrite_query", "expand_context", "filter_context", "generate_response"]
    
    def __init__(self, epsilon: float = 0.2, weights_path: str = "policy_weights.json"):
        self.epsilon = epsilon
        self.weights_path = weights_path
        self.policy_weights = self._load_weights()

    def _load_weights(self) -> Dict[str, Dict[str, float]]:
        """Load weights from local file or return default."""
        if os.path.exists(self.weights_path):
            try:
                with open(self.weights_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load weights: {e}")
        
        # Default weights: Uniformly initialized to 0.0 (log-probs)
        return {"default": {action: 0.0 for action in self.ACTION_SPACE}}

    def _save_weights(self):
        """Save current weights to local file."""
        try:
            with open(self.weights_path, 'w') as f:
                json.dump(self.policy_weights, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save weights: {e}")

    def _get_state_key(self, state: Dict[str, Any]) -> str:
        """Generate a hashable key for the state to lookup weights."""
        # Focus on Intent and Confusion Type for simple discretization
        # In a real system, this would be a vector embedding
        intent = state.get("student_profile", {}).get("last_intent", "chat")
        confusion = state.get("student_profile", {}).get("common_mistakes", [])
        confusion_key = "|".join(sorted(confusion)) if confusion else "none"
        return f"{intent}:{confusion_key}"
        
    def select_action(self, state: Dict[str, Any]) -> str:
        """
        Policy network: Epsilon-greedy with Learned Preferences.
        """
        # 1. Epsilon-greedy exploration
        if random.random() < self.epsilon:
            action = random.choice(self.ACTION_SPACE)
            logger.info(f"RL: Exploring action -> {action}")
            return action
            
        # 2. Hybrid Policy (Heuristics + Learned Preferences)
        state_key = self._get_state_key(state)
        weights = self.policy_weights.get(state_key, self.policy_weights["default"])
        
        # Convert log-weights to probabilities (Softmax)
        exp_weights = {a: np.exp(w) for a, w in weights.items()}
        total = sum(exp_weights.values())
        probs = {a: v / total for a, v in exp_weights.items()}
        
        # Sort actions by probability
        sorted_actions = sorted(self.ACTION_SPACE, key=lambda a: probs[a], reverse=True)
        
        previous_actions = state.get("previous_actions", [])
        
        # Apply heuristics first (sanity check)
        if not state.get("context"):
            if "rewrite_query" not in previous_actions: return "rewrite_query"
            if "expand_context" not in previous_actions: return "expand_context"
            
        # If heuristics are satisfied, pick according to learned probabilities
        # We filter out already taken actions to avoid loops
        for action in sorted_actions:
            if action not in previous_actions:
                return action
                
        return "generate_response"

    def train_on_preferences(self, state: Dict[str, Any], winner: str, loser: str, lr: float = 0.1):
        """
        Simple DPO-inspired weight update.
        Increases score of 'winner' and decreases 'loser'.
        """
        state_key = self._get_state_key(state)
        if state_key not in self.policy_weights:
            self.policy_weights[state_key] = self.policy_weights["default"].copy()
            
        # Gradient ascent step on the preference
        self.policy_weights[state_key][winner] += lr
        self.policy_weights[state_key][loser] -= lr
        
        logger.info(f"DPO Update [{state_key}]: {winner} > {loser}")
        self._save_weights()

    def calculate_reward(self, feedback: Optional[str], quality_scores: Dict[str, Any]) -> float:
        """
        Calculate reward based on student feedback and system quality scores.
        """
        reward = 0.0
        
        # Primary signal: Human feedback
        if feedback == "like":
            reward += 1.0
        elif feedback == "dislike":
            reward -= 1.0
            
        # Secondary signal: Quality scores (normalized to 0.0 - 1.0 range)
        # We weigh them less than direct human feedback
        if quality_scores:
            rag_relevance = quality_scores.get("rag_relevance", 0) / 100.0
            completeness = quality_scores.get("answer_completeness", 0) / 100.0
            hallucination = quality_scores.get("hallucination_risk", 0) / 100.0
            
            reward += (rag_relevance * 0.2) + (completeness * 0.2) - (hallucination * 0.1)
            
        return round(reward, 3)

    def rewrite_query(self, query: str, context_text: str = "") -> str:
        """
        Action: Rewrite the query for better retrieval.
        """
        prompt = """Rewrite the student query for textbook search. 
Rules:
1. If the query is a clear standalone topic (e.g., 'Thermodynamics', 'Photosynthesis'), preserve it as is or add only academic specificity. 
2. Only use the provided context to disambiguate vague snippets (e.g., 'examples' -> 'examples of [last mentioned topic]'). 
3. DO NOT carry over previous topics if the new query is a shift in subject.
Output ONLY the rewritten query text."""
        if context_text:
            prompt += f"\nRecent Context:\n{context_text[:500]}"
            
        try:
            rewritten = generate_response_with_groq(query=query, system_prompt=prompt)
            logger.info(f"RL Action: Rewritten query -> {rewritten}")
            return rewritten
        except Exception as e:
            logger.error(f"RL Action Error: Failed to rewrite query: {e}")
            return query

    def filter_context(self, query: str, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Action: Filter out irrelevant chunks.
        """
        if not chunks:
            return []
            
        # Simple heuristic: sort by score and take top 5 if too many
        filtered = sorted(chunks, key=lambda x: x.get("score", 0), reverse=True)[:5]
        logger.info(f"RL Action: Filtered {len(chunks)} chunks down to {len(filtered)}")
        return filtered

    def define_state(
        self,
        query: str, 
        context_chunks: List[Any], 
        student_profile: Dict[str, Any],
        rewritten_query: str = None, 
        previous_responses: List[str] = None, 
        previous_actions: List[str] = None,
        previous_rewards: List[float] = None
    ) -> Dict[str, Any]:
        """
        Define the state representation for the reinforcement learning agent.
        """
        state = {
            "original_query": query,                                    # The initial query from the user
            "current_query": rewritten_query if rewritten_query else query,  # Current version of the query (may be rewritten)
            "context": context_chunks,                                 # Retrieved context chunks (mapped from user's 'context')
            "student_profile": student_profile,                         # Added for personalization logic
            "previous_responses": previous_responses if previous_responses else [],  # History of generated responses
            "previous_actions": previous_actions if previous_actions else [],       # Track taken actions
            "previous_rewards": previous_rewards if previous_rewards else []         # History of received rewards
        }
        return state
