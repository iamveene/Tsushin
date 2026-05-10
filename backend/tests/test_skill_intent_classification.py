"""
Regression contract for the LLM-classified skill intent system.

After dropping the bilingual keyword chip-list anti-pattern, every affected skill
routes intent through AISkillClassifier. These tests pin that contract:

1. Each affected skill's get_default_config() and get_config_schema() no longer
   surface the keyword arrays the user complained about.
2. can_handle() consults the LLM classifier (mocked) and respects its verdict.
3. Cheap structural guards still short-circuit before any LLM call.
4. Slash dispatch is upstream of can_handle() — verified separately by Stage 2
   of the verification plan; this file only covers can_handle behavior.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types as pytypes
from datetime import datetime
from typing import Any, Dict, List, Optional


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


_ensure_package("agent", "agent")
_ensure_package("agent.skills", os.path.join("agent", "skills"))
_ensure_package("services", "services")

base_module = _load_module("agent.skills.base", os.path.join("agent", "skills", "base.py"))
InboundMessage = base_module.InboundMessage


# ---------------------------------------------------------------------------
# Shared classifier stub
# ---------------------------------------------------------------------------


class StubClassifier:
    """Fake AISkillClassifier that returns pre-programmed verdicts."""

    def __init__(self, intent_value: bool = True, entity_value: Optional[str] = None):
        self.intent_value = intent_value
        self.entity_value = entity_value
        self.intent_calls: List[Dict[str, Any]] = []
        self.entity_calls: List[Dict[str, Any]] = []

    async def classify_intent(self, **kwargs):
        self.intent_calls.append(kwargs)
        return self.intent_value

    async def extract_entity(self, **kwargs):
        self.entity_calls.append(kwargs)
        return self.entity_value


def _patch_classifier(monkeypatch, module, classifier: StubClassifier):
    """Patch the get_classifier import that lives inside each skill's helper."""
    fake_module = pytypes.ModuleType("agent.skills.ai_classifier")
    fake_module.get_classifier = lambda: classifier
    monkeypatch.setitem(sys.modules, "agent.skills.ai_classifier", fake_module)


def _msg(body: str, **overrides) -> InboundMessage:
    base = dict(
        id=overrides.pop("id", "msg-test"),
        sender="+5527999616279",
        sender_key="user-1",
        body=body,
        chat_id="chat-1",
        chat_name=None,
        is_group=False,
        timestamp=datetime.utcnow(),
        channel="whatsapp",
    )
    base.update(overrides)
    return InboundMessage(**base)


# ---------------------------------------------------------------------------
# Schema regression: keyword arrays are GONE from user-facing config
# ---------------------------------------------------------------------------


def test_image_skill_config_no_keyword_fields():
    image_skill = _load_module(
        "agent.skills.image_skill",
        os.path.join("agent", "skills", "image_skill.py"),
    )
    default = image_skill.ImageSkill.get_default_config()
    schema = image_skill.ImageSkill.get_config_schema()
    for key in ("edit_keywords", "generate_keywords", "keywords"):
        assert key not in default, f"ImageSkill default still exposes {key}"
        assert key not in schema["properties"], f"ImageSkill schema still exposes {key}"


def test_image_analysis_skill_config_no_keyword_fields():
    skill_module = _load_module(
        "agent.skills.image_analysis_skill",
        os.path.join("agent", "skills", "image_analysis_skill.py"),
    )
    default = skill_module.ImageAnalysisSkill.get_default_config()
    schema = skill_module.ImageAnalysisSkill.get_config_schema()
    for key in ("edit_handoff_keywords", "keywords"):
        assert key not in default
        assert key not in schema["properties"]


def test_gmail_skill_config_no_keyword_fields():
    skill_module = _load_module(
        "agent.skills.gmail_skill",
        os.path.join("agent", "skills", "gmail_skill.py"),
    )
    default = skill_module.GmailSkill.get_default_config()
    schema = skill_module.GmailSkill.get_config_schema()
    assert "keywords" not in default
    assert "keywords" not in schema["properties"]
    assert not hasattr(skill_module.GmailSkill, "EMAIL_KEYWORDS")


def test_automation_skill_no_hardcoded_keyword_lists():
    src_path = os.path.join(BACKEND_ROOT, "agent", "skills", "automation_skill.py")
    contents = open(src_path).read()
    assert "automation_keywords = [" not in contents, \
        "AutomationSkill should no longer carry an automation_keywords list"
    for sub_intent in ("list_keywords =", "run_keywords =", "status_keywords =", "help_keywords ="):
        assert sub_intent not in contents, \
            f"AutomationSkill should no longer carry {sub_intent.split(' ')[0]}"


def test_browser_automation_skill_config_no_keyword_field():
    skill_module = _load_module(
        "agent.skills.browser_automation_skill",
        os.path.join("agent", "skills", "browser_automation_skill.py"),
    )
    default = skill_module.BrowserAutomationSkill.get_default_config()
    schema = skill_module.BrowserAutomationSkill.get_config_schema()
    assert "keywords" not in default
    assert "keywords" not in schema["properties"]


def test_flight_search_skill_config_no_keyword_field():
    skill_module = _load_module(
        "agent.skills.flight_search_skill",
        os.path.join("agent", "skills", "flight_search_skill.py"),
    )
    default = skill_module.FlightSearchSkill.get_default_config()
    schema = skill_module.FlightSearchSkill.get_config_schema()
    assert "keywords" not in default
    assert "keywords" not in schema["properties"]


def test_search_skill_config_no_keyword_field():
    skill_module = _load_module(
        "agent.skills.search_skill",
        os.path.join("agent", "skills", "search_skill.py"),
    )
    default = skill_module.SearchSkill.get_default_config()
    schema = skill_module.SearchSkill.get_config_schema()
    assert "keywords" not in default
    assert "keywords" not in schema["properties"]


def test_agent_switcher_skill_config_no_keyword_field():
    skill_module = _load_module(
        "agent.skills.agent_switcher_skill",
        os.path.join("agent", "skills", "agent_switcher_skill.py"),
    )
    default = skill_module.AgentSwitcherSkill.get_default_config()
    schema = skill_module.AgentSwitcherSkill.get_config_schema()
    assert "keywords" not in default
    assert "keywords" not in schema["properties"]


def test_base_skill_no_longer_advertises_keywords():
    default = base_module.BaseSkill.get_default_config()
    schema = base_module.BaseSkill.get_config_schema()
    assert "keywords" not in default
    assert "keywords" not in schema["properties"]


# ---------------------------------------------------------------------------
# can_handle() behavior: trust the classifier, no keyword shortcuts
# ---------------------------------------------------------------------------


def test_image_skill_can_handle_image_caption_uses_classifier(monkeypatch):
    image_skill = _load_module(
        "agent.skills.image_skill",
        os.path.join("agent", "skills", "image_skill.py"),
    )
    stub = StubClassifier(entity_value="edit")
    _patch_classifier(monkeypatch, image_skill, stub)

    skill = image_skill.ImageSkill()
    skill._config = skill.get_default_config()

    msg = _msg("torna ela em preto e branco", media_type="image/png", id="img-edit-1")
    assert asyncio.run(skill.can_handle(msg)) is True
    assert len(stub.entity_calls) == 1


def test_image_skill_can_handle_image_caption_none_defers(monkeypatch):
    image_skill = _load_module(
        "agent.skills.image_skill",
        os.path.join("agent", "skills", "image_skill.py"),
    )
    stub = StubClassifier(entity_value="none")
    _patch_classifier(monkeypatch, image_skill, stub)

    skill = image_skill.ImageSkill()
    skill._config = skill.get_default_config()

    msg = _msg("bonita né?", media_type="image/png", id="img-comment-1")
    assert asyncio.run(skill.can_handle(msg)) is False


def test_image_skill_text_only_generate_intent_handled_in_legacy_mode(monkeypatch):
    image_skill = _load_module(
        "agent.skills.image_skill",
        os.path.join("agent", "skills", "image_skill.py"),
    )
    stub = StubClassifier(entity_value="generate")
    _patch_classifier(monkeypatch, image_skill, stub)

    skill = image_skill.ImageSkill()
    cfg = skill.get_default_config()
    cfg["execution_mode"] = "hybrid"  # text-only path requires legacy/hybrid
    skill._config = cfg

    msg = _msg("crie uma imagem de um elefante azul", id="img-gen-1")
    assert asyncio.run(skill.can_handle(msg)) is True


def test_image_skill_regression_mudar_no_longer_triggers(monkeypatch):
    """The old keyword 'mudar' substring would falsely trigger image edit on
    'vou mudar de assunto'. With the classifier in place this must NOT fire."""
    image_skill = _load_module(
        "agent.skills.image_skill",
        os.path.join("agent", "skills", "image_skill.py"),
    )
    stub = StubClassifier(entity_value="none")
    _patch_classifier(monkeypatch, image_skill, stub)

    skill = image_skill.ImageSkill()
    cfg = skill.get_default_config()
    cfg["execution_mode"] = "hybrid"
    skill._config = cfg
    skill._cache_recent_image(_msg("", media_type="image/png", id="prior-img"))

    msg = _msg("vou mudar de assunto agora", id="benign-1")
    assert asyncio.run(skill.can_handle(msg)) is False


def test_gmail_skill_can_handle_calls_classifier(monkeypatch):
    skill_module = _load_module(
        "agent.skills.gmail_skill",
        os.path.join("agent", "skills", "gmail_skill.py"),
    )
    stub = StubClassifier(intent_value=True)
    _patch_classifier(monkeypatch, skill_module, stub)

    skill = skill_module.GmailSkill()
    cfg = skill.get_default_config()
    cfg["execution_mode"] = "hybrid"
    skill._config = cfg

    msg = _msg("mostra meus emails", id="gmail-1")
    assert asyncio.run(skill.can_handle(msg)) is True
    assert len(stub.intent_calls) == 1
    assert stub.intent_calls[0]["message"] == "mostra meus emails"


def test_gmail_skill_can_handle_no_keyword_required(monkeypatch):
    """Confirms the keyword pre-filter is gone — a body with zero email-words
    still reaches the classifier (the LLM, not a substring scan, decides)."""
    skill_module = _load_module(
        "agent.skills.gmail_skill",
        os.path.join("agent", "skills", "gmail_skill.py"),
    )
    stub = StubClassifier(intent_value=True)
    _patch_classifier(monkeypatch, skill_module, stub)

    skill = skill_module.GmailSkill()
    cfg = skill.get_default_config()
    cfg["execution_mode"] = "hybrid"
    skill._config = cfg

    msg = _msg("alguma coisa nova de ontem?", id="gmail-2")
    assert asyncio.run(skill.can_handle(msg)) is True
    assert stub.intent_calls, "Classifier must be consulted, not bypassed by keyword pre-filter"


def test_automation_skill_can_handle_uses_classifier(monkeypatch):
    skill_module = _load_module(
        "agent.skills.automation_skill",
        os.path.join("agent", "skills", "automation_skill.py"),
    )
    stub = StubClassifier(intent_value=True)
    _patch_classifier(monkeypatch, skill_module, stub)

    skill = skill_module.AutomationSkill()
    cfg = skill.get_default_config() if hasattr(skill_module.AutomationSkill, "get_default_config") else {}
    cfg["execution_mode"] = "hybrid"
    cfg["is_enabled"] = True
    skill._config = cfg

    msg = _msg("rodar meu fluxo de relatórios", id="auto-1")
    assert asyncio.run(skill.can_handle(msg)) is True
    assert stub.intent_calls


def test_automation_skill_detect_intent_uses_extract_entity(monkeypatch):
    skill_module = _load_module(
        "agent.skills.automation_skill",
        os.path.join("agent", "skills", "automation_skill.py"),
    )
    stub = StubClassifier(entity_value="run")
    _patch_classifier(monkeypatch, skill_module, stub)

    skill = skill_module.AutomationSkill()
    msg = _msg("execute o flow de sincronização", id="auto-detect-1")
    intent = asyncio.run(skill._detect_intent(msg, {}))
    assert intent == "run"
    assert stub.entity_calls
    assert stub.entity_calls[0]["available_options"] == ["list", "run", "status", "help"]


def test_browser_automation_skill_can_handle_uses_classifier(monkeypatch):
    skill_module = _load_module(
        "agent.skills.browser_automation_skill",
        os.path.join("agent", "skills", "browser_automation_skill.py"),
    )
    stub = StubClassifier(intent_value=True)
    _patch_classifier(monkeypatch, skill_module, stub)

    skill = skill_module.BrowserAutomationSkill()
    cfg = skill.get_default_config()
    cfg["execution_mode"] = "hybrid"
    skill._config = cfg

    msg = _msg("tira print de google.com", id="browser-1")
    assert asyncio.run(skill.can_handle(msg)) is True


def test_flight_search_skill_can_handle_uses_classifier(monkeypatch):
    skill_module = _load_module(
        "agent.skills.flight_search_skill",
        os.path.join("agent", "skills", "flight_search_skill.py"),
    )
    stub = StubClassifier(intent_value=True)
    _patch_classifier(monkeypatch, skill_module, stub)

    skill = skill_module.FlightSearchSkill()
    cfg = skill.get_default_config()
    cfg["execution_mode"] = "hybrid"
    skill._config = cfg

    msg = _msg("voos GRU LIS amanhã", id="flight-1")
    assert asyncio.run(skill.can_handle(msg)) is True


def test_search_skill_can_handle_uses_classifier(monkeypatch):
    skill_module = _load_module(
        "agent.skills.search_skill",
        os.path.join("agent", "skills", "search_skill.py"),
    )
    stub = StubClassifier(intent_value=True)
    _patch_classifier(monkeypatch, skill_module, stub)

    skill = skill_module.SearchSkill()
    cfg = skill.get_default_config()
    cfg["execution_mode"] = "hybrid"
    skill._config = cfg

    msg = _msg("busca na web pelo Brasil 2026", id="search-1")
    assert asyncio.run(skill.can_handle(msg)) is True


def test_agent_switcher_skill_can_handle_uses_classifier(monkeypatch):
    skill_module = _load_module(
        "agent.skills.agent_switcher_skill",
        os.path.join("agent", "skills", "agent_switcher_skill.py"),
    )
    stub = StubClassifier(intent_value=True)
    _patch_classifier(monkeypatch, skill_module, stub)

    skill = skill_module.AgentSwitcherSkill()
    cfg = skill.get_default_config()
    cfg["execution_mode"] = "hybrid"
    skill._config = cfg

    msg = _msg("invocar agente Tsushin", id="switch-1")
    assert asyncio.run(skill.can_handle(msg)) is True


def test_agent_switcher_skill_skips_slash_commands(monkeypatch):
    """Slash commands are dispatched upstream of can_handle() but the skill's
    own structural guard for '/' is preserved — verifies it still fires."""
    skill_module = _load_module(
        "agent.skills.agent_switcher_skill",
        os.path.join("agent", "skills", "agent_switcher_skill.py"),
    )
    stub = StubClassifier(intent_value=True)
    _patch_classifier(monkeypatch, skill_module, stub)

    skill = skill_module.AgentSwitcherSkill()
    cfg = skill.get_default_config()
    cfg["execution_mode"] = "hybrid"
    skill._config = cfg

    msg = _msg("/switch Tsushin", id="switch-slash-1")
    assert asyncio.run(skill.can_handle(msg)) is False
    assert not stub.intent_calls, "Slash command must short-circuit before LLM call"
