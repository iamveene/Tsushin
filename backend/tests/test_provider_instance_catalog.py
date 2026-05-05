"""v0.7.0 LLM Provider catalog + cascade-delete tests.

Covers the backend-only behavior of the unified provider-instance API:

- ``GET /api/llm-providers/catalog`` returns one entry per supported vendor
  with the tenant's active instances embedded.
- ``GET /api/provider-instances/{id}/usage`` enumerates dependent agents.
- ``DELETE /api/provider-instances/{id}`` refuses without a reassign decision
  when there are dependents (HTTP 409) and applies the chosen reassignment
  atomically when one is supplied.
- ``bootstrap_orphan_vendor_agents`` materialises an Ollama instance and
  relinks orphan Ollama agents.

The tests use direct service calls + an isolated SQLite session so they
run fast and don't require the full FastAPI app stack.
"""

from __future__ import annotations

import os
import sys
import types

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

# Make the backend modules importable when pytest is run from the repo root.
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Optional stubs for dependencies not present in slim test envs.
docker_stub = types.ModuleType("docker")
docker_stub.errors = types.SimpleNamespace(NotFound=Exception, DockerException=Exception)
docker_stub.DockerClient = object
sys.modules.setdefault("docker", docker_stub)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):
    return "JSON"


import models_rbac  # noqa: F401, E402  — register Tenant/User tables
from models import Base, ProviderInstance, Agent, Contact  # noqa: E402
from services.provider_instance_service import ProviderInstanceService  # noqa: E402


@pytest.fixture()
def db():
    """SQLite in-memory session with the full schema."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _make_contact(db, tenant_id: str, name: str) -> Contact:
    contact = Contact(
        tenant_id=tenant_id,
        friendly_name=name,
        role="agent",
        is_active=True,
    )
    db.add(contact)
    db.commit()
    return contact


def _make_agent(db, tenant_id: str, contact_id: int, vendor: str, model: str, instance_id=None) -> Agent:
    agent = Agent(
        tenant_id=tenant_id,
        contact_id=contact_id,
        system_prompt="You are a helpful assistant.",
        model_provider=vendor,
        model_name=model,
        provider_instance_id=instance_id,
        is_active=True,
    )
    db.add(agent)
    db.commit()
    return agent


def _make_instance(db, tenant_id: str, vendor: str, name: str, *, is_default=False, is_active=True, models=None) -> ProviderInstance:
    instance = ProviderInstance(
        tenant_id=tenant_id,
        vendor=vendor,
        instance_name=name,
        base_url=f"https://example.test/{vendor}",
        is_default=is_default,
        is_active=is_active,
        available_models=models or [f"{vendor}-default"],
        health_status="healthy",
    )
    db.add(instance)
    db.commit()
    return instance


def test_catalog_returns_supported_vendors_with_active_instances(db):
    tid = "tenant_test_catalog"
    _make_instance(db, tid, "ollama", "Local Ollama", is_default=True, models=["llama3.2:3b"])
    _make_instance(db, tid, "openai", "OpenAI prod", is_default=True, models=["gpt-4.1-mini"])
    # Inactive instance must not surface.
    _make_instance(db, tid, "openai", "OpenAI legacy", is_active=False)

    catalog = ProviderInstanceService.get_catalog(tid, db)

    assert isinstance(catalog, list) and len(catalog) > 0
    by_vendor = {entry["vendor"]: entry for entry in catalog}
    assert "ollama" in by_vendor and "openai" in by_vendor and "anthropic" in by_vendor
    assert by_vendor["ollama"]["instances"][0]["instance_name"] == "Local Ollama"
    assert len(by_vendor["openai"]["instances"]) == 1, "soft-deleted instance must be hidden"
    assert by_vendor["anthropic"]["instances"] == []  # creatable but no instances yet
    assert by_vendor["anthropic"]["creatable"] is True


def test_get_instance_usage_lists_dependent_agents(db):
    tid = "tenant_usage"
    inst = _make_instance(db, tid, "ollama", "Ollama A", is_default=True)
    c1 = _make_contact(db, tid, "Bot A")
    c2 = _make_contact(db, tid, "Bot B")
    _make_agent(db, tid, c1.id, "ollama", "llama3.2:3b", instance_id=inst.id)
    _make_agent(db, tid, c2.id, "ollama", "llama3.2:3b", instance_id=inst.id)

    usage = ProviderInstanceService.get_instance_usage(inst.id, tid, db)
    names = sorted(a["name"] for a in usage["agents"])

    assert usage["dependent_count"] == 2
    assert names == ["Bot A", "Bot B"]
    assert usage["vendor"] == "ollama"


def test_get_instance_usage_is_tenant_scoped(db):
    inst = _make_instance(db, "tenant_owner", "ollama", "Owner Ollama")
    other = _make_contact(db, "tenant_other", "Foreign Bot")
    _make_agent(db, "tenant_other", other.id, "ollama", "llama3.2:3b", instance_id=inst.id)

    usage = ProviderInstanceService.get_instance_usage(inst.id, "tenant_owner", db)

    # Even though the foreign agent points at the owner's instance row, the
    # usage query is filtered by tenant and must not leak that agent.
    assert usage["dependent_count"] == 0


def test_delete_with_dependents_requires_decision(db):
    tid = "tenant_delete_block"
    inst = _make_instance(db, tid, "ollama", "Ollama victim")
    c = _make_contact(db, tid, "Dependent Bot")
    _make_agent(db, tid, c.id, "ollama", "llama3.2:3b", instance_id=inst.id)

    with pytest.raises(ValueError) as exc:
        ProviderInstanceService.delete_instance_with_reassign(inst.id, tid, db)

    assert str(exc.value) == "dependents_require_decision"
    db.refresh(inst)
    assert inst.is_active is True, "Instance must NOT be soft-deleted when caller didn't decide"


def test_delete_with_reassign_target_moves_agents(db):
    tid = "tenant_reassign"
    src = _make_instance(db, tid, "ollama", "Source", is_default=True, models=["a"])
    dst = _make_instance(db, tid, "ollama", "Target", models=["b"])
    c = _make_contact(db, tid, "Reassignable Bot")
    agent = _make_agent(db, tid, c.id, "ollama", "a", instance_id=src.id)

    result = ProviderInstanceService.delete_instance_with_reassign(
        src.id, tid, db, reassign_to_instance_id=dst.id
    )

    db.refresh(src)
    db.refresh(agent)
    assert src.is_active is False
    assert agent.provider_instance_id == dst.id
    assert agent.model_name == "b"  # snapped to target's first model
    assert result["reassigned_count"] == 1
    assert result["reassigned_to"]["id"] == dst.id


def test_delete_with_unassign_nulls_agents(db):
    tid = "tenant_unassign"
    src = _make_instance(db, tid, "ollama", "Source")
    c = _make_contact(db, tid, "Unassignable Bot")
    agent = _make_agent(db, tid, c.id, "ollama", "llama3.2:3b", instance_id=src.id)

    result = ProviderInstanceService.delete_instance_with_reassign(
        src.id, tid, db, unassign=True
    )

    db.refresh(src)
    db.refresh(agent)
    assert src.is_active is False
    assert agent.provider_instance_id is None
    assert agent.model_provider == "ollama"  # vendor preserved for runtime fallback
    assert result["reassigned_count"] == 1
    assert result["unassigned"] is True


def test_delete_rejects_self_as_reassign_target(db):
    tid = "tenant_self_reassign"
    inst = _make_instance(db, tid, "ollama", "OnlyOne")
    c = _make_contact(db, tid, "Bot")
    _make_agent(db, tid, c.id, "ollama", "x", instance_id=inst.id)

    with pytest.raises(ValueError) as exc:
        ProviderInstanceService.delete_instance_with_reassign(
            inst.id, tid, db, reassign_to_instance_id=inst.id
        )
    assert str(exc.value) == "reassign_target_is_self"


def test_delete_rejects_inactive_reassign_target(db):
    tid = "tenant_inactive_target"
    src = _make_instance(db, tid, "ollama", "Active Source")
    dead = _make_instance(db, tid, "ollama", "Already Dead", is_active=False)
    c = _make_contact(db, tid, "Bot")
    _make_agent(db, tid, c.id, "ollama", "x", instance_id=src.id)

    with pytest.raises(ValueError) as exc:
        ProviderInstanceService.delete_instance_with_reassign(
            src.id, tid, db, reassign_to_instance_id=dead.id
        )
    assert str(exc.value) == "reassign_target_invalid"


def test_delete_with_no_dependents_succeeds_without_payload(db):
    tid = "tenant_clean_delete"
    inst = _make_instance(db, tid, "openai", "Lonely")

    result = ProviderInstanceService.delete_instance_with_reassign(inst.id, tid, db)

    db.refresh(inst)
    assert inst.is_active is False
    assert result["reassigned_count"] == 0
    assert result["reassigned_to"] is None


def test_bootstrap_relinks_orphan_agent_to_existing_default(db):
    tid = "tenant_relink"
    default_inst = _make_instance(db, tid, "ollama", "Existing Default", is_default=True)
    c = _make_contact(db, tid, "Orphan Bot")
    orphan = _make_agent(db, tid, c.id, "ollama", "llama3.2:3b", instance_id=None)

    stats = ProviderInstanceService.bootstrap_orphan_vendor_agents(db)

    db.refresh(orphan)
    assert orphan.provider_instance_id == default_inst.id
    assert stats["agents_relinked"] >= 1


def test_bootstrap_warns_for_orphan_non_ollama_without_creating(db):
    tid = "tenant_orphan_gemini"
    c = _make_contact(db, tid, "Gemini Orphan")
    orphan = _make_agent(db, tid, c.id, "gemini", "gemini-2.5-flash", instance_id=None)

    stats = ProviderInstanceService.bootstrap_orphan_vendor_agents(db)

    db.refresh(orphan)
    # No Gemini instance was created (we lack credentials).
    assert orphan.provider_instance_id is None
    # Ollama branch did not fire for this tenant either.
    assert stats["instances_created"] == 0


def test_aiclient_ollama_orphan_raises_clear_error(db):
    """Mid-session orphan Ollama agent (no instance, no tenant default) must
    raise a Configure-via-Hub ValueError, not silently spin up a host client.

    This protects the v0.7.0 invariant: every Ollama runtime call is bound to
    an explicit provider_instance, either via the wizard / Studio edit or via
    the boot-time bootstrap. Mid-session orphans (an agent created after the
    backend booted in a tenant with no default Ollama) used to silently fall
    back to the host-mode env var; that fallback is gone now.
    """
    from agent.ai_client import AIClient

    tid = "tenant_orphan_ollama_runtime"
    c = _make_contact(db, tid, "Mid-Session Bot")
    _make_agent(db, tid, c.id, "ollama", "llama3.2:3b", instance_id=None)

    with pytest.raises(ValueError) as excinfo:
        AIClient(
            provider="ollama",
            model_name="llama3.2:3b",
            db=db,
            tenant_id=tid,
            provider_instance_id=None,
        )

    msg = str(excinfo.value)
    assert "Hub" in msg and "LLM Providers" in msg
    assert tid in msg


def test_bootstrap_is_idempotent(db):
    """Second call must not double-create the auto-Ollama instance or
    re-relink an already-linked agent. A boot loop (e.g. backend crash +
    restart) should not pile up duplicate rows.
    """
    tid = "tenant_idempotent_bootstrap"
    c = _make_contact(db, tid, "Idem Bot")
    _make_agent(db, tid, c.id, "ollama", "llama3.2:3b", instance_id=None)

    s1 = ProviderInstanceService.bootstrap_orphan_vendor_agents(db)
    s2 = ProviderInstanceService.bootstrap_orphan_vendor_agents(db)

    assert s1["instances_created"] >= 1
    assert s2["instances_created"] == 0
    assert s2["agents_relinked"] == 0

    ollama_count = (
        db.query(ProviderInstance)
        .filter(
            ProviderInstance.tenant_id == tid,
            ProviderInstance.vendor == "ollama",
        )
        .count()
    )
    assert ollama_count == 1
