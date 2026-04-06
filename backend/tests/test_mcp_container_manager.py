"""
Regression tests for MCPContainerManager.

These cover the WhatsApp reliability fixes around stale instance metadata,
blank container IDs, and health-check recovery via container-name fallback.
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

docker_stub = types.ModuleType("docker")
docker_stub.errors = types.SimpleNamespace(NotFound=Exception, DockerException=Exception)
docker_stub.DockerClient = object
sys.modules.setdefault("docker", docker_stub)

from models import WhatsAppMCPInstance
from services.container_runtime import ContainerNotFoundError
from services.mcp_container_manager import MCPContainerManager


@pytest.fixture
def mock_runtime():
    with patch("services.mcp_container_manager.get_container_runtime") as mock_get_runtime:
        runtime = MagicMock()
        mock_get_runtime.return_value = runtime
        yield runtime


@pytest.fixture
def manager(mock_runtime):
    return MCPContainerManager()


@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)


@pytest.fixture
def mock_instance():
    instance = MagicMock(spec=WhatsAppMCPInstance)
    instance.id = 2
    instance.tenant_id = "tenant_123"
    instance.container_name = "mcp-agent-tenant_123_1712400000"
    instance.phone_number = "+5511999999999"
    instance.instance_type = "agent"
    instance.container_id = ""
    instance.mcp_api_url = "http://legacy-host:8080/api"
    instance.mcp_port = 8080
    instance.messages_db_path = "/data/messages.db"
    instance.session_data_path = "/data/session"
    instance.api_secret = "secret"
    instance.status = "running"
    return instance


def _container_for(name: str):
    container = MagicMock()
    container.id = name
    return container


class TestMCPContainerManager:
    @patch("services.mcp_container_manager.requests.get")
    def test_health_check_recovers_when_container_id_is_blank_but_container_name_resolves(
        self,
        mock_requests,
        manager,
        mock_db,
        mock_runtime,
        mock_instance,
    ):
        resolved_container = _container_for("resolved-container-id")

        def get_container(ref):
            if ref == mock_instance.container_name:
                return resolved_container
            raise ContainerNotFoundError(ref)

        mock_runtime.get_container.side_effect = get_container
        mock_runtime.get_container_attrs.return_value = {
            "NetworkSettings": {"Ports": {"8080/tcp": [{"HostPort": "8091"}]}}
        }
        mock_runtime.get_container_status.return_value = "running"

        mock_response = MagicMock(status_code=200)
        mock_response.json.return_value = {
            "connected": True,
            "authenticated": True,
            "needs_reauth": False,
            "is_reconnecting": False,
            "reconnect_attempts": 0,
            "session_age_sec": 42,
            "last_activity_sec": 3,
        }
        mock_requests.return_value = mock_response

        health = manager.health_check(mock_instance, mock_db)

        assert health["status"] == "healthy"
        assert health["container_state"] == "running"
        assert health["api_reachable"] is True
        assert mock_instance.container_id == "resolved-container-id"
        assert mock_instance.mcp_api_url == f"http://{mock_instance.container_name}:8080/api"
        assert mock_instance.session_data_path == (
            f"/app/data/mcp/{mock_instance.tenant_id}/{mock_instance.container_name}/store"
        )
        assert mock_instance.messages_db_path.endswith("/messages.db")
        assert mock_instance.mcp_port == 8091
        assert any(call.args[0] == mock_instance.container_name for call in mock_runtime.get_container.call_args_list)
        mock_db.commit.assert_called()

    def test_health_check_returns_unavailable_when_id_and_name_both_missing(
        self,
        manager,
        mock_db,
        mock_runtime,
        mock_instance,
    ):
        mock_instance.container_id = None
        mock_runtime.get_container.side_effect = ContainerNotFoundError("missing")

        health = manager.health_check(mock_instance, mock_db)

        assert health["status"] == "unavailable"
        assert health["container_state"] == "not_found"
        assert "restart the instance" in health["error"]

    def test_reconcile_instance_repairs_container_id_before_health_check(
        self,
        manager,
        mock_db,
        mock_runtime,
        mock_instance,
    ):
        resolved_container = _container_for("container-from-name")

        def get_container(ref):
            if ref == mock_instance.container_name:
                return resolved_container
            raise ContainerNotFoundError(ref)

        mock_runtime.get_container.side_effect = get_container
        mock_runtime.get_container_attrs.return_value = {
            "NetworkSettings": {"Ports": {"8080/tcp": [{"HostPort": "8085"}]}}
        }

        changes = manager.reconcile_instance(mock_instance, mock_db)

        assert "container_ref" in changes
        assert changes["mcp_api_url"] == f"http://{mock_instance.container_name}:8080/api"
        assert changes["session_data_path"] == (
            f"/app/data/mcp/{mock_instance.tenant_id}/{mock_instance.container_name}/store"
        )
        assert changes["messages_db_path"] == (
            f"/app/data/mcp/{mock_instance.tenant_id}/{mock_instance.container_name}/store/messages.db"
        )
        assert changes["mcp_port"] == 8085
        assert mock_instance.container_id == "container-from-name"
        mock_db.commit.assert_called_once()
