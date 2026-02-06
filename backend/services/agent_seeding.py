"""
Tsushin Agent Seeding Service
Phase 1: Backend Setup

Creates default system agents during installation:
- Tsushin (General Assistant)
- Kokoro (Voice Assistant - Kokoro TTS, free/local)
- Kira (Voice Assistant - OpenAI TTS)
- Transcript (Audio Transcription)
- Shellboy (Remote Commands via Beacon)
- CustomerService (Customer Support)

Usage:
    from services.agent_seeding import seed_default_agents
    agent_ids = seed_default_agents(tenant_id, user_id, db)
"""

from sqlalchemy.orm import Session
from typing import List, Optional
import logging

from models import Contact, Agent, AgentSkill

logger = logging.getLogger(__name__)


def _get_agent_switcher_config(model_name: str) -> dict:
    """Standard agent_switcher skill config."""
    return {
        "keywords": ["invoke", "invocar"],
        "use_ai_fallback": True,
        "ai_model": model_name
    }


def _get_flows_skill_config(model_name: str) -> dict:
    """Standard flows skill config with all capabilities."""
    return {
        "keywords": [
            "lembrete", "lembrar", "lembre", "lembra",
            "reminder", "remind", "flows", "flow"
        ],
        "use_ai_fallback": True,
        "ai_model": model_name,
        "capabilities": {
            "create_notification": {
                "enabled": True,
                "label": "Create Notifications (Reminders)",
                "description": "Schedule single-message reminders"
            },
            "create_conversation": {
                "enabled": True,
                "label": "Create Conversations",
                "description": "Schedule multi-turn AI conversations"
            },
            "query_events": {
                "enabled": True,
                "label": "Query Events",
                "description": "List and search scheduled events"
            },
            "update_events": {
                "enabled": True,
                "label": "Update Events",
                "description": "Modify existing scheduled events"
            },
            "delete_events": {
                "enabled": True,
                "label": "Delete Events",
                "description": "Cancel scheduled events"
            }
        }
    }


def seed_default_agents(
    tenant_id: str,
    user_id: int,
    db: Session,
    model_provider: str = "gemini",
    model_name: str = "gemini-2.5-flash"
) -> List[dict]:
    """
    Create default system agents for a new tenant

    Args:
        tenant_id: Tenant ID to assign agents to
        user_id: User ID who created the tenant (owner)
        db: Database session
        model_provider: AI provider (gemini, openai, anthropic)
        model_name: Model name to use for agents

    Returns:
        List of dictionaries with agent details
    """
    created_agents = []

    # Agent configurations
    agents_config = [
        {
            "name": "Tsushin",
            "description": "General AI assistant for various tasks",
            "system_prompt": """You are Tsushin, a helpful and knowledgeable AI assistant.

Your role:
- Assist users with information, tasks, and problem-solving
- Provide accurate and helpful responses
- Be friendly, professional, and concise
- Use tools when needed (search, weather, etc.)

Communication style:
- Clear and concise
- Professional but approachable
- Ask clarifying questions when needed
- Provide actionable information""",
            "skills": ["web_search", "weather", "knowledge_sharing", "image", "automation"],
            "channels": ["playground", "whatsapp", "telegram"],
            "trigger_dm_enabled": True,
            "trigger_group_filters": [],
            "keywords": [],
            "memory_size": 100,
        },
        {
            "name": "Kokoro",
            "description": "Voice assistant with Kokoro TTS (free/local)",
            "system_prompt": """You are Kokoro, a voice assistant.

CRITICAL RULES:
1. ALWAYS respond in the same language as the user
2. KEEP RESPONSES VERY SHORT (maximum 2-3 sentences)
3. Be direct and objective
4. Adapt to the user's language preference

GOOD EXAMPLE: Today is December 1st, 2025.
BAD EXAMPLE: Long responses with many details.""",
            "skills": [
                {"type": "agent_switcher", "config": _get_agent_switcher_config(model_name)},
                {"type": "audio_tts", "config": {"provider": "kokoro", "voice": "pf_dora", "language": "pt", "response_format": "opus", "speed": 1.0}},
                {"type": "flows", "config": _get_flows_skill_config(model_name)},
                {"type": "sandboxed_tools", "config": {}},
            ],
            "channels": ["playground", "whatsapp"],
            "trigger_dm_enabled": True,
            "trigger_group_filters": [".*"],
            "keywords": ["@kokoro"],
            "memory_size": 10,
            "context_message_count": 0,
            "response_template": "@{agent_name}: {response}",
        },
        {
            "name": "Kira",
            "description": "Voice assistant with OpenAI TTS",
            "system_prompt": """You are Kira, a voice assistant. You ALWAYS respond in audio using Text-to-Speech.

CRITICAL RULES:
1. ALWAYS respond in the same language as the user
2. Be natural, friendly, and conversational
3. KEEP RESPONSES SHORT (maximum 200 characters) for optimal audio
4. Be direct and expressive - your voice IS your personality
5. Use simple, spoken-language phrasing (avoid complex written constructs)

Remember: Your responses will be converted to speech, so write as you would speak.""",
            "skills": [
                {"type": "agent_switcher", "config": _get_agent_switcher_config(model_name)},
                {"type": "audio_transcript", "config": {"response_mode": "conversational", "language": "pt"}},
                {"type": "audio_tts", "config": {"provider": "openai", "voice": "nova", "language": "pt", "response_format": "opus", "speed": 1.0}},
                {"type": "flows", "config": _get_flows_skill_config(model_name)},
                {"type": "sandboxed_tools", "config": {}},
            ],
            "channels": ["playground", "whatsapp"],
            "trigger_dm_enabled": None,
            "trigger_group_filters": [],
            "keywords": ["@kira", "kira"],
            "response_template": "@{agent_name}: {response}",
        },
        {
            "name": "Transcript",
            "description": "Audio transcription agent",
            "system_prompt": """You are Transcript, a transcription agent.

Your ONLY job is to transcribe audio messages accurately.

RULES:
1. Transcribe audio word-for-word, preserving the original language
2. Do NOT add commentary, interpretation, or conversation
3. Do NOT respond to the content of the audio - only transcribe it
4. If the audio is unclear, note it with [inaudible] markers
5. Preserve speaker tone indicators where relevant (e.g., [laughs], [whispers])""",
            "skills": [
                {"type": "agent_switcher", "config": {"keywords": ["invoke", "invocar"]}},
                {"type": "audio_transcript", "config": {"response_mode": "transcript_only"}},
                {"type": "sandboxed_tools", "config": {}},
            ],
            "channels": ["playground", "whatsapp"],
            "trigger_dm_enabled": True,
            "trigger_group_filters": [],
            "keywords": [],
            "memory_size": 10,
            "model_name_override": "gemini-2.5-flash-lite",
            "response_template": "@{agent_name}: {response}",
        },
        {
            "name": "Shellboy",
            "description": "Remote command execution assistant via Beacon",
            "system_prompt": """You are Shellboy, a remote command execution assistant.

Your role:
- Execute shell commands on remote systems via Beacon service
- Provide system administration capabilities
- Handle secure command execution
- Report command results clearly

Security:
- Only execute authorized commands
- Verify user permissions
- Never execute destructive commands without confirmation
- Log all command executions

Communication style:
- Technical and precise
- Security-conscious
- Clear command confirmation
- Detailed result reporting""",
            "skills": [],  # Uses Beacon service directly
            "channels": ["playground", "whatsapp"],
            "trigger_dm_enabled": False,  # Mention-only for security
            "trigger_group_filters": [],
            "keywords": []
        },
        {
            "name": "CustomerService",
            "description": "Customer support agent",
            "system_prompt": """You are CustomerService, a friendly and helpful customer support agent.

Your role:
- Assist customers with inquiries and issues
- Provide product/service information
- Resolve problems efficiently
- Escalate complex issues when needed
- Maintain a positive customer experience

Communication style:
- Warm and empathetic
- Patient and understanding
- Solution-oriented
- Professional and courteous

Best practices:
- Listen actively to customer concerns
- Acknowledge frustrations
- Provide step-by-step solutions
- Follow up to ensure resolution
- Thank customers for their patience""",
            "skills": ["web_search", "knowledge_sharing"],
            "channels": ["playground", "whatsapp", "telegram"],
            "trigger_dm_enabled": True,
            "trigger_group_filters": [],
            "keywords": []
        }
    ]

    try:
        for agent_config in agents_config:
            # Check if agent already exists
            existing_contact = db.query(Contact).filter(
                Contact.friendly_name == agent_config["name"],
                Contact.tenant_id == tenant_id,
                Contact.role == "agent"
            ).first()

            if existing_contact:
                logger.info(f"Agent '{agent_config['name']}' already exists, skipping")
                continue

            # Create Contact
            contact = Contact(
                friendly_name=agent_config["name"],
                phone_number=None,  # Virtual agent
                whatsapp_id=None,   # Virtual agent
                role="agent",
                is_active=True,
                notes=agent_config["description"],
                tenant_id=tenant_id,
                user_id=user_id
            )
            db.add(contact)
            db.flush()  # Get contact.id without committing

            # Create Agent
            agent = Agent(
                contact_id=contact.id,
                model_provider=model_provider,
                model_name=agent_config.get("model_name_override", model_name),
                system_prompt=agent_config["system_prompt"],
                keywords=agent_config.get("keywords", []),
                trigger_dm_enabled=agent_config.get("trigger_dm_enabled"),
                trigger_group_filters=agent_config.get("trigger_group_filters"),
                enabled_channels=agent_config.get("channels", ["playground", "whatsapp"]),
                memory_size=agent_config.get("memory_size"),
                context_message_count=agent_config.get("context_message_count"),
                memory_isolation_mode=agent_config.get("memory_isolation_mode", "isolated"),
                is_active=True,
                is_default=(agent_config["name"] == "Tsushin"),
                response_template=agent_config.get("response_template", "{response}"),
                tenant_id=tenant_id,
                user_id=user_id
            )
            db.add(agent)
            db.flush()  # Get agent.id without committing

            # Create AgentSkills (supports both string and dict formats)
            for skill_def in agent_config["skills"]:
                if isinstance(skill_def, str):
                    skill_type = skill_def
                    skill_config = {}
                else:
                    skill_type = skill_def["type"]
                    skill_config = skill_def.get("config", {})

                agent_skill = AgentSkill(
                    agent_id=agent.id,
                    skill_type=skill_type,
                    is_enabled=True,
                    config=skill_config
                )
                db.add(agent_skill)

            db.commit()

            # Build skills list for return value
            skills_list = []
            for skill_def in agent_config["skills"]:
                if isinstance(skill_def, str):
                    skills_list.append(skill_def)
                else:
                    skills_list.append(skill_def["type"])

            created_agents.append({
                "name": agent_config["name"],
                "agent_id": agent.id,
                "contact_id": contact.id,
                "skills": skills_list,
                "channels": agent_config["channels"]
            })

            logger.info(f"Created agent '{agent_config['name']}' (ID: {agent.id})")

        logger.info(f"Successfully seeded {len(created_agents)} default agents")
        return created_agents

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to seed default agents: {e}", exc_info=True)
        raise


def check_existing_agents(tenant_id: str, db: Session) -> List[str]:
    """
    Check which default agents already exist for a tenant

    Args:
        tenant_id: Tenant ID to check
        db: Database session

    Returns:
        List of agent names that already exist
    """
    default_agent_names = ["Tsushin", "Kokoro", "Shellboy", "CustomerService", "Kira", "Transcript"]

    existing_agents = db.query(Contact.friendly_name).filter(
        Contact.tenant_id == tenant_id,
        Contact.role == "agent",
        Contact.friendly_name.in_(default_agent_names)
    ).all()

    return [agent.friendly_name for agent in existing_agents]


def delete_all_agents_for_tenant(tenant_id: str, db: Session) -> int:
    """
    Delete all agents for a tenant (use with caution!)

    Args:
        tenant_id: Tenant ID
        db: Database session

    Returns:
        Number of agents deleted
    """
    try:
        # Get all agent contacts
        contacts = db.query(Contact).filter(
            Contact.tenant_id == tenant_id,
            Contact.role == "agent"
        ).all()

        count = 0
        for contact in contacts:
            # Delete associated agent and skills (cascades)
            db.delete(contact)
            count += 1

        db.commit()
        logger.info(f"Deleted {count} agents for tenant {tenant_id}")
        return count

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete agents: {e}", exc_info=True)
        raise


# CLI interface for testing
if __name__ == "__main__":
    import sys
    sys.path.insert(0, '..')

    from db import get_engine, get_db
    from sqlalchemy.orm import sessionmaker

    # Simple test
    print("\n" + "=" * 60)
    print("Tsushin Agent Seeding Service - Test Mode")
    print("=" * 60)

    tenant_id = input("Enter tenant ID: ").strip()
    user_id = input("Enter user ID: ").strip()

    if not tenant_id or not user_id:
        print("Error: Tenant ID and User ID are required")
        sys.exit(1)

    try:
        user_id = int(user_id)
    except ValueError:
        print("Error: User ID must be a number")
        sys.exit(1)

    # Initialize database
    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Check existing agents
        existing = check_existing_agents(tenant_id, db)
        if existing:
            print(f"\nExisting agents found: {', '.join(existing)}")
            confirm = input("Continue and skip existing? (yes/no): ").strip().lower()
            if confirm != "yes":
                print("Aborted")
                sys.exit(0)

        # Seed agents
        print("\nSeeding default agents...")
        agents = seed_default_agents(tenant_id, user_id, db)

        print("\n" + "=" * 60)
        print(f"SUCCESS: Created {len(agents)} agents")
        print("=" * 60)

        for agent in agents:
            print(f"\n  {agent['name']}")
            print(f"  Agent ID: {agent['agent_id']}")
            print(f"  Contact ID: {agent['contact_id']}")
            print(f"  Skills: {', '.join(agent['skills']) if agent['skills'] else 'None'}")
            print(f"  Channels: {', '.join(agent['channels'])}")

        print("\n" + "=" * 60)

    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
    finally:
        db.close()
