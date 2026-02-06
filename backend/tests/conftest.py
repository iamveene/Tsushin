"""
Pytest configuration and fixtures for Phase 4 testing
"""
import pytest
import os
import tempfile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db import Base

# Import LLM testing fixtures
from tests.fixtures.llm_fixtures import (
    mock_ai_client,
    test_agent_config,
    test_agent_openai_config,
    test_agent_gemini_config,
    test_agent_ollama_config,
    test_agent_openrouter_config,
)

@pytest.fixture(scope="function")
def test_db():
    """Create a temporary test database for each test"""
    # Create temporary database file
    db_fd, db_path = tempfile.mkstemp(suffix='.db')

    # Create engine and tables
    engine = create_engine(f'sqlite:///{db_path}')
    Base.metadata.create_all(engine)

    # Create session
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    # Cleanup
    session.close()
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture(scope="function")
def sample_messages():
    """Sample messages for testing"""
    return [
        {
            "id": "msg1",
            "sender_key": "user1",
            "text": "Hello, how are you today?",
            "timestamp": 1000000
        },
        {
            "id": "msg2",
            "sender_key": "user1",
            "text": "I need help with Python programming",
            "timestamp": 1000100
        },
        {
            "id": "msg3",
            "sender_key": "user1",
            "text": "What's the weather like?",
            "timestamp": 1000200
        },
        {
            "id": "msg4",
            "sender_key": "user2",
            "text": "Can you help me with cooking recipes?",
            "timestamp": 1000300
        },
        {
            "id": "msg5",
            "sender_key": "user2",
            "text": "I love Italian food",
            "timestamp": 1000400
        }
    ]


@pytest.fixture(scope="function")
def sample_config():
    """Sample configuration for testing"""
    return {
        "enable_semantic_search": True,
        "semantic_search_results": 5,
        "enable_summarization": True,
        "summarization_threshold": 20,
        "model_provider": "anthropic",
        "model_name": "claude-3.5-sonnet"
    }


# ============================================================================
# Integration Test Fixtures
# ============================================================================

@pytest.fixture(scope="function")
def integration_db():
    """
    Real database with full schema and seed data for integration tests.
    Creates in-memory SQLite database with all tables.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from models import Base
    from db import seed_rbac_defaults

    # Create in-memory database
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    # Create session
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Seed RBAC defaults (roles, permissions)
    seed_rbac_defaults(session)

    yield session

    # Cleanup
    session.close()


@pytest.fixture
def sample_tenant(integration_db):
    """Create test tenant with owner user for integration tests."""
    from models_rbac import Tenant, User, Role, UserRole

    # Create tenant
    tenant = Tenant(id="test-tenant", name="Test Organization", slug="test-org")
    integration_db.add(tenant)
    integration_db.commit()

    # Get owner role (created by seed_rbac_defaults)
    owner_role = integration_db.query(Role).filter(Role.name == "owner").first()

    # Create owner user (id is auto-generated, field is password_hash)
    user = User(
        email="test@example.com",
        password_hash="hashed_password_here",
        is_global_admin=False,
        tenant_id="test-tenant"
    )
    integration_db.add(user)
    integration_db.commit()

    # Assign owner role to user
    user_role = UserRole(
        user_id=user.id,
        role_id=owner_role.id,
        tenant_id=tenant.id
    )
    integration_db.add(user_role)
    integration_db.commit()

    return tenant, user


@pytest.fixture
def sample_agent(integration_db, sample_tenant):
    """Create test agent with contact for integration tests."""
    from models import Contact, Agent, TonePreset

    tenant, user = sample_tenant

    # Create tone preset
    tone = TonePreset(
        id=1,
        name="Friendly",
        description="Be warm and welcoming",
        is_system=True,
        tenant_id=None
    )
    integration_db.add(tone)

    # Create contact
    contact = Contact(
        id=1,
        friendly_name="Test Contact",
        phone_number="+1234567890",
        tenant_id=tenant.id
    )
    integration_db.add(contact)
    integration_db.commit()

    # Create agent
    agent = Agent(
        id=1,
        contact_id=contact.id,
        system_prompt="You are a helpful assistant.",
        tone_preset_id=tone.id,
        model_provider="anthropic",
        model_name="claude-3.5-sonnet",
        is_active=True,
        is_default=True,
        tenant_id=tenant.id
    )
    integration_db.add(agent)
    integration_db.commit()
    integration_db.refresh(agent)

    return agent
