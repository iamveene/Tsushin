"""
Phase 6.11.4: Create Agendador Agent

Creates dedicated scheduling agent with @mention-only triggering.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.orm import sessionmaker
from models import Contact, Agent, AgentSkill
import logging

logger = logging.getLogger(__name__)


def create_agendador_agent(db_path: str = "./data/agent.db"):
    """Create Agendador agent with scheduler skill"""

    from db import get_engine
    engine = get_engine(db_path)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        # Step 1: Check if Agendador contact exists
        existing_contact = session.query(Contact).filter(
            Contact.friendly_name == "Agendador"
        ).first()

        if existing_contact:
            logger.info("Agendador contact already exists, checking agent and skills...")
            agendador_contact = existing_contact
        else:
            # Step 2: Create Contact
            agendador_contact = Contact(
                friendly_name="Agendador",
                phone_number=None,  # Doesn't send messages
                whatsapp_id=None,   # Virtual agent (mention-only)
                role="agent",
                is_active=True,
                notes="Dedicated scheduling assistant - triggers on @mention only"
            )
            session.add(agendador_contact)
            session.commit()
            logger.info(f"✓ Created Contact 'Agendador' (ID: {agendador_contact.id})")

        # Step 3: Check if Agent exists, create if not
        existing_agent = session.query(Agent).filter(
            Agent.contact_id == agendador_contact.id
        ).first()

        if existing_agent:
            logger.info("Agendador agent already exists")
            agendador_agent = existing_agent
        else:
            agendador_agent = Agent(
                contact_id=agendador_contact.id,
                model_provider="gemini",
                model_name="gemini-2.5-flash",  # Fast model for quick scheduling
                system_prompt="""You are Agendador, a specialized scheduling assistant for WhatsApp.

Your role:
- Parse natural language scheduling requests in Portuguese or English
- Create reminders (NOTIFICATION) and conversations (CONVERSATION)
- Confirm scheduling details clearly
- Handle date/time parsing with Brazil timezone (GMT-3)

Be concise, friendly, and accurate. Always confirm:
- What will be scheduled
- When it will happen
- Who will be notified (if applicable)

Use emojis sparingly (✅ for confirmations, 📅 for dates).""",
                enabled_tools=[],  # No external tools needed
                keywords=[],       # NO keywords - mention-only triggering
                trigger_dm_enabled=False,  # Don't trigger on all DMs
                trigger_group_filters=[],  # Triggers in any group via @mention
                memory_size=50,    # Small memory (stateless scheduling)
                is_active=True,
                is_default=False,
                response_template="{response}"  # Clean response (no prefix needed)
            )
            session.add(agendador_agent)
            session.commit()
            logger.info(f"✓ Created Agent 'Agendador' (ID: {agendador_agent.id})")

        # Step 4: Check if Scheduler Skill exists, create if not
        existing_skill = session.query(AgentSkill).filter(
            AgentSkill.agent_id == agendador_agent.id,
            AgentSkill.skill_type == "scheduler"
        ).first()

        if existing_skill:
            logger.info("Scheduler skill already enabled")
            if not existing_skill.is_enabled:
                existing_skill.is_enabled = True
                session.commit()
                logger.info("✓ Re-enabled scheduler skill")
        else:
            scheduler_skill = AgentSkill(
                agent_id=agendador_agent.id,
                skill_type="scheduler",
                config={
                    "agent_id": agendador_agent.id,
                    "default_max_turns": 20,
                    "default_timeout_hours": 24,
                    "notification_template": "Hi {name}! Reminder: {reminder_text}"
                },
                is_enabled=True
            )
            session.add(scheduler_skill)
            session.commit()
            logger.info(f"✓ Enabled scheduler skill for Agendador")

        print("\n" + "="*60)
        print("SUCCESS: AGENDADOR AGENT CREATED")
        print("="*60)
        print(f"\nContact ID: {agendador_contact.id}")
        print(f"Agent ID: {agendador_agent.id}")
        print(f"Model: {agendador_agent.model_name}")
        print(f"Scheduler Skill: Enabled")
        print(f"\nUsage: @agendador me lembre de comprar pão em 2 horas")
        print("="*60)

        return agendador_agent.id

    except Exception as e:
        session.rollback()
        logger.error(f"Error creating Agendador: {e}", exc_info=True)
        raise
    finally:
        session.close()


def disable_scheduler_for_other_agents(agendador_id: int, db_path: str = "./data/agent.db"):
    """
    Optional: Disable scheduler skill for all agents except Agendador.
    This eliminates ALL keyword-based false positives.
    """
    from db import get_engine
    engine = get_engine(db_path)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        # Get all scheduler skills
        all_scheduler_skills = session.query(AgentSkill).filter(
            AgentSkill.skill_type == "scheduler"
        ).all()

        disabled_count = 0
        for skill in all_scheduler_skills:
            if skill.agent_id != agendador_id and skill.is_enabled:
                skill.is_enabled = False
                disabled_count += 1

        session.commit()
        logger.info(f"✓ Disabled scheduler skill for {disabled_count} other agents")

        print(f"\nScheduler skill disabled for {disabled_count} agents")
        print(f"Only @agendador can schedule now")

    except Exception as e:
        session.rollback()
        logger.error(f"Error disabling scheduler skills: {e}", exc_info=True)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    import sys

    # Parse arguments
    disable_others = "--disable-others" in sys.argv

    print("\nCreating Agendador Agent (Phase 6.11.4)")
    print("="*60)

    # Create Agendador
    agendador_id = create_agendador_agent()

    # Optional: Disable scheduler for other agents
    if disable_others:
        print("\nDisabling scheduler skill for other agents...")
        disable_scheduler_for_other_agents(agendador_id)
    else:
        print("\nTip: Run with --disable-others to disable scheduler for other agents")
        print("   This eliminates ALL false positives but requires @agendador for all scheduling")

    print("\nPhase 6.11.4 Complete!")
    print(f"\nTest with: @agendador me lembre de comprar pão em 1 hora")
