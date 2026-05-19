from __future__ import annotations

import asyncio
from types import SimpleNamespace


def test_tool_slash_routes_explicit_browser_and_flights_commands(monkeypatch):
    from services.slash_command_service import SlashCommandService

    service = SlashCommandService(db=SimpleNamespace())
    calls = []

    async def fake_browser(args, agent_id, sender_key, tenant_id):
        calls.append(("browser", args, agent_id, sender_key, tenant_id))
        return {"status": "success", "message": "browser ok"}

    async def fake_flights(args, agent_id, sender_key, tenant_id):
        calls.append(("flights", args, agent_id, sender_key, tenant_id))
        return {"status": "success", "message": "flights ok"}

    async def fake_search(query, tenant_id):
        calls.append(("search", query, tenant_id))
        return {"status": "success", "message": "search ok"}

    monkeypatch.setattr(service, "_execute_browser_tool", fake_browser)
    monkeypatch.setattr(service, "_execute_flights_tool", fake_flights)
    monkeypatch.setattr(service, "_execute_search_tool", fake_search)

    browser_result = asyncio.run(
        service._handle_tool_command(
            {"command_name": "browser"},
            ("navigate to https://example.com",),
            "",
            "tenant-a",
            7,
            "sender-a",
        )
    )
    flights_result = asyncio.run(
        service._handle_tool_command(
            {"command_name": "flights"},
            ("GRU to FCO on 2026-05-21",),
            "",
            "tenant-a",
            7,
            "sender-a",
        )
    )
    search_result = asyncio.run(
        service._handle_tool_command(
            {"command_name": "search"},
            ("OpenAI official site",),
            "",
            "tenant-a",
            7,
            "sender-a",
        )
    )

    assert browser_result["message"] == "browser ok"
    assert flights_result["message"] == "flights ok"
    assert search_result["message"] == "search ok"
    assert calls == [
        ("browser", "navigate to https://example.com", 7, "sender-a", "tenant-a"),
        ("flights", "GRU to FCO on 2026-05-21", 7, "sender-a", "tenant-a"),
        ("search", "OpenAI official site", "tenant-a"),
    ]


def test_image_slash_command_executes_generate_image_tool(monkeypatch):
    from agent.skills.base import SkillResult
    from agent.skills.skill_manager import SkillManager
    from services.slash_command_service import SlashCommandService

    service = SlashCommandService(db=SimpleNamespace())
    captured = {}

    async def fake_execute_tool_call(self, **kwargs):
        captured.update(kwargs)
        return SkillResult(
            success=True,
            output="Generated image",
            media_paths=["/tmp/generated.png"],
            metadata={"skill_type": "image", "model": "test"},
        )

    monkeypatch.setattr(SkillManager, "execute_tool_call", fake_execute_tool_call)

    result = asyncio.run(
        service._execute_image_tool(
            "a clean product mockup of a solar backpack",
            agent_id=7,
            sender_key="sender-a",
            tenant_id="tenant-a",
        )
    )

    assert captured["tool_name"] == "generate_image"
    assert captured["arguments"] == {"prompt": "a clean product mockup of a solar backpack"}
    assert captured["return_full_result"] is True
    assert getattr(captured["message"], "tenant_id") == "tenant-a"
    assert result["status"] == "success"
    assert result["tool_name"] == "image"
    assert result["media_paths"] == ["/tmp/generated.png"]
    assert result["tool_result_structured"]["skill_type"] == "image"
