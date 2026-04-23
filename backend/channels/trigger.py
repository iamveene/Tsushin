"""Trigger entry-point base contract."""

from __future__ import annotations

from abc import abstractmethod
from typing import Optional

from channels.base import EntryPoint
from channels.types import TriggerEvent


class Trigger(EntryPoint):
    """Event-driven entry point such as webhook/email/schedule."""

    @abstractmethod
    async def poll_or_receive(self) -> list[TriggerEvent]:
        """Fetch or receive one or more trigger events."""

    @abstractmethod
    async def emit_wake_event(self, event: TriggerEvent) -> None:
        """Persist or forward a normalized trigger event."""

    async def notify_external_system(self, result: dict) -> Optional[dict]:
        """Optional outbound callback for non-conversational triggers."""
        return None
