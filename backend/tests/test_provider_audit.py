"""
BUG-709 regression: provider-instance CRUD must emit audit_event rows
with no api_key in the payload.

The handler chain is exercised by calling the route function directly with
mocked DB / context dependencies. We verify:
  1. After a successful create, an audit_event row exists with
     action='provider.created' and resource_id == instance.id.
  2. The payload does NOT contain `api_key` or any encrypted value.
  3. Update and Delete paths emit equivalent audit events.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# AuditEvent.details uses Postgres JSONB which SQLite can't compile. Register
# a dialect-level fallback so Base.metadata.create_all on a sqlite engine
# renders JSONB as JSON. Test-only — production keeps real JSONB.
try:
    @compiles(JSONB, "sqlite")
    def _compile_jsonb_for_sqlite(type_, compiler, **kw):  # noqa: ARG001
        return "JSON"
except Exception:  # pragma: no cover — defensive
    pass

from api import routes_provider_instances as routes  # noqa: E402
from models import Base, ProviderInstance  # noqa: E402
from models_rbac import AuditEvent, Tenant, User  # noqa: E402


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Tenant.__table__,
            User.__table__,
            ProviderInstance.__table__,
            AuditEvent.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        # Seed minimum tenant + user for FK satisfaction in audit_event.
        session.add(Tenant(id="tenant-x", name="Tenant X", slug="tenant-x"))
        session.add(
            User(
                id=42,
                tenant_id="tenant-x",
                email="ops@example.com",
                password_hash="hashed",
                is_active=True,
            )
        )
        session.commit()
        yield session
    finally:
        session.close()


def _ctx(tenant_id: str = "tenant-x"):
    """Tenant context stub matching the auth_dependencies.TenantContext shape."""
    ctx = MagicMock()
    ctx.tenant_id = tenant_id
    ctx.can_access_resource = lambda tid: tid == tenant_id
    return ctx


def _user(db_session) -> User:
    return db_session.query(User).filter(User.id == 42).one()


def _request_stub() -> SimpleNamespace:
    return SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"user-agent": "pytest-regression/1.0"},
    )


def _bg_stub():
    bg = MagicMock()
    bg.add_task = MagicMock()
    return bg


def test_create_provider_instance_emits_audit_event_without_api_key(db_session, monkeypatch):
    """BUG-709: create handler must emit `provider.created` audit row."""
    # Stub the encryption helper so we don't need a real master key.
    monkeypatch.setattr(routes, "_encrypt_provider_key", lambda *a, **kw: "encrypted-blob-redacted")

    payload = routes.ProviderInstanceCreate(
        vendor="openai",
        instance_name="primary-openai",
        base_url="https://api.openai.com/v1",
        api_key="sk-supersecret-DO-NOT-LEAK",
        available_models=["gpt-4o-mini"],
        is_default=False,
    )

    # Patch SSRF to a no-op so the test does not depend on DNS/network.
    import utils.ssrf_validator as ssrf
    monkeypatch.setattr(ssrf, "validate_url", lambda *a, **kw: True)

    response = routes.create_provider_instance(
        data=payload,
        background_tasks=_bg_stub(),
        request=_request_stub(),
        db=db_session,
        current_user=_user(db_session),
        ctx=_ctx(),
    )

    # Audit row must exist.
    rows = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "provider.created")
        .all()
    )
    assert len(rows) == 1, f"Expected one provider.created audit row, got {len(rows)}"
    row = rows[0]
    assert row.tenant_id == "tenant-x"
    assert row.user_id == 42
    assert row.resource_type == "provider_instance"
    assert row.resource_id == str(response.id)

    # Payload sanity: api_key MUST NOT appear, and the encrypted blob MUST NOT
    # appear either.
    payload_blob = (row.details or {})
    assert "api_key" not in payload_blob, f"api_key leaked into audit payload: {payload_blob}"
    assert "api_key_encrypted" not in payload_blob, "encrypted blob leaked"
    serialized = str(payload_blob).lower()
    assert "supersecret" not in serialized, "secret leaked into audit payload"
    assert "encrypted-blob-redacted" not in serialized

    # Useful identity fields should be there.
    assert payload_blob.get("vendor") == "openai"
    assert payload_blob.get("instance_name") == "primary-openai"


def test_update_and_delete_emit_provider_audit_events(db_session, monkeypatch):
    """BUG-709: update and delete must each emit their own audit row."""
    monkeypatch.setattr(routes, "_encrypt_provider_key", lambda *a, **kw: "encrypted-blob-redacted")

    import utils.ssrf_validator as ssrf
    monkeypatch.setattr(ssrf, "validate_url", lambda *a, **kw: True)

    create = routes.create_provider_instance(
        data=routes.ProviderInstanceCreate(
            vendor="openai",
            instance_name="test-openai",
            base_url="https://api.openai.com/v1",
            api_key="sk-original-secret",
            available_models=["gpt-4o-mini"],
        ),
        background_tasks=_bg_stub(),
        request=_request_stub(),
        db=db_session,
        current_user=_user(db_session),
        ctx=_ctx(),
    )

    # Update — change the name and set a new key.
    routes.update_provider_instance(
        instance_id=create.id,
        data=routes.ProviderInstanceUpdate(
            instance_name="renamed-openai",
            api_key="sk-rotated-secret",
        ),
        background_tasks=_bg_stub(),
        request=_request_stub(),
        db=db_session,
        current_user=_user(db_session),
        ctx=_ctx(),
    )

    update_rows = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "provider.updated")
        .all()
    )
    assert len(update_rows) == 1
    upd = update_rows[0]
    assert upd.resource_id == str(create.id)
    upd_payload = upd.details or {}
    assert "api_key" not in upd_payload
    serialized = str(upd_payload).lower()
    assert "rotated" not in serialized, "rotated secret leaked into audit payload"
    assert upd_payload.get("instance_name") == "renamed-openai"

    # Delete (soft-delete).
    routes.delete_provider_instance(
        instance_id=create.id,
        request=_request_stub(),
        db=db_session,
        current_user=_user(db_session),
        ctx=_ctx(),
    )

    delete_rows = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "provider.deleted")
        .all()
    )
    assert len(delete_rows) == 1
    delr = delete_rows[0]
    assert delr.resource_id == str(create.id)
    del_payload = delr.details or {}
    assert "api_key" not in del_payload
    # Soft-deleted instance must have is_active=False reflected.
    assert del_payload.get("is_active") is False
