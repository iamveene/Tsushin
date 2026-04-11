"""
Regression tests for Cloudflare Tunnel Remote Access preflight checks.
"""

import asyncio
import os
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

docker_stub = types.ModuleType("docker")
docker_stub.errors = SimpleNamespace(NotFound=Exception, DockerException=Exception)
docker_stub.DockerClient = object
sys.modules.setdefault("docker", docker_stub)

from models import get_remote_access_proxy_target_url
from services.cloudflare_tunnel_service import (
    CloudflareTunnelService,
    TunnelConfigurationError,
)


def _loaded_config(target_url: str):
    return SimpleNamespace(
        enabled=True,
        mode="quick",
        autostart=False,
        protocol="auto",
        tunnel_token=None,
        tunnel_hostname=None,
        tunnel_dns_target=None,
        target_url=target_url,
    )


class TestCloudflareTunnelService:
    @patch.dict(os.environ, {"TSN_STACK_NAME": "tsushin-proofb"}, clear=False)
    def test_start_fails_closed_when_proxy_layer_is_unreachable(self):
        service = CloudflareTunnelService(session_factory=lambda: MagicMock())
        service._cloudflared_path = "/usr/local/bin/cloudflared"
        service._load_config = MagicMock(return_value=_loaded_config("http://frontend:3030"))

        expected_target = get_remote_access_proxy_target_url()

        probe = AsyncMock(return_value=False)
        with patch.object(service, "_probe_proxy_target", probe), patch(
            "services.cloudflare_tunnel_service.asyncio.create_subprocess_exec"
        ) as mock_create:
            with pytest.raises(TunnelConfigurationError) as exc_info:
                asyncio.run(service.start())

        assert expected_target in str(exc_info.value)
        probe.assert_awaited_once_with(expected_target, timeout=5.0)
        mock_create.assert_not_called()
