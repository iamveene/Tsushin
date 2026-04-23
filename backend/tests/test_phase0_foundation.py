import asyncio
import os
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models_rbac  # noqa: F401
from models import ChannelEventDedupe, SentinelConfig
from services.container_runtime import PORT_RANGES, iter_port_range, validate_port_ranges
from services.message_queue_service import MessageQueueService
from services.queue_router import QueueRouter
from services.sentinel_detections import DETECTION_REGISTRY, get_detection_types
from services.sentinel_effective_config import SentinelEffectiveConfig
from services.sentinel_seeding import seed_sentinel_config


def _make_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    with engine.begin() as conn:
        conn.exec_driver_sql("""
            CREATE TABLE message_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id VARCHAR(50) NOT NULL,
                channel VARCHAR(20) NOT NULL,
                message_type VARCHAR(32) NOT NULL,
                status VARCHAR(20) NOT NULL,
                agent_id INTEGER NOT NULL,
                sender_key VARCHAR(255) NOT NULL,
                payload JSON NOT NULL,
                priority INTEGER,
                retry_count INTEGER,
                max_retries INTEGER,
                error_message TEXT,
                queued_at DATETIME,
                processing_started_at DATETIME,
                completed_at DATETIME
            )
        """)
        conn.exec_driver_sql("""
            CREATE TABLE channel_event_dedupe (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id VARCHAR(50) NOT NULL,
                channel_type VARCHAR(32) NOT NULL,
                instance_id INTEGER NOT NULL,
                dedupe_key VARCHAR(512) NOT NULL,
                outcome VARCHAR(32) NOT NULL,
                created_at DATETIME NOT NULL,
                UNIQUE (tenant_id, channel_type, instance_id, dedupe_key)
            )
        """)
        conn.exec_driver_sql("""
            CREATE TABLE sentinel_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id VARCHAR(50),
                is_enabled BOOLEAN NOT NULL,
                enable_prompt_analysis BOOLEAN NOT NULL,
                enable_tool_analysis BOOLEAN NOT NULL,
                enable_shell_analysis BOOLEAN NOT NULL,
                detect_prompt_injection BOOLEAN NOT NULL,
                detect_agent_takeover BOOLEAN NOT NULL,
                detect_poisoning BOOLEAN NOT NULL,
                detect_shell_malicious_intent BOOLEAN NOT NULL,
                detect_memory_poisoning BOOLEAN NOT NULL,
                detect_browser_ssrf BOOLEAN NOT NULL,
                detect_vector_store_poisoning BOOLEAN NOT NULL,
                detect_continuous_agent_action_approval BOOLEAN NOT NULL,
                aggressiveness_level INTEGER NOT NULL,
                llm_provider VARCHAR(20) NOT NULL,
                llm_model VARCHAR(100) NOT NULL,
                llm_max_tokens INTEGER NOT NULL,
                llm_temperature FLOAT NOT NULL,
                prompt_injection_prompt TEXT,
                agent_takeover_prompt TEXT,
                poisoning_prompt TEXT,
                shell_intent_prompt TEXT,
                memory_poisoning_prompt TEXT,
                browser_ssrf_prompt TEXT,
                vector_store_poisoning_prompt TEXT,
                continuous_agent_action_approval_prompt TEXT,
                cache_ttl_seconds INTEGER NOT NULL,
                max_input_chars INTEGER NOT NULL,
                timeout_seconds FLOAT NOT NULL,
                block_on_detection BOOLEAN NOT NULL,
                log_all_analyses BOOLEAN NOT NULL,
                detection_mode VARCHAR(20) NOT NULL,
                enable_slash_command_analysis BOOLEAN NOT NULL,
                enable_notifications BOOLEAN NOT NULL,
                notification_on_block BOOLEAN NOT NULL,
                notification_on_detect BOOLEAN NOT NULL,
                notification_recipient VARCHAR(100),
                notification_message_template TEXT,
                created_by INTEGER,
                created_at DATETIME NOT NULL,
                updated_by INTEGER,
                updated_at DATETIME NOT NULL,
                UNIQUE (tenant_id)
            )
        """)
    Session = sessionmaker(bind=engine)
    return Session()


def test_port_ranges_are_centralized_inclusive_and_non_overlapping():
    assert PORT_RANGES["whisper"] == (6400, 6499)
    assert PORT_RANGES["searxng"] == (6500, 6599)
    assert 6499 in iter_port_range("whisper")
    assert 6500 in iter_port_range("searxng")
    validate_port_ranges()


def test_message_queue_defaults_to_inbound_message_type():
    db = _make_session()
    try:
        item = MessageQueueService(db).enqueue(
            channel="api",
            tenant_id="tenant-a",
            agent_id=1,
            sender_key="api-client",
            payload={"message": "hello"},
        )
        assert item.message_type == "inbound_message"
    finally:
        db.close()


@pytest.mark.parametrize("message_type", ["trigger_event", "continuous_task"])
def test_message_queue_accepts_phase0_discriminator_values(message_type):
    db = _make_session()
    try:
        item = MessageQueueService(db).enqueue(
            channel="webhook",
            tenant_id="tenant-a",
            agent_id=1,
            sender_key="webhook:test",
            payload={"event": "x"},
            message_type=message_type,
        )
        assert item.message_type == message_type
        assert item.agent_id == 1
        assert item.sender_key == "webhook:test"
    finally:
        db.close()


def test_channel_event_dedupe_is_unique_per_tenant():
    db = _make_session()
    try:
        db.add(ChannelEventDedupe(
            tenant_id="tenant-a",
            channel_type="webhook",
            instance_id=10,
            dedupe_key="abc",
            outcome="wake_emitted",
        ))
        db.commit()
        db.add(ChannelEventDedupe(
            tenant_id="tenant-b",
            channel_type="webhook",
            instance_id=10,
            dedupe_key="abc",
            outcome="wake_emitted",
        ))
        db.commit()
        db.add(ChannelEventDedupe(
            tenant_id="tenant-a",
            channel_type="webhook",
            instance_id=10,
            dedupe_key="abc",
            outcome="duplicate",
        ))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.close()


class _FakeWorker:
    def __init__(self):
        self.calls = []

    async def _process_playground_message(self, db, item):
        self.calls.append(("playground", item.id))
        return {"channel": "playground"}

    async def _process_whatsapp_message(self, db, item):
        self.calls.append(("whatsapp", item.id))

    async def _process_telegram_message(self, db, item):
        self.calls.append(("telegram", item.id))

    async def _process_webhook_message(self, db, item):
        self.calls.append(("webhook", item.id))
        return {"channel": "webhook"}

    async def _process_api_message(self, db, item):
        self.calls.append(("api", item.id))
        return {"channel": "api"}

    async def _process_slack_message(self, db, item):
        self.calls.append(("slack", item.id))

    async def _process_discord_message(self, db, item):
        self.calls.append(("discord", item.id))


def test_queue_router_preserves_all_inbound_channel_branches():
    async def run():
        router = QueueRouter()
        worker = _FakeWorker()
        for idx, channel in enumerate([
            "playground", "whatsapp", "telegram", "webhook", "api", "slack", "discord"
        ], start=1):
            item = SimpleNamespace(id=idx, channel=channel, message_type="inbound_message")
            await router.dispatch(worker, None, item)
        assert [call[0] for call in worker.calls] == [
            "playground", "whatsapp", "telegram", "webhook", "api", "slack", "discord"
        ]
    asyncio.run(run())


def test_queue_router_routes_webhook_trigger_events_through_current_webhook_path():
    async def run():
        router = QueueRouter()
        worker = _FakeWorker()
        item = SimpleNamespace(id=42, channel="webhook", message_type="trigger_event")

        result = await router.dispatch(worker, None, item)

        assert result == {"channel": "webhook"}
        assert worker.calls == [("webhook", 42)]

    asyncio.run(run())


def test_queue_router_rejects_unknown_channel_and_reserved_continuous_task():
    async def run():
        router = QueueRouter()
        worker = _FakeWorker()
        with pytest.raises(ValueError):
            await router.dispatch(worker, None, SimpleNamespace(id=1, channel="bogus", message_type="inbound_message"))
        with pytest.raises(NotImplementedError):
            await router.dispatch(worker, None, SimpleNamespace(id=2, channel="api", message_type="continuous_task"))
    asyncio.run(run())


def test_sentinel_detection_type_and_idempotent_seed():
    assert "continuous_agent_action_approval" in get_detection_types()
    assert DETECTION_REGISTRY["continuous_agent_action_approval"]["default_enabled"] is True

    db = _make_session()
    try:
        first = seed_sentinel_config(db)
        second = seed_sentinel_config(db)
        assert first.id == second.id
        assert db.query(SentinelConfig).count() == 1
        assert first.detect_continuous_agent_action_approval is True
    finally:
        db.close()


def test_legacy_sentinel_effective_config_includes_continuous_approval_toggle():
    config = SimpleNamespace(
        is_enabled=True,
        detection_mode="block",
        aggressiveness_level=1,
        enable_prompt_analysis=True,
        enable_tool_analysis=True,
        enable_shell_analysis=True,
        enable_slash_command_analysis=True,
        llm_provider="gemini",
        llm_model="gemini-2.5-flash-lite",
        llm_max_tokens=256,
        llm_temperature=0.1,
        cache_ttl_seconds=300,
        max_input_chars=5000,
        timeout_seconds=5.0,
        block_on_detection=True,
        log_all_analyses=False,
        enable_notifications=True,
        notification_on_block=True,
        notification_on_detect=False,
        notification_recipient=None,
        notification_message_template=None,
        detect_continuous_agent_action_approval=False,
        continuous_agent_action_approval_prompt="custom approval prompt",
    )
    effective = SentinelEffectiveConfig.from_legacy_config(config)
    assert effective.is_detection_enabled("continuous_agent_action_approval") is False
    assert effective.get_custom_prompt("continuous_agent_action_approval") == "custom approval prompt"
