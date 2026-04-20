"""
Unit tests for SearxngContainerManager and the SearXNG search-provider
registration.

Covers the pieces most likely to regress:

- Settings rendering: generated `settings.yml` must embed the caller-provided
  `secret_key` and enable `json` format + `limiter: false` (otherwise the
  JSON-search health check inside `SearxngContainerManager._check_health`
  would never return 200).
- Tar assembly: `_tar_bytes_for_settings` must produce a valid tarball whose
  only entry is `settings.yml` with the exact bytes we passed in — the
  Docker `put_archive` API expects that shape.
- Port allocation: `SearxngContainerManager._allocate_port` must stay within
  the 6500–6599 range and skip ports already claimed by another
  `SearxngInstance` row or already bound on 127.0.0.1.
- Registry shape: `SearXNGSearchProvider` is registered with the agreed
  `requires_api_key=False` so the wizard knows to skip the API-key step.
"""

import io
import os
import socket
import sys
import tarfile
import types
from typing import List
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Stub docker SDK in case the test runner doesn't have it — the module under
# test imports docker lazily and the pieces we exercise don't need it.
docker_stub = types.ModuleType("docker")
docker_stub.errors = types.SimpleNamespace(NotFound=Exception, DockerException=Exception)
docker_stub.DockerClient = object
sys.modules.setdefault("docker", docker_stub)

from services.searxng_container_manager import (  # noqa: E402
    PORT_RANGE_START,
    PORT_RANGE_END,
    SearxngContainerManager,
    _build_settings_yml,
    _tar_bytes_for_settings,
)


# ---------------------------------------------------------------------------
# settings.yml rendering
# ---------------------------------------------------------------------------

def test_build_settings_yml_contains_generated_secret():
    yml = _build_settings_yml(secret_key="abc123-generated", instance_label="Tsushin Search")
    decoded = yml.decode("utf-8")
    # The generated secret must appear verbatim — a hardcoded placeholder in
    # the repo would be a regression.
    assert "'abc123-generated'" in decoded
    # Must not ship the old PR-#24 hardcoded placeholder.
    assert "tsushin-searxng-local-secret-change-me" not in decoded


def test_build_settings_yml_enables_json_and_disables_limiter():
    """Without these, SearXNG rejects the agent's JSON search with 403 and our
    health check never goes green — which in turn would leave every auto-
    provisioned container stuck in container_status='error'."""
    yml = _build_settings_yml(secret_key="x", instance_label="x").decode("utf-8")
    assert "limiter: false" in yml
    assert "- json" in yml
    assert "- html" in yml


# ---------------------------------------------------------------------------
# tar assembly (put_archive payload)
# ---------------------------------------------------------------------------

def test_tar_bytes_for_settings_is_valid_tar_with_one_entry():
    yml_bytes = b"dummy settings"
    blob = _tar_bytes_for_settings(yml_bytes)

    buf = io.BytesIO(blob)
    with tarfile.open(fileobj=buf, mode="r") as tar:
        members = tar.getmembers()
        assert [m.name for m in members] == ["settings.yml"]
        extracted = tar.extractfile(members[0]).read()
        assert extracted == yml_bytes


# ---------------------------------------------------------------------------
# port allocation
# ---------------------------------------------------------------------------

class _FakePortQuery:
    """Minimal substitute for the SQLAlchemy query chain used inside
    SearxngContainerManager._get_used_ports."""
    def __init__(self, ports: List[int]):
        self._ports = ports

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return [(p,) for p in self._ports]


class _FakeDB:
    def __init__(self, used_ports: List[int]):
        self._used = used_ports

    def query(self, *args, **kwargs):
        return _FakePortQuery(self._used)


def test_allocate_port_stays_within_configured_range():
    mgr = SearxngContainerManager.__new__(SearxngContainerManager)  # bypass __init__
    db = _FakeDB(used_ports=[])
    port = mgr._allocate_port(db)
    assert PORT_RANGE_START <= port < PORT_RANGE_END


def test_allocate_port_skips_ports_already_used_in_db():
    mgr = SearxngContainerManager.__new__(SearxngContainerManager)
    reserved = list(range(PORT_RANGE_START, PORT_RANGE_START + 3))
    db = _FakeDB(used_ports=reserved)
    port = mgr._allocate_port(db)
    assert port not in reserved
    assert PORT_RANGE_START <= port < PORT_RANGE_END


def test_allocate_port_skips_ports_already_bound_on_loopback():
    """If a non-tsushin process holds a port in our range, we must NOT hand it
    out — otherwise container creation would fail with "address already in
    use" at Docker's bind step."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        # Find an actually-free port inside the range to reserve
        held_port = None
        for candidate in range(PORT_RANGE_START, PORT_RANGE_END):
            try:
                s.bind(("127.0.0.1", candidate))
                held_port = candidate
                break
            except OSError:
                continue
        if held_port is None:
            pytest.skip("No free port in range; host is saturated")

        mgr = SearxngContainerManager.__new__(SearxngContainerManager)
        db = _FakeDB(used_ports=[])
        port = mgr._allocate_port(db)
        assert port != held_port
        assert PORT_RANGE_START <= port < PORT_RANGE_END
    finally:
        s.close()


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

def test_searxng_registered_without_api_key_requirement():
    """Regression guard for the wizard: if `requires_api_key` ever flips to
    True here, the SearXNG step in AddIntegrationWizard would stop offering
    the auto-provision toggle and prompt the user for a key that doesn't
    exist."""
    # Reset-and-initialize to make the test hermetic.
    from hub.providers.search_registry import SearchProviderRegistry
    SearchProviderRegistry.reset()
    SearchProviderRegistry.initialize_providers()
    try:
        assert SearchProviderRegistry.is_provider_registered("searxng")
        cfg = SearchProviderRegistry.get_provider_config("searxng")
        assert cfg.get("requires_api_key") is False
        assert cfg.get("status", "available") == "available"
    finally:
        SearchProviderRegistry.reset()
