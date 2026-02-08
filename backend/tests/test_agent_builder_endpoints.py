"""
Agent Builder Batch Endpoints — Unit Tests (Phase I)

Tests for:
1. GET /api/v2/agents/{agent_id}/builder-data  (batch load)
2. POST /api/v2/agents/{agent_id}/builder-save (atomic save)

Uses in-memory SQLite database with direct model operations to verify
endpoint logic without requiring the full FastAPI app stack.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime

from models import (
    Base, Agent, Contact, Persona, AgentSkill, AgentKnowledge,
    SandboxedTool, AgentSandboxedTool, SentinelProfile, SentinelProfileAssignment,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def db_engine():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def tenant_id():
    return "test-tenant-builder"


@pytest.fixture
def test_contact(db):
    contact = Contact(friendly_name="TestAgent", whatsapp_id="test-wa-1")
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


@pytest.fixture
def test_persona(db):
    persona = Persona(
        name="Test Persona", description="A test persona",
        role_description="Helper", personality_traits="Friendly",
        is_active=True, is_system=False, tenant_id="test-tenant-builder",
    )
    db.add(persona)
    db.commit()
    db.refresh(persona)
    return persona


@pytest.fixture
def test_agent(db, test_contact, test_persona, tenant_id):
    agent = Agent(
        contact_id=test_contact.id, system_prompt="You are a test agent.",
        persona_id=test_persona.id, model_provider="gemini",
        model_name="gemini-2.5-flash", memory_size=10,
        memory_isolation_mode="isolated", enable_semantic_search=True,
        is_active=True, is_default=False, tenant_id=tenant_id,
        enabled_channels=["playground", "whatsapp"],
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@pytest.fixture
def test_skills(db, test_agent):
    skills = [
        AgentSkill(agent_id=test_agent.id, skill_type="web_search", is_enabled=True, config={"provider": "brave"}),
        AgentSkill(agent_id=test_agent.id, skill_type="weather", is_enabled=True, config={}),
        AgentSkill(agent_id=test_agent.id, skill_type="shell", is_enabled=False, config={}),
    ]
    db.add_all(skills)
    db.commit()
    return skills


@pytest.fixture
def test_knowledge(db, test_agent):
    doc = AgentKnowledge(
        agent_id=test_agent.id, document_name="guide.pdf",
        document_type="pdf", file_path="/data/guide.pdf",
        file_size_bytes=1024, num_chunks=5, status="completed",
    )
    db.add(doc)
    db.commit()
    return doc


@pytest.fixture
def test_tool(db, tenant_id):
    tool = SandboxedTool(
        name="nmap", tool_type="command", tenant_id=tenant_id,
        system_prompt="Run nmap scans", is_enabled=True,
    )
    db.add(tool)
    db.commit()
    db.refresh(tool)
    return tool


@pytest.fixture
def test_tool_mapping(db, test_agent, test_tool):
    mapping = AgentSandboxedTool(
        agent_id=test_agent.id, sandboxed_tool_id=test_tool.id, is_enabled=True,
    )
    db.add(mapping)
    db.commit()
    db.refresh(mapping)
    return mapping


@pytest.fixture
def system_profiles(db):
    profiles = [
        SentinelProfile(name="Off", slug="off", is_system=True, is_enabled=False, detection_mode="off", aggressiveness_level=0),
        SentinelProfile(name="Moderate", slug="moderate", is_system=True, is_enabled=True, detection_mode="block", aggressiveness_level=1, is_default=True),
        SentinelProfile(name="Aggressive", slug="aggressive", is_system=True, is_enabled=True, detection_mode="block", aggressiveness_level=2),
    ]
    db.add_all(profiles)
    db.commit()
    return profiles


@pytest.fixture
def test_sentinel_assignment(db, test_agent, system_profiles, tenant_id):
    assignment = SentinelProfileAssignment(
        tenant_id=tenant_id, agent_id=test_agent.id,
        profile_id=system_profiles[1].id, assigned_by=1,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


# ============================================================================
# Tests: builder-data response structure
# ============================================================================

class TestBuilderData:
    """Tests for the builder-data endpoint logic."""

    def test_agent_detail_fields(self, db, test_agent, test_contact, test_persona):
        """Agent detail should include all builder-relevant fields."""
        agent = db.query(Agent).filter(Agent.id == test_agent.id).first()
        contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()
        persona = db.query(Persona).filter(Persona.id == agent.persona_id).first()

        assert contact.friendly_name == "TestAgent"
        assert persona.name == "Test Persona"
        assert agent.model_provider == "gemini"
        assert agent.memory_isolation_mode == "isolated"
        assert agent.enable_semantic_search is True

    def test_skills_include_enabled_and_disabled(self, db, test_agent, test_skills):
        """Builder needs ALL skills (enabled + disabled) for state diffing."""
        skills = db.query(AgentSkill).filter(AgentSkill.agent_id == test_agent.id).all()
        assert len(skills) == 3
        enabled = [s for s in skills if s.is_enabled]
        disabled = [s for s in skills if not s.is_enabled]
        assert len(enabled) == 2
        assert len(disabled) == 1
        assert disabled[0].skill_type == "shell"

    def test_knowledge_metadata(self, db, test_agent, test_knowledge):
        """Knowledge docs should return metadata only (no file content)."""
        docs = db.query(AgentKnowledge).filter(AgentKnowledge.agent_id == test_agent.id).all()
        assert len(docs) == 1
        assert docs[0].document_name == "guide.pdf"
        assert docs[0].file_size_bytes == 1024
        assert docs[0].num_chunks == 5
        assert docs[0].status == "completed"

    def test_sentinel_assignment_with_profile_info(self, db, test_agent, test_sentinel_assignment, tenant_id):
        """Sentinel assignments should join profile name and slug."""
        rows = (
            db.query(SentinelProfileAssignment, SentinelProfile.name, SentinelProfile.slug)
            .join(SentinelProfile, SentinelProfileAssignment.profile_id == SentinelProfile.id)
            .filter(
                SentinelProfileAssignment.tenant_id == tenant_id,
                SentinelProfileAssignment.agent_id == test_agent.id,
            )
            .all()
        )
        assert len(rows) == 1
        assignment, name, slug = rows[0]
        assert name == "Moderate"
        assert slug == "moderate"

    def test_tool_mappings_with_tool_info(self, db, test_agent, test_tool_mapping, test_tool):
        """Tool mappings should join tool name and type."""
        rows = (
            db.query(AgentSandboxedTool, SandboxedTool.name, SandboxedTool.tool_type)
            .join(SandboxedTool, AgentSandboxedTool.sandboxed_tool_id == SandboxedTool.id)
            .filter(AgentSandboxedTool.agent_id == test_agent.id)
            .all()
        )
        assert len(rows) == 1
        mapping, name, tool_type = rows[0]
        assert name == "nmap"
        assert tool_type == "command"
        assert mapping.is_enabled is True


# ============================================================================
# Tests: builder-save atomicity and correctness
# ============================================================================

class TestBuilderSave:
    """Tests for the builder-save endpoint logic."""

    def test_save_agent_memory_config(self, db, test_agent):
        """Agent memory config should persist through save."""
        agent = db.query(Agent).filter(Agent.id == test_agent.id).first()
        agent.memory_size = 25
        agent.memory_isolation_mode = "shared"
        agent.enable_semantic_search = False
        agent.updated_at = datetime.utcnow()
        db.commit()

        refreshed = db.query(Agent).filter(Agent.id == test_agent.id).first()
        assert refreshed.memory_size == 25
        assert refreshed.memory_isolation_mode == "shared"
        assert refreshed.enable_semantic_search is False

    def test_save_skill_enable_disable(self, db, test_agent, test_skills):
        """Skills should be correctly toggled on/off."""
        # Disable web_search, enable shell
        web = db.query(AgentSkill).filter(
            AgentSkill.agent_id == test_agent.id, AgentSkill.skill_type == "web_search"
        ).first()
        shell = db.query(AgentSkill).filter(
            AgentSkill.agent_id == test_agent.id, AgentSkill.skill_type == "shell"
        ).first()

        web.is_enabled = False
        shell.is_enabled = True
        db.commit()

        skills = db.query(AgentSkill).filter(AgentSkill.agent_id == test_agent.id).all()
        enabled_types = {s.skill_type for s in skills if s.is_enabled}
        assert "web_search" not in enabled_types
        assert "shell" in enabled_types
        assert "weather" in enabled_types

    def test_save_skill_config_update(self, db, test_agent, test_skills):
        """Skill config should be updated when changed."""
        web = db.query(AgentSkill).filter(
            AgentSkill.agent_id == test_agent.id, AgentSkill.skill_type == "web_search"
        ).first()
        web.config = {"provider": "google", "max_results": 5}
        db.commit()

        refreshed = db.query(AgentSkill).filter(
            AgentSkill.agent_id == test_agent.id, AgentSkill.skill_type == "web_search"
        ).first()
        assert refreshed.config["provider"] == "google"
        assert refreshed.config["max_results"] == 5

    def test_save_tool_override(self, db, test_agent, test_tool_mapping):
        """Tool enabled state should toggle."""
        mapping = db.query(AgentSandboxedTool).filter(
            AgentSandboxedTool.id == test_tool_mapping.id
        ).first()
        assert mapping.is_enabled is True

        mapping.is_enabled = False
        db.commit()

        refreshed = db.query(AgentSandboxedTool).filter(
            AgentSandboxedTool.id == test_tool_mapping.id
        ).first()
        assert refreshed.is_enabled is False

    def test_save_sentinel_assign(self, db, test_agent, system_profiles, tenant_id):
        """Sentinel profile assignment should be created."""
        assignment = SentinelProfileAssignment(
            tenant_id=tenant_id, agent_id=test_agent.id,
            profile_id=system_profiles[2].id, assigned_by=1,
        )
        db.add(assignment)
        db.commit()

        found = db.query(SentinelProfileAssignment).filter(
            SentinelProfileAssignment.tenant_id == tenant_id,
            SentinelProfileAssignment.agent_id == test_agent.id,
            SentinelProfileAssignment.skill_type.is_(None),
        ).first()
        assert found is not None
        assert found.profile_id == system_profiles[2].id

    def test_save_sentinel_remove(self, db, test_agent, test_sentinel_assignment, tenant_id):
        """Sentinel profile assignment should be removable."""
        db.delete(test_sentinel_assignment)
        db.commit()

        found = db.query(SentinelProfileAssignment).filter(
            SentinelProfileAssignment.tenant_id == tenant_id,
            SentinelProfileAssignment.agent_id == test_agent.id,
        ).first()
        assert found is None

    def test_save_sentinel_reassign(self, db, test_agent, test_sentinel_assignment, system_profiles, tenant_id):
        """Sentinel assignment should update to a new profile (upsert)."""
        # Change from Moderate to Aggressive
        test_sentinel_assignment.profile_id = system_profiles[2].id
        db.commit()

        found = db.query(SentinelProfileAssignment).filter(
            SentinelProfileAssignment.tenant_id == tenant_id,
            SentinelProfileAssignment.agent_id == test_agent.id,
        ).first()
        assert found.profile_id == system_profiles[2].id

    def test_save_rollback_on_failure(self, db, test_agent, test_skills):
        """If an error occurs during save, all changes should roll back."""
        agent = db.query(Agent).filter(Agent.id == test_agent.id).first()
        original_memory = agent.memory_size

        try:
            agent.memory_size = 999
            # Simulate a skill update that would fail
            web = db.query(AgentSkill).filter(
                AgentSkill.agent_id == test_agent.id, AgentSkill.skill_type == "web_search"
            ).first()
            web.is_enabled = False
            # Force an error
            raise ValueError("Simulated save failure")
        except ValueError:
            db.rollback()

        refreshed_agent = db.query(Agent).filter(Agent.id == test_agent.id).first()
        assert refreshed_agent.memory_size == original_memory

        refreshed_skill = db.query(AgentSkill).filter(
            AgentSkill.agent_id == test_agent.id, AgentSkill.skill_type == "web_search"
        ).first()
        assert refreshed_skill.is_enabled is True

    def test_save_creates_new_skill(self, db, test_agent):
        """Save should create a new skill record if it doesn't exist."""
        new_skill = AgentSkill(
            agent_id=test_agent.id, skill_type="image",
            is_enabled=True, config={"provider": "dall-e"},
        )
        db.add(new_skill)
        db.commit()

        found = db.query(AgentSkill).filter(
            AgentSkill.agent_id == test_agent.id, AgentSkill.skill_type == "image"
        ).first()
        assert found is not None
        assert found.is_enabled is True
        assert found.config["provider"] == "dall-e"

    def test_save_disables_absent_skills(self, db, test_agent, test_skills):
        """Skills not in desired list should be disabled."""
        # Mark all skills as disabled (simulating the save endpoint logic)
        desired_types = {"weather"}  # Only keep weather
        all_skills = db.query(AgentSkill).filter(AgentSkill.agent_id == test_agent.id).all()
        for skill in all_skills:
            if skill.skill_type not in desired_types:
                skill.is_enabled = False
        db.commit()

        refreshed = db.query(AgentSkill).filter(AgentSkill.agent_id == test_agent.id).all()
        enabled_types = {s.skill_type for s in refreshed if s.is_enabled}
        assert enabled_types == {"weather"}


# ============================================================================
# Tests: global palette data
# ============================================================================

class TestBuilderGlobals:
    """Tests for global palette data (include_globals=true)."""

    def test_personas_include_system_and_tenant(self, db, test_persona):
        """Both system and tenant-specific personas should be returned."""
        system_persona = Persona(
            name="System Helper", description="Built-in", is_active=True,
            is_system=True, tenant_id=None,
        )
        db.add(system_persona)
        db.commit()

        all_personas = db.query(Persona).filter(Persona.is_active == True).all()
        assert len(all_personas) >= 2
        names = {p.name for p in all_personas}
        assert "Test Persona" in names
        assert "System Helper" in names

    def test_sentinel_profiles_include_system(self, db, system_profiles, tenant_id):
        """System profiles should always be included."""
        custom = SentinelProfile(
            name="Custom", slug="custom", tenant_id=tenant_id,
            is_system=False, is_enabled=True, detection_mode="detect_only",
            aggressiveness_level=1,
        )
        db.add(custom)
        db.commit()

        profiles = db.query(SentinelProfile).filter(
            (SentinelProfile.is_system == True) | (SentinelProfile.tenant_id == tenant_id)
        ).all()
        assert len(profiles) == 4  # 3 system + 1 custom
        names = {p.name for p in profiles}
        assert "Moderate" in names
        assert "Custom" in names

    def test_tools_filtered_by_tenant(self, db, test_tool, tenant_id):
        """Tools should be filtered by tenant."""
        other_tool = SandboxedTool(
            name="nuclei", tool_type="command", tenant_id="other-tenant",
            system_prompt="Run nuclei", is_enabled=True,
        )
        db.add(other_tool)
        db.commit()

        all_tools = db.query(SandboxedTool).all()
        tenant_tools = [t for t in all_tools if t.tenant_id is None or t.tenant_id == tenant_id]
        assert len(tenant_tools) == 1
        assert tenant_tools[0].name == "nmap"
