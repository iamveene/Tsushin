"""Integration tests for ASR instance deletion cascade.

When an ASR instance is deleted, every ``audio_transcript`` skill row that
pinned it must be reconciled in the same transaction:

  * If the tenant still has another active ASR instance → repoint the pinned
    skill at it (lowest-id successor wins for determinism).
  * Otherwise → disable the skill (``is_enabled=False``) so the agent stops
    trying to transcribe via a now-deleted endpoint, and reset the config to
    cloud OpenAI fallback (``asr_mode='openai'``, ``asr_instance_id=None``).

Without this cascade, a UI-driven deletion silently breaks every audio agent
pinned to that instance — the symptom would be agents starting to fall
through to OpenAI Whisper even though the tenant's privacy choice was local.

These tests run against the live PostgreSQL container in CI / dev. They
manage their own throwaway tenant + agents + ASR instances so other tests
aren't affected. Run via:

    docker exec tsushin-backend pytest backend/tests/test_asr_cascade_on_delete.py -v
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime
from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="cascade tests require a live DATABASE_URL — run inside tsushin-backend",
)


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine(os.environ["DATABASE_URL"])
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def tenant_id(db: Session) -> Iterator[str]:
    """Create a throwaway tenant + cleanup on teardown."""
    from models_rbac import Tenant

    tid = f"cascade-test-{secrets.token_hex(8)}"
    t = Tenant(
        id=tid,
        name=f"Cascade Test {tid[-6:]}",
        slug=f"cascade-{tid[-8:]}",
        plan="dev",
    )
    db.add(t)
    db.commit()
    try:
        yield tid
    finally:
        # Cascade-clean child rows in dependency order.
        from models import ASRInstance, AgentSkill, Agent, Contact
        db.query(AgentSkill).filter(
            AgentSkill.agent_id.in_(
                db.query(Agent.id).filter(Agent.tenant_id == tid)
            )
        ).delete(synchronize_session=False)
        db.query(Agent).filter(Agent.tenant_id == tid).delete(synchronize_session=False)
        db.query(Contact).filter(Contact.tenant_id == tid).delete(synchronize_session=False)
        db.query(ASRInstance).filter(ASRInstance.tenant_id == tid).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id == tid).delete(synchronize_session=False)
        db.commit()


def _make_asr_instance(db: Session, tenant_id: str, name: str) -> int:
    from services.whisper_instance_service import WhisperInstanceService
    inst = WhisperInstanceService.create_instance(
        tenant_id=tenant_id,
        vendor="openai_whisper",
        instance_name=name,
        db=db,
        default_model="base",
        auto_provision=False,
    )
    return inst.id


def _make_agent_with_pinned_skill(db: Session, tenant_id: str, asr_instance_id: int) -> int:
    """Create a minimal agent with an audio_transcript skill pinned to the
    given ASR instance. Returns the agent id."""
    from models import Agent, AgentSkill, Contact

    contact = Contact(
        tenant_id=tenant_id,
        friendly_name=f"cascade-agent-{secrets.token_hex(4)}",
        is_active=True,
    )
    db.add(contact)
    db.flush()

    agent = Agent(
        tenant_id=tenant_id,
        contact_id=contact.id,
        system_prompt="cascade test",
        is_active=True,
    )
    db.add(agent)
    db.flush()

    skill = AgentSkill(
        agent_id=agent.id,
        skill_type="audio_transcript",
        is_enabled=True,
        config={
            "asr_mode": "instance",
            "asr_instance_id": asr_instance_id,
            "language": "auto",
            "response_mode": "conversational",
        },
    )
    db.add(skill)
    db.commit()
    return agent.id


def test_cascade_reassigns_to_lowest_id_successor(db, tenant_id):
    from models import AgentSkill, Agent
    from services.whisper_instance_service import WhisperInstanceService

    inst_a = _make_asr_instance(db, tenant_id, "A")
    inst_b = _make_asr_instance(db, tenant_id, "B")
    inst_c = _make_asr_instance(db, tenant_id, "C")
    agent1 = _make_agent_with_pinned_skill(db, tenant_id, inst_a)
    agent2 = _make_agent_with_pinned_skill(db, tenant_id, inst_a)

    summary = WhisperInstanceService.delete_instance(inst_a, tenant_id, db)
    assert summary == {"reassigned": 2, "disabled": 0, "successor_instance_id": min(inst_b, inst_c)}

    # Verify both pinned skills got repointed to the lowest-id active successor.
    expected_successor = min(inst_b, inst_c)
    skills = db.query(AgentSkill).join(Agent, Agent.id == AgentSkill.agent_id).filter(
        Agent.tenant_id == tenant_id,
        AgentSkill.skill_type == "audio_transcript",
    ).all()
    for s in skills:
        assert s.is_enabled is True
        assert s.config["asr_mode"] == "instance"
        assert s.config["asr_instance_id"] == expected_successor


def test_cascade_disables_skills_when_no_successor(db, tenant_id):
    from models import AgentSkill, Agent
    from services.whisper_instance_service import WhisperInstanceService

    inst_only = _make_asr_instance(db, tenant_id, "OnlyOne")
    _make_agent_with_pinned_skill(db, tenant_id, inst_only)

    summary = WhisperInstanceService.delete_instance(inst_only, tenant_id, db)
    assert summary == {"reassigned": 0, "disabled": 1, "successor_instance_id": None}

    skill = db.query(AgentSkill).join(Agent, Agent.id == AgentSkill.agent_id).filter(
        Agent.tenant_id == tenant_id,
        AgentSkill.skill_type == "audio_transcript",
    ).first()
    assert skill is not None
    assert skill.is_enabled is False
    assert skill.config["asr_mode"] == "openai"
    assert skill.config["asr_instance_id"] is None


def test_cascade_ignores_skills_pinned_to_a_different_instance(db, tenant_id):
    from models import AgentSkill, Agent
    from services.whisper_instance_service import WhisperInstanceService

    inst_deleted = _make_asr_instance(db, tenant_id, "Doomed")
    inst_other = _make_asr_instance(db, tenant_id, "Other")
    agent_other = _make_agent_with_pinned_skill(db, tenant_id, inst_other)

    summary = WhisperInstanceService.delete_instance(inst_deleted, tenant_id, db)
    assert summary["reassigned"] == 0
    assert summary["disabled"] == 0

    other_skill = db.query(AgentSkill).join(Agent, Agent.id == AgentSkill.agent_id).filter(
        Agent.id == agent_other,
    ).first()
    assert other_skill.is_enabled is True
    assert other_skill.config["asr_instance_id"] == inst_other


def test_cascade_returns_zeros_when_no_pinned_skills(db, tenant_id):
    from services.whisper_instance_service import WhisperInstanceService

    inst = _make_asr_instance(db, tenant_id, "Lonely")
    # No agents pin this instance.
    summary = WhisperInstanceService.delete_instance(inst, tenant_id, db)
    assert summary == {"reassigned": 0, "disabled": 0, "successor_instance_id": None}


def test_delete_instance_returns_none_when_not_found(db, tenant_id):
    from services.whisper_instance_service import WhisperInstanceService

    summary = WhisperInstanceService.delete_instance(999_999, tenant_id, db)
    assert summary is None
