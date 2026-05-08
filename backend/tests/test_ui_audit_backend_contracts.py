from __future__ import annotations

import os
import sys
import types
import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
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

sentence_transformers_stub = types.ModuleType("sentence_transformers")


class _SentenceTransformer:
    def __init__(self, *_args, **_kwargs):
        pass

    def encode(self, *_args, **_kwargs):
        return [0.0, 0.0, 0.0]


sentence_transformers_stub.SentenceTransformer = _SentenceTransformer
sys.modules.setdefault("sentence_transformers", sentence_transformers_stub)

chromadb_stub = types.ModuleType("chromadb")
chromadb_stub.PersistentClient = lambda *args, **kwargs: SimpleNamespace()
chromadb_stub.Client = lambda *args, **kwargs: SimpleNamespace()
sys.modules.setdefault("chromadb", chromadb_stub)
chromadb_config_stub = types.ModuleType("chromadb.config")
chromadb_config_stub.Settings = lambda *args, **kwargs: SimpleNamespace()
sys.modules.setdefault("chromadb.config", chromadb_config_stub)

from api.routes_agent_communication import list_permissions  # noqa: E402
from api.routes_analytics import get_token_usage_by_agent  # noqa: E402
from api.routes_flows import list_runs  # noqa: E402
from api.routes_sentinel_profiles import (  # noqa: E402
    SentinelProfileAssignRequest,
    assign_profile,
    list_assignments,
)
from api.routes_vector_stores import list_vector_store_instances  # noqa: E402
from auth_dependencies import TenantContext  # noqa: E402
from services.agent_run_status import determine_agent_run_status  # noqa: E402
from models import (  # noqa: E402
    Agent,
    AgentCommunicationPermission,
    Base,
    Contact,
    FlowDefinition,
    FlowRun,
    SentinelProfile,
    SentinelProfileAssignment,
    TokenUsage,
    VectorStoreIndex,
    VectorStoreInstance,
)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Contact.__table__,
            Agent.__table__,
            AgentCommunicationPermission.__table__,
            SentinelProfile.__table__,
            SentinelProfileAssignment.__table__,
            FlowDefinition.__table__,
            FlowRun.__table__,
            TokenUsage.__table__,
            VectorStoreInstance.__table__,
            VectorStoreIndex.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ctx(db, tenant_id: str = "tenant-a", *, is_global_admin: bool = False) -> TenantContext:
    user = SimpleNamespace(id=1, tenant_id=tenant_id, is_global_admin=is_global_admin, email="user@example.test")
    return TenantContext(user=user, db=db)


def _seed_agent(db, *, agent_id: int, name: str, tenant_id: str = "tenant-a") -> Agent:
    contact = Contact(id=agent_id + 1000, tenant_id=tenant_id, friendly_name=name, role="agent")
    agent = Agent(
        id=agent_id,
        tenant_id=tenant_id,
        contact_id=contact.id,
        system_prompt=f"You are {name}.",
        model_provider="gemini",
        model_name="gemini-2.5-pro",
        response_template="{response}",
        enabled_channels=["playground"],
        is_active=True,
    )
    db.add(contact)
    db.add(agent)
    db.commit()
    return agent


def test_a2a_permission_list_cleans_deleted_agent_rules(db_session):
    _seed_agent(db_session, agent_id=1, name="Source")
    db_session.add(
        AgentCommunicationPermission(
            id=10,
            tenant_id="tenant-a",
            source_agent_id=1,
            target_agent_id=999,
            max_depth=3,
            rate_limit_rpm=30,
            is_enabled=True,
        )
    )
    db_session.commit()

    result = asyncio.run(list_permissions(current_user=SimpleNamespace(id=1), ctx=_ctx(db_session), db=db_session))

    assert result == []
    assert db_session.query(AgentCommunicationPermission).count() == 0


def test_agent_runs_reconcile_success_status_with_execution_error_output():
    status = determine_agent_run_status(
        {
            "output_preview": "Error executing webhook.post: curl: (3) URL rejected: Malformed input",
        },
        current_status="success",
    )

    assert status == "error"


def test_sentinel_assignment_labels_deleted_agent_and_rejects_cross_tenant_assign(db_session):
    profile = SentinelProfile(
        id=1,
        tenant_id="tenant-a",
        name="Strict",
        slug="strict",
        is_system=False,
        is_default=False,
    )
    db_session.add(profile)
    db_session.add(
        SentinelProfileAssignment(id=5, tenant_id="tenant-a", agent_id=999, profile_id=1)
    )
    _seed_agent(db_session, agent_id=2, name="Other Tenant Agent", tenant_id="tenant-b")
    db_session.commit()

    assignments = asyncio.run(list_assignments(agent_id=None, skill_type=None, ctx=_ctx(db_session), db=db_session))

    assert assignments[0].agent_name == "[deleted agent]"
    assert assignments[0].agent_deleted is True

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            assign_profile(
                data=SentinelProfileAssignRequest(profile_id=1, agent_id=2),
                current_user=SimpleNamespace(id=1),
                ctx=_ctx(db_session),
                db=db_session,
            )
        )
    assert exc.value.status_code == 404


def test_flow_runs_include_display_name_and_safe_subsecond_duration(db_session):
    flow = FlowDefinition(id=7, tenant_id="tenant-a", name="Daily Triage", is_active=True)
    now = datetime.utcnow()
    run = FlowRun(
        id=20,
        tenant_id="tenant-a",
        flow_definition_id=7,
        status="completed",
        started_at=now,
        completed_at=now,
        created_at=now,
    )
    db_session.add(flow)
    db_session.add(run)
    db_session.commit()

    result = list_runs(limit=10, db=db_session, tenant_context=_ctx(db_session))

    assert result[0].flow_name == "Daily Triage"
    assert result[0].flow_display_name == "Daily Triage"
    assert result[0].duration_ms == 0
    assert result[0].duration_label == "<1s"


def test_billing_by_agent_uses_display_names_and_fails_closed_without_tenant_agents(db_session):
    _seed_agent(db_session, agent_id=1, name="Billing Bot")
    db_session.add(
        TokenUsage(
            agent_id=1,
            operation_type="message_processing",
            model_provider="gemini",
            model_name="gemini-2.5-pro",
            total_tokens=42,
            estimated_cost=0.01,
        )
    )
    db_session.add(
        TokenUsage(
            agent_id=999,
            operation_type="message_processing",
            model_provider="gemini",
            model_name="gemini-2.5-pro",
            total_tokens=99,
            estimated_cost=9.99,
        )
    )
    db_session.commit()

    result = asyncio.run(get_token_usage_by_agent(days=30, db=db_session, current_user=SimpleNamespace(id=1), ctx=_ctx(db_session)))
    empty_tenant = asyncio.run(get_token_usage_by_agent(days=30, db=db_session, current_user=SimpleNamespace(id=1), ctx=_ctx(db_session, "tenant-empty")))

    assert result["agents"][0]["agent_name"] == "Billing Bot"
    assert all(row["agent_name"] != "Agent 1" for row in result["agents"])
    assert empty_tenant == {"agents": [], "days": 30}


def test_vector_store_list_masks_internal_runtime_identifiers(db_session):
    instance = VectorStoreInstance(
        id=3,
        tenant_id="tenant-a",
        vendor="qdrant",
        instance_name="Local Qdrant",
        base_url="http://vs-qdrant-abc:6333",
        extra_config={"collection_name": "case_memory_tenant_20260406004333855618_c58c99"},
        is_active=True,
        is_auto_provisioned=True,
        container_name="vs-qdrant-abc",
    )
    index = VectorStoreIndex(
        id=4,
        tenant_id="tenant-a",
        vector_store_instance_id=3,
        purpose="agent_kb",
        owner_type="agent",
        owner_id=1,
        embedding_provider="local",
        embedding_model="all-MiniLM-L6-v2",
        embedding_dims=384,
        embedding_metric="cosine",
        physical_collection_name="tsn_te4a672bb_agent_kb_agent_e85566a8_abc123",
        physical_namespace="tsn_te4a672bb_agent_kb_agent_e85566a8_abc123",
        physical_index_name="tsn-te4a672bb-agent-kb",
        contract_hash="abc123",
        is_active=True,
    )
    db_session.add(instance)
    db_session.add(index)
    db_session.commit()

    result = asyncio.run(list_vector_store_instances(vendor=None, ctx=_ctx(db_session), db=db_session))

    assert result[0]["base_url"] is None
    assert result[0]["display_url"] == "Managed by Tsushin"
    assert result[0]["extra_config"]["collection_name"] == "Default collection"
    assert result[0]["indexes"][0]["collection_name"] == "Agent Kb index"
    assert "tsn_" not in str(result[0])
    assert "vs-qdrant" not in str(result[0])
