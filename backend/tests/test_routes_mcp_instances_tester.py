"""
Targeted regression tests for tester MCP routes.
"""

import asyncio
import os
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

docker_stub = types.ModuleType("docker")
docker_stub.errors = types.SimpleNamespace(NotFound=Exception, DockerException=Exception)
docker_stub.DockerClient = object
sys.modules.setdefault("docker", docker_stub)

argon2_stub = types.ModuleType("argon2")

class _PasswordHasher:
    def hash(self, value):
        return value

    def verify(self, hashed, plain):
        return hashed == plain

argon2_stub.PasswordHasher = _PasswordHasher
argon2_exceptions_stub = types.ModuleType("argon2.exceptions")
argon2_exceptions_stub.VerifyMismatchError = ValueError
argon2_exceptions_stub.InvalidHashError = ValueError
sys.modules.setdefault("argon2", argon2_stub)
sys.modules.setdefault("argon2.exceptions", argon2_exceptions_stub)

from api.routes_mcp_instances import (
    get_tester_qr_code,
    get_tester_status,
    logout_tester,
    restart_tester,
)


@pytest.fixture
def mock_user():
    return SimpleNamespace(id=1, tenant_id="tenant_123", email="test@example.com", is_global_admin=False)


def test_get_tester_status_success(mock_user):
    manager = MagicMock()
    manager.get_tester_status.return_value = {
        "name": "tester-mcp",
        "api_url": "http://tester-mcp:8080/api",
        "status": "healthy",
        "container_id": "abc123",
        "container_state": "running",
        "image": "tsushin/tester:latest",
        "api_reachable": True,
        "connected": True,
        "authenticated": True,
        "needs_reauth": False,
        "is_reconnecting": False,
        "reconnect_attempts": 0,
        "session_age_sec": 10,
        "last_activity_sec": 2,
        "qr_available": False,
        "error": None,
    }

    with patch("api.routes_mcp_instances.MCPContainerManager", return_value=manager):
        response = asyncio.run(get_tester_status(current_user=mock_user, _=None))

    assert response.status == "healthy"
    assert response.api_reachable is True
    assert response.qr_message is None


def test_get_tester_status_sets_qr_message_when_qr_available(mock_user):
    manager = MagicMock()
    manager.get_tester_status.return_value = {
        "name": "tester-mcp",
        "api_url": "http://tester-mcp:8080/api",
        "status": "degraded",
        "container_id": "abc123",
        "container_state": "running",
        "image": None,
        "api_reachable": True,
        "connected": False,
        "authenticated": False,
        "needs_reauth": True,
        "is_reconnecting": False,
        "reconnect_attempts": 1,
        "session_age_sec": 0,
        "last_activity_sec": 0,
        "qr_available": True,
        "error": None,
    }

    with patch("api.routes_mcp_instances.MCPContainerManager", return_value=manager):
        response = asyncio.run(get_tester_status(current_user=mock_user, _=None))

    assert response.qr_available is True
    assert response.qr_message == "Scan QR code with WhatsApp"


def test_get_tester_qr_code_success(mock_user):
    manager = MagicMock()
    manager.get_tester_qr_code.return_value = "base64-qr"

    with patch("api.routes_mcp_instances.MCPContainerManager", return_value=manager):
        response = asyncio.run(get_tester_qr_code(current_user=mock_user, _=None))

    assert response.qr_code == "base64-qr"
    assert response.message == "Scan QR code with WhatsApp"


def test_restart_tester_success(mock_user):
    manager = MagicMock()

    with patch("api.routes_mcp_instances.MCPContainerManager", return_value=manager):
        response = asyncio.run(restart_tester(current_user=mock_user, _=None))

    manager.restart_tester.assert_called_once()
    assert response["success"] is True


def test_logout_tester_success(mock_user):
    manager = MagicMock()
    manager.logout_tester.return_value = {
        "success": True,
        "message": "Tester authentication reset",
    }

    with patch("api.routes_mcp_instances.MCPContainerManager", return_value=manager):
        response = asyncio.run(logout_tester(current_user=mock_user, _=None))

    manager.logout_tester.assert_called_once()
    assert response.success is True
    assert response.message == "Tester authentication reset"
    assert response.qr_code_ready is False


def test_get_tester_qr_code_returns_500_on_manager_exception(mock_user):
    manager = MagicMock()
    manager.get_tester_qr_code.side_effect = RuntimeError("boom")

    with patch("api.routes_mcp_instances.MCPContainerManager", return_value=manager):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_tester_qr_code(current_user=mock_user, _=None))

    assert exc_info.value.status_code == 500
    assert "Failed to fetch tester QR code" in exc_info.value.detail
