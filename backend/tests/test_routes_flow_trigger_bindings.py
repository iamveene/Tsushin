"""Flow trigger binding route contract tests."""

from __future__ import annotations

import os
import sys
import types
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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

from api.routes_flow_trigger_bindings import (  # noqa: E402
    FlowTriggerBindingCreate,
    create_binding,
)
from models import (  # noqa: E402
    Base,
    EmailChannelInstance,
    FlowDefinition,
    FlowNode,
    FlowRun,
    FlowTriggerBinding,
)
from models_rbac import Tenant, User  # noqa: E402


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Tenant.__table__,
            User.__table__,
            FlowDefinition.__table__,
            FlowNode.__table__,
            FlowRun.__table__,
            FlowTriggerBinding.__table__,
            EmailChannelInstance.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ctx(tenant_id: str):
    return SimpleNamespace(tenant_id=tenant_id)


def _seed_tenant(db, tenant_id: str, user_id: int):
    db.add(Tenant(id=tenant_id, name=tenant_id.title(), slug=tenant_id))
    db.add(
        User(
            id=user_id,
            tenant_id=tenant_id,
            email=f"{tenant_id}@example.com",
            password_hash="x",
            is_active=True,
        )
    )


def _seed_flow_and_email(db, *, tenant_id: str, user_id: int, flow_id: int, trigger_id: int):
    db.add(
        FlowDefinition(
            id=flow_id,
            tenant_id=tenant_id,
            name=f"{tenant_id} flow",
            execution_method="triggered",
        )
    )
    db.add(
        EmailChannelInstance(
            id=trigger_id,
            tenant_id=tenant_id,
            integration_name=f"{tenant_id} email",
            provider="gmail",
            created_by=user_id,
        )
    )
    db.commit()


def test_create_binding_validates_tenant_owned_trigger(db_session):
    _seed_tenant(db_session, "acme", 1)
    _seed_tenant(db_session, "other", 2)
    _seed_flow_and_email(db_session, tenant_id="acme", user_id=1, flow_id=10, trigger_id=20)
    _seed_flow_and_email(db_session, tenant_id="other", user_id=2, flow_id=11, trigger_id=21)

    created = create_binding(
        FlowTriggerBindingCreate(
            flow_definition_id=10,
            trigger_kind="email",
            trigger_instance_id=20,
        ),
        db=db_session,
        ctx=_ctx("acme"),
    )
    assert created.trigger_kind == "email"
    assert created.trigger_instance_id == 20

    with pytest.raises(HTTPException) as exc:
        create_binding(
            FlowTriggerBindingCreate(
                flow_definition_id=10,
                trigger_kind="email",
                trigger_instance_id=21,
            ),
            db=db_session,
            ctx=_ctx("acme"),
        )
    assert exc.value.status_code == 403
    assert exc.value.detail == "email trigger not owned by tenant"


def test_schedule_binding_kind_is_not_accepted():
    with pytest.raises(ValidationError):
        FlowTriggerBindingCreate(
            flow_definition_id=10,
            trigger_kind="schedule",
            trigger_instance_id=20,
        )
