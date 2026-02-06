"""
Integration Tests: Command Processing
Tests slash command and project pattern system with real database.
"""

import pytest
import re
from models import SlashCommand, ProjectCommandPattern
from models_rbac import Tenant


@pytest.mark.integration
class TestCommandProcessingIntegration:
    """Integration tests for command processing with database."""

    def test_create_and_match_slash_command(self, integration_db, sample_tenant):
        """Test creating slash command and pattern matching."""
        tenant, user = sample_tenant

        # Create slash command
        cmd = SlashCommand(
            tenant_id=tenant.id,
            category="project",
            command_name="project enter",
            language_code="en",
            pattern=r"^/(project|p)\s+enter\s+(.+)$",
            aliases=["p", "proj"],
            description="Enter a project",
            handler_type="built-in",
            handler_config={},
            is_enabled=True
        )
        integration_db.add(cmd)
        integration_db.commit()

        # Test pattern matching
        test_input = "/project enter my-project"
        match = re.match(cmd.pattern, test_input)

        assert match is not None
        assert match.group(1) == "project"
        assert match.group(2) == "my-project"

    def test_command_aliases(self, integration_db, sample_tenant):
        """Test command with multiple aliases."""
        tenant, user = sample_tenant

        cmd = SlashCommand(
            tenant_id=tenant.id,
            category="agent",
            command_name="invoke",
            language_code="en",
            pattern=r"^/(invoke|inv|i)\s+(.+)$",
            aliases=["inv", "i"],
            handler_type="built-in",
            handler_config={},
            is_enabled=True
        )
        integration_db.add(cmd)
        integration_db.commit()

        # Test all aliases work
        assert re.match(cmd.pattern, "/invoke test")
        assert re.match(cmd.pattern, "/inv test")
        assert re.match(cmd.pattern, "/i test")

    def test_multilingual_project_patterns(self, integration_db, sample_tenant):
        """Test project command patterns in multiple languages."""
        tenant, user = sample_tenant

        # English pattern
        pattern_en = ProjectCommandPattern(
            tenant_id=tenant.id,
            command_type="enter",
            language_code="en",
            pattern=r"(enter|join|start)\s+(.+)",
            response_template="Entering project: {project_name}",
            is_active=True
        )

        # Portuguese pattern
        pattern_pt = ProjectCommandPattern(
            tenant_id=tenant.id,
            command_type="enter",
            language_code="pt",
            pattern=r"(entrar|começar)\s+(.+)",
            response_template="Entrando no projeto: {project_name}",
            is_active=True
        )

        integration_db.add_all([pattern_en, pattern_pt])
        integration_db.commit()

        # Test English matching
        en_match = re.search(pattern_en.pattern, "enter my-project", re.IGNORECASE)
        assert en_match is not None

        # Test Portuguese matching
        pt_match = re.search(pattern_pt.pattern, "entrar meu-projeto", re.IGNORECASE)
        assert pt_match is not None

    def test_command_tenant_isolation(self, integration_db):
        """Test commands are isolated by tenant."""
        # Create two tenants
        tenant1 = Tenant(id="tenant1", name="Org 1", slug="org-1")
        tenant2 = Tenant(id="tenant2", name="Org 2", slug="org-2")
        integration_db.add_all([tenant1, tenant2])
        integration_db.commit()

        # Create command for tenant1
        cmd1 = SlashCommand(
            tenant_id=tenant1.id,
            category="custom",
            command_name="custom1",
            pattern=r"^/custom1$",
            handler_type="built-in",
            handler_config={},
            is_enabled=True
        )

        # Create command for tenant2
        cmd2 = SlashCommand(
            tenant_id=tenant2.id,
            category="custom",
            command_name="custom2",
            pattern=r"^/custom2$",
            handler_type="built-in",
            handler_config={},
            is_enabled=True
        )

        integration_db.add_all([cmd1, cmd2])
        integration_db.commit()

        # Query by tenant
        t1_cmds = integration_db.query(SlashCommand).filter(
            SlashCommand.tenant_id == tenant1.id
        ).all()

        t2_cmds = integration_db.query(SlashCommand).filter(
            SlashCommand.tenant_id == tenant2.id
        ).all()

        assert len(t1_cmds) == 1
        assert len(t2_cmds) == 1
        assert t1_cmds[0].command_name == "custom1"
        assert t2_cmds[0].command_name == "custom2"

    def test_active_vs_inactive_commands(self, integration_db, sample_tenant):
        """Test filtering active vs inactive commands."""
        tenant, user = sample_tenant

        # Create active command
        active_cmd = SlashCommand(
            tenant_id=tenant.id,
            category="test",
            command_name="active",
            pattern=r"^/active$",
            handler_type="built-in",
            handler_config={},
            is_enabled=True
        )

        # Create inactive command
        inactive_cmd = SlashCommand(
            tenant_id=tenant.id,
            category="test",
            command_name="inactive",
            pattern=r"^/inactive$",
            handler_type="built-in",
            handler_config={},
            is_enabled=False
        )

        integration_db.add_all([active_cmd, inactive_cmd])
        integration_db.commit()

        # Query only active commands
        active_commands = integration_db.query(SlashCommand).filter(
            SlashCommand.tenant_id == tenant.id,
            SlashCommand.is_enabled == True
        ).all()

        assert len(active_commands) == 1
        assert active_commands[0].command_name == "active"

    def test_project_pattern_command_types(self, integration_db, sample_tenant):
        """Test all project command types."""
        tenant, user = sample_tenant

        command_types = ["enter", "exit", "upload", "list", "help"]

        # Create pattern for each type
        for cmd_type in command_types:
            pattern = ProjectCommandPattern(
                tenant_id=tenant.id,
                command_type=cmd_type,
                language_code="en",
                pattern=f"{cmd_type}.*",
                response_template=f"Executing {cmd_type}",
                is_active=True
            )
            integration_db.add(pattern)

        integration_db.commit()

        # Verify all created
        patterns = integration_db.query(ProjectCommandPattern).filter(
            ProjectCommandPattern.tenant_id == tenant.id
        ).all()

        assert len(patterns) == 5
        retrieved_types = {p.command_type for p in patterns}
        assert retrieved_types == set(command_types)
