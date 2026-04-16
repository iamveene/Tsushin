"""
Cluster 3 backend regressions.

Covers:
- custom script skills failing closed on empty stdout
- custom skill test endpoint rejecting empty-success script results
- Vertex AI saved-instance discovery using curated fallback models
"""

import asyncio
import os
import sys
import types
from types import SimpleNamespace

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
