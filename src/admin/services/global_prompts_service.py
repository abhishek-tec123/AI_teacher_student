"""
Global Prompts Management Module
Handles in-memory storage and management of universal teaching rules/prompts.
"""

import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import os
import logging
logger = logging.getLogger(__name__)


# In-memory storage for global prompts
GLOBAL_PROMPTS: Dict[str, Dict[str, Any]] = {}

# File for persistence (optional)
PROMPTS_FILE = "global_prompts_backup.json"

def load_prompts_from_file():
    """Load prompts from backup file if it exists."""
    try:
        if os.path.exists(PROMPTS_FILE):
            with open(PROMPTS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                GLOBAL_PROMPTS.update(data)
                logger.info(f"Loaded {len(GLOBAL_PROMPTS)} prompts from backup file")
    except Exception as e:
        logger.warning(f"Failed to load prompts from backup file: {e}")

def save_prompts_to_file():
    """Save prompts to backup file."""
    try:
        with open(PROMPTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(GLOBAL_PROMPTS, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(GLOBAL_PROMPTS)} prompts to backup file")
    except Exception as e:
        logger.warning(f"Failed to save prompts to backup file: {e}")

def create_global_prompt(name: str, content: str, priority: int = 1, version: str = "v1") -> Dict[str, Any]:
    """Create a new global prompt."""
    prompt_id = str(uuid.uuid4())
    
    prompt = {
        "id": prompt_id,
        "name": name,
        "content": content,
        "priority": priority,
        "enabled": False,  # Disabled by default
        "version": version,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }
    
    GLOBAL_PROMPTS[prompt_id] = prompt
    save_prompts_to_file()
    
    logger.info(f"Created global prompt '{name}' with ID: {prompt_id}")
    return prompt

def get_all_prompts() -> List[Dict[str, Any]]:
    """Get all global prompts."""
    return list(GLOBAL_PROMPTS.values())

def get_prompt_by_id(prompt_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific prompt by ID."""
    return GLOBAL_PROMPTS.get(prompt_id)

def update_prompt(prompt_id: str, **kwargs) -> Optional[Dict[str, Any]]:
    """Update a global prompt."""
    if prompt_id not in GLOBAL_PROMPTS:
        return None
    
    prompt = GLOBAL_PROMPTS[prompt_id]
    
    # Update allowed fields
    allowed_fields = ["name", "content", "priority", "version"]
    for field, value in kwargs.items():
        if field in allowed_fields:
            prompt[field] = value
    
    prompt["updated_at"] = datetime.now().isoformat()
    save_prompts_to_file()
    
    logger.info(f"Updated global prompt '{prompt.get('name')}' with ID: {prompt_id}")
    return prompt

def delete_prompt(prompt_id: str) -> bool:
    """Delete a global prompt."""
    if prompt_id not in GLOBAL_PROMPTS:
        return False
    
    prompt_name = GLOBAL_PROMPTS[prompt_id].get("name", "Unknown")
    del GLOBAL_PROMPTS[prompt_id]
    save_prompts_to_file()
    
    logger.info(f"Deleted global prompt '{prompt_name}' with ID: {prompt_id}")
    return True

def enable_prompt(prompt_id: str) -> Optional[Dict[str, Any]]:
    """Enable a global prompt."""
    if prompt_id not in GLOBAL_PROMPTS:
        return None
    
    GLOBAL_PROMPTS[prompt_id]["enabled"] = True
    GLOBAL_PROMPTS[prompt_id]["updated_at"] = datetime.now().isoformat()
    save_prompts_to_file()
    
    prompt_name = GLOBAL_PROMPTS[prompt_id].get("name", "Unknown")
    logger.info(f"Enabled global prompt '{prompt_name}' with ID: {prompt_id}")
    return GLOBAL_PROMPTS[prompt_id]

def disable_prompt(prompt_id: str) -> Optional[Dict[str, Any]]:
    """Disable a global prompt."""
    if prompt_id not in GLOBAL_PROMPTS:
        return None
    
    GLOBAL_PROMPTS[prompt_id]["enabled"] = False
    GLOBAL_PROMPTS[prompt_id]["updated_at"] = datetime.now().isoformat()
    save_prompts_to_file()
    
    prompt_name = GLOBAL_PROMPTS[prompt_id].get("name", "Unknown")
    logger.info(f"Disabled global prompt '{prompt_name}' with ID: {prompt_id}")
    return GLOBAL_PROMPTS[prompt_id]

def get_enabled_prompts() -> List[Dict[str, Any]]:
    """Get all enabled prompts sorted by priority."""
    enabled = [p for p in GLOBAL_PROMPTS.values() if p.get("enabled", False)]
    return sorted(enabled, key=lambda x: x.get("priority", 999))

def get_highest_priority_enabled_prompt() -> Optional[Dict[str, Any]]:
    """Get the highest priority enabled prompt."""
    enabled_prompts = get_enabled_prompts()
    return enabled_prompts[0] if enabled_prompts else None

def initialize_default_prompts():
    """Initialize some default prompts if none exist."""
    if not GLOBAL_PROMPTS:
        # Create default prompts based on the frontend examples
        default_prompts = [
            {
                "name": "Respectful Communication",
                "content": "Always communicate respectfully with students. Use encouraging language and avoid criticism.",
                "priority": 1,
                "version": "v3"
            },
            {
                "name": "Safety Guidelines", 
                "content": "Never provide content that is harmful, inappropriate, or off-topic. Redirect to learning materials.",
                "priority": 3,
                "version": "v1"
            }
        ]
        
        for prompt_data in default_prompts:
            prompt = create_global_prompt(**prompt_data)
            # Enable the first prompt by default
            if prompt_data["name"] == "Respectful Communication":
                enable_prompt(prompt["id"])
        
        logger.info("Initialized default global prompts")

# Initialize the module
load_prompts_from_file()
initialize_default_prompts()
