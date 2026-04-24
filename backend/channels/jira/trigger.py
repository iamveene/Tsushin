"""Jira trigger adapter for normalized issue wakeups."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, ClassVar, Optional

from sqlalchemy.orm import Session

from channels.trigger import Trigger
from channels.types import HealthResult, TriggerEvent
from services.trigger_dispatch_service import TriggerDispatchInput, TriggerDispatchService


_JIRA_TZ_RE = re.compile(r"([+-]\d{2})(\d{2})$")


def _parse_jira_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        return datetime.utcnow()

    normalized = value.strip().replace("Z", "+00:00")
    normalized = _JIRA_TZ_RE.sub(r"\1:\2", normalized)
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.utcnow()


def _first_user_identifier(*users: Any) -> Optional[str]:
    for user in users:
        if not isinstance(user, dict):
            continue
        for key in ("accountId", "emailAddress", "displayName", "name"):
            value = user.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


class JiraTrigger(Trigger):
    """Normalize Jira issues and dispatch them to continuous-agent wakeups."""

    channel_type: ClassVar[str] = "jira"
    delivery_mode: ClassVar[str] = "poll"
    supports_threads: ClassVar[bool] = False
    supports_reactions: ClassVar[bool] = False
    supports_rich_formatting: ClassVar[bool] = False
    supports_media: ClassVar[bool] = False
    text_chunk_limit: ClassVar[int] = 16000

    def __init__(
        self,
        db_session: Session,
        jira_instance_id: int,
        logger: logging.Logger,
        dispatcher: Optional[TriggerDispatchService] = None,
    ) -> None:
        self.db = db_session
        self.jira_instance_id = jira_instance_id
        self.logger = logger
        self.dispatcher = dispatcher or TriggerDispatchService(db_session)

    async def start(self) -> None:
        """No persistent connection is needed for Jira polling."""
        return None

    async def stop(self) -> None:
        """No persistent connection is needed for Jira polling."""
        return None

    def _load_instance(self):
        from models import JiraChannelInstance

        return self.db.query(JiraChannelInstance).filter_by(id=self.jira_instance_id).first()

    def normalize_issue_payload(self, issue: dict[str, Any]) -> TriggerDispatchInput:
        """Convert a Jira issue payload into the dispatcher contract."""
        instance = self._load_instance()
        if instance is None:
            raise ValueError("Jira trigger instance not found")
        return self._issue_to_dispatch_input(issue, instance)

    def _issue_to_dispatch_input(self, issue: dict[str, Any], instance: Any) -> TriggerDispatchInput:
        if not isinstance(issue, dict):
            raise ValueError("Jira issue payload must be an object")

        issue_id = str(issue.get("id") or "").strip()
        issue_key = str(issue.get("key") or "").strip()
        issue_identity = issue_id or issue_key
        if not issue_identity:
            raise ValueError("Jira issue payload must include id or key")

        fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else {}
        updated = str(fields.get("updated") or issue.get("updated") or "").strip()
        dedupe_updated = updated or "unknown-updated"
        dedupe_key = f"{issue_identity}:{dedupe_updated}"
        occurred_at = _parse_jira_datetime(updated)

        payload = {
            "issue": issue,
            "jira": {
                "site_url": instance.site_url,
                "project_key": instance.project_key,
                "jql": instance.jql,
            },
        }
        sender_key = _first_user_identifier(fields.get("reporter"), fields.get("assignee"))

        return TriggerDispatchInput(
            trigger_type=self.channel_type,
            instance_id=instance.id,
            event_type="jira.issue.updated",
            dedupe_key=dedupe_key,
            payload=payload,
            occurred_at=occurred_at,
            importance="normal",
            explicit_agent_id=instance.default_agent_id,
            sender_key=sender_key or issue_key or issue_id,
            source_id=issue_key or issue_id,
        )

    async def poll_or_receive(self) -> list[TriggerEvent]:
        """Polling orchestration lives outside this thin adapter for now."""
        return []

    async def emit_wake_event(self, event: TriggerEvent) -> None:
        """Forward an already-normalized TriggerEvent through the dispatcher."""
        dispatch_input = TriggerDispatchInput(
            trigger_type=event.trigger_type,
            instance_id=event.instance_id,
            event_type=event.event_type,
            dedupe_key=event.dedupe_key,
            payload=event.payload,
            occurred_at=event.occurred_at,
            importance=event.importance,
            explicit_agent_id=event.matched_agent_id,
            sender_key=None,
            source_id=None,
        )
        self.dispatcher.dispatch(dispatch_input)

    async def emit_issue_wake_event(self, issue: dict[str, Any]):
        """Normalize and dispatch a Jira issue payload."""
        return self.dispatcher.dispatch(self.normalize_issue_payload(issue))

    async def health_check(self) -> HealthResult:
        instance = self._load_instance()
        if instance is None:
            return HealthResult(healthy=False, status="error", detail="Jira trigger not found")
        if not instance.is_active or instance.status == "paused":
            return HealthResult(healthy=False, status="paused", detail="Jira trigger paused")
        return HealthResult(
            healthy=(instance.health_status == "healthy"),
            status=instance.health_status or "unknown",
            detail=instance.health_status_reason,
        )

    def validate_recipient(self, recipient: str) -> bool:
        """Jira trigger wakeups do not have user-addressable recipients."""
        return True
