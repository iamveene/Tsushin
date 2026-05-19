from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace


def _handler_with_fake_db(handler_cls):
    query = SimpleNamespace(filter=lambda *_args, **_kwargs: SimpleNamespace(first=lambda: SimpleNamespace(tenant_id="tenant-a")))
    return handler_cls(db=SimpleNamespace(query=lambda *_args, **_kwargs: query), mcp_sender=SimpleNamespace())


def test_flow_skill_step_rejects_prompt_only_legacy_execution():
    from flows.flow_engine import SkillStepHandler

    class FakeToolSkill:
        skill_type = "fake_tool"
        skill_name = "Fake Tool"

        @classmethod
        def get_default_config(cls):
            return {}

        async def execute_tool(self, _arguments, _message, _config):
            raise AssertionError("prompt-only skill steps must not execute")

    class FakeSkillManager:
        registry = {"fake_tool": FakeToolSkill}

        async def get_skill_config(self, *_args, **_kwargs):
            return {}

    async def run_step():
        import agent.skills.skill_manager as skill_manager_module

        original_skill_manager = getattr(skill_manager_module, "_skill_manager", None)
        skill_manager_module._skill_manager = FakeSkillManager()
        try:
            return await _handler_with_fake_db(SkillStepHandler).execute(
                SimpleNamespace(
                    id=11,
                    agent_id=7,
                    config_json=json.dumps(
                        {
                            "skill_type": "fake_tool",
                            "prompt": "old natural language prompt",
                        }
                    ),
                ),
                {},
                SimpleNamespace(id=99, tenant_id="tenant-a", flow_definition_id=1),
                SimpleNamespace(id=1001),
            )
        finally:
            skill_manager_module._skill_manager = original_skill_manager

    result = asyncio.run(run_step())

    assert result["status"] == "failed"
    assert result["metadata"]["error"] == "missing_tool_arguments"
    assert "tool_arguments" in result["output"]


def test_flow_skill_step_executes_explicit_tool_arguments():
    from agent.skills.base import SkillResult
    from flows.flow_engine import SkillStepHandler

    captured = {}

    class FakeToolSkill:
        skill_type = "fake_tool"
        skill_name = "Fake Tool"

        @classmethod
        def get_default_config(cls):
            return {"enabled": True}

        def set_db_session(self, db):
            captured["db"] = db

        async def execute_tool(self, arguments, message, config):
            captured["arguments"] = arguments
            captured["message_body"] = message.body
            captured["config"] = config
            return SkillResult(success=True, output="tool ok", metadata={"action": arguments["action"]})

    class FakeSkillManager:
        registry = {"fake_tool": FakeToolSkill}

        async def get_skill_config(self, *_args, **_kwargs):
            return {"from_agent": True}

    async def run_step():
        import agent.skills.skill_manager as skill_manager_module

        original_skill_manager = getattr(skill_manager_module, "_skill_manager", None)
        skill_manager_module._skill_manager = FakeSkillManager()
        try:
            return await _handler_with_fake_db(SkillStepHandler).execute(
                SimpleNamespace(
                    id=12,
                    agent_id=7,
                    config_json=json.dumps(
                        {
                            "skill_type": "fake_tool",
                            "prompt": "context only",
                            "tool_arguments": {"action": "list", "limit": 3},
                        }
                    ),
                ),
                {},
                SimpleNamespace(id=100, tenant_id="tenant-a", flow_definition_id=1),
                SimpleNamespace(id=1002),
            )
        finally:
            skill_manager_module._skill_manager = original_skill_manager

    result = asyncio.run(run_step())

    assert result["status"] == "completed"
    assert result["execution_mode"] == "tool"
    assert captured["arguments"] == {"action": "list", "limit": 3}
    assert captured["message_body"] == "context only"
    assert captured["config"]["from_agent"] is True
    assert captured["config"]["tenant_id"] == "tenant-a"
