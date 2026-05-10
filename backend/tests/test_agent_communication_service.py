"""
Targeted regression tests for agent communication permission lifecycle.
"""

import asyncio
import importlib.util
import os
import sys
import types
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy.ext.compiler import compiles
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
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

import models_rbac  # noqa: F401
from models import (
    Base,
    Agent,
    AgentCommunicationPermission,
    AgentSkill,
    AgentTeamMemberA2ASnapshot,
    Contact,
)
from services.agent_communication_service import AgentCommunicationService


BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure_package(package_name: str, relative_path: str):
    module = sys.modules.get(package_name)
    if module is None:
        module = types.ModuleType(package_name)
        module.__path__ = [os.path.join(BACKEND_ROOT, relative_path)]
        sys.modules[package_name] = module
    return module


def _load_module(module_name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(
        module_name,
        os.path.join(BACKEND_ROOT, relative_path),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def stub_default_skill_config():
    with patch.object(
        AgentCommunicationService,
        "_get_default_agent_communication_config",
        new=lambda self, *, auto_managed: (
            {"keywords": [], self.AUTO_MANAGED_SKILL_MARKER: True}
            if auto_managed
            else {"keywords": []}
        ),
    ):
        yield


def _create_agent(db_session, *, tenant_id: str, name: str, provider_instance_id=None) -> Agent:
    contact = Contact(
        friendly_name=name,
        role="agent",
        tenant_id=tenant_id,
        is_active=True,
    )
    db_session.add(contact)
    db_session.flush()

    agent = Agent(
        contact_id=contact.id,
        tenant_id=tenant_id,
        system_prompt=f"You are {name}",
        model_provider="openai",
        model_name="gpt-4o-mini",
        is_active=True,
        provider_instance_id=provider_instance_id,
    )
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)
    return agent


def test_create_permission_creates_auto_managed_skill(db_session):
    tenant_id = "tenant-a2a"
    source = _create_agent(db_session, tenant_id=tenant_id, name="Source")
    target = _create_agent(db_session, tenant_id=tenant_id, name="Target")
    service = AgentCommunicationService(db_session, tenant_id)

    perm = service.create_permission(source.id, target.id)
    skill = db_session.query(AgentSkill).filter(
        AgentSkill.agent_id == source.id,
        AgentSkill.skill_type == "agent_communication",
    ).one()

    assert perm.is_enabled is True
    assert skill.is_enabled is True
    assert skill.config[service.AUTO_MANAGED_SKILL_MARKER] is True


def test_create_permission_does_not_reenable_manual_disabled_skill(db_session):
    tenant_id = "tenant-a2a"
    source = _create_agent(db_session, tenant_id=tenant_id, name="Manual Source")
    target = _create_agent(db_session, tenant_id=tenant_id, name="Manual Target")
    db_session.add(AgentSkill(
        agent_id=source.id,
        skill_type="agent_communication",
        is_enabled=False,
        config={"keywords": []},
    ))
    db_session.commit()

    service = AgentCommunicationService(db_session, tenant_id)
    service.create_permission(source.id, target.id)

    skill = db_session.query(AgentSkill).filter(
        AgentSkill.agent_id == source.id,
        AgentSkill.skill_type == "agent_communication",
    ).one()
    assert skill.is_enabled is False
    assert service.AUTO_MANAGED_SKILL_MARKER not in (skill.config or {})


def test_disable_last_permission_disables_auto_managed_skill_and_stays_disabled(db_session):
    tenant_id = "tenant-a2a"
    source = _create_agent(db_session, tenant_id=tenant_id, name="Update Source")
    target = _create_agent(db_session, tenant_id=tenant_id, name="Update Target")
    service = AgentCommunicationService(db_session, tenant_id)

    perm = service.create_permission(source.id, target.id)
    updated = service.update_permission(perm.id, is_enabled=False)
    skill = db_session.query(AgentSkill).filter(
        AgentSkill.agent_id == source.id,
        AgentSkill.skill_type == "agent_communication",
    ).one()

    assert updated is not None
    assert updated.is_enabled is False
    assert skill.is_enabled is False

    service.update_permission(perm.id, rate_limit_rpm=99)
    db_session.refresh(skill)
    assert skill.is_enabled is False


def test_reenable_permission_reenables_auto_managed_skill(db_session):
    tenant_id = "tenant-a2a"
    source = _create_agent(db_session, tenant_id=tenant_id, name="Reenable Source")
    target = _create_agent(db_session, tenant_id=tenant_id, name="Reenable Target")
    service = AgentCommunicationService(db_session, tenant_id)

    perm = service.create_permission(source.id, target.id)
    service.update_permission(perm.id, is_enabled=False)
    service.update_permission(perm.id, is_enabled=True)

    skill = db_session.query(AgentSkill).filter(
        AgentSkill.agent_id == source.id,
        AgentSkill.skill_type == "agent_communication",
    ).one()
    db_session.refresh(skill)

    assert skill.config[service.AUTO_MANAGED_SKILL_MARKER] is True
    assert skill.is_enabled is True


def test_delete_last_permission_disables_auto_managed_skill(db_session):
    tenant_id = "tenant-a2a"
    source = _create_agent(db_session, tenant_id=tenant_id, name="Delete Source")
    target = _create_agent(db_session, tenant_id=tenant_id, name="Delete Target")
    service = AgentCommunicationService(db_session, tenant_id)

    perm = service.create_permission(source.id, target.id)

    assert service.delete_permission(perm.id) is True

    skill = db_session.query(AgentSkill).filter(
        AgentSkill.agent_id == source.id,
        AgentSkill.skill_type == "agent_communication",
    ).one()
    remaining = db_session.query(AgentCommunicationPermission).count()

    assert remaining == 0
    assert skill.is_enabled is False


def test_a2a_snapshot_permission_fks_use_set_null():
    """Regression: the snapshot table has TWO FKs to
    agent_communication_permission (the single-column ``permission_id`` and
    the composite ``(tenant_id, permission_id)``). Both must use
    ``ON DELETE SET NULL`` — if the composite FK reverts to the SQL default
    (``NO ACTION``), Postgres blocks every permission delete with a
    ``ForeignKeyViolation`` whenever a snapshot row references the
    permission, surfacing as a 500 on
    ``DELETE /api/agent-communication/permissions/{id}``.

    Asserted at the SQLAlchemy schema layer because SQLite (used elsewhere in
    this file) does not enforce composite FKs strictly, so a behavioral test
    cannot catch this regression on its own.
    """
    perm_fks = [
        fk
        for fk in AgentTeamMemberA2ASnapshot.__table__.foreign_key_constraints
        if fk.referred_table.name == "agent_communication_permission"
    ]
    assert len(perm_fks) == 2, (
        "Expected exactly two FKs from agent_team_member_a2a_snapshot to "
        "agent_communication_permission (single-column + composite); "
        f"found {len(perm_fks)}."
    )
    for fk in perm_fks:
        assert fk.ondelete == "SET NULL", (
            f"FK {fk.name!r} on agent_team_member_a2a_snapshot must use "
            f"ON DELETE SET NULL (got {fk.ondelete!r}). Without it, "
            f"Postgres blocks deletes on agent_communication_permission "
            f"and DELETE /api/agent-communication/permissions/{{id}} "
            f"returns 500."
        )




def test_invoke_target_agent_preserves_provider_instance_id(db_session):
    tenant_id = "tenant-a2a"
    source = _create_agent(db_session, tenant_id=tenant_id, name="Invoker")
    target = _create_agent(
        db_session,
        tenant_id=tenant_id,
        name="Receiver",
        provider_instance_id=42,
    )
    service = AgentCommunicationService(db_session, tenant_id)
    captured = {}

    fake_agent_service_module = types.ModuleType("agent.agent_service")

    class FakeAgentService:
        def __init__(self, agent_config, **kwargs):
            captured["agent_config"] = agent_config

        async def process_message(self, **kwargs):
            captured["process_kwargs"] = kwargs
            return {"answer": "delegated"}

    fake_agent_service_module.AgentService = FakeAgentService

    fake_multi_agent_memory_module = types.ModuleType("agent.memory.multi_agent_memory")

    class FakeMemoryManager:
        def __init__(self, db, agent_config):
            self.agent_config = agent_config

        async def get_context(self, **kwargs):
            return None

        def get_agent_memory(self, agent_id):
            return types.SimpleNamespace(
                format_context_for_prompt=lambda *args, **kwargs: "[No previous context]"
            )

    fake_multi_agent_memory_module.MultiAgentMemoryManager = FakeMemoryManager

    with patch.dict(sys.modules, {
        "agent.agent_service": fake_agent_service_module,
        "agent.memory.multi_agent_memory": fake_multi_agent_memory_module,
    }):
        result = asyncio.run(service._invoke_target_agent(
            target_agent=target,
            message="delegate this",
            context=None,
            source_agent=source,
            depth=1,
        ))

    assert captured["agent_config"]["provider_instance_id"] == 42
    assert captured["process_kwargs"]["original_query"] == "delegate this"
    assert result["answer"] == "delegated"


def test_list_agents_delegate_intent_creates_real_session(db_session, monkeypatch):
    _ensure_package("agent", "agent")
    _ensure_package("agent.skills", os.path.join("agent", "skills"))
    base_module = _load_module("agent.skills.base", os.path.join("agent", "skills", "base.py"))
    skill_module = _load_module(
        "agent.skills.agent_communication_skill",
        os.path.join("agent", "skills", "agent_communication_skill.py"),
    )

    tenant_id = "tenant-a2a-skill"
    source = _create_agent(db_session, tenant_id=tenant_id, name="Source Agent")
    target = _create_agent(db_session, tenant_id=tenant_id, name="Target Agent")
    db_session.add(AgentCommunicationPermission(
        tenant_id=tenant_id,
        source_agent_id=source.id,
        target_agent_id=target.id,
        is_enabled=True,
        max_depth=3,
        rate_limit_rpm=30,
    ))
    db_session.commit()

    async def _fake_invoke(self, target_agent, message, context, source_agent, depth, *, allow_target_skills=False, session_id=None):
        assert target_agent.id == target.id
        assert source_agent.id == source.id
        assert "Target Agent" in message
        return {"answer": "Delegated answer", "tokens": {"total": 11}}

    async def _fake_sentinel(self, message, source_agent_id, target_agent_id, depth):
        return None

    monkeypatch.setattr(AgentCommunicationService, "_invoke_target_agent", _fake_invoke)
    monkeypatch.setattr(AgentCommunicationService, "_sentinel_analyze", _fake_sentinel)

    skill = skill_module.AgentCommunicationSkill()
    skill.set_db_session(db_session)
    skill._agent_id = source.id

    message = base_module.InboundMessage(
        id="msg-1",
        sender="tester",
        sender_key="playground_u1_a1_t1",
        body="Please delegate this task to Target Agent and let them answer directly.",
        chat_id="playground",
        chat_name=None,
        is_group=False,
        timestamp=datetime.utcnow(),
        channel="playground",
    )

    result = asyncio.run(skill.execute_tool(
        {"action": "list_agents"},
        message,
        {"tenant_id": tenant_id, "default_timeout": 60},
    ))

    from models import AgentCommunicationSession, AgentCommunicationMessage

    session = db_session.query(AgentCommunicationSession).one()
    messages = db_session.query(AgentCommunicationMessage).order_by(AgentCommunicationMessage.id.asc()).all()

    assert result.success is True
    assert result.output == "Delegated answer"
    assert result.metadata["session_id"] == session.id
    assert session.session_type == "delegate"
    assert session.status == "completed"
    assert [msg.direction for msg in messages] == ["request", "response"]


def test_agent_service_prefers_tool_result_when_response_empty():
    _ensure_package("agent", "agent")
    _ensure_package("agent.tools", os.path.join("agent", "tools"))
    _ensure_package("agent.knowledge", os.path.join("agent", "knowledge"))
    _ensure_package("services", "services")

    # Only install the stub if the real module hasn't already been imported
    # by another test in this pytest session. Clobbering breaks downstream
    # tests like test_new_providers.py that exercise the real `AIClient`.
    if "agent.ai_client" not in sys.modules:
        ai_client_stub = types.ModuleType("agent.ai_client")
        ai_client_stub.AIClient = type("AIClient", (), {})
        # `agent.ai_client` re-exports `get_api_key` from
        # `services.api_key_service`. Downstream tests
        # `@patch("agent.ai_client.get_api_key", ...)` so expose a no-op.
        ai_client_stub.get_api_key = lambda *args, **kwargs: None
        sys.modules["agent.ai_client"] = ai_client_stub

    if "agent.tools.sandboxed_tool_wrapper" not in sys.modules:
        tools_stub = types.ModuleType("agent.tools.sandboxed_tool_wrapper")
        tools_stub.SandboxedToolWrapper = type("SandboxedToolWrapper", (), {})
        sys.modules["agent.tools.sandboxed_tool_wrapper"] = tools_stub

    if "agent.knowledge.knowledge_service" not in sys.modules:
        knowledge_stub = types.ModuleType("agent.knowledge.knowledge_service")
        knowledge_stub.KnowledgeService = type("KnowledgeService", (), {})
        # Other modules (e.g. api/routes_knowledge_base.py via
        # `from app import app`) import KnowledgeMetadataError from this
        # module. Provide a no-op subclass of RuntimeError so downstream
        # tests don't fail with `cannot import name 'KnowledgeMetadataError'`.
        knowledge_stub.KnowledgeMetadataError = type(
            "KnowledgeMetadataError", (RuntimeError,), {}
        )
        sys.modules["agent.knowledge.knowledge_service"] = knowledge_stub

    # Only install the lightweight stub if the real package hasn't already
    # been imported. Clobbering breaks downstream tests like
    # test_provider_instance_hardening.py which need to import
    # `agent.skills.skill_manager` (the stub is a plain ModuleType without
    # __path__, so submodule imports raise ModuleNotFoundError).
    # Ensure `agent.skills` exists in sys.modules with the attributes our
    # downstream loads need (`get_skill_manager`, `InboundMessage`). If the
    # module is already present (either the real package or a placeholder
    # from a previous _ensure_package call), augment it rather than clobber,
    # so test_provider_instance_hardening.py can still load the real
    # `agent.skills.skill_manager`.
    skills_module = sys.modules.get("agent.skills")
    if skills_module is None:
        skills_module = types.ModuleType("agent.skills")
        skills_module.__path__ = [os.path.join(BACKEND_ROOT, "agent", "skills")]
        sys.modules["agent.skills"] = skills_module
    if not hasattr(skills_module, "get_skill_manager"):
        skills_module.get_skill_manager = lambda *args, **kwargs: None
    if not hasattr(skills_module, "InboundMessage"):
        skills_module.InboundMessage = type("InboundMessage", (), {})

    if "services.watcher_activity_service" not in sys.modules:
        watcher_stub = types.ModuleType("services.watcher_activity_service")
        watcher_stub.emit_kb_used_async = lambda *args, **kwargs: None
        # `agent/router.py` imports several emitters from this module. Provide
        # no-op shims so downstream tests that import `from app import app`
        # don't fail with ImportError when our stub is the resident module.
        watcher_stub.emit_agent_processing_async = lambda *args, **kwargs: None
        watcher_stub.emit_skill_used_async = lambda *args, **kwargs: None
        watcher_stub.emit_channel_health_async = lambda *args, **kwargs: None
        watcher_stub.emit_agent_communication_async = lambda *args, **kwargs: None
        watcher_stub.emit_continuous_run_async = lambda *args, **kwargs: None
        watcher_stub.WatcherActivityService = type("WatcherActivityService", (), {})
        sys.modules["services.watcher_activity_service"] = watcher_stub

    agent_service_module = _load_module("agent.agent_service", os.path.join("agent", "agent_service.py"))
    service = agent_service_module.AgentService.__new__(agent_service_module.AgentService)
    service.logger = types.SimpleNamespace(info=lambda *args, **kwargs: None)

    assert service._prefer_tool_result_when_response_empty("", "CUSTOM_SKILL_OK") == "CUSTOM_SKILL_OK"
    assert service._prefer_tool_result_when_response_empty("   ", "CUSTOM_SKILL_OK") == "CUSTOM_SKILL_OK"
    assert service._prefer_tool_result_when_response_empty("Model reply", "CUSTOM_SKILL_OK") == "Model reply"


def test_resolve_agent_by_name_uses_exact_match_before_normalized_fallback(db_session):
    _ensure_package("agent", "agent")
    _ensure_package("agent.skills", os.path.join("agent", "skills"))
    _load_module("agent.skills.base", os.path.join("agent", "skills", "base.py"))
    skill_module = _load_module(
        "agent.skills.agent_communication_skill",
        os.path.join("agent", "skills", "agent_communication_skill.py"),
    )

    tenant_id = "tenant-a2a-normalized"
    exact = _create_agent(db_session, tenant_id=tenant_id, name="Support Agent")
    fallback = _create_agent(db_session, tenant_id=tenant_id, name="ACME Sales")

    skill = skill_module.AgentCommunicationSkill()
    skill.set_db_session(db_session)

    assert skill._resolve_agent_by_name("Support Agent", tenant_id).id == exact.id
    assert skill._resolve_agent_by_name("ACME Sales agent", tenant_id).id == fallback.id


# ---------------------------------------------------------------------------
# allow_target_skills toggle (v0.7.2)
# ---------------------------------------------------------------------------


def test_create_permission_defaults_allow_target_skills_to_false(db_session):
    tenant_id = "tenant-target-skills-default"
    source = _create_agent(db_session, tenant_id=tenant_id, name="S-default")
    target = _create_agent(db_session, tenant_id=tenant_id, name="T-default")
    service = AgentCommunicationService(db_session, tenant_id)

    perm = service.create_permission(source.id, target.id)
    db_session.refresh(perm)

    assert perm.allow_target_skills is False


def test_create_permission_accepts_allow_target_skills_true(db_session):
    tenant_id = "tenant-target-skills-opt-in"
    source = _create_agent(db_session, tenant_id=tenant_id, name="S-opt")
    target = _create_agent(db_session, tenant_id=tenant_id, name="T-opt")
    service = AgentCommunicationService(db_session, tenant_id)

    captured_audit = []
    with patch.object(
        AgentCommunicationService,
        "_audit_log",
        new=lambda self, action, src, tgt, details: captured_audit.append((action, src, tgt, details)),
    ):
        perm = service.create_permission(source.id, target.id, allow_target_skills=True)

    db_session.refresh(perm)
    assert perm.allow_target_skills is True

    create_entry = next((e for e in captured_audit if e[0] == "agent_comm.permission.create"), None)
    assert create_entry is not None
    assert create_entry[3].get("allow_target_skills") is True


def test_update_permission_toggles_allow_target_skills(db_session):
    tenant_id = "tenant-target-skills-update"
    source = _create_agent(db_session, tenant_id=tenant_id, name="S-upd")
    target = _create_agent(db_session, tenant_id=tenant_id, name="T-upd")
    service = AgentCommunicationService(db_session, tenant_id)
    perm = service.create_permission(source.id, target.id)

    updated = service.update_permission(perm.id, allow_target_skills=True)
    assert updated is not None
    assert updated.allow_target_skills is True

    updated = service.update_permission(perm.id, allow_target_skills=False)
    assert updated.allow_target_skills is False


def _capture_invoke(service, target, source, *, allow_target_skills):
    """Run _invoke_target_agent with stubbed AgentService; return captured kwargs."""
    captured = {}

    fake_agent_service_module = types.ModuleType("agent.agent_service")

    class FakeAgentService:
        def __init__(self, agent_config, **kwargs):
            captured["agent_config"] = agent_config
            captured["init_kwargs"] = kwargs

        async def process_message(self, **kwargs):
            return {"answer": "ok"}

    fake_agent_service_module.AgentService = FakeAgentService

    fake_multi_agent_memory_module = types.ModuleType("agent.memory.multi_agent_memory")

    class FakeMemoryManager:
        def __init__(self, db, agent_config):
            pass

        async def get_context(self, **kwargs):
            return None

        def get_agent_memory(self, agent_id):
            return types.SimpleNamespace(
                format_context_for_prompt=lambda *args, **kwargs: "[No previous context]"
            )

    fake_multi_agent_memory_module.MultiAgentMemoryManager = FakeMemoryManager

    with patch.dict(sys.modules, {
        "agent.agent_service": fake_agent_service_module,
        "agent.memory.multi_agent_memory": fake_multi_agent_memory_module,
    }):
        asyncio.run(service._invoke_target_agent(
            target_agent=target,
            message="delegated question",
            context=None,
            source_agent=source,
            depth=1,
            allow_target_skills=allow_target_skills,
        ))

    return captured


def test_invoke_target_agent_disables_skills_when_flag_false(db_session):
    tenant_id = "tenant-target-skills-off"
    source = _create_agent(db_session, tenant_id=tenant_id, name="S-off")
    target = _create_agent(db_session, tenant_id=tenant_id, name="T-off")
    service = AgentCommunicationService(db_session, tenant_id)

    captured = _capture_invoke(service, target, source, allow_target_skills=False)

    assert captured["init_kwargs"]["disable_skills"] is True


def test_invoke_target_agent_enables_skills_when_flag_true(db_session):
    tenant_id = "tenant-target-skills-on"
    source = _create_agent(db_session, tenant_id=tenant_id, name="S-on")
    target = _create_agent(db_session, tenant_id=tenant_id, name="T-on")
    service = AgentCommunicationService(db_session, tenant_id)

    captured = _capture_invoke(service, target, source, allow_target_skills=True)

    assert captured["init_kwargs"]["disable_skills"] is False


def test_send_message_propagates_permission_flag_to_invoke(db_session, monkeypatch):
    tenant_id = "tenant-target-skills-wire"
    source = _create_agent(db_session, tenant_id=tenant_id, name="S-wire")
    target = _create_agent(db_session, tenant_id=tenant_id, name="T-wire")
    service = AgentCommunicationService(db_session, tenant_id)
    perm = service.create_permission(source.id, target.id, allow_target_skills=True)
    assert perm.allow_target_skills is True

    captured = {}

    async def _fake_invoke(self, target_agent, message, context, source_agent, depth, *, allow_target_skills=False, session_id=None):
        captured["allow_target_skills"] = allow_target_skills
        captured["session_id"] = session_id
        return {"answer": "ok", "tokens": {"total": 0}}

    async def _fake_sentinel(self, message, source_agent_id, target_agent_id, depth):
        return None

    monkeypatch.setattr(AgentCommunicationService, "_invoke_target_agent", _fake_invoke)
    monkeypatch.setattr(AgentCommunicationService, "_sentinel_analyze", _fake_sentinel)

    result = asyncio.run(service.send_message(
        source_agent_id=source.id,
        target_agent_id=target.id,
        message="please fetch",
    ))

    assert result.success is True
    assert captured["allow_target_skills"] is True
    assert captured["session_id"] == result.session_id


def test_invoke_target_agent_injects_comm_parent_session_id(db_session):
    """_invoke_target_agent must thread session_id into agent_config so nested
    A2A calls populate parent_session_id and _detect_loop runs."""
    tenant_id = "tenant-loop-prop"
    source = _create_agent(db_session, tenant_id=tenant_id, name="S-loop")
    target = _create_agent(db_session, tenant_id=tenant_id, name="T-loop")
    service = AgentCommunicationService(db_session, tenant_id)

    captured = _capture_invoke_with_session(service, target, source, session_id=4242)
    assert captured["agent_config"]["comm_parent_session_id"] == 4242
    assert captured["agent_config"]["comm_depth"] == 1


def _capture_invoke_with_session(service, target, source, *, session_id):
    captured = {}

    fake_agent_service_module = types.ModuleType("agent.agent_service")

    class FakeAgentService:
        def __init__(self, agent_config, **kwargs):
            captured["agent_config"] = agent_config
            captured["init_kwargs"] = kwargs

        async def process_message(self, **kwargs):
            return {"answer": "ok"}

    fake_agent_service_module.AgentService = FakeAgentService

    fake_multi_agent_memory_module = types.ModuleType("agent.memory.multi_agent_memory")

    class FakeMemoryManager:
        def __init__(self, db, agent_config):
            pass

        async def get_context(self, **kwargs):
            return None

        def get_agent_memory(self, agent_id):
            return types.SimpleNamespace(
                format_context_for_prompt=lambda *args, **kwargs: "[No previous context]"
            )

    fake_multi_agent_memory_module.MultiAgentMemoryManager = FakeMemoryManager

    with patch.dict(sys.modules, {
        "agent.agent_service": fake_agent_service_module,
        "agent.memory.multi_agent_memory": fake_multi_agent_memory_module,
    }):
        asyncio.run(service._invoke_target_agent(
            target_agent=target,
            message="q",
            context=None,
            source_agent=source,
            depth=1,
            allow_target_skills=True,
            session_id=session_id,
        ))

    return captured
