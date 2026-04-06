"""
Graph preview regression tests for WhatsApp binding resolution.
"""

import asyncio
import os
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

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

from api.routes_agents_protected import get_agents_graph_preview


class QueryStub:
    def __init__(self, result, *, first_result=None):
        self._result = result
        self._first_result = first_result

    def join(self, *args, **kwargs):
        return self

    def outerjoin(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def group_by(self, *args, **kwargs):
        return self

    def subquery(self):
        return SimpleNamespace(c=SimpleNamespace(
            skills_count="skills_count",
            doc_count="doc_count",
            chunk_count="chunk_count",
            sentinel_enabled="sentinel_enabled",
            agent_id="agent_id",
        ))

    def all(self):
        return self._result

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self._first_result


class FakeTenantContext:
    def __init__(self, db, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.is_global_admin = False

    def filter_by_tenant(self, query, column):
        return query


def make_agent(agent_id: int, *, enabled_channels, whatsapp_integration_id=None):
    return SimpleNamespace(
        id=agent_id,
        contact_id=agent_id,
        is_active=True,
        is_default=False,
        model_provider="gemini",
        model_name="gemini-2.5-pro",
        memory_isolation_mode="isolated",
        enabled_channels=enabled_channels,
        whatsapp_integration_id=whatsapp_integration_id,
        telegram_integration_id=None,
        webhook_integration_id=None,
        tenant_id="tenant-graph",
        avatar=None,
    )


def make_instance(instance_id: int, *, status="running", instance_type="agent"):
    return SimpleNamespace(
        id=instance_id,
        tenant_id="tenant-graph",
        container_name=f"mcp-{instance_id}",
        phone_number=f"+55110000000{instance_id}",
        instance_type=instance_type,
        status=status,
        health_status="healthy",
        created_at=instance_id,
    )


def build_ctx(agent_rows, whatsapp_instances, *, explicit_instance=None):
    db = MagicMock()

    def query_side_effect(*args):
        first_arg = args[0]
        arg_name = getattr(first_arg, "__name__", None)

        if arg_name == "Agent":
            return QueryStub(agent_rows)
        if arg_name == "WhatsAppMCPInstance":
            return QueryStub(whatsapp_instances, first_result=explicit_instance)
        if arg_name in {"TelegramBotInstance", "WebhookIntegration"}:
            return QueryStub([])

        return QueryStub([])

    db.query.side_effect = query_side_effect
    return FakeTenantContext(db, "tenant-graph")


def test_graph_preview_keeps_explicit_whatsapp_binding():
    explicit = make_instance(11)
    fallback = make_instance(12)
    agent = make_agent(1, enabled_channels=["playground", "whatsapp"], whatsapp_integration_id=explicit.id)
    row = (agent, "Explicit", 0, 0, 0, False)

    response = asyncio.run(get_agents_graph_preview(ctx=build_ctx([row], [explicit, fallback], explicit_instance=explicit)))
    result = response.agents[0]

    assert result.whatsapp_integration_id == explicit.id
    assert result.resolved_whatsapp_integration_id == explicit.id
    assert result.whatsapp_binding_status == "explicit"
    assert result.whatsapp_binding_source == "explicit"


def test_graph_preview_resolves_default_whatsapp_binding_when_single_active_instance():
    instance = make_instance(21)
    agent = make_agent(2, enabled_channels=["playground", "whatsapp"])
    row = (agent, "Resolved", 0, 0, 0, False)

    response = asyncio.run(get_agents_graph_preview(ctx=build_ctx([row], [instance])))
    result = response.agents[0]

    assert result.whatsapp_integration_id is None
    assert result.resolved_whatsapp_integration_id == instance.id
    assert result.whatsapp_binding_status == "resolved"
    assert result.whatsapp_binding_source == "resolved_default"


def test_graph_preview_marks_whatsapp_binding_ambiguous_when_multiple_active_instances():
    instance_a = make_instance(31)
    instance_b = make_instance(32)
    agent = make_agent(3, enabled_channels=["playground", "whatsapp"])
    row = (agent, "Ambiguous", 0, 0, 0, False)

    response = asyncio.run(get_agents_graph_preview(ctx=build_ctx([row], [instance_a, instance_b])))
    result = response.agents[0]

    assert result.resolved_whatsapp_integration_id is None
    assert result.whatsapp_binding_status == "ambiguous"
    assert result.whatsapp_binding_source == "none"


def test_graph_preview_marks_whatsapp_binding_disabled_when_channel_disabled():
    agent = make_agent(4, enabled_channels=["playground"])
    row = (agent, "Disabled", 0, 0, 0, False)

    response = asyncio.run(get_agents_graph_preview(ctx=build_ctx([row], [])))
    result = response.agents[0]

    assert result.resolved_whatsapp_integration_id is None
    assert result.whatsapp_binding_status == "disabled"
    assert result.whatsapp_binding_source == "disabled"
