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
    MCPInstanceCreate,
    create_mcp_instance,
    get_tester_qr_code,
    get_tester_status,
    logout_tester,
    restart_tester,
)


@pytest.fixture
def mock_user():
    return SimpleNamespace(id=1, tenant_id="tenant_123", email="test@example.com", is_global_admin=False)


@pytest.fixture
def global_admin_without_tenant():
    return SimpleNamespace(id=99, tenant_id=None, email="admin@example.com", is_global_admin=True)


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
    manager.get_tester_phone_number.return_value = None

    with patch("api.routes_mcp_instances.MCPContainerManager", return_value=manager) as manager_cls:
        response = asyncio.run(get_tester_status(current_user=mock_user, _=None))

    manager_cls.assert_called_once_with(mock_user.tenant_id)
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
    manager.get_tester_phone_number.return_value = None

    with patch("api.routes_mcp_instances.MCPContainerManager", return_value=manager) as manager_cls:
        response = asyncio.run(get_tester_status(current_user=mock_user, _=None))

    manager_cls.assert_called_once_with(mock_user.tenant_id)
    assert response.qr_available is True
    assert response.qr_message == "Scan QR code with WhatsApp"


def test_get_tester_status_preserves_runtime_source(mock_user):
    manager = MagicMock()
    manager.get_tester_status.return_value = {
        "name": "runtime-tester-1",
        "api_url": "http://runtime-tester-1:8080/api",
        "status": "healthy",
        "container_id": "abc123",
        "container_state": "running",
        "image": "tsushin/tester-mcp:latest",
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
        "source": "runtime",
    }
    manager.get_tester_phone_number.return_value = None

    with patch("api.routes_mcp_instances.MCPContainerManager", return_value=manager):
        response = asyncio.run(get_tester_status(current_user=mock_user, _=None))

    assert response.source == "runtime"


def test_get_tester_qr_code_success(mock_user):
    manager = MagicMock()
    manager.get_tester_qr_code.return_value = "base64-qr"

    with patch("api.routes_mcp_instances.MCPContainerManager", return_value=manager) as manager_cls:
        response = asyncio.run(get_tester_qr_code(current_user=mock_user, _=None))

    manager_cls.assert_called_once_with(mock_user.tenant_id)
    assert response.qr_code == "base64-qr"
    assert response.message == "Scan QR code with WhatsApp"


def test_restart_tester_success(mock_user):
    manager = MagicMock()

    with patch("api.routes_mcp_instances.MCPContainerManager", return_value=manager) as manager_cls:
        response = asyncio.run(restart_tester(current_user=mock_user, _=None))

    manager_cls.assert_called_once_with(mock_user.tenant_id)
    manager.restart_tester.assert_called_once()
    assert response["success"] is True


def test_logout_tester_success(mock_user):
    manager = MagicMock()
    manager.logout_tester.return_value = {
        "success": True,
        "message": "Tester authentication reset",
    }

    with patch("api.routes_mcp_instances.MCPContainerManager", return_value=manager) as manager_cls:
        response = asyncio.run(logout_tester(current_user=mock_user, _=None))

    manager_cls.assert_called_once_with(mock_user.tenant_id)
    manager.logout_tester.assert_called_once()
    assert response.success is True
    assert response.message == "Tester authentication reset"
    assert response.qr_code_ready is False


def test_get_tester_qr_code_returns_500_on_manager_exception(mock_user):
    manager = MagicMock()
    manager.get_tester_qr_code.side_effect = RuntimeError("boom")

    with patch("api.routes_mcp_instances.MCPContainerManager", return_value=manager) as manager_cls:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_tester_qr_code(current_user=mock_user, _=None))

    manager_cls.assert_called_once_with(mock_user.tenant_id)
    assert exc_info.value.status_code == 500
    assert "Failed to fetch tester QR code" in exc_info.value.detail


def test_get_tester_status_rejects_missing_tenant_context(global_admin_without_tenant):
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_tester_status(current_user=global_admin_without_tenant, _=None, db=MagicMock()))

    assert exc_info.value.status_code == 403
    assert "Tenant context required" in exc_info.value.detail


def test_create_mcp_instance_rejects_missing_tenant_context(global_admin_without_tenant):
    request = MagicMock()
    request.app.state = SimpleNamespace()
    db = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            create_mcp_instance(
                data=MCPInstanceCreate(phone_number="+5500000000001", instance_type="tester"),
                request=request,
                current_user=global_admin_without_tenant,
                _=None,
                context=SimpleNamespace(),
                db=db,
            )
        )

    assert exc_info.value.status_code == 403
    assert "Tenant context required" in exc_info.value.detail


def test_create_mcp_instance_conflict_hides_foreign_instance_metadata(mock_user):
    request = MagicMock()
    request.app.state = SimpleNamespace()
    foreign_instance = SimpleNamespace(id=42, tenant_id="tenant_other", phone_number="+55 11 99999-1111")
    db = MagicMock()
    db.query.return_value.all.return_value = [foreign_instance]

    manager = MagicMock()

    with patch("api.routes_mcp_instances.MCPContainerManager", return_value=manager):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                create_mcp_instance(
                    data=MCPInstanceCreate(phone_number="+5511999991111", instance_type="agent"),
                    request=request,
                    current_user=mock_user,
                    _=None,
                    context=SimpleNamespace(),
                    db=db,
                )
            )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "An existing WhatsApp MCP instance already uses this phone number."
    assert "42" not in exc_info.value.detail
