import asyncio

import pytest

from mcp_reader.watcher import MCPWatcher


class FakeReader:
    def __init__(self, messages):
        self.messages = messages
        self._called = False

    def get_new_messages(self, last_timestamp):
        if self._called:
            return []
        self._called = True
        return list(self.messages)

    def get_latest_timestamp(self):
        return "1970-01-01 00:00:00"


class FakeFilter:
    def should_trigger(self, message):
        return "conversation"


@pytest.mark.asyncio
async def test_whatsapp_conversation_messages_are_debounced():
    records = []

    async def on_message(msg, trigger_type):
        records.append((msg, trigger_type))

    messages = [
        {
            "id": "m1",
            "sender": "5511990000001",
            "body": "Primeira mensagem",
            "timestamp": "2026-01-19 19:00:01",
            "channel": "whatsapp",
            "chat_id": "5511990000001@lid",
            "is_group": 0
        },
        {
            "id": "m2",
            "sender": "5511990000001",
            "body": "Segunda mensagem",
            "timestamp": "2026-01-19 19:00:02",
            "channel": "whatsapp",
            "chat_id": "5511990000001@lid",
            "is_group": 0
        }
    ]

    watcher = MCPWatcher(
        reader=FakeReader(messages),
        message_filter=FakeFilter(),
        on_message_callback=on_message,
        whatsapp_conversation_delay_seconds=0.05
    )

    await watcher._poll_messages()
    await asyncio.sleep(0.08)

    assert len(records) == 1
    assert records[0][0]["body"] == "Primeira mensagem\nSegunda mensagem"
    assert records[0][0]["aggregated_message_ids"] == ["m1", "m2"]


@pytest.mark.asyncio
async def test_non_whatsapp_conversation_messages_skip_debounce():
    records = []

    async def on_message(msg, trigger_type):
        records.append((msg, trigger_type))

    messages = [
        {
            "id": "t1",
            "sender": "user-1",
            "body": "Primeira",
            "timestamp": "2026-01-19 19:00:01",
            "channel": "telegram",
            "chat_id": "chat-1",
            "is_group": 0
        },
        {
            "id": "t2",
            "sender": "user-1",
            "body": "Segunda",
            "timestamp": "2026-01-19 19:00:02",
            "channel": "telegram",
            "chat_id": "chat-1",
            "is_group": 0
        }
    ]

    watcher = MCPWatcher(
        reader=FakeReader(messages),
        message_filter=FakeFilter(),
        on_message_callback=on_message,
        whatsapp_conversation_delay_seconds=0.05
    )

    await watcher._poll_messages()

    assert len(records) == 2
    assert records[0][0]["body"] == "Primeira"
    assert records[1][0]["body"] == "Segunda"
