"""
Tsushin Shell Skill Seeding Service

Creates AgentSkill(skill_type='shell') rows per agent so the Shell Commands
skill becomes visible in the per-agent Skills UI (with an enable/disable toggle).

Unlike sandboxed_tools, the shell skill has no tenant-level tool registry —
it is a per-agent skill gated by the AgentSkill master toggle. It is seeded
with is_enabled=False because shell command execution is privileged and must
be explicitly opted-in per agent.

Usage:
    from services.shell_skill_seeding import (
        seed_shell_skill_for_agent,
        seed_shell_skill_for_tenant,
        backfill_shell_skill_all_tenants,
    )
"""

import logging
from typing import Optional
from sqlalchemy.orm import Session

from models import Agent, AgentSkill, Contact
from agent.skills.shell_skill import ShellSkill

logger = logging.getLogger(__name__)

SHELL_SKILL_TYPE = "shell"

# BUG-593: Shellboy is the purpose-built shell agent — its headline command
# path (/shell ...) must work out of the box. Every other seeded agent keeps
# the default-disabled posture so tenants opt-in per agent.
SHELL_ENABLED_AGENT_NAMES = {"shellboy"}


def _shell_is_enabled_default_for(db: Session, agent: Agent) -> bool:
    # Agent identity lives on the linked Contact row (friendly_name).
    contact = db.query(Contact.friendly_name).filter(
        Contact.id == agent.contact_id
    ).first()
    if not contact or not contact[0]:
        return False
    return contact[0].strip().lower() in SHELL_ENABLED_AGENT_NAMES


def seed_shell_skill_for_agent(
    db: Session,
    agent: Agent,
    is_enabled: bool = False,
    commit: bool = True,
) -> Optional[AgentSkill]:
    """
    Idempotently create an AgentSkill(skill_type='shell') row for the given agent.

    Default is_enabled=False — shell is privileged, opt-in per agent.

    Args:
        db: Database session
        agent: Agent ORM instance
        is_enabled: Whether to enable the skill by default (default False)
        commit: Whether to commit the transaction (default True)

    Returns:
        The AgentSkill row (existing or newly created), or None on failure.
    """
    existing = db.query(AgentSkill).filter(
        AgentSkill.agent_id == agent.id,
        AgentSkill.skill_type == SHELL_SKILL_TYPE,
    ).first()

    if existing:
        return existing

    skill = AgentSkill(
        agent_id=agent.id,
        skill_type=SHELL_SKILL_TYPE,
        is_enabled=is_enabled,
        config=ShellSkill.get_default_config(),
    )
    db.add(skill)
    if commit:
        db.commit()
        db.refresh(skill)
    else:
        db.flush()

    logger.info(
        f"Seeded shell skill for agent_id={agent.id} (is_enabled={is_enabled})"
    )
    return skill


def seed_shell_skill_for_tenant(db: Session, tenant_id: str) -> int:
    """
    Seed shell skill rows for every agent belonging to the given tenant.

    BUG-593: The canonical "Shellboy" agent ships with shell enabled so its
    headline /shell commands work on fresh installs. Every other agent keeps
    the default-disabled posture.

    Args:
        db: Database session
        tenant_id: Tenant ID

    Returns:
        Number of AgentSkill rows newly created.
    """
    created = 0
    try:
        agents = db.query(Agent).filter(Agent.tenant_id == tenant_id).all()
        for agent in agents:
            existing = db.query(AgentSkill).filter(
                AgentSkill.agent_id == agent.id,
                AgentSkill.skill_type == SHELL_SKILL_TYPE,
            ).first()
            if existing:
                if (
                    _shell_is_enabled_default_for(db, agent)
                    and not existing.is_enabled
                ):
                    existing.is_enabled = True
                continue
            skill = AgentSkill(
                agent_id=agent.id,
                skill_type=SHELL_SKILL_TYPE,
                is_enabled=_shell_is_enabled_default_for(db, agent),
                config=ShellSkill.get_default_config(),
            )
            db.add(skill)
            created += 1

        if created > 0:
            db.commit()
            logger.info(
                f"Seeded shell skill for {created} agents in tenant {tenant_id}"
            )
        return created
    except Exception as e:
        db.rollback()
        logger.error(
            f"Failed to seed shell skill for tenant {tenant_id}: {e}",
            exc_info=True,
        )
        raise


def backfill_shell_skill_all_tenants(db: Session) -> int:
    """
    Migration: Ensure every existing agent (across all tenants) has an
    AgentSkill(skill_type='shell') row. Idempotent.

    Returns:
        Number of AgentSkill records created.
    """
    try:
        # Find agents that have no shell skill row
        agents_with_skill = db.query(AgentSkill.agent_id).filter(
            AgentSkill.skill_type == SHELL_SKILL_TYPE
        ).all()
        agent_ids_with_skill = {row[0] for row in agents_with_skill}

        all_agents = db.query(Agent).all()
        created = 0
        enabled_for_shellboy = 0
        for agent in all_agents:
            if agent.id in agent_ids_with_skill:
                # BUG-593: Ensure existing Shellboy agents on upgraded
                # installs also get the shell skill enabled.
                if _shell_is_enabled_default_for(db, agent):
                    existing = db.query(AgentSkill).filter(
                        AgentSkill.agent_id == agent.id,
                        AgentSkill.skill_type == SHELL_SKILL_TYPE,
                    ).first()
                    if existing and not existing.is_enabled:
                        existing.is_enabled = True
                        enabled_for_shellboy += 1
                continue
            skill = AgentSkill(
                agent_id=agent.id,
                skill_type=SHELL_SKILL_TYPE,
                is_enabled=_shell_is_enabled_default_for(db, agent),
                config=ShellSkill.get_default_config(),
            )
            db.add(skill)
            created += 1

        if created > 0 or enabled_for_shellboy > 0:
            db.commit()
            logger.info(
                f"Backfill: Created shell skill row for {created} agents "
                f"(enabled for {enabled_for_shellboy} existing Shellboy agents)"
            )
        return created
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to backfill shell skill: {e}", exc_info=True)
        return 0
