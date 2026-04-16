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
    @patch.dict(os.environ, {"TSN_STACK_NAME": "tsushin-proofb"}, clear=False)
    @patch("services.mcp_container_manager.requests.get")
    def test_get_tester_status_prefers_stack_specific_compose_tester_and_avoids_generic_cross_stack_match(
        self,
        mock_requests,
        manager,
        mock_runtime,
    ):
        def get_container(ref):
            if ref == "proofb-ui-tester":
                return _container_for(ref)
            raise ContainerNotFoundError(ref)

        mock_runtime.get_container.side_effect = get_container
        mock_runtime.get_container_attrs.return_value = {
            "status": "running",
            "id": "proofb-ui-tester-id",
            "image_tags": ["tsushin/tester-mcp:latest"],
        }
        manager._ensure_container_on_tsushin_network = MagicMock()

        def fake_get(url, headers=None, timeout=None):
            response = MagicMock()
            if url.endswith("/health"):
                response.status_code = 200
                response.json.return_value = {
                    "status": "healthy",
                    "connected": True,
                    "authenticated": True,
                    "needs_reauth": False,
                    "is_reconnecting": False,
                    "reconnect_attempts": 0,
                    "session_age_sec": 20,
                    "last_activity_sec": 1,
                }
                return response
            if url.endswith("/qr-code"):
                response.status_code = 200
                response.json.return_value = {"qr_code": "stack-scoped-qr"}
                return response
            raise AssertionError(f"Unexpected URL: {url}")

        mock_requests.side_effect = fake_get

        tester_status = manager.get_tester_status()

        assert tester_status["name"] == "proofb-ui-tester"
        assert tester_status["api_url"] == "http://proofb-ui-tester:8080/api"
        assert tester_status["source"] == "compose"
        assert tester_status["qr_available"] is True
        requested_containers = [call.args[0] for call in mock_runtime.get_container.call_args_list]
        assert "proofb-ui-tester" in requested_containers
        assert "tester-mcp" not in requested_containers

    @patch("services.mcp_container_manager.requests.post")
    @patch("services.mcp_container_manager.requests.get")
    def test_tester_actions_use_resolved_runtime_target(
        self,
        mock_get,
        mock_post,
        manager,
        mock_runtime,
    ):
        def resolve_runtime_tester():
            manager._set_tester_target(
                "mcp-tester-runtime",
                "http://mcp-tester-runtime:8080/api",
                "runtime",
            )
            return _container_for("mcp-tester-runtime")

        manager._get_tester_container = MagicMock(side_effect=resolve_runtime_tester)
        manager._get_tester_headers = MagicMock(return_value={"Authorization": "Bearer test"})

        qr_response = MagicMock(status_code=200)
        qr_response.json.return_value = {"qr_code": "runtime-qr"}
        mock_get.return_value = qr_response

        logout_response = MagicMock(status_code=200)
        logout_response.json.return_value = {"success": True, "message": "logged out"}
        mock_post.return_value = logout_response

        assert manager.get_tester_qr_code() == "runtime-qr"
        assert manager.restart_tester()["success"] is True
        assert manager.reset_tester_auth()["success"] is True

        mock_get.assert_called_once_with(
            "http://mcp-tester-runtime:8080/api/qr-code",
            headers={"Authorization": "Bearer test"},
            timeout=10,
        )
        mock_post.assert_called_once_with(
            "http://mcp-tester-runtime:8080/api/logout",
            headers={"Authorization": "Bearer test"},
            timeout=10,
        )
        mock_runtime.restart_container.assert_called_once_with("mcp-tester-runtime", timeout=15)

    @patch("services.mcp_container_manager.requests.get")
    def test_get_tester_status_falls_back_to_runtime_tester_instance_when_compose_missing(
        self,
        mock_requests,
        manager,
        mock_runtime,
    ):
        manager.tenant_id = "tenant_123"
        tester_instance = MagicMock(spec=WhatsAppMCPInstance)
        tester_instance.id = 88
        tester_instance.tenant_id = "tenant_123"
        tester_instance.container_name = "runtime-tester-88"
        tester_instance.instance_type = "tester"
        tester_instance.status = "running"

        class FakeQuery:
            def filter(self, *args, **kwargs):
                return self

            def order_by(self, *args, **kwargs):
                return self

            def first(self):
                return tester_instance

        class FakeDB:
            def query(self, _model):
                return FakeQuery()

            def close(self):
                pass

        runtime_container = _container_for(tester_instance.container_name)
        runtime_container.attrs = {
            "Config": {"Env": ["MCP_API_SECRET=runtime-secret", "PHONE_NUMBER=+5511999999999"]},
        }

        def get_container(ref):
            if ref == tester_instance.container_name:
                return runtime_container
            raise ContainerNotFoundError(ref)

        mock_runtime.get_container.side_effect = get_container
        mock_runtime.get_container_attrs.return_value = {
            "status": "running",
            "id": "runtime-tester-container-id",
            "image_tags": ["tsushin/tester-mcp:latest"],
        }
        manager._get_compose_tester_container = MagicMock(return_value=None)
        manager._get_tester_headers = MagicMock(return_value={"Authorization": "Bearer runtime-secret"})
        manager._ensure_container_on_tsushin_network = MagicMock()

        db_iter = iter([FakeDB()])

        def fake_get(url, headers=None, timeout=None):
            response = MagicMock()
            response.status_code = 200
            if url.endswith("/health"):
                response.json.return_value = {
                    "status": "healthy",
                    "connected": True,
                    "authenticated": True,
                    "needs_reauth": False,
                    "is_reconnecting": False,
                    "reconnect_attempts": 0,
                    "session_age_sec": 7,
                    "last_activity_sec": 1,
                }
            elif url.endswith("/qr-code"):
                response.json.return_value = {"qr_code": "runtime-tester-qr"}
            else:
                raise AssertionError(f"Unexpected URL: {url}")
            return response

        mock_requests.side_effect = fake_get

        fake_db_module = types.SimpleNamespace(get_db=lambda: db_iter)

        with patch.dict(sys.modules, {"db": fake_db_module}):
            tester_status = manager.get_tester_status()

        assert tester_status["source"] == "runtime"
        assert tester_status["name"] == tester_instance.container_name
        assert tester_status["api_url"] == f"http://{tester_instance.container_name}:8080/api"
        assert tester_status["qr_available"] is True

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
        expected_alias = manager._build_runtime_dns_alias(mock_instance)

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
        assert mock_instance.mcp_api_url == f"http://{expected_alias}:8080/api"
        assert mock_instance.session_data_path == (
            f"/app/data/mcp/{mock_instance.tenant_id}/{mock_instance.container_name}/store"
        )
        assert mock_instance.messages_db_path.endswith("/messages.db")
        assert mock_instance.mcp_port == 8091
        assert any(call.args[0] == mock_instance.container_name for call in mock_runtime.get_container.call_args_list)
        assert any(
            call.kwargs.get("aliases") == [expected_alias]
            for call in mock_runtime.ensure_container_on_network.call_args_list
        )
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
        expected_alias = manager._build_runtime_dns_alias(mock_instance)

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
        assert changes["mcp_api_url"] == f"http://{expected_alias}:8080/api"
        assert changes["mcp_dns_alias"] == expected_alias
        assert changes["session_data_path"] == (
            f"/app/data/mcp/{mock_instance.tenant_id}/{mock_instance.container_name}/store"
        )
        assert changes["messages_db_path"] == (
            f"/app/data/mcp/{mock_instance.tenant_id}/{mock_instance.container_name}/store/messages.db"
        )
        assert changes["mcp_port"] == 8085
        assert mock_instance.container_id == "container-from-name"
        mock_db.commit.assert_called_once()
