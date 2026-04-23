from __future__ import annotations

import asyncio

from channels.base import Channel, ChannelAdapter
from channels.dispatch import dispatch_outbound
from channels.registry import ChannelRegistry
from channels.trigger import Trigger
from channels.types import HealthResult, SendResult, TriggerEvent


class FakeChannel(Channel):
    channel_type = "fake-channel"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def health_check(self) -> HealthResult:
        return HealthResult(healthy=True, status="ok")

    async def send_message(self, to: str, text: str, *, media_path=None, **kwargs) -> SendResult:
        self.calls.append(
            {"to": to, "text": text, "media_path": media_path, "kwargs": kwargs}
        )
        return SendResult(success=True, message_id="msg-1")


class FakeTrigger(Trigger):
    channel_type = "fake-trigger"

    def __init__(self) -> None:
        self.notifications: list[dict] = []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def health_check(self) -> HealthResult:
        return HealthResult(healthy=True, status="ok")

    async def poll_or_receive(self) -> list[TriggerEvent]:
        return []

    async def emit_wake_event(self, event: TriggerEvent) -> None:
        return None

    async def notify_external_system(self, result: dict):
        self.notifications.append(result)
        return {"success": True, "message_id": "whk-1"}


def test_dispatch_outbound_sends_via_channel_or_trigger():
    channel = FakeChannel()
    trigger = FakeTrigger()

    async def _run():
        channel_result = await dispatch_outbound(
            channel,
            recipient="C123",
            message_text="hello",
            agent_id=42,
            thread_ts="123.456",
        )
        trigger_result = await dispatch_outbound(
            trigger,
            recipient="ignored",
            message_text="callback body",
            agent_id=77,
        )
        return channel_result, trigger_result

    channel_result, trigger_result = asyncio.run(_run())

    assert channel_result.success is True
    assert trigger_result["success"] is True
    assert channel.calls == [
        {
            "to": "C123",
            "text": "hello",
            "media_path": None,
            "kwargs": {"agent_id": 42, "thread_ts": "123.456"},
        }
    ]
    assert trigger.notifications == [
        {"to": "ignored", "text": "callback body", "media_path": None, "agent_id": 77}
    ]


def test_channel_registry_separates_channels_and_triggers():
    registry = ChannelRegistry()
    registry.register("playground", FakeChannel())
    registry.register("webhook", FakeTrigger())

    assert ChannelAdapter is Channel
    assert registry.list_channels() == ["playground"]
    assert registry.list_triggers() == ["webhook"]
    assert registry.has_channel("playground") is True
    assert registry.has_channel("webhook") is False
