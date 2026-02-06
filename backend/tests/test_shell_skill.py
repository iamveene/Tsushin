"""
Shell Skill Integration Tests - Phase 18.3

Tests for:
- ShellCommandService
- ShellSkill
- Command queueing and result handling
- Target resolution
"""

import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import ShellIntegration, ShellCommand, Agent, HubIntegration
from services.shell_command_service import ShellCommandService, CommandResult, CommandStatus
from agent.skills.shell_skill import ShellSkill
from agent.skills.base import InboundMessage


# Test database setup
@pytest.fixture
def db_session():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")

    # Only create the tables we need for shell tests (avoid FK issues with other tables)
    from models import Base
    tables_to_create = [
        HubIntegration.__table__,
        ShellIntegration.__table__,
        ShellCommand.__table__,
        Agent.__table__,
    ]

    # Create tables in order (respecting FK dependencies)
    for table in tables_to_create:
        table.create(engine, checkfirst=True)

    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def test_tenant_id():
    """Test tenant ID."""
    return "test-tenant-001"


@pytest.fixture
def test_agent(db_session, test_tenant_id):
    """Create a test agent."""
    agent = Agent(
        contact_id=1,
        system_prompt="You are a test agent",
        tenant_id=test_tenant_id,
        is_active=True
    )
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)
    return agent


@pytest.fixture
def test_shell(db_session, test_tenant_id):
    """Create a test shell integration using raw SQL to avoid inheritance issues."""
    from sqlalchemy import text

    # Insert hub_integration first
    db_session.execute(text("""
        INSERT INTO hub_integration (type, name, display_name, is_active, tenant_id, health_status)
        VALUES (:type, :name, :display_name, :is_active, :tenant_id, :health_status)
    """), {
        "type": "shell",
        "name": "test-server",
        "display_name": "Test Server",
        "is_active": True,
        "tenant_id": test_tenant_id,
        "health_status": "healthy"
    })

    # Get the inserted hub id
    result = db_session.execute(text("SELECT last_insert_rowid()"))
    hub_id = result.scalar()

    # Insert shell_integration
    db_session.execute(text("""
        INSERT INTO shell_integration (id, api_key_hash, poll_interval, mode, hostname, last_checkin, os_info)
        VALUES (:id, :api_key_hash, :poll_interval, :mode, :hostname, :last_checkin, :os_info)
    """), {
        "id": hub_id,
        "api_key_hash": "test_hash_12345",
        "poll_interval": 5,
        "mode": "beacon",
        "hostname": "test-server",
        "last_checkin": datetime.utcnow().isoformat() + "Z",
        "os_info": '{"name": "Linux", "version": "5.15.0"}'
    })

    db_session.commit()

    # Load and return the shell integration
    shell = db_session.query(ShellIntegration).filter(ShellIntegration.id == hub_id).first()
    return shell


class TestShellCommandService:
    """Tests for ShellCommandService."""

    def test_get_available_shells(self, db_session, test_tenant_id, test_shell):
        """Test listing available shells."""
        service = ShellCommandService(db_session)
        shells = service.get_available_shells(test_tenant_id)

        assert len(shells) == 1
        assert shells[0].id == test_shell.id
        assert shells[0].hostname == "test-server"

    def test_get_available_shells_empty(self, db_session):
        """Test listing shells for tenant with no shells."""
        service = ShellCommandService(db_session)
        shells = service.get_available_shells("nonexistent-tenant")

        assert len(shells) == 0

    def test_find_shell_by_target_default(self, db_session, test_tenant_id, test_shell):
        """Test finding shell with 'default' target."""
        service = ShellCommandService(db_session)
        shell, error = service.find_shell_by_target("default", test_tenant_id)

        assert error is None
        assert shell is not None
        assert shell.id == test_shell.id

    def test_find_shell_by_target_hostname(self, db_session, test_tenant_id, test_shell):
        """Test finding shell by hostname."""
        service = ShellCommandService(db_session)
        shell, error = service.find_shell_by_target("test-server", test_tenant_id)

        assert error is None
        assert shell is not None
        assert shell.hostname == "test-server"

    def test_find_shell_by_target_not_found(self, db_session, test_tenant_id, test_shell):
        """Test finding non-existent shell."""
        service = ShellCommandService(db_session)
        shell, error = service.find_shell_by_target("nonexistent-host", test_tenant_id)

        assert shell is None
        assert error is not None
        assert "No shell found" in error

    def test_find_shell_by_target_all(self, db_session, test_tenant_id, test_shell):
        """Test that @all returns None (handled separately)."""
        service = ShellCommandService(db_session)
        shell, error = service.find_shell_by_target("@all", test_tenant_id)

        assert shell is None
        assert error is None  # @all is valid, just handled differently

    def test_queue_command(self, db_session, test_tenant_id, test_shell):
        """Test queueing a command."""
        service = ShellCommandService(db_session)

        command = service.queue_command(
            shell_id=test_shell.id,
            commands=["ls -la", "pwd"],
            initiated_by="user:test@example.com",
            tenant_id=test_tenant_id,
            timeout_seconds=60
        )

        assert command.id is not None
        assert command.shell_id == test_shell.id
        assert command.commands == ["ls -la", "pwd"]
        assert command.status == CommandStatus.QUEUED.value
        assert command.tenant_id == test_tenant_id

    def test_get_command_result_not_found(self, db_session):
        """Test getting result for non-existent command."""
        service = ShellCommandService(db_session)
        result = service.get_command_result("nonexistent-uuid")

        assert result.success is False
        assert result.status == "not_found"

    def test_get_command_result_queued(self, db_session, test_tenant_id, test_shell):
        """Test getting result for queued command."""
        service = ShellCommandService(db_session)

        command = service.queue_command(
            shell_id=test_shell.id,
            commands=["ls"],
            initiated_by="user:test",
            tenant_id=test_tenant_id
        )

        result = service.get_command_result(command.id)

        assert result.success is False  # Not completed yet
        assert result.status == CommandStatus.QUEUED.value

    def test_get_command_result_completed(self, db_session, test_tenant_id, test_shell):
        """Test getting result for completed command."""
        service = ShellCommandService(db_session)

        # Create and manually complete a command
        command = service.queue_command(
            shell_id=test_shell.id,
            commands=["ls"],
            initiated_by="user:test",
            tenant_id=test_tenant_id
        )

        # Simulate beacon completing the command
        command.status = CommandStatus.COMPLETED.value
        command.exit_code = 0
        command.stdout = "file1.txt\nfile2.txt"
        command.completed_at = datetime.utcnow()
        db_session.commit()

        result = service.get_command_result(command.id)

        assert result.success is True
        assert result.status == CommandStatus.COMPLETED.value
        assert result.exit_code == 0
        assert result.stdout == "file1.txt\nfile2.txt"

    def test_execute_command_no_shells(self, db_session):
        """Test executing command when no shells are available."""
        service = ShellCommandService(db_session)

        result = service.execute_command(
            script="ls",
            target="default",
            tenant_id="nonexistent-tenant",
            initiated_by="user:test",
            wait_for_result=False
        )

        assert result.success is False
        assert "No shell" in result.error_message

    def test_execute_command_fire_and_forget(self, db_session, test_tenant_id, test_shell):
        """Test fire-and-forget execution."""
        service = ShellCommandService(db_session)

        result = service.execute_command(
            script="ls -la",
            target="default",
            tenant_id=test_tenant_id,
            initiated_by="user:test",
            wait_for_result=False
        )

        assert result.success is True
        assert result.status == CommandStatus.QUEUED.value
        assert result.command_id is not None


class TestCommandResult:
    """Tests for CommandResult formatting."""

    def test_to_agent_response_success(self):
        """Test successful command response."""
        result = CommandResult(
            success=True,
            command_id="test-id",
            status="completed",
            exit_code=0,
            stdout="Hello, World!"
        )

        response = result.to_agent_response()

        assert "✅" in response
        assert "Hello, World!" in response
        assert "exit code: 0" in response

    def test_to_agent_response_failure(self):
        """Test failed command response."""
        result = CommandResult(
            success=False,
            command_id="test-id",
            status="failed",
            exit_code=1,
            stderr="Command not found"
        )

        response = result.to_agent_response()

        assert "❌" in response
        assert "Command not found" in response
        assert "exit code: 1" in response

    def test_to_agent_response_timeout(self):
        """Test timeout response."""
        result = CommandResult(
            success=False,
            command_id="test-id",
            status="timeout",
            timed_out=True
        )

        response = result.to_agent_response()

        assert "⏱️" in response
        assert "timed out" in response

    def test_to_agent_response_truncated(self):
        """Test long output is truncated."""
        long_output = "x" * 3000
        result = CommandResult(
            success=True,
            command_id="test-id",
            status="completed",
            exit_code=0,
            stdout=long_output
        )

        response = result.to_agent_response()

        assert len(response) < 3000
        assert "truncated" in response


class TestShellSkill:
    """Tests for ShellSkill."""

    @pytest.fixture
    def skill(self, db_session, test_agent):
        """Create a configured ShellSkill."""
        skill = ShellSkill()
        skill.set_db_session(db_session)
        skill._agent_id = test_agent.id
        skill._config = ShellSkill.get_default_config()
        return skill

    @pytest.mark.asyncio
    async def test_can_handle_slash_command(self, skill):
        """Test detection of /shell command."""
        message = InboundMessage(
            id="1",
            sender="user",
            sender_key="12345",
            body="/shell ls -la",
            chat_id="chat1",
            chat_name="Test",
            is_group=False,
            timestamp=datetime.now()
        )

        result = await skill.can_handle(message)
        assert result is True

    @pytest.mark.asyncio
    async def test_can_handle_slash_command_with_target(self, skill):
        """Test detection of /shell command with target."""
        message = InboundMessage(
            id="1",
            sender="user",
            sender_key="12345",
            body="/shell server-001:df -h",
            chat_id="chat1",
            chat_name="Test",
            is_group=False,
            timestamp=datetime.now()
        )

        result = await skill.can_handle(message)
        assert result is True

    @pytest.mark.asyncio
    async def test_can_handle_regular_message(self, skill):
        """Test that regular messages are not handled."""
        message = InboundMessage(
            id="1",
            sender="user",
            sender_key="12345",
            body="Hello, how are you?",
            chat_id="chat1",
            chat_name="Test",
            is_group=False,
            timestamp=datetime.now()
        )

        result = await skill.can_handle(message)
        assert result is False

    @pytest.mark.asyncio
    async def test_process_shell_command(self, skill, test_shell):
        """Test processing a /shell command."""
        message = InboundMessage(
            id="1",
            sender="user",
            sender_key="12345",
            body="/shell ls -la",
            chat_id="chat1",
            chat_name="Test",
            is_group=False,
            timestamp=datetime.now()
        )

        config = ShellSkill.get_default_config()
        result = await skill.process(message, config)

        assert result.success is True
        assert "queued" in result.output.lower()
        assert result.metadata.get("command_id") is not None

    @pytest.mark.asyncio
    async def test_process_shell_command_with_target(self, skill, test_shell):
        """Test processing a /shell command with target."""
        message = InboundMessage(
            id="1",
            sender="user",
            sender_key="12345",
            body="/shell test-server:uptime",
            chat_id="chat1",
            chat_name="Test",
            is_group=False,
            timestamp=datetime.now()
        )

        config = ShellSkill.get_default_config()
        result = await skill.process(message, config)

        assert result.success is True
        assert result.metadata.get("target") == "test-server"

    def test_get_tool_definition(self):
        """Test tool definition schema."""
        definition = ShellSkill.get_tool_definition()

        assert definition["name"] == "run_shell_command"
        assert "parameters" in definition
        assert "script" in definition["parameters"]["properties"]
        assert "target" in definition["parameters"]["properties"]
        assert "timeout" in definition["parameters"]["properties"]

    def test_get_available_targets(self, skill, test_shell):
        """Test getting available targets."""
        targets = skill.get_available_targets()

        assert len(targets) == 1
        assert targets[0]["hostname"] == "test-server"
        assert targets[0]["is_online"] is True


class TestShellToolIntegration:
    """Integration tests for shell tool execution."""

    @pytest.mark.asyncio
    async def test_tool_execution_flow(self, db_session, test_tenant_id, test_shell, test_agent):
        """Test full tool execution flow."""
        from agent.tools.shell_tool import run_shell_command

        # Execute command (fire and forget since we can't wait in tests)
        with patch.object(ShellCommandService, 'wait_for_completion') as mock_wait:
            mock_wait.return_value = CommandResult(
                success=True,
                command_id="test-uuid",
                status="completed",
                exit_code=0,
                stdout="test output"
            )

            result = await run_shell_command(
                script="ls -la",
                db=db_session,
                agent_id=test_agent.id,
                target="default",
                timeout=60
            )

        assert "✅" in result or "queued" in result.lower()


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
