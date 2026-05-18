"""
Dynamic Prompts Package

Provides registry, builder, schemas, and formatters for agent-specific,
dynamically-generated prompts with no hardcoded examples.
"""

from .registry import PromptRegistry
from .builder import PromptBuilder
from .schemas import (
    QuizItem,
    QuizResponse,
    EvaluationScores,
    IntentClassification,
    ConfusionDiagnosis,
    StudyPlanSection,
    StudyPlanResponse,
)
from .topic_inference import infer_topic_from_history
from .agent_configs import AgentConfig, get_agent_persona_map, DEFAULT_PERSONA

__all__ = [
    "PromptRegistry",
    "PromptBuilder",
    "QuizItem",
    "QuizResponse",
    "EvaluationScores",
    "IntentClassification",
    "ConfusionDiagnosis",
    "StudyPlanSection",
    "StudyPlanResponse",
    "infer_topic_from_history",
    "AgentConfig",
    "get_agent_persona_map",
    "DEFAULT_PERSONA",
]
