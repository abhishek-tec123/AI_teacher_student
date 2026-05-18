"""
Formatters that convert Pydantic models and persona configs into
prompt-friendly instruction blocks.
"""

import json
from typing import Type
from pydantic import BaseModel


class SchemaFormatter:
    """Converts a Pydantic model into a strict JSON Schema instruction block."""

    @staticmethod
    def to_prompt_instruction(model: Type[BaseModel]) -> str:
        schema = model.model_json_schema()
        return (
            "\n---\n"
            "STRICT OUTPUT FORMAT:\n"
            "You MUST respond with valid JSON matching this schema exactly.\n"
            "Do NOT include markdown code fences (```json), explanations, or any text outside the JSON.\n\n"
            f"JSON Schema:\n{json.dumps(schema, indent=2)}\n"
        )


class PersonaFormatter:
    """Converts persona config dict into a natural-language identity block."""

    @staticmethod
    def to_identity_block(persona: dict) -> str:
        agent_name = persona.get("agent_name", "")
        description = persona.get("description", "")
        vibe = persona.get("persona_vibe", "")
        greeting_style = persona.get("greeting_style", "")
        closing_style = persona.get("closing_style", "")
        format_rules = persona.get("response_format_rules", "")
        subject = persona.get("subject", "")

        lines = ["IDENTITY:"]
        if agent_name:
            lines.append(f"- Name: {agent_name}")
        if description:
            lines.append(f"- Role: {description}")
        if vibe:
            lines.append(f"- Vibe: {vibe}")
        if subject:
            lines.append(f"- Subject Specialty: {subject}")

        lines.append("\nGREETING RULES:")
        if greeting_style:
            lines.append(f"- Default greeting style: {greeting_style}")
        lines.append("- Use your OWN words. NEVER copy a fixed script.")
        lines.append("- Vary your greeting each time.")
        lines.append("- Match your tone to your vibe.")

        lines.append("\nCLOSING RULES:")
        if closing_style:
            lines.append(f"- Default closing style: {closing_style}")
        lines.append("- Alternate between: encouragement, a subject teaser, a simple offer, or omit a closing.")
        lines.append('- NEVER use the same closing twice in a row.')
        lines.append('- NEVER use generic praise like "You\'re doing great" more than once per session.')

        if format_rules:
            lines.append(f"\nFORMAT RULES:\n{format_rules}")

        return "\n".join(lines)

    @staticmethod
    def to_freshness_block() -> str:
        return (
            "\nFRESHNESS RULES:\n"
            "- Do NOT repeat the same opening or closing from previous turns.\n"
            '- Do NOT use generic praise like "You\'re doing great" more than once per session.\n'
            "- If you used an analogy in the previous turn, use a different one now.\n"
            "- If you used a real-life example before, pick a new domain.\n"
            "- Vary sentence structure and phrasing so responses never feel copied.\n"
        )
