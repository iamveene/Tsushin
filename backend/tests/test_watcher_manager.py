"""
WatcherManager regressions for API-reader preference and SQLite fallback behavior.
"""

import asyncio
import os
import sys
import types
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

docker_stub = types.ModuleType("docker")
docker_stub.errors = types.SimpleNamespace(NotFound=Exception, DockerException=Exception)
docker_stub.DockerClient = object
sys.modules.setdefault("docker", docker_stub)

stub_watcher_module = types.ModuleType("mcp_reader.watcher")
stub_watcher_module.MCPWatcher = object
sys.modules.setdefault("mcp_reader.watcher", stub_watcher_module)

stub_sqlite_module = types.ModuleType("mcp_reader.sqlite_reader")
stub_sqlite_module.MCPDatabaseReader = object
sys.modules.setdefault("mcp_reader.sqlite_reader", stub_sqlite_module)

stub_api_module = types.ModuleType("mcp_reader.api_reader")
stub_api_module.MCPAPIReader = object
sys.modules.setdefault("mcp_reader.api_reader", stub_api_module)

stub_router_module = types.ModuleType("agent.router")
stub_router_module.AgentRouter = object
sys.modules.setdefault("agent.router", stub_router_module)

from services.watcher_manager import WatcherManager


@pytest.fixture
def app_state():
    return SimpleNamespace(watchers={}, watcher_tasks={})


@pytest.fixture
def manager(app_state):
    return WatcherManager(app_state)


@pytest.fixture
def mock_instance():
    return SimpleNamespace(
        id=7,
        tenant_id="tenant-watchers",
        status="running",
        mcp_api_url="http://mcp-agent:8080/api",
        api_secret="secret",
        phone_number="+5511999999999",
        group_filters=None,
        number_filters=None,
        group_keywords=None,
        dm_auto_mode=True,
        messages_db_path="/tmp/messages.db",
        created_at=datetime.utcnow(),
        mcp_port=8090,
    )


@pytest.fixture
def mock_config():
    return SimpleNamespace(
        contact_mappings="{}",
        group_keywords="[]",
        group_filters=[],
        number_filters=[],
        dm_auto_mode=True,
        agent_number="+5511999999999",
        agent_name="Watcher Agent",
        model_provider="gemini",
        model_name="gemini-2.5-pro",
        system_prompt="You are helpful.",
        memory_size=10,
        maintenance_mode=False,
        maintenance_message=None,
        context_message_count=10,
        context_char_limit=8000,
        enable_semantic_search=False,
        semantic_search_results=5,
        semantic_similarity_threshold=0.3,
        whatsapp_conversation_delay_seconds=1.5,
    )


def build_mock_db(instance, config, agents=None):
    agents = agents or []

    instance_query = MagicMock()
    instance_query.filter.return_value.first.return_value = instance

    config_query = MagicMock()
    config_query.first.return_value = config

    agent_query = MagicMock()
    agent_query.filter.return_value.all.return_value = agents

    db = MagicMock()
    db.query.side_effect = [instance_query, config_query, agent_query]
    return db


def test_start_watcher_prefers_api_reader_when_available(manager, app_state, mock_instance, mock_config):
    db = build_mock_db(mock_instance, mock_config)
    api_reader = MagicMock()
    api_reader.is_available.return_value = True
    router = MagicMock()
    watcher = MagicMock()
    task = MagicMock()
    reconciler = MagicMock()

    with (
        patch("services.watcher_manager.MCPContainerManager", return_value=reconciler),
        patch("services.watcher_manager.MCPAPIReader", return_value=api_reader),
        patch("services.watcher_manager.MCPDatabaseReader") as sqlite_reader_cls,
        patch("services.watcher_manager.AgentRouter", return_value=router) as router_cls,
        patch("services.watcher_manager.MCPWatcher", return_value=watcher),
        patch("services.watcher_manager.asyncio.create_task", return_value=task),
        patch("agent.contact_service_cached.CachedContactService", return_value=MagicMock()),
    ):
        started = asyncio.run(manager.start_watcher_for_instance(mock_instance.id, db))

    assert started is True
    reconciler.reconcile_instance.assert_called_once_with(mock_instance, db)
    sqlite_reader_cls.assert_not_called()
    assert router_cls.call_args.kwargs["mcp_reader"] is api_reader
    assert app_state.watchers[mock_instance.id] is watcher
    assert app_state.watcher_tasks[mock_instance.id] is task


def test_start_watcher_keeps_api_reader_when_api_unavailable_and_sqlite_path_missing(
    manager,
    app_state,
    mock_instance,
    mock_config,
):
    db = build_mock_db(mock_instance, mock_config)
    api_reader = MagicMock()
    api_reader.is_available.return_value = False
    router = MagicMock()
    watcher = MagicMock()
    task = MagicMock()

    with (
        patch("services.watcher_manager.MCPContainerManager", return_value=MagicMock()),
        patch("services.watcher_manager.MCPAPIReader", return_value=api_reader),
        patch("services.watcher_manager.MCPDatabaseReader") as sqlite_reader_cls,
        patch("services.watcher_manager.AgentRouter", return_value=router) as router_cls,
        patch("services.watcher_manager.MCPWatcher", return_value=watcher),
        patch("services.watcher_manager.asyncio.create_task", return_value=task),
        patch("services.watcher_manager.os.path.exists", return_value=False),
        patch("agent.contact_service_cached.CachedContactService", return_value=MagicMock()),
    ):
        started = asyncio.run(manager.start_watcher_for_instance(mock_instance.id, db))

    assert started is True
    sqlite_reader_cls.assert_not_called()
    assert router_cls.call_args.kwargs["mcp_reader"] is api_reader
    assert app_state.watchers[mock_instance.id] is watcher


def test_start_watcher_falls_back_to_sqlite_only_when_local_db_exists(
    manager,
    mock_instance,
    mock_config,
):
    db = build_mock_db(mock_instance, mock_config)
    api_reader = MagicMock()
    api_reader.is_available.return_value = False
    sqlite_reader = MagicMock()

    with (
        patch("services.watcher_manager.MCPContainerManager", return_value=MagicMock()),
        patch("services.watcher_manager.MCPAPIReader", return_value=api_reader),
        patch("services.watcher_manager.MCPDatabaseReader", return_value=sqlite_reader) as sqlite_reader_cls,
        patch("services.watcher_manager.AgentRouter", return_value=MagicMock()) as router_cls,
        patch("services.watcher_manager.MCPWatcher", return_value=MagicMock()),
        patch("services.watcher_manager.asyncio.create_task", return_value=MagicMock()),
        patch("services.watcher_manager.os.path.exists", return_value=True),
        patch("agent.contact_service_cached.CachedContactService", return_value=MagicMock()),
    ):
        started = asyncio.run(manager.start_watcher_for_instance(mock_instance.id, db))

    assert started is True
    sqlite_reader_cls.assert_called_once_with(mock_instance.messages_db_path, contact_mappings={})
    assert router_cls.call_args.kwargs["mcp_reader"] is sqlite_reader
