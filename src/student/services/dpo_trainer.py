import logging
import os
import sys
from typing import List, Dict, Any, Tuple
from datetime import datetime
from bson import ObjectId

# Add paths

from student.repositories.student_repository import StudentManager
from student.agents.rl_optimizer import RLOptimizer
logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO)

def extract_preference_pairs(student_manager: StudentManager):
    """
    Extracts winning and losing actions from conversation history.
    """
    preference_dataset = []
    
    # Iterate through all students
    all_students = student_manager.students.find({})
    
    for student in all_students:
        history = student.get("conversation_history", {})
        
        # Group by subject
        for subject, turns in history.items():
            # For each turn, check for RL metadata and feedback
            for turn in turns:
                rl_meta = turn.get("rl_metadata", {})
                trajectory = rl_meta.get("trajectory", [])
                feedback = turn.get("feedback", "neutral")
                
                if not trajectory or feedback == "neutral":
                    continue
                
                # We consider the last action in the trajectory as the 'impact' action
                # (e.g., if we rewritten the query and it led to a good response)
                # For simplicity, we'll take the first non-generic action
                actions = [a for a in trajectory if a != "generate_response"]
                if not actions:
                    continue
                    
                action = actions[0] # The primary decision made
                
                # Mock state for key generation
                # We need the same state logic as RLOptimizer
                state = {
                    "student_profile": {
                        "last_intent": turn.get("intent", "chat"),
                        "common_mistakes": [turn.get("confusion_type")] if turn.get("confusion_type") != "NO_CONFUSION" else []
                    }
                }
                
                preference_dataset.append({
                    "state": state,
                    "action": action,
                    "feedback": feedback
                })
                
    return preference_dataset

def train_dpo():
    """
    Main training loop.
    """
    sm = StudentManager()
    optimizer = RLOptimizer()
    
    dataset = extract_preference_pairs(sm)
    logger.info(f"Extracted {len(dataset)} recorded turns with feedback.")
    
    # Simple pairing: Compare Likes vs Dislikes within the same state key
    by_state = {}
    for entry in dataset:
        key = optimizer._get_state_key(entry["state"])
        if key not in by_state:
            by_state[key] = {"liked": [], "disliked": []}
        
        if entry["feedback"] == "like":
            by_state[key]["liked"].append(entry["action"])
        elif entry["feedback"] == "dislike":
            by_state[key]["disliked"].append(entry["action"])
            
    # Apply DPO updates
    updates = 0
    for key, data in by_state.items():
        # For every liked action and every disliked action in this state...
        for winner in data["liked"]:
            for loser in data["disliked"]:
                # The state should be roughly the same
                mock_state = {"student_profile": {"last_intent": key.split(":")[0], "common_mistakes": key.split(":")[1].split("|") if key.split(":")[1] != "none" else []}}
                optimizer.train_on_preferences(mock_state, winner, loser)
                updates += 1
                
    logger.info(f"DPO Training Complete. Applied {updates} preference updates.")

if __name__ == "__main__":
    train_dpo()
