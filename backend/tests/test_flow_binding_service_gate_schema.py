"""Auto-flow gate node uses canonical config_json keys.

The flow_engine's GateExecutor and the editor form (``StepConfigForm``
in ``frontend/app/flows/page.tsx``) both read ``gate_mode`` /
``gate_conditions`` / ``gate_logic``. Pre-fix the auto-flow generator
in ``services.flow_binding_service.create_auto_flow_for_trigger`` wrote
``mode`` / ``rules`` / ``logic`` instead — the engine silently ignored
those keys and defaulted to "programmatic" with zero conditions, so the
gate only happened to pass-all by accident. The day someone added a
real rule via the UI it was saved under ``gate_conditions`` while the
auto-gen ``rules`` lingered as dead config.

This test locks the canonical contract end-to-end at the auto-flow
generator boundary.
"""

from __future__ import annotations

import json
import os
import sys
import types

import pytest
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

from models import (  # noqa: E402
    Base,
    FlowDefinition,
    FlowNode,
    FlowTriggerBinding,
    JiraChannelInstance,
)
from models_rbac import Tenant, User  # noqa: E402
from services.flow_binding_service import (  # noqa: E402
    ensure_system_managed_flow_for_trigger,
)


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
            FlowTriggerBinding.__table__,
            JiraChannelInstance.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _seed_jira_instance(db, *, tenant_id: str, instance_id: int):
    db.add(Tenant(id=tenant_id, name=tenant_id.title(), slug=tenant_id))
    db.add(
        User(
            id=1,
            tenant_id=tenant_id,
            email=f"{tenant_id}@example.com",
            password_hash="x",
            is_active=True,
        )
    )
    db.add(
        JiraChannelInstance(
            id=instance_id,
            tenant_id=tenant_id,
            integration_name="QA Jira",
            site_url="https://example.atlassian.net",
            project_key="JSM",
            jql="project = JSM",
            created_by=1,
            is_active=True,
            status="active",
        )
    )
    db.flush()


def test_auto_flow_gate_uses_canonical_schema_keys(db_session):
    _seed_jira_instance(db_session, tenant_id="tenant-a", instance_id=14)

    flow, _binding, created = ensure_system_managed_flow_for_trigger(
        db_session,
        tenant_id="tenant-a",
        trigger_kind="jira",
        trigger_instance_id=14,
        default_agent_id=1,
    )
    db_session.commit()
    assert created is True

    gate = (
        db_session.query(FlowNode)
        .filter(FlowNode.flow_definition_id == flow.id, FlowNode.type == "gate")
        .one()
    )
    config = json.loads(gate.config_json)

    # Must match GateExecutor.execute() in flow_engine.py and the
    # gate-mode toggle in the flow editor.
    assert config.get("gate_mode") == "programmatic"
    assert config.get("gate_conditions") == []
    assert config.get("gate_logic") == "all"
    # Pre-fix orphan keys must NOT leak into the new contract — otherwise
    # they accumulate as dead config next to the canonical ones.
    assert "mode" not in config
    assert "rules" not in config
    assert "logic" not in config
