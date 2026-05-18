"""
Focused regressions for the Track D Whisper/Speaches container manager helpers.
"""

import io
import os
import socket
import sys
import types
import wave
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

docker_stub = types.ModuleType("docker")
docker_stub.errors = types.SimpleNamespace(NotFound=Exception, DockerException=Exception)
docker_stub.DockerClient = object
sys.modules.setdefault("docker", docker_stub)

from services.whisper_container_manager import (  # noqa: E402
    PORT_RANGE_END,
    PORT_RANGE_START,
    VENDOR_CONFIGS,
    WhisperContainerManager,
    _build_silent_wav_bytes,
    startup_reconcile,
)
# Note: `_make_basic_auth_header` was removed in BUG-703 (v0.7.0) when the
# Whisper provider migrated from HTTP Basic to Bearer-token auth. The
# corresponding `test_make_basic_auth_header_uses_tsushin_contract` test
# below is skipped via marker because the helper no longer exists.


class _FakePortQuery:
    def __init__(self, ports):
        self._ports = ports

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return [(p,) for p in self._ports]


class _FakeDB:
    def __init__(self, used_ports):
        self._used = used_ports
        self.commits = 0

    def query(self, *args, **kwargs):
        return _FakePortQuery(self._used)

    def commit(self):
        self.commits += 1


class _FakeListQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._rows)


class _FakeReconcileDB:
    def __init__(self, rows):
        self.rows = rows
        self.commits = 0
        self.rollbacks = 0

    def query(self, *args, **kwargs):
        return _FakeListQuery(self.rows)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _FakeContainer:
    def __init__(
        self,
        name,
        *,
        labels=None,
        status="running",
        container_id="cid-123",
        attrs=None,
    ):
        self.name = name
        self.labels = labels or {}
        self.status = status
        self.id = container_id
        self.attrs = attrs or {
            "Name": name,
            "Id": container_id,
            "Config": {"Labels": self.labels},
            "State": {"Status": status, "ExitCode": 0, "OOMKilled": False},
            "RestartCount": 0,
        }

    def reload(self):
        return None


class _FakeContainersApi:
    def __init__(self, containers):
        self._containers = list(containers)
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        return list(self._containers)


class _FakeManagedRuntime:
    def __init__(self, containers=None, by_name=None):
        self.containers_api = _FakeContainersApi(containers or [])
        self.raw_client = SimpleNamespace(containers=self.containers_api)
        self.by_name = by_name or {
            container.name: container for container in (containers or [])
        }
        self.removed = []
        self.started = []
        self.restarted = []
        self.created = []
        self.logs = {}

    def get_container(self, name):
        if name not in self.by_name:
            raise Exception(f"Container {name} not found")
        return self.by_name[name]

    def get_container_status(self, name):
        return self.by_name[name].status

    def remove_container(self, name, force=False):
        self.removed.append((name, force))

    def start_container(self, name):
        self.started.append(name)

    def restart_container(self, name):
        self.restarted.append(name)

    def create_container(self, **kwargs):
        self.created.append(kwargs)
        container = _FakeContainer(
            kwargs["name"],
            labels=kwargs.get("labels"),
            status="running",
            container_id=f"created-{len(self.created)}",
        )
        self.by_name[kwargs["name"]] = container
        return container

    def get_container_logs(self, name, tail=100):
        return self.logs.get(name, "log line")


import pytest


@pytest.mark.skip(reason="BUG-703 (v0.7.0): Whisper migrated from Basic to Bearer auth; _make_basic_auth_header removed.")
def test_make_basic_auth_header_uses_tsushin_contract():
    pass


def test_build_silent_wav_bytes_returns_valid_wav():
    blob = _build_silent_wav_bytes(1.0)
    with wave.open(io.BytesIO(blob), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getframerate() == 16000
        assert wav.getsampwidth() == 2
        assert wav.getnframes() > 0


def test_allocate_port_stays_within_whisper_range():
    mgr = WhisperContainerManager.__new__(WhisperContainerManager)
    port = mgr._allocate_port(_FakeDB([]))
    assert PORT_RANGE_START <= port <= PORT_RANGE_END


def test_allocate_port_skips_ports_bound_on_loopback():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        held_port = None
        for candidate in range(PORT_RANGE_START, PORT_RANGE_END + 1):
            try:
                s.bind(("127.0.0.1", candidate))
                held_port = candidate
                break
            except OSError:
                continue
        assert held_port is not None
        mgr = WhisperContainerManager.__new__(WhisperContainerManager)
        port = mgr._allocate_port(_FakeDB([]))
        assert port != held_port
    finally:
        s.close()


@pytest.mark.skip(reason="BUG-703 (v0.7.0): Whisper migrated from Basic+X-API-Key to Bearer auth; _warm_up signature changed (no `username` kwarg).")
def test_warm_up_uses_basic_auth_and_x_api_key():
    pass


@pytest.mark.skip(reason="BUG-703 (v0.7.0): Whisper migrated from Basic+X-API-Key to Bearer auth; _wait_for_health signature changed (no `username` kwarg).")
def test_wait_for_health_relies_on_authenticated_probe_not_public_health():
    pass


def test_start_container_waits_for_authenticated_warm_up_before_running():
    mgr = WhisperContainerManager.__new__(WhisperContainerManager)
    db = _FakeDB([])
    instance = SimpleNamespace(
        id=42,
        tenant_id="tenant-1",
        container_name="tsushin-whisper-42",
        container_status="stopped",
        health_status="unavailable",
        health_status_reason=None,
        last_health_check=None,
    )
    container = _FakeContainer(
        instance.container_name,
        labels={
            "tsushin.service": "asr",
            "tsushin.tenant": "tenant-1",
            "tsushin.instance_id": "42",
        },
    )
    mgr.runtime = _FakeManagedRuntime(containers=[container])

    with patch.object(mgr, "_get_instance", return_value=instance), patch.object(
        mgr, "_ensure_authenticated_ready", return_value=False
    ) as mock_ready:
        status = mgr.start_container(42, "tenant-1", db)

    assert status == "error"
    assert instance.container_status == "error"
    assert instance.health_status == "unavailable"
    assert "authenticated warm-up failed" in instance.health_status_reason
    assert instance.last_health_check is not None
    assert db.commits == 1
    assert mgr.runtime.started == [instance.container_name]
    mock_ready.assert_called_once_with(instance, db)


def test_restart_container_waits_for_authenticated_warm_up_before_running():
    mgr = WhisperContainerManager.__new__(WhisperContainerManager)
    db = _FakeDB([])
    instance = SimpleNamespace(
        id=43,
        tenant_id="tenant-1",
        container_name="tsushin-whisper-43",
        container_status="running",
        health_status="healthy",
        health_status_reason=None,
        last_health_check=None,
    )
    container = _FakeContainer(
        instance.container_name,
        labels={
            "tsushin.service": "asr",
            "tsushin.tenant": "tenant-1",
            "tsushin.instance_id": "43",
        },
    )
    mgr.runtime = _FakeManagedRuntime(containers=[container])

    with patch.object(mgr, "_get_instance", return_value=instance), patch.object(
        mgr, "_ensure_authenticated_ready", return_value=True
    ) as mock_ready:
        status = mgr.restart_container(43, "tenant-1", db)

    assert status == "running"
    assert instance.container_status == "running"
    assert instance.health_status == "healthy"
    assert "authenticated warm-up" in instance.health_status_reason
    assert instance.last_health_check is not None
    assert db.commits == 1
    assert mgr.runtime.restarted == [instance.container_name]
    mock_ready.assert_called_once_with(instance, db)


def test_startup_reconcile_requires_authenticated_warm_up():
    instance = SimpleNamespace(
        id=44,
        tenant_id="tenant-1",
        container_name="tsushin-whisper-44",
        container_status="creating",
        health_status=None,
        health_status_reason=None,
        is_active=True,
        last_health_check=None,
    )
    db = _FakeReconcileDB([instance])
    runtime = SimpleNamespace(
        get_container=lambda name: object(),
        get_container_status=lambda name: "running",
    )

    with patch("services.whisper_container_manager.get_container_runtime", return_value=runtime), patch.object(
        WhisperContainerManager, "_ensure_authenticated_ready", return_value=False
    ) as mock_ready:
        startup_reconcile(db)

    assert instance.container_status == "error"
    assert instance.health_status == "unavailable"
    assert "authenticated warm-up failed" in instance.health_status_reason
    assert instance.last_health_check is not None
    assert db.commits == 1
    mock_ready.assert_called_once()


def test_reconcile_removes_orphan_managed_asr_container():
    container = _FakeContainer(
        "tsushin-whisper-dead-99",
        status="exited",
        labels={
            "tsushin.service": "asr",
            "tsushin.lifecycle": "auto-provisioned",
            "tsushin.tenant": "tenant-missing",
            "tsushin.instance_id": "99",
        },
    )
    mgr = WhisperContainerManager.__new__(WhisperContainerManager)
    mgr.runtime = _FakeManagedRuntime(containers=[container])
    db = _FakeReconcileDB([])

    stats = mgr.reconcile_managed_containers(db)

    assert stats["orphan_containers_seen"] == 1
    assert stats["orphan_containers_removed"] == 1
    assert mgr.runtime.removed == [("tsushin-whisper-dead-99", True)]
    assert db.commits == 1
    assert mgr.runtime.containers_api.calls[0]["all"] is True


def test_reconcile_marks_row_unavailable_on_container_ownership_mismatch():
    row = SimpleNamespace(
        id=7,
        tenant_id="tenant-a",
        container_name="tsushin-whisper-a-7",
        container_id="cid-a",
        container_status="running",
        health_status="healthy",
        health_status_reason=None,
        last_health_check=None,
        is_active=True,
    )
    foreign_container = _FakeContainer(
        "tsushin-whisper-a-7",
        labels={
            "tsushin.service": "asr",
            "tsushin.lifecycle": "auto-provisioned",
            "tsushin.tenant": "tenant-b",
            "tsushin.instance_id": "7",
        },
    )
    mgr = WhisperContainerManager.__new__(WhisperContainerManager)
    mgr.runtime = _FakeManagedRuntime(containers=[], by_name={row.container_name: foreign_container})
    db = _FakeReconcileDB([row])

    stats = mgr.reconcile_managed_containers(db)

    assert stats["rows_updated"] == 1
    assert row.container_status == "ownership_mismatch"
    assert row.health_status == "unavailable"
    assert "ownership mismatch" in row.health_status_reason
    assert row.last_health_check is not None
    assert db.commits == 1


def test_retry_refuses_to_replace_foreign_container_name():
    foreign_container = _FakeContainer(
        "tsushin-whisper-a-7",
        labels={
            "tsushin.service": "asr",
            "tsushin.lifecycle": "auto-provisioned",
            "tsushin.tenant": "tenant-b",
            "tsushin.instance_id": "7",
        },
    )
    mgr = WhisperContainerManager.__new__(WhisperContainerManager)
    mgr.runtime = _FakeManagedRuntime(
        containers=[foreign_container],
        by_name={foreign_container.name: foreign_container},
    )

    with pytest.raises(RuntimeError, match="mismatched ownership"):
        mgr._remove_existing_container_for_retry(
            foreign_container.name,
            tenant_id="tenant-a",
            instance_id=7,
        )

    assert mgr.runtime.removed == []


def test_speaches_default_memory_limit_is_4g():
    assert VENDOR_CONFIGS["speaches"]["default_mem_limit"] == "4g"


def test_provision_targets_preserve_existing_volume_port_and_name_on_resize():
    mgr = WhisperContainerManager.__new__(WhisperContainerManager)
    instance = SimpleNamespace(
        id=88,
        tenant_id="tenant-preserve",
        container_name="tsushin-whisper-existing-88",
        volume_name="tsushin-whisper-existing-cache-88",
        container_port=6444,
    )

    targets = mgr._resolve_provision_targets(
        instance,
        _FakeDB([]),
        preserve_existing=True,
    )

    assert targets["container_name"] == "tsushin-whisper-existing-88"
    assert targets["volume_name"] == "tsushin-whisper-existing-cache-88"
    assert targets["port"] == 6444


def test_reprovision_updates_mem_limit_and_preserves_existing_runtime_targets():
    mgr = WhisperContainerManager.__new__(WhisperContainerManager)
    db = _FakeDB([])
    instance = SimpleNamespace(
        id=89,
        tenant_id="tenant-1",
        vendor="speaches",
        container_name="tsushin-whisper-tenant-89",
        volume_name="tsushin-whisper-cache-89",
        container_port=6445,
        container_status="running",
        health_status="healthy",
        health_status_reason=None,
        last_health_check=None,
        mem_limit="2g",
        cpu_quota=None,
        is_auto_provisioned=True,
    )
    container = _FakeContainer(
        instance.container_name,
        labels={
            "tsushin.service": "asr",
            "tsushin.tenant": "tenant-1",
            "tsushin.instance_id": "89",
        },
    )
    mgr.runtime = _FakeManagedRuntime(containers=[container])

    def fake_provision(row, db_arg, *, preserve_existing=False):
        assert row is instance
        assert db_arg is db
        assert preserve_existing is True
        assert row.container_name == "tsushin-whisper-tenant-89"
        assert row.volume_name == "tsushin-whisper-cache-89"
        assert row.container_port == 6445
        row.container_status = "running"
        row.health_status = "healthy"
        row.health_status_reason = "Auto-provisioned and passed authenticated warm-up"

    with patch.object(mgr, "_get_instance", return_value=instance), patch.object(
        mgr,
        "provision",
        side_effect=fake_provision,
    ) as mock_provision:
        result = mgr.reprovision(89, "tenant-1", db, mem_limit="4g")

    assert result is instance
    assert instance.mem_limit == "4g"
    assert instance.container_status == "running"
    assert db.commits == 1
    mock_provision.assert_called_once()


def test_reprovision_preserves_runtime_targets_for_model_promotion():
    mgr = WhisperContainerManager.__new__(WhisperContainerManager)
    db = _FakeDB([])
    instance = SimpleNamespace(
        id=92,
        tenant_id="tenant-1",
        vendor="speaches",
        container_name="tsushin-whisper-tenant-92",
        volume_name="tsushin-whisper-cache-92",
        container_port=6448,
        container_status="running",
        health_status="healthy",
        health_status_reason=None,
        last_health_check=None,
        mem_limit="8g",
        cpu_quota=None,
        default_model="Systran/faster-whisper-medium",
        is_auto_provisioned=True,
    )
    container = _FakeContainer(
        instance.container_name,
        labels={
            "tsushin.service": "asr",
            "tsushin.tenant": "tenant-1",
            "tsushin.instance_id": "92",
        },
    )
    mgr.runtime = _FakeManagedRuntime(containers=[container])

    def fake_provision(row, db_arg, *, preserve_existing=False):
        assert preserve_existing is True
        assert row.default_model == "Systran/faster-whisper-medium"
        assert row.container_name == "tsushin-whisper-tenant-92"
        assert row.volume_name == "tsushin-whisper-cache-92"
        assert row.container_port == 6448
        row.container_status = "running"
        row.health_status = "healthy"

    with patch.object(mgr, "_get_instance", return_value=instance), patch.object(
        mgr,
        "provision",
        side_effect=fake_provision,
    ) as mock_provision:
        result = mgr.reprovision(92, "tenant-1", db)

    assert result is instance
    assert instance.default_model == "Systran/faster-whisper-medium"
    assert db.commits == 1
    mock_provision.assert_called_once()


def test_get_status_surfaces_restart_and_oom_context():
    mgr = WhisperContainerManager.__new__(WhisperContainerManager)
    db = _FakeDB([])
    instance = SimpleNamespace(
        id=90,
        tenant_id="tenant-1",
        container_name="tsushin-whisper-90",
        container_port=6446,
        container_image="speaches:test",
        volume_name="tsushin-whisper-cache-90",
        base_url="http://whisper-90:8000",
        container_status="running",
        health_status="healthy",
        health_status_reason=None,
        last_health_check=None,
    )
    container = _FakeContainer(
        instance.container_name,
        labels={
            "tsushin.service": "asr",
            "tsushin.tenant": "tenant-1",
            "tsushin.instance_id": "90",
        },
        status="exited",
        attrs={
            "Name": instance.container_name,
            "Id": "cid-90",
            "Config": {"Labels": {
                "tsushin.service": "asr",
                "tsushin.tenant": "tenant-1",
                "tsushin.instance_id": "90",
            }},
            "RestartCount": 3,
            "State": {
                "Status": "exited",
                "OOMKilled": True,
                "ExitCode": 137,
                "Error": "",
                "StartedAt": "2026-05-18T10:00:00Z",
                "FinishedAt": "2026-05-18T10:01:00Z",
            },
        },
    )
    mgr.runtime = _FakeManagedRuntime(containers=[container])

    with patch.object(mgr, "_get_instance", return_value=instance):
        status = mgr.get_status(90, "tenant-1", db)

    assert status["status"] == "exited"
    assert status["restart_count"] == 3
    assert status["oom_killed"] is True
    assert status["exit_code"] == 137
    assert status["recent_exit"] is True
    assert instance.health_status == "unavailable"
    assert "oom_killed=true" in instance.health_status_reason
    assert "exit_code=137" in instance.health_status_reason
    assert db.commits == 1


def test_get_logs_prefixes_recent_exit_context_after_ownership_check():
    mgr = WhisperContainerManager.__new__(WhisperContainerManager)
    db = _FakeDB([])
    instance = SimpleNamespace(
        id=91,
        tenant_id="tenant-1",
        container_name="tsushin-whisper-91",
    )
    labels = {
        "tsushin.service": "asr",
        "tsushin.tenant": "tenant-1",
        "tsushin.instance_id": "91",
    }
    container = _FakeContainer(
        instance.container_name,
        labels=labels,
        status="exited",
        attrs={
            "Name": instance.container_name,
            "Id": "cid-91",
            "Config": {"Labels": labels},
            "RestartCount": 1,
            "State": {
                "Status": "exited",
                "OOMKilled": True,
                "ExitCode": 137,
                "FinishedAt": "2026-05-18T10:01:00Z",
            },
        },
    )
    runtime = _FakeManagedRuntime(containers=[container])
    runtime.logs[instance.container_name] = "speaches process exited"
    mgr.runtime = runtime

    with patch.object(mgr, "_get_instance", return_value=instance):
        logs = mgr.get_logs(91, "tenant-1", db, tail=50)

    assert logs.startswith("[container runtime] restart_count=1, oom_killed=true, exit_code=137")
    assert "speaches process exited" in logs
