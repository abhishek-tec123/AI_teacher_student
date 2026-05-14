"""
Utility to update agent performance after each conversation
"""

from .agent_performance_monitor import AgentPerformanceMonitor
import logging
logger = logging.getLogger(__name__)

def update_agent_performance_after_query(
    subject_agent_id: str, 
    quality_scores: dict, 
    feedback: str = "neutral", 
    confusion_type: str = "NO_CONFUSION"
) -> bool:
    """
    Update agent performance metrics after each conversation.
    
    Call this function after each agent query to maintain cumulative performance data.
    
    Args:
        subject_agent_id: The agent ID
        quality_scores: Dictionary with pedagogical_value, critical_confidence, etc.
        feedback: Student feedback (like/dislike/neutral)
        confusion_type: Detected confusion type
    
    Returns:
        bool: True if update successful, False otherwise
    """
    try:
        monitor = AgentPerformanceMonitor()
        return monitor.update_agent_performance(
            subject_agent_id=subject_agent_id,
            quality_scores=quality_scores,
            feedback=feedback,
            confusion_type=confusion_type
        )
    except Exception as e:
        logger.info(f"Error updating agent performance: {e}")
        return False

# Example usage in conversation handler:
# 
# def handle_conversation(student_id, subject_agent_id, query, response):
#     # ... your conversation logic ...
#     
#     # Get quality scores from evaluation
#     quality_scores = evaluate_response(...)
#     
#     # Update agent performance
#     update_agent_performance_after_query(
#         subject_agent_id=subject_agent_id,
#         quality_scores=quality_scores,
#         feedback=student_feedback,
#         confusion_type=detected_confusion
#     )
