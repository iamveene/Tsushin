"""
Focused regressions for provider-instance and SearXNG hub cleanup behavior.
"""

import asyncio
import os
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
from models import Base, Agent, AgentSkill, ProviderInstance, SearxngInstance


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


_ensure_package("api", "api")
_ensure_package("services", "services")

routes_provider_instances = _load_module(
    "api.routes_provider_instances",
    os.path.join("api", "routes_provider_instances.py"),
)
routes_searxng_instances = _load_module(
    "api.routes_searxng_instances",
    os.path.join("api", "routes_searxng_instances.py"),
)


def _make_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _make_ctx(db, tenant_id: str):
    user = SimpleNamespace(tenant_id=tenant_id, is_global_admin=False)
    return TenantContext(user=user, db=db)


def _dump_model(model):
    return model.model_dump() if hasattr(model, "model_dump") else model.dict()


def _seed_provider_instance(db, tenant_id: str) -> ProviderInstance:
    instance = ProviderInstance(
        tenant_id=tenant_id,
        vendor="ollama",
        instance_name="Managed Ollama",
        base_url="http://tsushin-ollama-abcd1234-1:11434",
        available_models=["llama3.2"],
        is_default=True,
        is_active=True,
        is_auto_provisioned=True,
        container_status="running",
        container_name="tsushin-ollama-abcd1234-1",
        container_port=6789,
        container_image="ollama/ollama:latest",
        volume_name="tsushin-ollama-abcd1234-1",
        mem_limit="6g",
        gpu_enabled=True,
        pulled_models=["llama3.2", "nomic-embed-text"],
        health_status="healthy",
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return instance


def _seed_searxng_instance(db, tenant_id: str) -> SearxngInstance:
    instance = SearxngInstance(
        tenant_id=tenant_id,
        vendor="searxng",
        instance_name="Web Search",
        description="Tenant search",
        base_url="http://searxng.internal",
        is_active=True,
        is_auto_provisioned=False,
        container_status="none",
        health_status="healthy",
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return instance


def _seed_agent_with_web_search(db, tenant_id: str, provider: str, instance_id: int):
    agent = Agent(
        contact_id=10_000 + instance_id,
        system_prompt="Test agent prompt",
        tenant_id=tenant_id,
        persona_id=None,
        model_provider="openai",
        model_name="gpt-4o-mini",
        is_active=True,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)

    skill = AgentSkill(
        agent_id=agent.id,
        skill_type="web_search",
        is_enabled=True,
        config={"provider": provider, "searxng_instance_id": instance_id},
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return agent, skill


def test_provider_instance_response_includes_ollama_container_metadata():
    db = _make_session()
    try:
        instance = _seed_provider_instance(db, "tenant-alpha")
        ctx = _make_ctx(db, "tenant-alpha")
        current_user = SimpleNamespace(id=1)

        response = routes_provider_instances.get_provider_instance(
            instance_id=instance.id,
            db=db,
            current_user=current_user,
            ctx=ctx,
        )
        payload = _dump_model(response)

        assert payload["is_auto_provisioned"] is True
        assert payload["container_status"] == "running"
        assert payload["container_name"] == "tsushin-ollama-abcd1234-1"
        assert payload["container_port"] == 6789
        assert payload["container_image"] == "ollama/ollama:latest"
        assert payload["volume_name"] == "tsushin-ollama-abcd1234-1"
        assert payload["mem_limit"] == "6g"
        assert payload["gpu_enabled"] is True
        assert payload["pulled_models"] == ["llama3.2", "nomic-embed-text"]
    finally:
        db.close()


def test_delete_provider_instance_deprovisions_auto_provisioned_ollama_before_soft_delete():
    db = _make_session()
    try:
        instance = _seed_provider_instance(db, "tenant-alpha")
        ctx = _make_ctx(db, "tenant-alpha")
        current_user = SimpleNamespace(id=1)

        deprovision_seen_active = {"value": None}

        def _deprovision(instance_id, tenant_id, db_session, remove_volume=False):
            row = db_session.query(ProviderInstance).filter(
                ProviderInstance.id == instance_id,
                ProviderInstance.tenant_id == tenant_id,
            ).first()
            deprovision_seen_active["value"] = row.is_active if row else None
            row.container_status = "none"
            row.container_name = None
            row.container_port = None
            row.container_id = None
            row.base_url = None
            db_session.commit()

        mock_manager = MagicMock()
        mock_manager.deprovision.side_effect = _deprovision

        with patch("services.ollama_container_manager.OllamaContainerManager", return_value=mock_manager):
            result = routes_provider_instances.delete_provider_instance(
                instance_id=instance.id,
                db=db,
                current_user=current_user,
                ctx=ctx,
            )

        db.refresh(instance)
        assert deprovision_seen_active["value"] is True
        mock_manager.deprovision.assert_called_once_with(
            instance.id, "tenant-alpha", db, remove_volume=False
        )
        assert instance.is_active is False
        assert instance.container_status == "none"
        assert instance.container_name is None
        assert result["message"] == "Provider instance 'Managed Ollama' deleted successfully"
    finally:
        db.close()


def test_delete_searxng_instance_scopes_agent_skill_cleanup_to_tenant_agents():
    db = _make_session()
    try:
        tenant_a_instance = _seed_searxng_instance(db, "tenant-alpha")
        _seed_agent_with_web_search(db, "tenant-alpha", "searxng", tenant_a_instance.id)
        _, tenant_b_skill = _seed_agent_with_web_search(
            db,
            "tenant-bravo",
            "searxng",
            tenant_a_instance.id + 999,
        )

        ctx = _make_ctx(db, "tenant-alpha")

        result = asyncio.run(
            routes_searxng_instances.delete_searxng_instance(
                instance_id=tenant_a_instance.id,
                remove_volume=False,
                ctx=ctx,
                db=db,
            )
        )

        db.refresh(tenant_b_skill)
        assert result["detail"] == "SearXNG instance deleted"
        assert db.query(SearxngInstance).filter(SearxngInstance.id == tenant_a_instance.id).first().is_active is False
        assert tenant_b_skill.config == {
            "provider": "searxng",
            "searxng_instance_id": tenant_a_instance.id + 999,
        }
        tenant_a_skill = (
            db.query(AgentSkill)
            .join(Agent, AgentSkill.agent_id == Agent.id)
            .filter(Agent.tenant_id == "tenant-alpha")
            .first()
        )
        assert tenant_a_skill.config == {}
    finally:
        db.close()
