"""
Tsushin Tone Preset Seeding Service

Creates default system tone presets during database initialization.
These presets are shared across all tenants (tenant_id=None, is_system=True)
and appear in the "Tone Presets" section of Settings > Prompts.

Default Tone Presets:
- Friendly: Warm, approachable with emojis
- Professional: Formal, detailed, structured
- Casual: Laid-back, informal, conversational
- Multilingual: Adapts language to user's input

Usage:
    from services.tone_preset_seeding import seed_default_tone_presets
    seed_default_tone_presets(db)
"""

from sqlalchemy.orm import Session
from typing import List
import logging

from models import TonePreset

logger = logging.getLogger(__name__)


def seed_default_tone_presets(db: Session) -> List[dict]:
    """
    Create default system tone presets (shared across all tenants).

    These presets have is_system=True and tenant_id=None, making them
    available as templates for all tenants.

    This function will add any missing presets without duplicating existing ones.

    Args:
        db: Database session

    Returns:
        List of dictionaries with created preset details
    """
    # Get existing system preset names
    existing_names = set(
        name for (name,) in db.query(TonePreset.name)
        .filter(TonePreset.is_system == True)
        .all()
    )

    default_presets = [
        {
            "name": "Friendly",
            "description": "Be warm, friendly, and approachable. Use casual language and emojis when appropriate. Keep responses conversational and helpful. Show empathy and enthusiasm.",
        },
        {
            "name": "Professional",
            "description": "Be formal, precise, and professional. Provide well-structured, detailed responses. Avoid casual language, slang, or emojis. Maintain an objective and authoritative tone.",
        },
        {
            "name": "Casual",
            "description": "Be relaxed and informal, like chatting with a friend. Use conversational language and feel free to be humorous when appropriate. Keep things light and relatable.",
        },
        {
            "name": "Multilingual",
            "description": "Automatically detect and respond in the same language the user is communicating. If they write in Portuguese, respond in Portuguese. If in English, respond in English. Adapt your cultural references and expressions to match the detected language.",
        },
    ]

    created_presets = []

    try:
        for preset_data in default_presets:
            # Skip if already exists
            if preset_data["name"] in existing_names:
                continue

            preset = TonePreset(
                name=preset_data["name"],
                description=preset_data["description"],
                is_system=True,
                tenant_id=None,  # Shared across all tenants
            )
            db.add(preset)

            created_presets.append({
                "name": preset_data["name"],
                "description": preset_data["description"]
            })

            logger.info(f"Created system tone preset: {preset_data['name']}")

        db.commit()
        logger.info(f"Successfully seeded {len(created_presets)} default tone presets")
        return created_presets

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to seed default tone presets: {e}", exc_info=True)
        raise
