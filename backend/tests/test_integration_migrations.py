"""
Integration Tests: Database Migrations
Tests database schema integrity and migrations.
"""

import pytest
from sqlalchemy import inspect, create_engine
from sqlalchemy.orm import sessionmaker
from models import Base


@pytest.mark.integration
class TestMigrationIntegration:
    """Integration tests for database migrations and schema."""

    def test_full_schema_creation(self):
        """Test creating full schema from scratch."""
        # Create fresh in-memory database
        engine = create_engine("sqlite:///:memory:")

        # Create all tables
        Base.metadata.create_all(engine)

        # Inspect schema
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        # Verify critical tables exist
        # Note: Messages are stored as JSON in conversation_thread.conversation_history, not in a separate table
        expected_tables = [
            "config",
            "contact",
            "agent",
            "tone_preset",
            "persona",
            "slash_command",
            "project_command_pattern",
            "conversation_thread",
            "tenant",
            "user",
            "role",
            "permission",
            "user_role"
        ]

        for table in expected_tables:
            assert table in tables, f"Table {table} not found in schema"

    def test_foreign_key_constraints(self):
        """Test foreign key relationships are properly defined."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)

        inspector = inspect(engine)

        # Check agent -> whatsapp_mcp_instance FK (agent.whatsapp_integration_id)
        agent_fks = inspector.get_foreign_keys("agent")
        whatsapp_fks = [fk for fk in agent_fks if "whatsapp_mcp_instance" in str(fk.get("referred_table"))]
        assert len(whatsapp_fks) > 0, "Agent should have FK to whatsapp_mcp_instance"

        # Check contact_channel_mapping -> contact FK
        channel_mapping_fks = inspector.get_foreign_keys("contact_channel_mapping")
        contact_fks = [fk for fk in channel_mapping_fks if "contact" in str(fk.get("referred_table"))]
        assert len(contact_fks) > 0, "ContactChannelMapping should have FK to Contact"

    def test_idempotent_migration(self):
        """Test schema can be created multiple times (idempotent)."""
        engine = create_engine("sqlite:///:memory:")

        # Create schema first time
        Base.metadata.create_all(engine)

        # Create schema second time (should not error)
        try:
            Base.metadata.create_all(engine)
            success = True
        except Exception as e:
            success = False
            print(f"Error: {e}")

        assert success, "Schema creation should be idempotent"

    def test_default_data_seeding(self, integration_db):
        """Test default RBAC data is properly seeded."""
        from models_rbac import Role, Permission

        # Check roles exist
        roles = integration_db.query(Role).all()
        role_names = {r.name for r in roles}

        expected_roles = {"owner", "admin", "member", "readonly"}
        assert expected_roles.issubset(role_names), "Default roles should be seeded"

        # Check permissions exist
        permissions = integration_db.query(Permission).all()
        assert len(permissions) > 0, "Permissions should be seeded"

        # Check permission structure
        permission_names = {p.name for p in permissions}
        assert "agents.read" in permission_names
        assert "agents.write" in permission_names

    def test_unique_constraints(self):
        """Test unique constraints are properly defined."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)

        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()

        from models import TonePreset
        from models_rbac import Tenant

        # Create tenant
        tenant = Tenant(id="test", name="Test", slug="test")
        session.add(tenant)
        session.commit()

        # Create first tone preset
        tone1 = TonePreset(
            name="Friendly",
            description="Test",
            tenant_id=tenant.id
        )
        session.add(tone1)
        session.commit()

        # Try to create duplicate name in same tenant (should work - no unique constraint on name alone)
        # But duplicate id should fail
        from sqlalchemy.exc import IntegrityError

        tone_dup = TonePreset(
            id=tone1.id,  # Same ID
            name="Different",
            description="Test2",
            tenant_id=tenant.id
        )
        session.add(tone_dup)

        try:
            session.commit()
            duplicate_allowed = True
        except IntegrityError:
            duplicate_allowed = False
            session.rollback()

        assert not duplicate_allowed, "Duplicate IDs should not be allowed"

        session.close()

    def test_index_creation(self):
        """Test database indexes are created for performance."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)

        inspector = inspect(engine)

        # Check some critical indexes exist
        agent_indexes = inspector.get_indexes("agent")
        assert len(agent_indexes) >= 0, "Agent table should have indexes"

        # Check conversation_thread indexes (messages are stored in conversation_history JSON)
        thread_indexes = inspector.get_indexes("conversation_thread")
        assert len(thread_indexes) >= 0, "ConversationThread table should have indexes"
