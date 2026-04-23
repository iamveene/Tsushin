import sys
import asyncio
import types
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

docker_stub = types.ModuleType("docker")
docker_stub.errors = types.SimpleNamespace(NotFound=Exception, DockerException=Exception)
docker_stub.DockerClient = object
sys.modules.setdefault("docker", docker_stub)

argon2_stub = types.ModuleType("argon2")
argon2_exceptions_stub = types.ModuleType("argon2.exceptions")


class _PasswordHasher:
    def hash(self, password):
        return f"stubbed:{password}"

    def verify(self, hashed_password, plain_password):
        if hashed_password != f"stubbed:{plain_password}":
            raise VerifyMismatchError()
        return True


class VerifyMismatchError(Exception):
    pass


argon2_stub.PasswordHasher = _PasswordHasher
argon2_exceptions_stub.VerifyMismatchError = VerifyMismatchError
sys.modules.setdefault("argon2", argon2_stub)
sys.modules.setdefault("argon2.exceptions", argon2_exceptions_stub)


from api import routes_audit, routes_shell, shell_approval_routes  # noqa: E402
from services.audit_service import TenantAuditActions  # noqa: E402
from services.shell_approval_service import ShellApprovalService  # noqa: E402


def test_parse_audit_datetime_expands_date_only_bounds():
    assert routes_audit._parse_audit_datetime("2026-04-23") == datetime(2026, 4, 23, 0, 0, 0)
    assert routes_audit._parse_audit_datetime("2026-04-23", end_of_day=True) == datetime(2026, 4, 23, 23, 59, 59, 999999)


def test_parse_audit_date_range_rejects_inverted_dates():
    with pytest.raises(HTTPException) as exc:
        routes_audit._parse_audit_date_range("2026-04-24", "2026-04-23")

    assert exc.value.status_code == 400
    assert "from_date" in str(exc.value.detail)


def test_derive_beacon_rate_limit_scales_and_clamps():
    assert routes_shell._derive_beacon_rate_limit(5, minimum=30, maximum=360, multiplier=3) == 36
    assert routes_shell._derive_beacon_rate_limit(1, minimum=30, maximum=360, multiplier=3) == 180
    assert routes_shell._derive_beacon_rate_limit(120, minimum=30, maximum=360, multiplier=3) == 30


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


class _FakeDB:
    def __init__(self, integration):
        self.integration = integration
        self.added = []
        self.commits = 0

    def query(self, model):
        return _FakeQuery(self.integration)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        return None


def test_queue_command_returns_429_when_command_rate_limit_is_hit(monkeypatch):
    integration = SimpleNamespace(
        id=7,
        tenant_id="tenant-track-e",
        is_active=True,
        allowed_commands=[],
        allowed_paths=[],
        yolo_mode=False,
    )
    db = _FakeDB(integration)
    current_user = SimpleNamespace(id=101, email="owner@example.com")
    ctx = SimpleNamespace(
        tenant_id="tenant-track-e",
        can_access_resource=lambda tenant_id: tenant_id == "tenant-track-e",
    )

    import services.shell_security_service as shell_security_service

    monkeypatch.setattr(
        shell_security_service,
        "get_security_service",
        lambda: SimpleNamespace(check_rate_limit=lambda shell_id: (False, "Rate limit exceeded (60 commands/minute)")),
    )
    audit_calls = []
    monkeypatch.setattr(routes_shell, "_log_shell_command_audit_event", lambda **kwargs: audit_calls.append(kwargs))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            routes_shell.queue_command(
                shell_id=integration.id,
                request=routes_shell.CommandQueueRequest(commands=["whoami"], timeout_seconds=60),
                db=db,
                current_user=current_user,
                ctx=ctx,
                _=None,
            )
        )

    assert exc.value.status_code == 429
    assert db.commits == 1
    assert len(db.added) == 1
    blocked_command = db.added[0]
    assert blocked_command.status == "blocked"
    assert "Rate limit exceeded" in blocked_command.error_message
    assert audit_calls[0]["tenant_id"] == "tenant-track-e"
    assert audit_calls[0]["action"] == TenantAuditActions.SHELL_COMMAND_BLOCKED
    assert audit_calls[0]["severity"] == "warning"
    assert audit_calls[0]["details"]["blocked_by"] == "rate_limit"


class _DenyLimiter:
    def __init__(self):
        self.calls = []

    def allow(self, key, max_requests, window_seconds=60):
        self.calls.append((key, max_requests, window_seconds))
        return False


def test_beacon_version_and_download_rate_limits_are_enforced(monkeypatch):
    import middleware.rate_limiter as rate_limiter

    limiter = _DenyLimiter()
    monkeypatch.setattr(rate_limiter, "api_rate_limiter", limiter)
    integration = SimpleNamespace(id=55, poll_interval=15)

    with pytest.raises(HTTPException) as version_exc:
        routes_shell._enforce_beacon_rate_limit(integration, "version")

    with pytest.raises(HTTPException) as download_exc:
        routes_shell._enforce_beacon_rate_limit(integration, "download")

    assert version_exc.value.status_code == 429
    assert download_exc.value.status_code == 429
    assert limiter.calls == [
        ("shell_beacon:55:version", routes_shell.BEACON_VERSION_RATE_LIMIT_RPM, 60),
        ("shell_beacon:55:download", routes_shell.BEACON_DOWNLOAD_RATE_LIMIT_RPM, 60),
    ]


class _ApprovalExpireQuery:
    def __init__(self, commands):
        self.commands = commands
        self.filters = []

    def filter(self, *conditions):
        self.filters.extend(conditions)
        return self

    def all(self):
        filter_text = " ".join(str(condition) for condition in self.filters)
        assert "shell_command.tenant_id" in filter_text
        assert "shell_command.status" in filter_text
        assert "shell_command.queued_at" in filter_text
        tenant_values = [
            getattr(getattr(condition, "right", None), "value", None)
            for condition in self.filters
            if getattr(getattr(condition, "left", None), "key", None) == "tenant_id"
        ]
        assert tenant_values == ["tenant-a"]
        return [
            command
            for command in self.commands
            if command.tenant_id == "tenant-a" and command.status == "pending_approval"
        ]


class _ApprovalExpireDB:
    def __init__(self, commands):
        self.commands = commands
        self.commits = 0

    def query(self, model):
        return _ApprovalExpireQuery(self.commands)

    def commit(self):
        self.commits += 1


def test_shell_approval_expiry_is_scoped_to_tenant(monkeypatch):
    old = datetime.utcnow() - timedelta(minutes=ShellApprovalService.DEFAULT_EXPIRATION_MINUTES + 5)
    tenant_a_command = SimpleNamespace(
        id="cmd-a",
        tenant_id="tenant-a",
        status="pending_approval",
        queued_at=old,
        error_message=None,
        completed_at=None,
    )
    tenant_b_command = SimpleNamespace(
        id="cmd-b",
        tenant_id="tenant-b",
        status="pending_approval",
        queued_at=old,
        error_message=None,
        completed_at=None,
    )
    db = _ApprovalExpireDB([tenant_a_command, tenant_b_command])
    service = ShellApprovalService(db)
    audit_calls = []
    monkeypatch.setattr(service, "_log_audit_event", lambda **kwargs: audit_calls.append(kwargs))

    assert service.expire_old_approvals("tenant-a") == 1
    assert tenant_a_command.status == "expired"
    assert tenant_b_command.status == "pending_approval"
    assert db.commits == 1
    assert audit_calls[0]["command_id"] == "cmd-a"


def test_expire_old_approvals_route_passes_current_tenant(monkeypatch):
    class FakeApprovalService:
        tenant_id = None

        def expire_old_approvals(self, tenant_id):
            self.tenant_id = tenant_id
            return 3

    fake_service = FakeApprovalService()
    monkeypatch.setattr(shell_approval_routes, "get_approval_service", lambda db: fake_service)

    result = asyncio.run(
        shell_approval_routes.expire_old_approvals(
            db=SimpleNamespace(),
            current_user=SimpleNamespace(id=5),
            ctx=SimpleNamespace(tenant_id="tenant-route"),
        )
    )

    assert fake_service.tenant_id == "tenant-route"
    assert result["expired_count"] == 3


def test_shell_approval_service_resolves_user_prefixed_email_identifier():
    expected_user = SimpleNamespace(id=42)
    fake_db = SimpleNamespace(query=lambda model: _FakeQuery(expected_user))
    service = ShellApprovalService(fake_db)

    assert service._get_user_id("user:approver@example.com") == 42
