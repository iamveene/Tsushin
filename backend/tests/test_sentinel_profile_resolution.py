"""
Sentinel Security Profiles — Resolution Chain Tests

Tests for skill-level profile resolution via the get_effective_config()
call in analyze_prompt, analyze_tool_call, and analyze_shell_command.

Verifies the hierarchy: Skill -> Agent -> Tenant -> System Default
"""

import pytest
import json
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, SentinelProfile, SentinelProfileAssignment
from services.sentinel_profiles_service import SentinelProfilesService
from services.sentinel_effective_config import SentinelEffectiveConfig


@pytest.fixture(autouse=True)
def clear_profile_cache():
    """Clear the class-level profile cache before each test."""
    SentinelProfilesService._profile_cache.clear()
    yield
    SentinelProfilesService._profile_cache.clear()


@pytest.fixture
def db_engine():
    """Create in-memory SQLite database."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Create a database session for testing."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def tenant_id():
    return "test-tenant-profiles"


@pytest.fixture
def system_profiles(db_session):
    """Seed the 4 system profiles (same as production seeding)."""
    profiles = [
        SentinelProfile(
            id=1,
            name="Off",
            slug="off",
            description="Sentinel disabled",
            tenant_id=None,
            is_system=True,
            is_default=False,
            is_enabled=False,
            detection_mode="off",
            aggressiveness_level=0,
            detection_overrides="{}",
        ),
        SentinelProfile(
            id=2,
            name="Permissive",
            slug="permissive",
            description="Log-only, moderate sensitivity",
            tenant_id=None,
            is_system=True,
            is_default=False,
            is_enabled=True,
            detection_mode="detect_only",
            aggressiveness_level=1,
            detection_overrides="{}",
        ),
        SentinelProfile(
            id=3,
            name="Moderate",
            slug="moderate",
            description="Block threats, moderate sensitivity",
            tenant_id=None,
            is_system=True,
            is_default=True,
            is_enabled=True,
            detection_mode="block",
            aggressiveness_level=1,
            detection_overrides="{}",
        ),
        SentinelProfile(
            id=4,
            name="Aggressive",
            slug="aggressive",
            description="Block all, max sensitivity",
            tenant_id=None,
            is_system=True,
            is_default=False,
            is_enabled=True,
            detection_mode="block",
            aggressiveness_level=3,
            detection_overrides="{}",
        ),
    ]
    for p in profiles:
        db_session.add(p)
    db_session.commit()
    return profiles


@pytest.fixture
def tenant_profile(db_session, tenant_id):
    """Create a tenant-specific profile."""
    profile = SentinelProfile(
        id=10,
        name="Tenant Custom",
        slug="tenant-custom",
        description="Tenant-level custom profile",
        tenant_id=tenant_id,
        is_system=False,
        is_default=False,
        is_enabled=True,
        detection_mode="block",
        aggressiveness_level=2,
        detection_overrides=json.dumps({"prompt_injection": {"enabled": True}}),
    )
    db_session.add(profile)
    db_session.commit()
    return profile


@pytest.fixture
def agent_profile(db_session, tenant_id):
    """Create an agent-specific profile."""
    profile = SentinelProfile(
        id=20,
        name="Agent Override",
        slug="agent-override",
        description="Agent-level override profile",
        tenant_id=tenant_id,
        is_system=False,
        is_default=False,
        is_enabled=True,
        detection_mode="detect_only",
        aggressiveness_level=1,
        detection_overrides=json.dumps({"shell_malicious": {"enabled": False}}),
    )
    db_session.add(profile)
    db_session.commit()
    return profile


@pytest.fixture
def skill_profile(db_session, tenant_id):
    """Create a skill-specific profile (for shell skill)."""
    profile = SentinelProfile(
        id=30,
        name="Shell Strict",
        slug="shell-strict",
        description="Strict profile for shell skill",
        tenant_id=tenant_id,
        is_system=False,
        is_default=False,
        is_enabled=True,
        detection_mode="block",
        aggressiveness_level=3,
        detection_overrides=json.dumps({"shell_malicious": {"enabled": True}}),
    )
    db_session.add(profile)
    db_session.commit()
    return profile


class TestProfileResolutionChain:
    """Test the skill -> agent -> tenant -> system resolution chain."""

    def test_system_default_fallback(self, db_session, tenant_id, system_profiles):
        """When no assignments exist, system default (Moderate) is used."""
        service = SentinelProfilesService(db_session, tenant_id)
        config = service.get_effective_config(agent_id=None, skill_type=None)

        assert config is not None
        assert config.profile_name == "Moderate"
        assert config.profile_source == "system"
        assert config.detection_mode == "block"
        assert config.aggressiveness_level == 1

    def test_tenant_level_assignment(
        self, db_session, tenant_id, system_profiles, tenant_profile
    ):
        """Tenant-level assignment overrides system default."""
        # Create tenant-level assignment
        assignment = SentinelProfileAssignment(
            tenant_id=tenant_id,
            agent_id=None,
            skill_type=None,
            profile_id=tenant_profile.id,
        )
        db_session.add(assignment)
        db_session.commit()

        service = SentinelProfilesService(db_session, tenant_id)
        config = service.get_effective_config(agent_id=None, skill_type=None)

        assert config is not None
        assert config.profile_name == "Tenant Custom"
        assert config.profile_source == "tenant"
        assert config.aggressiveness_level == 2

    def test_agent_level_overrides_tenant(
        self, db_session, tenant_id, system_profiles, tenant_profile, agent_profile
    ):
        """Agent-level assignment overrides tenant-level."""
        agent_id = 99

        # Tenant-level assignment
        db_session.add(SentinelProfileAssignment(
            tenant_id=tenant_id, agent_id=None, skill_type=None,
            profile_id=tenant_profile.id,
        ))
        # Agent-level assignment
        db_session.add(SentinelProfileAssignment(
            tenant_id=tenant_id, agent_id=agent_id, skill_type=None,
            profile_id=agent_profile.id,
        ))
        db_session.commit()

        service = SentinelProfilesService(db_session, tenant_id)
        config = service.get_effective_config(agent_id=agent_id, skill_type=None)

        assert config is not None
        assert config.profile_name == "Agent Override"
        assert config.profile_source == "agent"
        assert config.detection_mode == "detect_only"

    def test_skill_level_overrides_agent(
        self, db_session, tenant_id, system_profiles,
        tenant_profile, agent_profile, skill_profile
    ):
        """Skill-level assignment overrides agent-level."""
        agent_id = 99

        # All three levels assigned
        db_session.add(SentinelProfileAssignment(
            tenant_id=tenant_id, agent_id=None, skill_type=None,
            profile_id=tenant_profile.id,
        ))
        db_session.add(SentinelProfileAssignment(
            tenant_id=tenant_id, agent_id=agent_id, skill_type=None,
            profile_id=agent_profile.id,
        ))
        db_session.add(SentinelProfileAssignment(
            tenant_id=tenant_id, agent_id=agent_id, skill_type="shell",
            profile_id=skill_profile.id,
        ))
        db_session.commit()

        service = SentinelProfilesService(db_session, tenant_id)
        config = service.get_effective_config(agent_id=agent_id, skill_type="shell")

        assert config is not None
        assert config.profile_name == "Shell Strict"
        assert config.profile_source == "skill"
        assert config.aggressiveness_level == 3

    def test_skill_falls_through_to_agent(
        self, db_session, tenant_id, system_profiles, agent_profile
    ):
        """When no skill-level assignment, falls through to agent."""
        agent_id = 99

        db_session.add(SentinelProfileAssignment(
            tenant_id=tenant_id, agent_id=agent_id, skill_type=None,
            profile_id=agent_profile.id,
        ))
        db_session.commit()

        service = SentinelProfilesService(db_session, tenant_id)
        config = service.get_effective_config(agent_id=agent_id, skill_type="shell")

        assert config is not None
        assert config.profile_name == "Agent Override"
        assert config.profile_source == "agent"

    def test_agent_falls_through_to_tenant(
        self, db_session, tenant_id, system_profiles, tenant_profile
    ):
        """When no agent-level assignment, falls through to tenant."""
        agent_id = 99

        db_session.add(SentinelProfileAssignment(
            tenant_id=tenant_id, agent_id=None, skill_type=None,
            profile_id=tenant_profile.id,
        ))
        db_session.commit()

        service = SentinelProfilesService(db_session, tenant_id)
        config = service.get_effective_config(agent_id=agent_id, skill_type=None)

        assert config is not None
        assert config.profile_name == "Tenant Custom"
        assert config.profile_source == "tenant"

    def test_system_profile_direct_assignment(
        self, db_session, tenant_id, system_profiles
    ):
        """Tenant can assign a system profile directly."""
        agent_id = 99
        aggressive = system_profiles[3]  # Aggressive profile

        db_session.add(SentinelProfileAssignment(
            tenant_id=tenant_id, agent_id=agent_id, skill_type=None,
            profile_id=aggressive.id,
        ))
        db_session.commit()

        service = SentinelProfilesService(db_session, tenant_id)
        config = service.get_effective_config(agent_id=agent_id, skill_type=None)

        assert config is not None
        assert config.profile_name == "Aggressive"
        assert config.profile_source == "agent"
        assert config.aggressiveness_level == 3

    def test_detection_overrides_resolved(
        self, db_session, tenant_id, system_profiles, skill_profile
    ):
        """Detection overrides from profile JSON are properly resolved."""
        agent_id = 99

        db_session.add(SentinelProfileAssignment(
            tenant_id=tenant_id, agent_id=agent_id, skill_type="shell",
            profile_id=skill_profile.id,
        ))
        db_session.commit()

        service = SentinelProfilesService(db_session, tenant_id)
        config = service.get_effective_config(agent_id=agent_id, skill_type="shell")

        assert config is not None
        # Shell Strict has shell_malicious explicitly enabled
        assert config.is_detection_enabled("shell_malicious") is True

    def test_detection_defaults_from_registry(
        self, db_session, tenant_id, system_profiles
    ):
        """Detection types not in overrides fall back to registry defaults."""
        service = SentinelProfilesService(db_session, tenant_id)
        config = service.get_effective_config(agent_id=None, skill_type=None)

        assert config is not None
        # System Moderate has empty detection_overrides = {},
        # so all detections use registry default_enabled (typically True)
        assert config.detection_config is not None
        assert len(config.detection_config) > 0

    def test_cache_invalidation_on_assignment(
        self, db_session, tenant_id, system_profiles, tenant_profile, agent_profile
    ):
        """Cache is cleared when a new assignment is made."""
        agent_id = 99
        service = SentinelProfilesService(db_session, tenant_id)

        # First call — resolves to system default
        config1 = service.get_effective_config(agent_id=agent_id, skill_type=None)
        assert config1.profile_name == "Moderate"

        # Add agent-level assignment (this should clear cache)
        service.assign_profile(agent_profile.id, agent_id=agent_id)

        # Second call — should resolve to agent profile
        config2 = service.get_effective_config(agent_id=agent_id, skill_type=None)
        assert config2.profile_name == "Agent Override"
        assert config2.profile_source == "agent"


class TestSentinelServiceSkillType:
    """Test that SentinelService methods properly forward skill_type."""

    def test_get_effective_config_with_skill_type(
        self, db_session, tenant_id, system_profiles, skill_profile
    ):
        """SentinelService.get_effective_config passes skill_type to profile service."""
        from services.sentinel_service import SentinelService

        agent_id = 99

        # Assign skill-level profile
        db_session.add(SentinelProfileAssignment(
            tenant_id=tenant_id, agent_id=agent_id, skill_type="shell",
            profile_id=skill_profile.id,
        ))
        db_session.commit()

        service = SentinelService(db_session, tenant_id)
        config = service.get_effective_config(agent_id=agent_id, skill_type="shell")

        assert config is not None
        assert config.profile_name == "Shell Strict"
        assert config.profile_source == "skill"

    def test_get_effective_config_without_skill_type(
        self, db_session, tenant_id, system_profiles
    ):
        """Without skill_type, resolves at agent/tenant/system level."""
        from services.sentinel_service import SentinelService

        service = SentinelService(db_session, tenant_id)
        config = service.get_effective_config(agent_id=None, skill_type=None)

        assert config is not None
        assert config.profile_source == "system"
