"""
Pydantic schemas for agents that return structured data (JSON).
Injected into prompts as JSON Schema instructions.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class QuizItem(BaseModel):
    question: str = Field(..., description="The quiz question text")
    options: list[str] = Field(
        ..., min_length=4, max_length=4, description="Exactly 4 answer choices"
    )
    answer: str = Field(..., description="The correct option, must match one of the options")


class QuizResponse(BaseModel):
    quiz: list[QuizItem] = Field(..., description="List of quiz questions")


class EvaluationScores(BaseModel):
    pedagogical_value: float = Field(..., ge=0.0, le=1.0)
    critical_confidence: float = Field(..., ge=0.0, le=1.0)
    rag_relevance: float = Field(..., ge=0.0, le=1.0)
    answer_completeness: float = Field(..., ge=0.0, le=1.0)
    hallucination_risk: float = Field(..., ge=0.0, le=1.0)


class IntentClassification(BaseModel):
    intent: Literal["QUIZ", "STUDY_PLAN", "NOTES", "SUMMARY", "CHAT"] = Field(...)
    topic: Optional[str] = Field(None, description="Extracted main topic or null")
    confidence: float = Field(..., ge=0.0, le=1.0)


class ConfusionDiagnosis(BaseModel):
    confusion_type: Literal[
        "NO_CONFUSION", "CONCEPT_GAP", "FORMULA_CONFUSION", "PROCEDURAL_ERROR"
    ] = Field(...)
    reason: str = Field(...)
    teaching_strategy: str = Field(...)


class StudyPlanSection(BaseModel):
    title: str = Field(...)
    subtopics: list[str] = Field(...)
    explanation: str = Field(...)


class StudyPlanResponse(BaseModel):
    main_topic: str = Field(...)
    sections: list[StudyPlanSection] = Field(...)
