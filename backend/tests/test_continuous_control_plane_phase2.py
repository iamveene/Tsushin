from __future__ import annotations

import json
import os
import re
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path
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

from api.routes_channel_event_rules import (  # noqa: E402
    ChannelEventRuleCreate,
    ChannelEventRuleReorder,
    create_channel_event_rule,
    list_channel_event_rules,
    reorder_channel_event_rules,
)
from api import routes_continuous as continuous_routes  # noqa: E402
from api.routes_continuous import (  # noqa: E402
    ContinuousCaller,
    get_continuous_run,
    get_wake_event_payload,
    list_continuous_agents,
    list_wake_events,
)
from middleware.rate_limiter import SlidingWindowRateLimiter  # noqa: E402
from models import (  # noqa: E402
    Agent,
    Base,
    BudgetPolicy,
    ChannelEventRule,
    Contact,
    ContinuousAgent,
    ContinuousRun,
    ContinuousSubscription,
    DeliveryPolicy,
    SentinelProfile,
    SlackIntegration,
    WakeEvent,
)
from models_rbac import Tenant, User  # noqa: E402
from services.continuous_agent_service import (  # noqa: E402
    BudgetDecision,
    BudgetKind,
    ContinuousBudgetLimiter,
)
from services.api_client_service import API_ROLE_SCOPES  # noqa: E402


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Tenant.__table__,
            User.__table__,
            Contact.__table__,
            Agent.__table__,
            SentinelProfile.__table__,
            DeliveryPolicy.__table__,
            BudgetPolicy.__table__,
            ContinuousAgent.__table__,
            ContinuousSubscription.__table__,
            WakeEvent.__table__,
            ContinuousRun.__table__,
            SlackIntegration.__table__,
            ChannelEventRule.__table__,
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


def _seed_tenant_user_agent(db, *, tenant_id: str, user_id: int, agent_id: int, contact_id: int):
    db.add(Tenant(id=tenant_id, name=tenant_id.title(), slug=tenant_id))
    db.add(User(id=user_id, tenant_id=tenant_id, email=f"{tenant_id}@example.com", password_hash="x", is_active=True))
    db.add(Contact(id=contact_id, tenant_id=tenant_id, friendly_name=f"Agent {tenant_id}", role="agent"))
    db.add(
        Agent(
            id=agent_id,
            tenant_id=tenant_id,
            contact_id=contact_id,
            system_prompt="prompt",
            model_provider="gemini",
            model_name="gemini-2.5-pro",
            response_template="{response}",
            is_active=True,
        )
    )


def _seed_continuous_agent(db, *, tenant_id: str, agent_id: int, continuous_agent_id: int):
    delivery = DeliveryPolicy(tenant_id=tenant_id, name=f"delivery-{tenant_id}")
    budget = BudgetPolicy(tenant_id=tenant_id, name=f"budget-{tenant_id}", max_runs_per_day=2, on_exhaustion="pause")
    db.add_all([delivery, budget])
    db.flush()
    ca = ContinuousAgent(
        id=continuous_agent_id,
        tenant_id=tenant_id,
        agent_id=agent_id,
        name=f"CA {tenant_id}",
        execution_mode="hybrid",
        delivery_policy_id=delivery.id,
        budget_policy_id=budget.id,
        status="active",
    )
    db.add(ca)
    db.flush()
    return ca


def test_read_only_continuous_apis_are_tenant_scoped_and_paginated(db_session):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, agent_id=101, contact_id=201)
    _seed_tenant_user_agent(db_session, tenant_id="tenant-b", user_id=2, agent_id=102, contact_id=202)
    ca_a = _seed_continuous_agent(db_session, tenant_id="tenant-a", agent_id=101, continuous_agent_id=301)
    ca_b = _seed_continuous_agent(db_session, tenant_id="tenant-b", agent_id=102, continuous_agent_id=302)

    for idx in range(55):
        db_session.add(
            WakeEvent(
                tenant_id="tenant-a",
                continuous_agent_id=ca_a.id,
                channel_type="email",
                channel_instance_id=1,
                event_type="message.new",
                occurred_at=datetime.utcnow() + timedelta(seconds=idx),
                dedupe_key=f"a-{idx}",
                payload_ref=f"backend/data/wake_events/a-{idx}.json",
            )
        )
    foreign_run = ContinuousRun(
        tenant_id="tenant-b",
        continuous_agent_id=ca_b.id,
        wake_event_ids=[],
        execution_mode="hybrid",
        status="queued",
    )
    db_session.add(foreign_run)
    db_session.commit()

    caller = ContinuousCaller(tenant_id="tenant-a", user_id=1)
    agents_page = list_continuous_agents(
        limit=10,
        offset=0,
        status_filter=None,
        caller=caller,
        db=db_session,
    )
    events_page = list_wake_events(
        limit=50,
        offset=50,
        status_filter=None,
        channel_type=None,
        channel_instance_id=None,
        occurred_after=None,
        occurred_before=None,
        caller=caller,
        db=db_session,
    )

    assert agents_page.total == 1
    assert agents_page.items[0].agent_name == "Agent tenant-a"
    assert events_page.total == 55
    assert events_page.limit == 50
    assert events_page.offset == 50
    assert len(events_page.items) == 5
    assert all(item.payload_ref and not hasattr(item, "payload") for item in events_page.items)

    with pytest.raises(HTTPException) as exc_info:
        get_continuous_run(continuous_run_id=foreign_run.id, caller=caller, db=db_session)
    assert exc_info.value.status_code == 403


def test_wake_events_filter_by_occurred_window(db_session):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, agent_id=101, contact_id=201)
    ca = _seed_continuous_agent(db_session, tenant_id="tenant-a", agent_id=101, continuous_agent_id=301)
    base = datetime(2026, 4, 24, 12, 0, 0)
    for idx, occurred_at in enumerate((base, base + timedelta(hours=1), base + timedelta(hours=2))):
        db_session.add(
            WakeEvent(
                tenant_id="tenant-a",
                continuous_agent_id=ca.id,
                channel_type="email",
                channel_instance_id=7,
                event_type="message.new",
                occurred_at=occurred_at,
                dedupe_key=f"window-{idx}",
                payload_ref=f"backend/data/wake_events/window-{idx}.json",
            )
        )
    db_session.commit()

    page = list_wake_events(
        limit=50,
        offset=0,
        status_filter=None,
        channel_type="email",
        channel_instance_id=7,
        occurred_after=base + timedelta(minutes=30),
        occurred_before=base + timedelta(minutes=90),
        caller=ContinuousCaller(tenant_id="tenant-a", user_id=1),
        db=db_session,
    )

    assert page.total == 1
    assert page.items[0].dedupe_key == "window-1"


def test_wake_event_payload_endpoint_enforces_tenant_and_safe_path(db_session, tmp_path, monkeypatch):
    payload_root = tmp_path / "backend" / "data" / "wake_events"
    payload_root.mkdir(parents=True)
    monkeypatch.setattr(continuous_routes, "WAKE_EVENT_PAYLOAD_ROOT", payload_root.resolve())

    (payload_root / "good.json").write_text(
        json.dumps({"payload": {"subject": "Hello", "token": "[REDACTED]"}}),
        encoding="utf-8",
    )
    secret_path = tmp_path / "backend" / "data" / "secret.json"
    secret_path.write_text(json.dumps({"token": "must-not-read"}), encoding="utf-8")

    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, agent_id=101, contact_id=201)
    _seed_tenant_user_agent(db_session, tenant_id="tenant-b", user_id=2, agent_id=102, contact_id=202)
    ca_a = _seed_continuous_agent(db_session, tenant_id="tenant-a", agent_id=101, continuous_agent_id=301)
    ca_b = _seed_continuous_agent(db_session, tenant_id="tenant-b", agent_id=102, continuous_agent_id=302)

    good = WakeEvent(
        tenant_id="tenant-a",
        continuous_agent_id=ca_a.id,
        channel_type="email",
        channel_instance_id=1,
        event_type="message.new",
        occurred_at=datetime.utcnow(),
        dedupe_key="good",
        payload_ref="backend/data/wake_events/good.json",
    )
    missing_ref = WakeEvent(
        tenant_id="tenant-a",
        continuous_agent_id=ca_a.id,
        channel_type="email",
        channel_instance_id=1,
        event_type="message.new",
        occurred_at=datetime.utcnow(),
        dedupe_key="missing-ref",
        payload_ref=None,
    )
    missing_file = WakeEvent(
        tenant_id="tenant-a",
        continuous_agent_id=ca_a.id,
        channel_type="email",
        channel_instance_id=1,
        event_type="message.new",
        occurred_at=datetime.utcnow(),
        dedupe_key="missing-file",
        payload_ref="backend/data/wake_events/missing.json",
    )
    unsafe_ref = WakeEvent(
        tenant_id="tenant-a",
        continuous_agent_id=ca_a.id,
        channel_type="email",
        channel_instance_id=1,
        event_type="message.new",
        occurred_at=datetime.utcnow(),
        dedupe_key="unsafe",
        payload_ref="backend/data/wake_events/../secret.json",
    )
    foreign = WakeEvent(
        tenant_id="tenant-b",
        continuous_agent_id=ca_b.id,
        channel_type="email",
        channel_instance_id=1,
        event_type="message.new",
        occurred_at=datetime.utcnow(),
        dedupe_key="foreign",
        payload_ref="backend/data/wake_events/good.json",
    )
    db_session.add_all([good, missing_ref, missing_file, unsafe_ref, foreign])
    db_session.commit()

    caller = ContinuousCaller(tenant_id="tenant-a", user_id=1)
    response = get_wake_event_payload(wake_event_id=good.id, caller=caller, db=db_session)
    assert response.payload_ref == "backend/data/wake_events/good.json"
    assert response.payload["payload"]["token"] == "[REDACTED]"

    with pytest.raises(HTTPException) as missing_ref_exc:
        get_wake_event_payload(wake_event_id=missing_ref.id, caller=caller, db=db_session)
    assert missing_ref_exc.value.status_code == 404

    with pytest.raises(HTTPException) as missing_file_exc:
        get_wake_event_payload(wake_event_id=missing_file.id, caller=caller, db=db_session)
    assert missing_file_exc.value.status_code == 410

    with pytest.raises(HTTPException) as unsafe_exc:
        get_wake_event_payload(wake_event_id=unsafe_ref.id, caller=caller, db=db_session)
    assert unsafe_exc.value.status_code == 404

    with pytest.raises(HTTPException) as foreign_exc:
        get_wake_event_payload(wake_event_id=foreign.id, caller=caller, db=db_session)
    assert foreign_exc.value.status_code == 403


def test_budget_limiter_keys_by_budget_kind():
    limiter = ContinuousBudgetLimiter(SlidingWindowRateLimiter())
    policy = BudgetPolicy(
        tenant_id="tenant-a",
        name="Daily",
        max_runs_per_day=1,
        max_tool_invocations_per_day=1,
        on_exhaustion="degrade_to_hybrid",
    )

    first_run = limiter.check(
        tenant_id="tenant-a",
        continuous_agent_id=1,
        policy=policy,
        budget_kind=BudgetKind.RUN,
    )
    second_run = limiter.check(
        tenant_id="tenant-a",
        continuous_agent_id=1,
        policy=policy,
        budget_kind=BudgetKind.RUN,
    )
    first_tool = limiter.check(
        tenant_id="tenant-a",
        continuous_agent_id=1,
        policy=policy,
        budget_kind=BudgetKind.TOOL_INVOCATION,
    )

    assert first_run.allowed is True
    assert second_run.allowed is False
    assert second_run.decision == BudgetDecision.DEGRADE_TO_HYBRID
    assert first_tool.allowed is True


def test_api_client_roles_can_read_watcher_continuous_surfaces():
    for role in ("api_readonly", "api_member", "api_admin", "api_owner"):
        assert "watcher.read" in API_ROLE_SCOPES[role]


def test_channel_event_rule_create_validates_instance_and_agent_tenant(db_session):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, agent_id=101, contact_id=201)
    _seed_tenant_user_agent(db_session, tenant_id="tenant-b", user_id=2, agent_id=102, contact_id=202)
    slack_a = SlackIntegration(
        id=401,
        tenant_id="tenant-a",
        workspace_id="T-A",
        workspace_name="A",
        bot_token_encrypted="secret",
    )
    slack_b = SlackIntegration(
        id=402,
        tenant_id="tenant-b",
        workspace_id="T-B",
        workspace_name="B",
        bot_token_encrypted="secret",
    )
    db_session.add_all([slack_a, slack_b])
    db_session.commit()

    created = create_channel_event_rule(
        channel_type="slack",
        instance_id=slack_a.id,
        payload=ChannelEventRuleCreate(
            event_type="message.channels",
            criteria={"text_contains": "urgent"},
            priority=10,
            agent_id=101,
        ),
        ctx=_ctx("tenant-a"),
        current_user=SimpleNamespace(id=1),
        db=db_session,
    )
    listed = list_channel_event_rules(
        channel_type="slack",
        instance_id=slack_a.id,
        limit=50,
        offset=0,
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    assert created.channel_type == "slack"
    assert created.criteria == {"text_contains": "urgent"}
    assert listed.total == 1

    with pytest.raises(HTTPException) as exc_info:
        create_channel_event_rule(
            channel_type="slack",
            instance_id=slack_b.id,
            payload=ChannelEventRuleCreate(criteria={}, priority=20, agent_id=101),
            ctx=_ctx("tenant-a"),
            current_user=SimpleNamespace(id=1),
            db=db_session,
        )
    assert exc_info.value.status_code == 403

    with pytest.raises(HTTPException) as exc_info:
        create_channel_event_rule(
            channel_type="slack",
            instance_id=slack_a.id,
            payload=ChannelEventRuleCreate(criteria={}, priority=20, agent_id=102),
            ctx=_ctx("tenant-a"),
            current_user=SimpleNamespace(id=1),
            db=db_session,
        )
    assert exc_info.value.status_code == 403


def test_channel_event_rule_reorder_validates_full_tenant_scoped_rule_set(db_session):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, agent_id=101, contact_id=201)
    _seed_tenant_user_agent(db_session, tenant_id="tenant-b", user_id=2, agent_id=102, contact_id=202)
    slack_a = SlackIntegration(
        id=401,
        tenant_id="tenant-a",
        workspace_id="T-A",
        workspace_name="A",
        bot_token_encrypted="secret",
    )
    slack_a_other = SlackIntegration(
        id=403,
        tenant_id="tenant-a",
        workspace_id="T-A2",
        workspace_name="A2",
        bot_token_encrypted="secret",
    )
    slack_b = SlackIntegration(
        id=402,
        tenant_id="tenant-b",
        workspace_id="T-B",
        workspace_name="B",
        bot_token_encrypted="secret",
    )
    db_session.add_all([slack_a, slack_a_other, slack_b])
    db_session.add_all(
        [
            ChannelEventRule(
                id=501,
                tenant_id="tenant-a",
                channel_type="slack",
                channel_instance_id=slack_a.id,
                event_type="message",
                criteria={"contains": "one"},
                priority=10,
                agent_id=101,
            ),
            ChannelEventRule(
                id=502,
                tenant_id="tenant-a",
                channel_type="slack",
                channel_instance_id=slack_a.id,
                event_type="message",
                criteria={"contains": "two"},
                priority=20,
                agent_id=101,
            ),
            ChannelEventRule(
                id=503,
                tenant_id="tenant-a",
                channel_type="slack",
                channel_instance_id=slack_a.id,
                event_type="message",
                criteria={"contains": "three"},
                priority=30,
                agent_id=101,
            ),
            ChannelEventRule(
                id=504,
                tenant_id="tenant-a",
                channel_type="slack",
                channel_instance_id=slack_a_other.id,
                event_type="message",
                criteria={},
                priority=10,
                agent_id=101,
            ),
            ChannelEventRule(
                id=601,
                tenant_id="tenant-b",
                channel_type="slack",
                channel_instance_id=slack_b.id,
                event_type="message",
                criteria={},
                priority=10,
                agent_id=102,
            ),
        ]
    )
    db_session.commit()

    reordered = reorder_channel_event_rules(
        channel_type="slack",
        instance_id=slack_a.id,
        payload=ChannelEventRuleReorder(rule_ids=[503, 501, 502]),
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    assert [item.id for item in reordered.items] == [503, 501, 502]
    assert [item.priority for item in reordered.items] == [10, 20, 30]

    listed = list_channel_event_rules(
        channel_type="slack",
        instance_id=slack_a.id,
        limit=50,
        offset=0,
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )
    assert [item.id for item in listed.items] == [503, 501, 502]

    with pytest.raises(HTTPException) as exc_info:
        reorder_channel_event_rules(
            channel_type="slack",
            instance_id=slack_a.id,
            payload=ChannelEventRuleReorder(rule_ids=[503, 503, 502]),
            ctx=_ctx("tenant-a"),
            _user=SimpleNamespace(id=1),
            db=db_session,
        )
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info:
        reorder_channel_event_rules(
            channel_type="slack",
            instance_id=slack_a.id,
            payload=ChannelEventRuleReorder(rule_ids=[503, 501]),
            ctx=_ctx("tenant-a"),
            _user=SimpleNamespace(id=1),
            db=db_session,
        )
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info:
        reorder_channel_event_rules(
            channel_type="slack",
            instance_id=slack_a.id,
            payload=ChannelEventRuleReorder(rule_ids=[503, 501, 504]),
            ctx=_ctx("tenant-a"),
            _user=SimpleNamespace(id=1),
            db=db_session,
        )
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info:
        reorder_channel_event_rules(
            channel_type="slack",
            instance_id=slack_a.id,
            payload=ChannelEventRuleReorder(rule_ids=[503, 501, 601]),
            ctx=_ctx("tenant-a"),
            _user=SimpleNamespace(id=1),
            db=db_session,
        )
    assert exc_info.value.status_code == 403


def test_channel_event_rule_api_is_channel_only(db_session):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, agent_id=101, contact_id=201)

    with pytest.raises(HTTPException) as exc_info:
        list_channel_event_rules(
            channel_type="email",
            instance_id=1,
            limit=50,
            offset=0,
            ctx=_ctx("tenant-a"),
            _user=SimpleNamespace(id=1),
            db=db_session,
        )
    assert exc_info.value.status_code == 404


def test_a2_migration_chain_is_linear_from_current_head():
    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"

    def load_revision(filename: str):
        text = (versions / filename).read_text()
        revision = re.search(r'revision:\s*str\s*=\s*"([^"]+)"', text)
        down_revision = re.search(r'down_revision:\s*Union\[str,\s*None\]\s*=\s*"([^"]+)"', text)
        assert revision is not None
        assert down_revision is not None
        return revision.group(1), down_revision.group(1)

    assert load_revision("0047_add_continuous_agent_models.py") == ("0047", "0059")
    assert load_revision("0050_add_channel_event_rule.py") == ("0050", "0047")
