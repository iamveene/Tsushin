"""Managed Email triage helpers for v0.7.0 continuous agents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from email.utils import getaddresses
from typing import Any, Optional

from sqlalchemy.orm import Session

from hub.google.gmail_service import GMAIL_DRAFT_COMPATIBLE_SCOPES
from models import (
    ContinuousAgent,
    ContinuousSubscription,
    EmailChannelInstance,
    GmailIntegration,
    OAuthToken,
)
from services.default_agent_service import get_default_agent


EMAIL_TRIAGE_EVENT_TYPE = "email.message.received"
_INACTIVE_GMAIL_HEALTH = {"disconnected", "unavailable", "unhealthy"}


@dataclass(frozen=True)
class EmailTriageSubscription:
    """IDs created or reused for the managed Email triage flow."""

    email_trigger_id: int
    continuous_agent_id: int
    continuous_subscription_id: int
    agent_id: int
    created_agent: bool
    created_subscription: bool


def ensure_email_triage_subscription(
    db: Session,
    *,
    tenant_id: str,
    email_trigger_id: int,
) -> EmailTriageSubscription:
    """Create or reuse the system-owned Email triage continuous linkage."""

    trigger = (
        db.query(EmailChannelInstance)
        .filter(
            EmailChannelInstance.id == email_trigger_id,
            EmailChannelInstance.tenant_id == tenant_id,
        )
        .first()
    )
    if trigger is None:
        raise ValueError("email_trigger_not_found")

    _validate_triage_gmail_integration(db, tenant_id=tenant_id, trigger=trigger)

    agent_id = get_default_agent(db, tenant_id, "email", instance_id=trigger.id)
    if agent_id is None:
        raise ValueError("missing_default_agent")

    managed_name = f"Email Triage: {trigger.integration_name}"
    continuous_agent = (
        db.query(ContinuousAgent)
        .filter(
            ContinuousAgent.tenant_id == tenant_id,
            ContinuousAgent.agent_id == agent_id,
            ContinuousAgent.name == managed_name,
            ContinuousAgent.is_system_owned == True,  # noqa: E712
        )
        .first()
    )
    created_agent = continuous_agent is None
    if continuous_agent is None:
        continuous_agent = ContinuousAgent(
            tenant_id=tenant_id,
            agent_id=agent_id,
            name=managed_name,
            execution_mode="hybrid",
            status="active",
            is_system_owned=True,
        )
        db.add(continuous_agent)
        db.flush()
    elif continuous_agent.status != "active":
        continuous_agent.status = "active"

    subscription = (
        db.query(ContinuousSubscription)
        .filter(
            ContinuousSubscription.tenant_id == tenant_id,
            ContinuousSubscription.continuous_agent_id == continuous_agent.id,
            ContinuousSubscription.channel_type == "email",
            ContinuousSubscription.channel_instance_id == trigger.id,
            ContinuousSubscription.event_type == EMAIL_TRIAGE_EVENT_TYPE,
            ContinuousSubscription.is_system_owned == True,  # noqa: E712
        )
        .first()
    )
    created_subscription = subscription is None
    if subscription is None:
        subscription = ContinuousSubscription(
            tenant_id=tenant_id,
            continuous_agent_id=continuous_agent.id,
            channel_type="email",
            channel_instance_id=trigger.id,
            event_type=EMAIL_TRIAGE_EVENT_TYPE,
            status="active",
            is_system_owned=True,
        )
        db.add(subscription)
        db.flush()
    elif subscription.status != "active":
        subscription.status = "active"

    db.commit()
    db.refresh(continuous_agent)
    db.refresh(subscription)
    return EmailTriageSubscription(
        email_trigger_id=trigger.id,
        continuous_agent_id=continuous_agent.id,
        continuous_subscription_id=subscription.id,
        agent_id=agent_id,
        created_agent=created_agent,
        created_subscription=created_subscription,
    )


def _validate_triage_gmail_integration(
    db: Session,
    *,
    tenant_id: str,
    trigger: EmailChannelInstance,
) -> None:
    """Fail closed before enabling managed triage for a Gmail trigger."""

    if trigger.provider != "gmail":
        raise ValueError("unsupported_email_provider")
    if not trigger.gmail_integration_id:
        raise ValueError("missing_gmail_integration")

    integration = (
        db.query(GmailIntegration)
        .filter(GmailIntegration.id == trigger.gmail_integration_id)
        .first()
    )
    if integration is None:
        raise ValueError("gmail_integration_not_found")
    if integration.tenant_id != tenant_id:
        raise ValueError("gmail_integration_tenant_mismatch")
    if integration.type != "gmail":
        raise ValueError("gmail_integration_type_mismatch")
    if not integration.is_active or (integration.health_status or "").lower() in _INACTIVE_GMAIL_HEALTH:
        raise ValueError("gmail_integration_inactive")

    token = (
        db.query(OAuthToken)
        .filter(OAuthToken.integration_id == integration.id)
        .order_by(OAuthToken.created_at.desc())
        .first()
    )
    if token is None:
        raise ValueError("gmail_integration_missing_token")
    token_scopes = set((token.scope or "").split())
    if not (token_scopes & GMAIL_DRAFT_COMPATIBLE_SCOPES):
        raise ValueError("gmail_integration_missing_draft_scope")


def _first_address(value: Any) -> Optional[str]:
    addresses = getaddresses([str(value or "")])
    for _, address in addresses:
        address = address.strip()
        if address:
            return address
    return None


def _reply_subject(subject: Any) -> str:
    value = str(subject or "").strip() or "(No Subject)"
    return value if value.lower().startswith("re:") else f"Re: {value}"


def build_triage_draft_arguments(email_payload: dict[str, Any]) -> dict[str, Any]:
    """Build a conservative draft response from a fetched Gmail message."""

    message = email_payload.get("message") if isinstance(email_payload.get("message"), dict) else email_payload
    recipient = _first_address(message.get("from"))
    if not recipient:
        raise ValueError("email_payload_missing_sender")

    subject = _reply_subject(message.get("subject"))
    body_text = str(message.get("body_text") or message.get("snippet") or "").strip()
    if len(body_text) > 1200:
        body_text = body_text[:1200] + "..."
    draft_body = (
        "Thanks for your email. I am reviewing this and will follow up shortly.\n\n"
        "---\n"
        "Context captured by Tsushin Email Triage:\n"
        f"Subject: {message.get('subject') or '(No Subject)'}\n"
        f"From: {message.get('from') or 'Unknown'}\n"
        f"Preview: {body_text or message.get('snippet') or '(No preview available)'}"
    )
    return {
        "action": "draft",
        "to": [recipient],
        "subject": subject,
        "body": draft_body,
    }


async def create_triage_draft(
    db: Session,
    *,
    trigger: EmailChannelInstance,
    continuous_agent: ContinuousAgent,
    email_payload: dict[str, Any],
    sender_key: Optional[str] = None,
) -> dict[str, Any]:
    """Create a Gmail draft through GmailSkill so Sentinel approval applies."""

    if not trigger.gmail_integration_id:
        raise ValueError("email_trigger_missing_gmail_integration")

    from agent.skills.base import InboundMessage
    from agent.skills.gmail_skill import GmailSkill

    skill = GmailSkill()
    skill.set_db_session(db)
    message_body = email_payload.get("message") if isinstance(email_payload.get("message"), dict) else {}
    message_id = message_body.get("id") or email_payload.get("message_id") or email_payload.get("id") or "email-triage"
    message = InboundMessage(
        id=str(message_id),
        sender=sender_key or "email-triage",
        sender_key=sender_key or "email-triage",
        body="Create an Email Triage draft response.",
        chat_id=f"email-trigger:{trigger.id}",
        chat_name=trigger.integration_name,
        is_group=False,
        timestamp=datetime.utcnow(),
        channel="email",
    )
    result = await skill.execute_tool(
        build_triage_draft_arguments(email_payload),
        message,
        {
            "integration_id": trigger.gmail_integration_id,
            "continuous_agent_context": {
                "tenant_id": trigger.tenant_id,
                "agent_id": continuous_agent.agent_id,
                "sender_key": sender_key,
                "mode": continuous_agent.execution_mode,
                "continuous_agent_id": continuous_agent.id,
            },
        },
    )
    return {
        "success": result.success,
        "output": result.output,
        "metadata": result.metadata,
    }
