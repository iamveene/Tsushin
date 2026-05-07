"""Round-trip contract for FlowNode failure/success behavior fields.

The flow editor renders an "On failure" select bound to ``step.on_failure``.
The backing DB column exists, the flow_engine reads it, and the auto-flow
generator writes ``on_failure='continue'`` for the Default-agent step. But
the legacy ``/api/flows/{id}/steps`` endpoints (FlowNodeCreate /
FlowNodeUpdate / FlowNodeResponse) used to omit ``on_failure``,
``on_success`` and ``retry_delay_seconds`` from their Pydantic schemas —
so the editor loaded a saved ``continue`` value as undefined and rendered
"Stop flow", and saving the form silently rewrote the field to NULL.

These tests lock the round-trip: GET returns persisted values, POST
persists submitted values, PUT updates them.
"""

from __future__ import annotations

import os
import sys
import types
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):
    return "JSON"


from api.routes_flows import (  # noqa: E402
    router as flows_router,
    get_tenant_context,
    set_engine,
)
from models import Base, FlowDefinition, FlowNode  # noqa: E402


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine


@pytest.fixture
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


def _build_app(db_engine):
    app = FastAPI()
    app.include_router(flows_router)

    fake_ctx = SimpleNamespace(
        tenant_id="tenant-step-roundtrip",
        user=SimpleNamespace(id=1),
    )
    fake_ctx.filter_by_tenant = lambda query, tenant_column: query.filter(
        tenant_column == fake_ctx.tenant_id
    )
    app.dependency_overrides[get_tenant_context] = lambda: fake_ctx
    set_engine(db_engine)

    fake_user = SimpleNamespace(
        id=1, tenant_id="tenant-step-roundtrip", email="step@test.local"
    )
    from fastapi.routing import APIRoute

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for dependency in route.dependant.dependencies:
            if getattr(dependency.call, "__name__", "") == "check":
                app.dependency_overrides[dependency.call] = lambda fake_user=fake_user: fake_user
    return app


def _seed_flow(db_session) -> int:
    flow = FlowDefinition(
        name="On-failure round-trip",
        tenant_id="tenant-step-roundtrip",
        is_active=True,
        flow_type="workflow",
        execution_method="triggered",
        created_at=datetime.utcnow(),
    )
    db_session.add(flow)
    db_session.commit()
    return flow.id


def test_get_steps_includes_on_failure_when_persisted(db_engine, db_session):
    flow_id = _seed_flow(db_session)
    db_session.add(
        FlowNode(
            flow_definition_id=flow_id,
            type="conversation",
            position=1,
            config_json="{}",
            name="Default agent",
            on_failure="continue",
            on_success="continue",
            retry_delay_seconds=10,
        )
    )
    db_session.commit()

    client = TestClient(_build_app(db_engine))
    response = client.get(f"/api/flows/{flow_id}/steps")
    assert response.status_code == 200, response.text

    payload = response.json()
    assert len(payload) == 1
    step = payload[0]
    # Pre-fix: these keys were absent from FlowNodeResponse, so the editor
    # rendered a fresh "Stop flow" default instead of the saved value.
    assert step["on_failure"] == "continue"
    assert step["on_success"] == "continue"
    assert step["retry_delay_seconds"] == 10


def test_post_step_persists_on_failure(db_engine, db_session):
    flow_id = _seed_flow(db_session)
    client = TestClient(_build_app(db_engine))

    response = client.post(
        f"/api/flows/{flow_id}/steps",
        json={
            "type": "conversation",
            "position": 1,
            "config_json": {},
            "name": "Soft-fail step",
            "on_failure": "continue",
            "on_success": "continue",
            "retry_delay_seconds": 7,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["on_failure"] == "continue"
    assert body["on_success"] == "continue"
    assert body["retry_delay_seconds"] == 7

    # And it actually landed on the row, not just in the response.
    persisted = (
        db_session.query(FlowNode)
        .filter(FlowNode.flow_definition_id == flow_id, FlowNode.position == 1)
        .one()
    )
    assert persisted.on_failure == "continue"
    assert persisted.on_success == "continue"
    assert persisted.retry_delay_seconds == 7


def test_put_step_updates_on_failure(db_engine, db_session):
    flow_id = _seed_flow(db_session)
    step = FlowNode(
        flow_definition_id=flow_id,
        type="conversation",
        position=1,
        config_json="{}",
        name="Default agent",
        on_failure="continue",
    )
    db_session.add(step)
    db_session.commit()
    step_id = step.id

    client = TestClient(_build_app(db_engine))
    response = client.put(
        f"/api/flows/{flow_id}/steps/{step_id}",
        json={"on_failure": "skip", "on_success": "continue", "retry_delay_seconds": 3},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["on_failure"] == "skip"
    assert body["on_success"] == "continue"
    assert body["retry_delay_seconds"] == 3

    db_session.expire_all()
    refreshed = db_session.query(FlowNode).filter(FlowNode.id == step_id).one()
    assert refreshed.on_failure == "skip"
    assert refreshed.on_success == "continue"
    assert refreshed.retry_delay_seconds == 3
