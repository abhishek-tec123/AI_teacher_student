"""
AgentConfig dataclass and persona map loader.

Each subject agent in the DB can have persona fields in agent_metadata.
This module builds an in-memory map from agent_id -> persona config.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for a single subject agent's prompt persona."""

    agent_id: str = ""
    agent_name: str = ""
    description: str = ""
    subject: str = ""
    persona_vibe: str = "friendly teacher"
    greeting_style: str = "warm and welcoming"
    closing_style: str = "gentle encouragement"
    response_format_rules: str = ""
    emoji_policy: str = "never"
    example_policy: str = "always give fresh examples, never repeat"
    supports_language: bool = True
    supports_profile: bool = True
    supports_deep_dive: bool = True


def _build_config_from_metadata(agent_id: str, metadata: dict, subject: str = "") -> AgentConfig:
    """Create AgentConfig from raw agent_metadata dict."""
    return AgentConfig(
        agent_id=agent_id,
        agent_name=metadata.get("agent_name", ""),
        description=metadata.get("description", ""),
        subject=subject or metadata.get("subject", ""),
        persona_vibe=metadata.get("persona_vibe", "friendly teacher"),
        greeting_style=metadata.get("greeting_style", "warm and welcoming"),
        closing_style=metadata.get("closing_style", "gentle encouragement"),
        response_format_rules=metadata.get("response_format_rules", ""),
        emoji_policy=metadata.get("emoji_policy", "never"),
        example_policy=metadata.get("example_policy", "always give fresh examples, never repeat"),
    )


# Default persona used when no agent metadata is available
DEFAULT_PERSONA = AgentConfig(
    agent_id="default",
    agent_name="Teacher",
    description="A supportive school teacher",
    persona_vibe="friendly teacher",
    greeting_style="warm and welcoming",
    closing_style="gentle encouragement",
)


_agent_persona_map: Dict[str, AgentConfig] = {}


def get_agent_persona_map() -> Dict[str, AgentConfig]:
    """Return the cached agent persona map. If empty, attempt to load from DB."""
    global _agent_persona_map
    if _agent_persona_map:
        return _agent_persona_map

    try:
        from teacher.repositories.get_agent_data import get_all_agents_data

        agents = get_all_agents_data()
        for agent in agents:
            agent_id = str(agent.get("_id") or agent.get("agent_id", ""))
            if not agent_id:
                continue
            metadata = agent.get("agent_metadata", {})
            subject = agent.get("subject", "")
            _agent_persona_map[agent_id] = _build_config_from_metadata(agent_id, metadata, subject)
        logger.info(f"Loaded {_agent_persona_map} agent personas into map")
    except Exception as e:
        logger.warning(f"Could not load agent personas from DB: {e}")

    return _agent_persona_map


def get_agent_config(agent_id: Optional[str]) -> AgentConfig:
    """Fetch config for a single agent_id. Falls back to DEFAULT_PERSONA."""
    if not agent_id:
        return DEFAULT_PERSONA

    # Check cache first
    if agent_id in _agent_persona_map:
        return _agent_persona_map[agent_id]

    # Try DB lookup
    try:
        from teacher.repositories.get_agent_data import get_agent_data

        agent_data = get_agent_data(agent_id)
        if agent_data:
            metadata = agent_data.get("agent_metadata", {})
            subject = agent_data.get("subject", "")
            config = _build_config_from_metadata(agent_id, metadata, subject)
            _agent_persona_map[agent_id] = config
            return config
    except Exception as e:
        logger.warning(f"Failed to load agent config for {agent_id}: {e}")

    return DEFAULT_PERSONA


def clear_agent_persona_cache():
    """Clear the in-memory cache (useful after agent edits)."""
    global _agent_persona_map
    _agent_persona_map = {}
    logger.info("Cleared agent persona cache")
