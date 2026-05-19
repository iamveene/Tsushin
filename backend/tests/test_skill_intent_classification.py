"""Regression contract for retired raw-text skill execution.

Skills may run through LLM tool calls, slash commands, passive hooks, or
special media hooks. Plain natural-language text must not dispatch tool skills
through SkillManager.process_message_with_skills().
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types as pytypes
from datetime import datetime
from types import SimpleNamespace


BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure_package(package_name: str, relative_path: str):
    module = sys.modules.get(package_name)
    if module is None:
        module = pytypes.ModuleType(package_name)
        module.__path__ = [os.path.join(BACKEND_ROOT, relative_path)]
        sys.modules[package_name] = module
    return module


def _load_module(module_name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(
        module_name,
        os.path.join(BACKEND_ROOT, relative_path),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


if "dateparser" not in sys.modules:
    fake_dateparser = pytypes.ModuleType("dateparser")
    fake_dateparser.parse = lambda *_args, **_kwargs: None
    sys.modules["dateparser"] = fake_dateparser

_ensure_package("agent", "agent")
_ensure_package("agent.skills", os.path.join("agent", "skills"))
_ensure_package("services", "services")

base_module = _load_module("agent.skills.base", os.path.join("agent", "skills", "base.py"))
InboundMessage = base_module.InboundMessage

skills_package = sys.modules["agent.skills"]
skills_package.BaseSkill = base_module.BaseSkill
skills_package.InboundMessage = base_module.InboundMessage
skills_package.SkillResult = base_module.SkillResult


def _get_skill_manager_proxy():
    from agent.skills.skill_manager import get_skill_manager

    return get_skill_manager()


skills_package.get_skill_manager = _get_skill_manager_proxy


SKILL_CLASSES = [
    ("agent_switcher_skill.py", "AgentSwitcherSkill"),
    ("shell_skill.py", "ShellSkill"),
    ("gmail_skill.py", "GmailSkill"),
    ("image_skill.py", "ImageSkill"),
    ("search_skill.py", "SearchSkill"),
    ("flight_search_skill.py", "FlightSearchSkill"),
    ("automation_skill.py", "AutomationSkill"),
    ("flows_skill.py", "FlowsSkill"),
    ("browser_automation_skill.py", "BrowserAutomationSkill"),
    ("scheduler_skill.py", "SchedulerSkill"),
    ("scheduler_query_skill.py", "SchedulerQuerySkill"),
    ("okg_term_memory_skill.py", "OKGTermMemorySkill"),
    ("image_analysis_skill.py", "ImageAnalysisSkill"),
    ("jira_skill.py", "JiraSkill"),
    ("code_repository_skill.py", "CodeRepositorySkill"),
    ("password_vault_skill.py", "PasswordVaultSkill"),
]

TEXT_ONLY_TOOL_CLASSES = [
    item
    for item in SKILL_CLASSES
    if item[1] != "ImageAnalysisSkill"
]

RETIRED_CONFIG_KEYS = {
    "execution_mode",
    "keywords",
    "trigger_keywords",
    "trigger_mode",
    "use_ai_fallback",
    "edit_keywords",
    "generate_keywords",
    "edit_handoff_keywords",
}


def _skill_class(module_file: str, class_name: str):
    module_name = f"agent.skills.{module_file.removesuffix('.py')}"
    module = _load_module(module_name, os.path.join("agent", "skills", module_file))
    return getattr(module, class_name)


def _message(body: str, **overrides) -> InboundMessage:
    payload = {
        "id": overrides.pop("id", "msg-test"),
        "sender": "+5527999616279",
        "sender_key": "user-1",
        "body": body,
        "chat_id": "chat-1",
        "chat_name": None,
        "is_group": False,
        "timestamp": datetime.utcnow(),
        "channel": "whatsapp",
    }
    payload.update(overrides)
    return InboundMessage(**payload)


def test_affected_skill_config_schemas_do_not_expose_retired_modes_or_keywords():
    for module_file, class_name in SKILL_CLASSES:
        cls = _skill_class(module_file, class_name)
        default_config = cls.get_default_config() or {}
        schema_props = (cls.get_config_schema() or {}).get("properties", {})

        for key in RETIRED_CONFIG_KEYS:
            assert key not in default_config, f"{class_name} default exposes {key}"
            assert key not in schema_props, f"{class_name} schema exposes {key}"


def test_runtime_ignores_persisted_execution_mode_overrides():
    class ConcreteSkill(base_module.BaseSkill):
        async def can_handle(self, _message):
            return False

        async def process(self, _message, _config):
            return base_module.SkillResult(success=True, output="")

    tool_skill = ConcreteSkill()
    tool_skill.execution_mode = "tool"
    tool_skill._config = {"execution_mode": "hybrid"}

    passive_skill = ConcreteSkill()
    passive_skill.execution_mode = "passive"
    passive_skill._config = {"execution_mode": "tool"}

    assert tool_skill.is_tool_enabled({"execution_mode": "legacy"}) is True
    assert passive_skill.is_tool_enabled({"execution_mode": "tool"}) is False


def test_tool_skills_do_not_can_handle_raw_text_even_with_retired_persisted_config(monkeypatch):
    class ExplodingClassifier:
        async def classify_intent(self, **_kwargs):
            raise AssertionError("raw-text skill dispatch must not call AISkillClassifier")

        async def extract_entity(self, **_kwargs):
            raise AssertionError("raw-text skill dispatch must not call AISkillClassifier")

    fake_module = pytypes.ModuleType("agent.skills.ai_classifier")
    fake_module.get_classifier = lambda: ExplodingClassifier()
    monkeypatch.setitem(sys.modules, "agent.skills.ai_classifier", fake_module)

    msg = _message("please search flights, email me, browse this site, and switch agents")
    for module_file, class_name in TEXT_ONLY_TOOL_CLASSES:
        cls = _skill_class(module_file, class_name)
        skill = cls()
        skill._config = {
            **(cls.get_default_config() or {}),
            "execution_mode": "hybrid",
            "keywords": ["search", "email", "switch"],
            "use_ai_fallback": True,
        }

        assert asyncio.run(skill.can_handle(msg)) is False, class_name


def test_image_media_hook_still_handles_attached_image_edit_requests(monkeypatch):
    image_module = _load_module("agent.skills.image_skill", os.path.join("agent", "skills", "image_skill.py"))

    class StubClassifier:
        async def extract_entity(self, **_kwargs):
            return "edit"

    fake_module = pytypes.ModuleType("agent.skills.ai_classifier")
    fake_module.get_classifier = lambda: StubClassifier()
    monkeypatch.setitem(sys.modules, "agent.skills.ai_classifier", fake_module)

    skill = image_module.ImageSkill()
    skill._config = skill.get_default_config()
    msg = _message("make the background white", id="img-edit", media_type="image/png")

    assert asyncio.run(skill.can_handle(msg)) is True


def test_image_analysis_media_hook_still_handles_plain_attached_images():
    image_analysis_module = _load_module(
        "agent.skills.image_analysis_skill",
        os.path.join("agent", "skills", "image_analysis_skill.py"),
    )
    skill = image_analysis_module.ImageAnalysisSkill()
    skill._config = skill.get_default_config()
    msg = _message("", id="img-analysis", media_type="image/png")

    assert asyncio.run(skill.can_handle(msg)) is True


def test_custom_skill_adapter_ignores_keyword_trigger_mode():
    adapter_module = _load_module(
        "agent.skills.custom_skill_adapter",
        os.path.join("agent", "skills", "custom_skill_adapter.py"),
    )
    adapter = adapter_module.CustomSkillAdapter(
        SimpleNamespace(
            slug="old-keyword-skill",
            name="Old Keyword Skill",
            description="Old keyword config should not dispatch raw text",
            execution_mode="tool",
            trigger_mode="keyword",
            trigger_keywords=["run me"],
        )
    )

    assert asyncio.run(adapter.can_handle(_message("run me now"))) is False


def test_custom_skill_api_rejects_retired_modes_and_keyword_triggers():
    source = open(os.path.join(BACKEND_ROOT, "api", "routes_custom_skills.py"), encoding="utf-8").read()

    assert "execution_mode not in ('tool', 'passive')" in source
    assert "trigger_mode != 'llm_decided'" in source
    assert "trigger_keywords are no longer supported" in source
    assert '"hybrid"' not in source
    assert "'hybrid'" not in source
