"""
Cluster 3 backend regressions.

Covers:
- custom script skills failing closed on empty stdout
- custom skill test endpoint rejecting empty-success script results
- Vertex AI saved-instance discovery using curated fallback models
- flow creation rejecting invalid execution method/source configurations
"""

import asyncio
import os
import sys
import types
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
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


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):
    return "JSON"


from auth_dependencies import TenantContext
import models_rbac  # noqa: F401
from models import Base, CustomSkill, CustomSkillExecution, ProviderInstance


BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure_package(package_name: str, relative_path: str):
    module = sys.modules.get(package_name)
    if module is None:
        module = types.ModuleType(package_name)
        module.__path__ = [os.path.join(BACKEND_ROOT, relative_path)]
        sys.modules[package_name] = module
    return module


def _load_module(module_name: str, relative_path: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        module_name,
        os.path.join(BACKEND_ROOT, relative_path),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_ensure_package("agent", "agent")
_ensure_package("agent.skills", os.path.join("agent", "skills"))
_ensure_package("api", "api")
_ensure_package("services", "services")

# `_ensure_package` only creates a placeholder package — `__init__.py` is
# never executed, so `get_skill_manager` / `InboundMessage` aren't on the
# placeholder. Downstream tests in the same pytest session that import
# `from app import app` need those attributes.
_skills_pkg = sys.modules.get("agent.skills")
if _skills_pkg is not None:
    if not hasattr(_skills_pkg, "get_skill_manager"):
        _skills_pkg.get_skill_manager = lambda *args, **kwargs: None
    if not hasattr(_skills_pkg, "InboundMessage"):
        _skills_pkg.InboundMessage = type("InboundMessage", (), {})

_load_module(
    "agent.skills.base",
    os.path.join("agent", "skills", "base.py"),
)
CustomSkillAdapter = _load_module(
    "agent.skills.custom_skill_adapter",
    os.path.join("agent", "skills", "custom_skill_adapter.py"),
).CustomSkillAdapter
routes_custom_skills = _load_module(
    "api.routes_custom_skills",
    os.path.join("api", "routes_custom_skills.py"),
)
routes_provider_instances = _load_module(
    "api.routes_provider_instances",
    os.path.join("api", "routes_provider_instances.py"),
)
routes_flows = _load_module(
    "api.routes_flows",
    os.path.join("api", "routes_flows.py"),
)
from schemas import FlowCreate, FlowStepConfig, FlowStepCreate  # noqa: E402
from models import FlowDefinition, FlowNode  # noqa: E402


def _make_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _make_ctx(db, tenant_id: str):
    user = SimpleNamespace(tenant_id=tenant_id, is_global_admin=False)
    return TenantContext(user=user, db=db)


def _seed_custom_skill(db, tenant_id: str) -> CustomSkill:
    skill = CustomSkill(
        tenant_id=tenant_id,
        source="tenant",
        slug="empty-script",
        name="Empty Script",
        skill_type_variant="script",
        execution_mode="tool",
        trigger_mode="llm_decided",
        timeout_seconds=30,
        is_enabled=True,
        scan_status="clean",
        version="1.0.0",
        input_schema={},
        config_schema=[],
        trigger_keywords=[],
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill


def _seed_provider_instance(db, tenant_id: str) -> ProviderInstance:
    instance = ProviderInstance(
        tenant_id=tenant_id,
        vendor="vertex_ai",
        instance_name="Vertex Production",
        base_url=None,
        extra_config={"project_id": "demo-project", "region": "us-central1"},
        available_models=[],
        is_default=False,
        is_active=True,
        health_status="healthy",
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return instance


def _flow_request():
    return SimpleNamespace(client=None, headers={})


def _flow_ctx():
    return SimpleNamespace(tenant_id="tenant-alpha", user=SimpleNamespace(id=1))


def _source_step(position: int = 1, **config_overrides) -> FlowStepCreate:
    config = {"trigger_kind": "email", "trigger_instance_id": 123}
    config.update(config_overrides)
    return FlowStepCreate(
        name="Source",
        type="source",
        position=position,
        config=FlowStepConfig(**config),
    )


def _message_step(position: int = 2) -> FlowStepCreate:
    return FlowStepCreate(
        name="Notify",
        type="message",
        position=position,
        config=FlowStepConfig(content="hello"),
    )


def _create_flow(db, payload: FlowCreate):
    return routes_flows.create_flow_v2(
        payload,
        request=_flow_request(),
        db=db,
        tenant_context=_flow_ctx(),
    )


def _assert_no_flow_persisted(db):
    assert db.query(FlowDefinition).count() == 0
    assert db.query(FlowNode).count() == 0


def test_custom_skill_adapter_fails_closed_on_empty_stdout(monkeypatch):
    record = SimpleNamespace(
        id=7,
        slug="empty-script",
        name="Empty Script",
        description="",
        execution_mode="tool",
        skill_type_variant="script",
        script_entrypoint="main.py",
        script_language="python",
        timeout_seconds=30,
        mcp_server_id=None,
        mcp_tool_name=None,
    )

    deploy_module = types.ModuleType("services.custom_skill_deploy_service")

    class _DeployService:
        @staticmethod
        async def ensure_deployed(*_args, **_kwargs):
            return True

    deploy_module.CustomSkillDeployService = _DeployService
    monkeypatch.setitem(sys.modules, "services.custom_skill_deploy_service", deploy_module)

    toolbox_module = types.ModuleType("services.toolbox_container_service")

    class _ToolboxService:
        async def execute_command(self, *_args, **_kwargs):
            return {
                "stdout": "",
                "stderr": "",
                "exit_code": 0,
                "execution_time_ms": 12,
            }

    toolbox_module.get_toolbox_service = lambda: _ToolboxService()
    monkeypatch.setitem(sys.modules, "services.toolbox_container_service", toolbox_module)

    adapter = CustomSkillAdapter(skill_record=record)
    result = asyncio.run(adapter.execute_tool({}, config={"tenant_id": "tenant-alpha", "db": object()}))

    assert result.success is False
    assert "no usable output" in result.output.lower()


def test_custom_skill_test_route_rejects_blank_success(monkeypatch):
    db = _make_session()
    try:
        skill = _seed_custom_skill(db, "tenant-alpha")

        class _FakeAdapter:
            def __init__(self, skill_record=None):
                self.skill_record = skill_record

            async def execute_tool(self, arguments, message=None, config=None):
                return SimpleNamespace(success=True, output="", metadata={"from": "fake"})

        monkeypatch.setattr(
            sys.modules["agent.skills.custom_skill_adapter"],
            "CustomSkillAdapter",
            _FakeAdapter,
        )

        ctx = _make_ctx(db, "tenant-alpha")
        current_user = SimpleNamespace(id=1)

        result = asyncio.run(
            routes_custom_skills.test_custom_skill(
                skill_id=skill.id,
                payload=routes_custom_skills.CustomSkillTestRequest(arguments={}),
                db=db,
                current_user=current_user,
                ctx=ctx,
            )
        )

        execution = db.query(CustomSkillExecution).first()

        assert result["success"] is False
        assert "no usable output" in result["output"].lower()
        assert execution.status == "failed"
        assert execution.error is not None
    finally:
        db.close()


def test_vertex_saved_instance_discovery_uses_curated_fallback():
    db = _make_session()
    try:
        instance = _seed_provider_instance(db, "tenant-alpha")
        ctx = _make_ctx(db, "tenant-alpha")
        current_user = SimpleNamespace(id=1)

        result = asyncio.run(
            routes_provider_instances.discover_models(
                instance_id=instance.id,
                db=db,
                current_user=current_user,
                ctx=ctx,
            )
        )

        db.refresh(instance)

        assert result["count"] > 0
        assert result["models"] == instance.available_models
        assert "gemini-2.5-flash" in result["models"]
    finally:
        db.close()


def test_create_triggered_flow_accepts_valid_source_step(monkeypatch):
    monkeypatch.setattr(routes_flows, "log_tenant_event", lambda *args, **kwargs: None)
    db = _make_session()
    try:
        out = _create_flow(
            db,
            FlowCreate(
                name="Email triage",
                execution_method="triggered",
                steps=[_source_step(), _message_step()],
            ),
        )

        assert out.name == "Email triage"
        assert out.execution_method == "triggered"
        assert out.node_count == 2
        stored_source = db.query(FlowNode).filter(FlowNode.position == 1).one()
        assert stored_source.type == "source"
        assert '"trigger_kind": "email"' in stored_source.config_json
        assert '"trigger_instance_id": 123' in stored_source.config_json
    finally:
        db.close()


@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        (
            FlowCreate(name="Missing source", execution_method="triggered", steps=[_message_step(position=1)]),
            "must declare exactly one Source step",
        ),
        (
            FlowCreate(
                name="Duplicate source",
                execution_method="triggered",
                steps=[_source_step(), _source_step(trigger_instance_id=124)],
            ),
            "exactly one Source step",
        ),
        (
            FlowCreate(
                name="Source moved",
                execution_method="triggered",
                steps=[_source_step(position=2)],
            ),
            "Source step must be at position 1",
        ),
        (
            FlowCreate(
                name="Bad trigger kind",
                execution_method="triggered",
                steps=[_source_step(trigger_kind="schedule"), _message_step()],
            ),
            "trigger_kind must be one of",
        ),
        (
            FlowCreate(
                name="Bad trigger id",
                execution_method="triggered",
                steps=[_source_step(trigger_instance_id=0), _message_step()],
            ),
            "trigger_instance_id must be greater than 0",
        ),
        (
            FlowCreate(name="Immediate source", execution_method="immediate", steps=[_source_step()]),
            "Source steps are only supported",
        ),
        (
            FlowCreate(name="Scheduled missing time", execution_method="scheduled"),
            "scheduled_at is required",
        ),
        (
            FlowCreate(name="Recurring missing rule", execution_method="recurring"),
            "recurrence_rule is required",
        ),
        (
            FlowCreate(name="Keyword empty", execution_method="keyword", trigger_keywords=[" ", ""]),
            "At least one non-empty trigger keyword",
        ),
    ],
)
def test_create_flow_rejects_invalid_execution_configs_before_persist(monkeypatch, payload, detail):
    monkeypatch.setattr(routes_flows, "log_tenant_event", lambda *args, **kwargs: None)
    db = _make_session()
    try:
        with pytest.raises(HTTPException) as exc:
            _create_flow(db, payload)

        assert exc.value.status_code == 422
        assert detail in exc.value.detail
        _assert_no_flow_persisted(db)
    finally:
        db.close()


def test_create_scheduled_recurring_and_keyword_valid_payloads_still_work(monkeypatch):
    monkeypatch.setattr(routes_flows, "log_tenant_event", lambda *args, **kwargs: None)
    db = _make_session()
    try:
        scheduled = _create_flow(
            db,
            FlowCreate(
                name="Scheduled",
                execution_method="scheduled",
                scheduled_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
            ),
        )
        recurring = _create_flow(
            db,
            FlowCreate(
                name="Recurring",
                execution_method="recurring",
                recurrence_rule={"frequency": "daily", "interval": 1},
            ),
        )
        keyword = _create_flow(
            db,
            FlowCreate(
                name="Keyword",
                execution_method="keyword",
                trigger_keywords=["run report"],
            ),
        )

        assert scheduled.execution_method == "scheduled"
        assert recurring.execution_method == "recurring"
        assert keyword.execution_method == "keyword"
        assert db.query(FlowDefinition).count() == 3
    finally:
        db.close()
