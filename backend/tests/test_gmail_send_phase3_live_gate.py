"""
Phase 3.1 live Gmail outbound gate tests.

These tests are intentionally pointed at the real Phase 0.5 Gmail fixture
account. They prove:
- direct GmailService send works and lands in Sent
- direct GmailService reply works in-thread
- GmailSkill's agent tool send path works against the live integration
- draft creation is proven only after the live fixture has gmail.compose,
  gmail.modify, or mail.google.com/
- an optional full API/agent-chat proof sends through the public chat endpoint
"""

import asyncio
import os
import sys
import types
from uuid import uuid4

import pytest

if os.getenv("TSN_RUN_GMAIL_PHASE3_LIVE_GATE") != "1":
    pytest.skip(
        "Phase 3.1 Gmail live gate is root-only. Set "
        "TSN_RUN_GMAIL_PHASE3_LIVE_GATE=1 after manual OAuth reauthorization.",
        allow_module_level=True,
    )

import httpx
from sqlalchemy.orm import sessionmaker


BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

docker_stub = types.ModuleType("docker")
docker_stub.errors = types.SimpleNamespace(NotFound=Exception, DockerException=Exception)
docker_stub.DockerClient = object
sys.modules.setdefault("docker", docker_stub)

import settings
from agent.skills.gmail_skill import GmailSkill
from db import get_engine
from hub.google.gmail_service import (
    GMAIL_DRAFT_COMPATIBLE_SCOPES,
    GmailService,
)
from models import Agent, AgentSkill, AgentSkillIntegration, Contact


def _run(coro):
    return asyncio.run(coro)


async def _wait_for_search(service: GmailService, query: str, attempts: int = 15, delay: float = 1.0):
    for _ in range(attempts):
        messages = await service.search_messages(query, max_results=10)
        if messages:
            return messages
        await asyncio.sleep(delay)
    return []


async def _wait_for_thread_messages(
    service: GmailService,
    thread_id: str,
    *,
    min_messages: int,
    attempts: int = 10,
    delay: float = 1.0,
):
    for _ in range(attempts):
        thread = await service.get_thread(thread_id)
        if len(thread.get("messages", [])) >= min_messages:
            return thread
        await asyncio.sleep(delay)
    return await service.get_thread(thread_id)


def _required_env(name: str) -> str:
    value = os.getenv(name)
    assert value, f"{name} must be set for this root-only live gate."
    return value


@pytest.fixture(scope="module")
def live_db_session():
    if not settings.DATABASE_URL.startswith("postgresql"):
        raise RuntimeError(
            "Phase 3.1 live Gmail gate must run against the shared PostgreSQL runtime, "
            f"but DATABASE_URL resolved to {settings.DATABASE_URL!r}."
        )

    engine = get_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(scope="module")
def live_gmail_service(live_db_session, gmail_oauth_fixture):
    return GmailService(live_db_session, gmail_oauth_fixture["integration_id"])


@pytest.fixture
def live_gmail_agent(live_db_session, gmail_oauth_fixture):
    suffix = uuid4().hex[:10]
    contact = Contact(
        friendly_name=f"gmail-live-gate-{suffix}",
        role="agent",
        tenant_id=gmail_oauth_fixture["tenant_id"],
        is_active=True,
    )
    live_db_session.add(contact)
    live_db_session.flush()

    agent = Agent(
        contact_id=contact.id,
        system_prompt="You are a test-only Gmail live gate agent.",
        tenant_id=gmail_oauth_fixture["tenant_id"],
        model_provider="openai",
        model_name="gpt-4o-mini",
        enabled_channels=["playground"],
        enable_semantic_search=False,
        is_active=True,
    )
    live_db_session.add(agent)
    live_db_session.flush()

    skill = AgentSkill(
        agent_id=agent.id,
        skill_type="gmail",
        is_enabled=True,
        config={},
    )
    skill_integration = AgentSkillIntegration(
        agent_id=agent.id,
        skill_type="gmail",
        integration_id=gmail_oauth_fixture["integration_id"],
        config={},
    )
    live_db_session.add_all([skill, skill_integration])
    live_db_session.commit()

    try:
        yield agent
    finally:
        live_db_session.query(AgentSkillIntegration).filter(
            AgentSkillIntegration.agent_id == agent.id,
            AgentSkillIntegration.skill_type == "gmail",
        ).delete()
        live_db_session.query(AgentSkill).filter(
            AgentSkill.agent_id == agent.id,
            AgentSkill.skill_type == "gmail",
        ).delete()
        live_db_session.query(Agent).filter(Agent.id == agent.id).delete()
        live_db_session.query(Contact).filter(Contact.id == contact.id).delete()
        live_db_session.commit()


def test_gmail_live_service_send_reply_and_sent_visibility(live_gmail_service, gmail_oauth_fixture):
    assert live_gmail_service.can_send_messages() is True

    subject = f"Tsushin Phase 3.1 live send {uuid4().hex[:10]}"
    send_response = _run(
        live_gmail_service.send_message(
            to=gmail_oauth_fixture["email"],
            subject=subject,
            body_text="Phase 3.1 direct GmailService send proof.",
        )
    )
    assert send_response.get("id"), "GmailService.send_message did not return a live Gmail message id"

    sent_messages = _run(_wait_for_search(live_gmail_service, f'in:sent subject:"{subject}"'))
    assert sent_messages, "Sent mailbox did not surface the direct GmailService send"

    reply_response = _run(
        live_gmail_service.reply_to_message(
            sent_messages[0]["id"],
            body_text="Phase 3.1 direct GmailService reply proof.",
        )
    )
    assert reply_response.get("id"), "GmailService.reply_to_message did not return a live Gmail message id"

    thread = _run(
        _wait_for_thread_messages(
            live_gmail_service,
            reply_response.get("threadId") or send_response.get("threadId"),
            min_messages=2,
        )
    )
    assert len(thread.get("messages", [])) >= 2


def test_gmail_live_agent_send_path_and_sent_visibility(
    live_db_session,
    live_gmail_service,
    gmail_oauth_fixture,
    live_gmail_agent,
):
    skill = GmailSkill()
    skill.set_db_session(live_db_session)
    skill._agent_id = live_gmail_agent.id

    subject = f"Tsushin Phase 3.1 live agent {uuid4().hex[:10]}"
    result = _run(
        skill.execute_tool(
            {
                "action": "send",
                "to": gmail_oauth_fixture["email"],
                "subject": subject,
                "body": "Phase 3.1 GmailSkill live send proof.",
            },
            message=None,
            config=skill.get_default_config(),
        )
    )

    assert result.success is True
    assert result.metadata["action"] == "send"
    assert result.metadata["message_id"]

    sent_messages = _run(_wait_for_search(live_gmail_service, f'in:sent subject:"{subject}"'))
    assert sent_messages, "Sent mailbox did not surface the GmailSkill send"


def test_gmail_live_draft_behavior_matches_live_scopes(live_gmail_service, gmail_oauth_fixture):
    subject = f"Tsushin Phase 3.1 live draft {uuid4().hex[:10]}"
    scopes = set(gmail_oauth_fixture["scopes"])
    has_live_draft_scope = bool(scopes & GMAIL_DRAFT_COMPATIBLE_SCOPES)

    assert has_live_draft_scope, (
        "Phase 3.1 Gmail live gate requires gmail.compose, gmail.modify, or "
        "mail.google.com/. Re-authorize the fixture before treating this gate "
        "as green."
    )
    assert live_gmail_service.can_create_drafts() is True

    response = _run(
        live_gmail_service.create_draft(
            to=gmail_oauth_fixture["email"],
            subject=subject,
            body_text="Phase 3.1 GmailService live draft proof.",
        )
    )
    assert response.get("id"), "GmailService.create_draft did not return a draft id"

    draft_messages = _run(_wait_for_search(live_gmail_service, f'in:drafts subject:"{subject}"'))
    assert draft_messages, "Draft mailbox did not surface the live GmailService draft"


@pytest.mark.skipif(
    os.getenv("TSN_RUN_GMAIL_AGENT_CHAT_LIVE_GATE") != "1",
    reason=(
        "Set TSN_RUN_GMAIL_AGENT_CHAT_LIVE_GATE=1 plus "
        "TSN_GMAIL_AGENT_CHAT_BASE_URL, TSN_GMAIL_AGENT_CHAT_API_TOKEN, and "
        "TSN_GMAIL_AGENT_CHAT_AGENT_ID for the root-only full API/agent-chat proof."
    ),
)
def test_gmail_live_agent_chat_api_sends_and_sent_visibility(live_gmail_service, gmail_oauth_fixture):
    base_url = _required_env("TSN_GMAIL_AGENT_CHAT_BASE_URL").rstrip("/")
    api_token = _required_env("TSN_GMAIL_AGENT_CHAT_API_TOKEN")
    agent_id = _required_env("TSN_GMAIL_AGENT_CHAT_AGENT_ID")
    subject = f"Tsushin Phase 3.1 live agent-chat {uuid4().hex[:10]}"

    response = httpx.post(
        f"{base_url}/api/v1/agents/{agent_id}/chat",
        headers={"Authorization": f"Bearer {api_token}"},
        json={
            "message": (
                "Use the Gmail tool to send an email now, not a draft, to "
                f"{gmail_oauth_fixture['email']} with subject \"{subject}\" "
                "and body \"Phase 3.1 full API agent-chat Gmail send proof.\""
            )
        },
        timeout=120.0,
    )
    response.raise_for_status()
    payload = response.json()
    assert payload.get("status") == "success", payload

    sent_messages = _run(_wait_for_search(live_gmail_service, f'in:sent subject:"{subject}"'))
    assert sent_messages, "Sent mailbox did not surface the full API agent-chat send"
