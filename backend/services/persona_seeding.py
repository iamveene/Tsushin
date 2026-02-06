"""
Tsushin Persona Seeding Service

Creates default system personas during database initialization.
These personas are shared across all tenants (tenant_id=None) and
appear in the "Persona Template Library" in the Studio.

Default Personas:
- Friendly Assistant (warm, approachable, uses emojis)
- Professional Expert (formal, detailed, structured)
- Neutral Helper (balanced, general-purpose)
- Casual Buddy (laid-back, informal, slang-friendly)

Usage:
    from services.persona_seeding import seed_default_personas
    seed_default_personas(db)
"""

from sqlalchemy.orm import Session
from typing import List
import logging

from models import Persona

logger = logging.getLogger(__name__)


def seed_default_personas(db: Session) -> List[dict]:
    """
    Create default system personas (shared across all tenants).

    These personas have is_system=True and tenant_id=None, making them
    available as templates for all tenants to clone.

    Args:
        db: Database session

    Returns:
        List of dictionaries with created persona details
    """
    # Check if already seeded
    existing = db.query(Persona).filter(Persona.is_system == True).first()
    if existing:
        logger.info("Default personas already exist, skipping seed")
        return []

    default_personas = [
        {
            "name": "Friendly Assistant",
            "description": "A warm, approachable assistant that uses casual language and emojis",
            "custom_tone": "Be warm, friendly, and use emojis when appropriate. Keep responses conversational and helpful.",
            "personality_traits": "Empathetic, patient, enthusiastic, supportive",
        },
        {
            "name": "Professional Expert",
            "description": "A formal, knowledgeable expert providing detailed, structured responses",
            "custom_tone": "Be professional, formal, and precise. Provide well-structured, detailed responses without casual language.",
            "personality_traits": "Analytical, thorough, objective, authoritative",
        },
        {
            "name": "Neutral Helper",
            "description": "A balanced, helpful assistant with neutral tone - ideal for general-purpose use",
            "custom_tone": "Be helpful, clear, and balanced. Maintain a neutral, professional-yet-friendly tone.",
            "personality_traits": "Balanced, clear, efficient, adaptable",
        },
        {
            "name": "Casual Buddy",
            "description": "A laid-back, informal friend who chats casually and uses slang",
            "custom_tone": "Be casual, relaxed, and use informal language like you're chatting with a friend. Feel free to use slang and be conversational.",
            "personality_traits": "Relaxed, humorous, informal, relatable",
        }
    ]

    created_personas = []

    try:
        for persona_data in default_personas:
            persona = Persona(
                name=persona_data["name"],
                description=persona_data["description"],
                custom_tone=persona_data["custom_tone"],
                personality_traits=persona_data["personality_traits"],
                is_system=True,
                is_active=True,
                tenant_id=None,  # Shared across all tenants
                enabled_skills=[],
                enabled_sandboxed_tools=[],
                enabled_knowledge_bases=[],
            )
            db.add(persona)

            created_personas.append({
                "name": persona_data["name"],
                "description": persona_data["description"]
            })

            logger.info(f"✓ Created system persona: {persona_data['name']}")

        db.commit()
        logger.info(f"Successfully seeded {len(created_personas)} default personas")
        return created_personas

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to seed default personas: {e}", exc_info=True)
        raise
