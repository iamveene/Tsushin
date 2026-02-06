"""
Unit tests for Shell Skill models and endpoints (Phase 18).

Tests cover:
- ShellIntegration model (CRUD, API key generation/verification)
- ShellCommand model (lifecycle, status transitions)
- API endpoints for integration management
- Beacon registration and command queue endpoints
"""

import pytest
import hashlib
import base64
import secrets
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Test fixtures
from fastapi.testclient import TestClient


class TestShellIntegrationModel:
    """Tests for the ShellIntegration model."""

    def test_model_creation(self, db_session):
        """Test creating a ShellIntegration with all fields."""
        from models import HubIntegration, ShellIntegration

        # Create parent HubIntegration
        integration = ShellIntegration(
            name="Test Shell",
            description="Test shell integration",
            tenant_id=1,
            created_by=1,
            api_key_hash="test_hash_placeholder",
            poll_interval=30,
            mode="interactive",
            allowed_commands=["ls", "cat", "echo"],
            allowed_paths=["/home", "/tmp"],
            hostname="test-host",
            os_info="Linux 5.4.0",
            retention_days=30
        )

        db_session.add(integration)
        db_session.commit()

        # Verify polymorphic identity
        assert integration.type == "shell"
        assert integration.poll_interval == 30
        assert integration.mode == "interactive"
        assert "ls" in integration.allowed_commands
        assert "/home" in integration.allowed_paths

    def test_api_key_generation(self):
        """Test API key generation with proper format."""
        from api.routes_shell import generate_api_key

        api_key = generate_api_key()

        # Check format: shb_ prefix + 43 chars base64
        assert api_key.startswith("shb_")
        assert len(api_key) == 47  # 4 (prefix) + 43 (base64)

        # Verify base64 part is valid
        base64_part = api_key[4:]
        try:
            decoded = base64.urlsafe_b64decode(base64_part + "=")
            assert len(decoded) == 32  # 256 bits
        except Exception:
            pytest.fail("API key base64 part is not valid")

    def test_api_key_hashing(self):
        """Test API key hashing for secure storage."""
        from api.routes_shell import hash_api_key

        api_key = "shb_testkey123456789012345678901234567890123"
        hashed = hash_api_key(api_key)

        # Verify SHA-256 hash length (64 hex chars)
        assert len(hashed) == 64

        # Verify deterministic hashing
        assert hash_api_key(api_key) == hashed

    def test_api_key_verification(self):
        """Test API key verification logic."""
        from api.routes_shell import generate_api_key, hash_api_key, verify_api_key

        # Generate key and hash
        api_key = generate_api_key()
        hashed = hash_api_key(api_key)

        # Verify correct key
        assert verify_api_key(api_key, hashed) is True

        # Verify wrong key fails
        wrong_key = "shb_wrongkey12345678901234567890123456789012"
        assert verify_api_key(wrong_key, hashed) is False

    def test_last_checkin_update(self, db_session):
        """Test updating last_checkin timestamp."""
        from models import ShellIntegration

        integration = ShellIntegration(
            name="Checkin Test",
            tenant_id=1,
            created_by=1,
            api_key_hash="hash_placeholder",
            poll_interval=30
        )
        db_session.add(integration)
        db_session.commit()

        # Update last_checkin
        integration.last_checkin = datetime.utcnow()
        db_session.commit()

        # Verify update
        db_session.refresh(integration)
        assert integration.last_checkin is not None
        assert (datetime.utcnow() - integration.last_checkin).total_seconds() < 5


class TestShellCommandModel:
    """Tests for the ShellCommand model."""

    def test_command_creation(self, db_session):
        """Test creating a ShellCommand with all fields."""
        from models import ShellIntegration, ShellCommand

        # Create integration first
        integration = ShellIntegration(
            name="Command Test Integration",
            tenant_id=1,
            created_by=1,
            api_key_hash="hash_placeholder",
            poll_interval=30
        )
        db_session.add(integration)
        db_session.commit()

        # Create command
        command = ShellCommand(
            shell_integration_id=integration.id,
            command="ls -la /tmp",
            working_directory="/home/user",
            timeout_seconds=60,
            priority=5,
            requested_by=1,
            tenant_id=1
        )
        db_session.add(command)
        db_session.commit()

        assert command.status == "queued"
        assert command.command == "ls -la /tmp"
        assert command.priority == 5

    def test_command_status_transitions(self, db_session):
        """Test command status transitions through lifecycle."""
        from models import ShellIntegration, ShellCommand

        # Create integration and command
        integration = ShellIntegration(
            name="Status Test Integration",
            tenant_id=1,
            created_by=1,
            api_key_hash="hash_placeholder"
        )
        db_session.add(integration)
        db_session.commit()

        command = ShellCommand(
            shell_integration_id=integration.id,
            command="echo hello",
            requested_by=1,
            tenant_id=1
        )
        db_session.add(command)
        db_session.commit()

        # Transition: queued -> sent
        assert command.status == "queued"
        command.status = "sent"
        command.sent_at = datetime.utcnow()
        db_session.commit()

        # Transition: sent -> executing
        command.status = "executing"
        command.started_at = datetime.utcnow()
        db_session.commit()

        # Transition: executing -> completed
        command.status = "completed"
        command.completed_at = datetime.utcnow()
        command.exit_code = 0
        command.stdout = "hello"
        db_session.commit()

        db_session.refresh(command)
        assert command.status == "completed"
        assert command.exit_code == 0
        assert command.stdout == "hello"

    def test_command_failure_status(self, db_session):
        """Test command failure status with error info."""
        from models import ShellIntegration, ShellCommand

        integration = ShellIntegration(
            name="Failure Test Integration",
            tenant_id=1,
            created_by=1,
            api_key_hash="hash_placeholder"
        )
        db_session.add(integration)
        db_session.commit()

        command = ShellCommand(
            shell_integration_id=integration.id,
            command="invalid_command",
            requested_by=1,
            tenant_id=1
        )
        db_session.add(command)
        db_session.commit()

        # Simulate failure
        command.status = "failed"
        command.completed_at = datetime.utcnow()
        command.exit_code = 127
        command.stderr = "command not found"
        command.error_message = "Command execution failed"
        db_session.commit()

        db_session.refresh(command)
        assert command.status == "failed"
        assert command.exit_code == 127
        assert "not found" in command.stderr


class TestShellAPIEndpoints:
    """Tests for Shell Skill API endpoints."""

    def test_list_integrations_empty(self, test_client, auth_headers):
        """Test listing integrations when none exist."""
        response = test_client.get(
            "/api/shell/integrations",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_create_integration(self, test_client, auth_headers):
        """Test creating a new shell integration."""
        response = test_client.post(
            "/api/shell/integrations",
            headers=auth_headers,
            json={
                "name": "Test Shell Integration",
                "description": "For testing",
                "poll_interval": 60,
                "mode": "batch",
                "allowed_commands": ["ls", "cat"],
                "allowed_paths": ["/tmp"]
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Shell Integration"
        assert data["mode"] == "batch"
        assert "api_key" in data  # Key returned only on creation
        assert data["api_key"].startswith("shb_")

    def test_get_integration(self, test_client, auth_headers, shell_integration):
        """Test getting a specific integration."""
        response = test_client.get(
            f"/api/shell/integrations/{shell_integration.id}",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == shell_integration.id
        assert data["name"] == shell_integration.name
        # API key should NOT be returned on get
        assert "api_key" not in data

    def test_update_integration(self, test_client, auth_headers, shell_integration):
        """Test updating an integration."""
        response = test_client.patch(
            f"/api/shell/integrations/{shell_integration.id}",
            headers=auth_headers,
            json={
                "poll_interval": 120,
                "allowed_commands": ["ls", "cat", "grep"]
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["poll_interval"] == 120
        assert "grep" in data["allowed_commands"]

    def test_delete_integration(self, test_client, auth_headers, shell_integration):
        """Test deleting an integration."""
        response = test_client.delete(
            f"/api/shell/integrations/{shell_integration.id}",
            headers=auth_headers
        )

        assert response.status_code == 204

        # Verify deleted
        get_response = test_client.get(
            f"/api/shell/integrations/{shell_integration.id}",
            headers=auth_headers
        )
        assert get_response.status_code == 404

    def test_regenerate_api_key(self, test_client, auth_headers, shell_integration):
        """Test regenerating API key for an integration."""
        response = test_client.post(
            f"/api/shell/integrations/{shell_integration.id}/regenerate-key",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "api_key" in data
        assert data["api_key"].startswith("shb_")


class TestBeaconEndpoints:
    """Tests for beacon registration and command queue endpoints."""

    def test_beacon_register(self, test_client, shell_integration_with_key):
        """Test beacon registration with valid API key."""
        integration, api_key = shell_integration_with_key

        response = test_client.post(
            "/api/shell/register",
            headers={"X-Shell-Api-Key": api_key},
            json={
                "hostname": "beacon-host",
                "os_info": "Linux 5.15.0",
                "remote_ip": "192.168.1.100"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "registered"
        assert data["poll_interval"] == integration.poll_interval

    def test_beacon_register_invalid_key(self, test_client):
        """Test beacon registration with invalid API key."""
        response = test_client.post(
            "/api/shell/register",
            headers={"X-Shell-Api-Key": "shb_invalidkey12345678901234567890123456789"},
            json={
                "hostname": "beacon-host",
                "os_info": "Linux"
            }
        )

        assert response.status_code == 401

    def test_beacon_checkin(self, test_client, shell_integration_with_key):
        """Test beacon check-in (polling for commands)."""
        integration, api_key = shell_integration_with_key

        response = test_client.post(
            "/api/shell/checkin",
            headers={"X-Shell-Api-Key": api_key}
        )

        assert response.status_code == 200
        data = response.json()
        assert "commands" in data
        assert isinstance(data["commands"], list)

    def test_beacon_checkin_with_queued_commands(
        self, test_client, auth_headers, shell_integration_with_key, db_session
    ):
        """Test beacon check-in returns queued commands."""
        from models import ShellCommand

        integration, api_key = shell_integration_with_key

        # Create a queued command
        command = ShellCommand(
            shell_integration_id=integration.id,
            command="echo test",
            requested_by=1,
            tenant_id=1
        )
        db_session.add(command)
        db_session.commit()

        # Beacon check-in should return the command
        response = test_client.post(
            "/api/shell/checkin",
            headers={"X-Shell-Api-Key": api_key}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["commands"]) >= 1

        returned_cmd = next(
            (c for c in data["commands"] if c["id"] == command.id),
            None
        )
        assert returned_cmd is not None
        assert returned_cmd["command"] == "echo test"

    def test_beacon_submit_result(
        self, test_client, shell_integration_with_key, db_session
    ):
        """Test beacon submitting command result."""
        from models import ShellCommand

        integration, api_key = shell_integration_with_key

        # Create a command in "sent" status
        command = ShellCommand(
            shell_integration_id=integration.id,
            command="echo hello",
            status="sent",
            sent_at=datetime.utcnow(),
            requested_by=1,
            tenant_id=1
        )
        db_session.add(command)
        db_session.commit()

        # Submit result
        response = test_client.post(
            "/api/shell/result",
            headers={"X-Shell-Api-Key": api_key},
            json={
                "command_id": command.id,
                "status": "completed",
                "exit_code": 0,
                "stdout": "hello\n",
                "stderr": "",
                "started_at": datetime.utcnow().isoformat() + "Z",
                "completed_at": datetime.utcnow().isoformat() + "Z"
            }
        )

        assert response.status_code == 200

        # Verify command updated
        db_session.refresh(command)
        assert command.status == "completed"
        assert command.exit_code == 0
        assert command.stdout == "hello\n"


class TestCommandQueueEndpoints:
    """Tests for command queue management endpoints."""

    def test_list_commands(self, test_client, auth_headers, shell_integration):
        """Test listing commands for an integration."""
        response = test_client.get(
            f"/api/shell/commands?integration_id={shell_integration.id}",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    def test_queue_command(self, test_client, auth_headers, shell_integration):
        """Test queuing a new command."""
        response = test_client.post(
            "/api/shell/commands",
            headers=auth_headers,
            json={
                "integration_id": shell_integration.id,
                "command": "whoami",
                "working_directory": "/tmp",
                "timeout_seconds": 30,
                "priority": 10
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["command"] == "whoami"
        assert data["status"] == "queued"
        assert data["priority"] == 10

    def test_get_command(self, test_client, auth_headers, shell_command):
        """Test getting a specific command."""
        response = test_client.get(
            f"/api/shell/commands/{shell_command.id}",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == shell_command.id

    def test_cancel_command(self, test_client, auth_headers, shell_command):
        """Test cancelling a queued command."""
        response = test_client.delete(
            f"/api/shell/commands/{shell_command.id}",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"


# Fixtures
@pytest.fixture
def db_session():
    """Create a test database session."""
    from models import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    session.close()
    engine.dispose()


@pytest.fixture
def test_client(db_session):
    """Create a test client with mocked database."""
    from app import app
    from api.routes import set_engine
    from api.routes_shell import set_engine as set_shell_engine

    # Set up test engine
    engine = db_session.get_bind()
    set_engine(engine)
    set_shell_engine(engine)

    with TestClient(app) as client:
        yield client


@pytest.fixture
def auth_headers():
    """Generate mock authentication headers."""
    # In production, this would be a real JWT token
    return {
        "Authorization": "Bearer test-token",
        "X-Tenant-Id": "1"
    }


@pytest.fixture
def shell_integration(db_session):
    """Create a test shell integration."""
    from models import ShellIntegration
    from api.routes_shell import generate_api_key, hash_api_key

    api_key = generate_api_key()

    integration = ShellIntegration(
        name="Test Integration",
        tenant_id=1,
        created_by=1,
        api_key_hash=hash_api_key(api_key),
        poll_interval=30,
        mode="interactive"
    )
    db_session.add(integration)
    db_session.commit()

    return integration


@pytest.fixture
def shell_integration_with_key(db_session):
    """Create a test shell integration and return with API key."""
    from models import ShellIntegration
    from api.routes_shell import generate_api_key, hash_api_key

    api_key = generate_api_key()

    integration = ShellIntegration(
        name="Test Integration With Key",
        tenant_id=1,
        created_by=1,
        api_key_hash=hash_api_key(api_key),
        poll_interval=30
    )
    db_session.add(integration)
    db_session.commit()

    return integration, api_key


@pytest.fixture
def shell_command(db_session, shell_integration):
    """Create a test shell command."""
    from models import ShellCommand

    command = ShellCommand(
        shell_integration_id=shell_integration.id,
        command="echo test",
        requested_by=1,
        tenant_id=1
    )
    db_session.add(command)
    db_session.commit()

    return command


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
