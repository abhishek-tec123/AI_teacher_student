"""
PromptBuilder — assembles complete prompts per agent with persona, schema, and freshness.
"""

from typing import Dict, Any, Optional
from common.utils.language_detector import get_language_instruction
from common.prompts.registry import PromptRegistry
from common.prompts.formatters import SchemaFormatter, PersonaFormatter
from common.prompts.agent_configs import get_agent_config, DEFAULT_PERSONA
from common.prompts.schemas import (
    QuizResponse,
    EvaluationScores,
    IntentClassification,
    ConfusionDiagnosis,
)


class PromptBuilder:
    """Builds dynamic prompts per agent using persona config and schema enforcement."""

    def __init__(
        self,
        agent_id: Optional[str] = None,
        student_profile: Optional[dict] = None,
        language: str = "english",
    ):
        self.agent_id = agent_id
        self.student_profile = student_profile or {}
        self.language = language
        self.persona = get_agent_config(agent_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _language_block(self) -> str:
        return get_language_instruction(self.language)

    def _profile_block(self) -> str:
        level = self.student_profile.get("level", "basic")
        tone = self.student_profile.get("tone", "friendly")
        learning_style = self.student_profile.get("learning_style", "step-by-step")
        response_length = self.student_profile.get("response_length", "long")
        include_example = self.student_profile.get("include_example", True)
        common_mistakes = self.student_profile.get("common_mistakes", [])

        lines = [
            "STUDENT PROFILE:",
            f"- Level: {level}",
            f"- Tone: {tone}",
            f"- Learning style: {learning_style}",
            f"- Response length: {response_length}",
            f"- Include example: {include_example}",
            f"- Common mistakes: {common_mistakes}",
        ]
        return "\n".join(lines)

    def _length_block(self, response_length: str, is_deep_dive: bool = False, deep_dive_count: int = 0) -> str:
        if is_deep_dive:
            if deep_dive_count == 1:
                return "\nProvide a MUCH LONGER and MORE DETAILED response than before (4+ paragraphs). Include multiple examples, detailed breakdowns, and broader context.\n"
            elif deep_dive_count == 2:
                return "\nProvide a VERY LONG and DETAILED response (6+ paragraphs). Go deep using your knowledge. Bring genuinely NEW insights and depth.\n"
            else:
                return "\nProvide a DETAILED response (4+ paragraphs) with new angles and insights. Keep it fresh with minor changes in angle.\n"
        elif response_length == "short":
            return "\n" + PromptRegistry.get_template("length_short") + "\n"
        elif response_length == "medium":
            return "\n" + PromptRegistry.get_template("length_medium") + "\n"
        else:
            return "\n" + PromptRegistry.get_template("length_very_long") + "\n"

    def _deep_dive_block(self, level: int, topic: str) -> str:
        if level == 1:
            return PromptRegistry.render("deep_dive_level_1", topic=topic)
        elif level == 2:
            return PromptRegistry.render("deep_dive_level_2", topic=topic)
        else:
            return PromptRegistry.render("deep_dive_level_3", topic=topic)

    def _global_prompt_block(self) -> str:
        try:
            from admin.services.global_prompts_service import get_highest_priority_enabled_prompt
            gp = get_highest_priority_enabled_prompt()
            if gp:
                return gp.get("content", "")
        except Exception:
            pass
        return ""

    def _global_rag_block(self) -> str:
        try:
            from admin.services.global_settings_service import get_global_rag_settings
            settings = get_global_rag_settings()
            if settings.get("enabled", False) and settings.get("content", ""):
                return f"\n\n--- GLOBAL RAG CONTEXT ---\n{settings['content']}\n--- END GLOBAL RAG CONTEXT ---\n"
        except Exception:
            pass
        return ""

    def _persona_identity_block(self) -> str:
        return PersonaFormatter.to_identity_block(self.persona.__dict__)

    def _freshness_block(self) -> str:
        return PersonaFormatter.to_freshness_block()

    # ------------------------------------------------------------------
    # Public build methods
    # ------------------------------------------------------------------

    def build_teacher_prompt(
        self,
        *,
        class_name: str,
        subject: str,
        confusion_type: str,
        session_context: str,
        current_query: str,
        is_deep_dive: bool = False,
        deep_dive_topic: Optional[str] = None,
        deep_dive_count: int = 0,
        is_practice: bool = False,
        inferred_topic: Optional[str] = None,
    ) -> str:
        """Assemble the full teacher prompt with persona, freshness, and inferred topic."""
        parts = []

        # 1. Base prompt
        parts.append(PromptRegistry.render("base_teacher", subject=subject))

        # 2. Global prompt
        global_prompt = self._global_prompt_block()
        if global_prompt:
            parts.append(global_prompt)

        # 3. Persona identity
        parts.append(self._persona_identity_block())

        # 4. Language
        parts.append(self._language_block())

        # 5. Profile
        parts.append(self._profile_block())

        # 6. Context
        parts.append(f"\nCLASS: {class_name}")
        parts.append(f"SUBJECT: {subject}")
        parts.append(f"DETECTED CONFUSION: {confusion_type}")

        if inferred_topic:
            parts.append(f"\nINFERRED TOPIC: {inferred_topic}")
            parts.append("If the student's query is vague, assume they are asking about this topic.")

        # 7. Format rules
        parts.append(PromptRegistry.render("teacher_format_rules", is_practice=is_practice))

        # 8. Length
        response_length = self.student_profile.get("response_length", "long")
        parts.append(self._length_block(response_length, is_deep_dive, deep_dive_count))

        # 9. Deep dive
        if is_deep_dive:
            topic = deep_dive_topic or current_query
            parts.append(self._deep_dive_block(deep_dive_count or 1, topic))

        # 10. Freshness
        parts.append(self._freshness_block())

        # 11. Global RAG
        parts.append(self._global_rag_block())

        # 12. Session context
        if session_context:
            parts.append(f"\nPrevious conversation (Last 20 turns for context only):\n{session_context}\n")

        # 13. Final query
        parts.append(f"\nOriginal Student Question:\n{current_query}\n")

        return "\n".join(parts).strip()

    def build_greeting_prompt(
        self,
        *,
        is_formal: bool = False,
    ) -> str:
        """Build a greeting prompt with persona and language."""
        identity = self._persona_identity_block()
        language = self._language_block()

        if is_formal and self.persona.agent_name:
            return PromptRegistry.render(
                "greeting_formal",
                identity_block=identity,
                language_instruction=language,
            )
        return PromptRegistry.render(
            "greeting_casual",
            language_instruction=language,
        )

    def build_general_chat_prompt(self) -> str:
        """Build a general (non-academic) chat prompt."""
        return PromptRegistry.render(
            "general_chat",
            language_instruction=self._language_block(),
        )

    def build_quiz_prompt(
        self,
        *,
        conversation_text: str,
        topic: Optional[str],
        num_questions: int,
        is_retry: bool = False,
    ) -> str:
        """Build a quiz generation prompt with schema enforcement."""
        topic_instruction = (
            f"The quiz MUST be strictly about this topic: {topic}.\n"
            f"Focus on concepts discussed in the student's learning history.\n"
            if topic
            else "The quiz should be based on the student's recent learning conversations.\n"
        )

        schema_instruction = SchemaFormatter.to_prompt_instruction(QuizResponse)
        template_name = "quiz_retry" if is_retry else "quiz_generation"

        return PromptRegistry.render(
            template_name,
            num_questions=num_questions,
            topic_instruction=topic_instruction,
            conversation_text=conversation_text,
            schema_instruction=schema_instruction,
            topic=topic or "the student's recent learning",
        )

    def build_evaluation_prompt(
        self,
        *,
        query: str,
        response: str,
        subject: str,
        confusion_type: Optional[str],
    ) -> str:
        """Build an evaluation prompt with schema enforcement."""
        schema_instruction = SchemaFormatter.to_prompt_instruction(EvaluationScores)

        return PromptRegistry.render(
            "evaluation",
            query=query,
            subject=subject,
            level=self.student_profile.get("level", "unknown"),
            learning_style=self.student_profile.get("learning_style", "unknown"),
            include_example=self.student_profile.get("include_example", False),
            tone=self.student_profile.get("tone", "neutral"),
            response_length=self.student_profile.get("response_length", "unspecified"),
            confusion_type=confusion_type or "None",
            response=response,
            schema_instruction=schema_instruction,
        )

    def build_study_plan_prompt(
        self,
        *,
        topic: str,
        session_context: str,
        profile_hint: str,
    ) -> str:
        """Build a study plan prompt."""
        return PromptRegistry.render(
            "study_plan",
            topic=topic,
            session_context=session_context,
            profile_hint=profile_hint,
        )

    def build_notes_prompt(
        self,
        *,
        topic: str,
        history_text: str,
        profile_hint: str,
    ) -> str:
        """Build a notes generation prompt."""
        return PromptRegistry.render(
            "notes_generation",
            topic=topic,
            history_text=history_text,
            profile_hint=profile_hint,
        )

    def build_summary_prompt(
        self,
        *,
        topic: str,
        history_text: str,
        profile_hint: str,
    ) -> str:
        """Build a summary generation prompt."""
        return PromptRegistry.render(
            "summary_generation",
            topic=topic,
            history_text=history_text,
            profile_hint=profile_hint,
        )

    def build_intent_classification_prompt(
        self,
        *,
        query: str,
        current_subject: Optional[str],
    ) -> str:
        """Build an intent classification prompt with schema enforcement."""
        schema_instruction = SchemaFormatter.to_prompt_instruction(IntentClassification)
        return PromptRegistry.render(
            "intent_classification",
            current_subject=current_subject,
            schema_instruction=schema_instruction,
        )

    def build_confusion_diagnosis_prompt(
        self,
        *,
        question: str,
        subject: str,
        class_name: str,
    ) -> str:
        """Build a confusion diagnosis prompt with schema enforcement."""
        schema_instruction = SchemaFormatter.to_prompt_instruction(ConfusionDiagnosis)
        return PromptRegistry.render(
            "confusion_diagnosis",
            question=question,
            subject=subject,
            class_name=class_name,
            schema_instruction=schema_instruction,
        )

    def build_session_summary_prompt(
        self,
        *,
        previous_summary: str,
        new_conversation: str,
    ) -> str:
        """Build a session summary prompt."""
        return PromptRegistry.render(
            "session_summary",
            previous_summary=previous_summary,
            new_conversation=new_conversation,
        )

    def build_topic_inference_prompt(
        self,
        *,
        conversation_text: str,
    ) -> str:
        """Build a lightweight topic inference prompt."""
        return PromptRegistry.render(
            "topic_inference",
            conversation_text=conversation_text,
        )
