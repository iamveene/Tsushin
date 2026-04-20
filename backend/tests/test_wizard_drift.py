"""
Wizard drift guards — assert frontend-hardcoded catalog arrays don't silently
drift from the backend registries that serve the same catalogs at runtime.

Context: the Tsushin Agent Wizard / Audio Wizard / Onboarding Wizard increasingly
fetch their catalogs (skills, TTS providers, TTS voices) from the backend at
runtime. Static fallback arrays live in the frontend for offline / degraded mode.
These tests read the fallback arrays as text and cross-check them against the
backend registries so an added skill or TTS provider never ships with the
fallback copy missing the new entry.

These tests are intentionally lightweight — they parse frontend TS files as
text rather than executing them. Run with:

    docker exec tsushin-backend pytest backend/tests/test_wizard_drift.py -v

Or directly on the host (requires the Python deps available to pytest):

    pytest backend/tests/test_wizard_drift.py -v
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Set

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "frontend"

# Skills intentionally hidden from the wizard (require post-creation setup
# the wizard doesn't collect inline). Must match the BaseSkill subclass attr.
WIZARD_HIDDEN_SKILLS: Set[str] = {"gmail", "shell", "flows", "agent_communication"}

# TTS provider IDs registered at startup in TTSProviderRegistry.initialize_providers().
# If you add a provider there, add its ID here AND ensure a matching entry exists
# in frontend/components/audio-wizard/defaults.ts (the fallback list).
EXPECTED_TTS_PROVIDERS: Set[str] = {"openai", "kokoro", "elevenlabs", "gemini"}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Guard 1 — Skill catalog drift
# ---------------------------------------------------------------------------

def test_skill_catalog_frontend_matches_backend_registry():
    """
    Every skill registered by SkillManager._register_builtin_skills must also
    have a matching SKILL_DISPLAY_INFO entry in
    `frontend/components/skills/skill-constants.ts`. This is the catalog the
    frontend Agent Studio + wizard render from.

    This catches the recurring bug where a new skill is added to the backend
    but the frontend skill card / wizard row is never updated.
    """
    from agent.skills.skill_manager import SkillManager

    sm = SkillManager()
    backend_types = set(sm.registry.keys())

    constants_path = FRONTEND / "components" / "skills" / "skill-constants.ts"
    assert constants_path.exists(), f"skill-constants.ts not found at {constants_path}"
    text = _read(constants_path)

    # Match top-level keys of the SKILL_DISPLAY_INFO dict. Format:
    #   foo_bar: {
    # or
    #   foo_bar: {...
    # Intentionally forgiving regex; we care about presence, not syntax.
    info_block = re.search(
        r"SKILL_DISPLAY_INFO:\s*Record<[^>]+>\s*=\s*\{(.*?)\n\}",
        text,
        re.DOTALL,
    )
    assert info_block, "SKILL_DISPLAY_INFO block not found in skill-constants.ts"
    frontend_types = set(re.findall(r"^\s{2}(\w+):\s*\{", info_block.group(1), re.MULTILINE))

    # HIDDEN_SKILLS declared in the same file — allowed to be absent from
    # backend registry (they're explicitly removed from the system).
    hidden_match = re.search(r"HIDDEN_SKILLS\s*=\s*new Set<string>\(\[([^\]]*)\]\)", text)
    hidden: Set[str] = set()
    if hidden_match:
        hidden = set(re.findall(r"'([^']+)'", hidden_match.group(1)))

    missing_in_frontend = backend_types - frontend_types - hidden
    extra_in_frontend = frontend_types - backend_types - hidden

    assert not missing_in_frontend, (
        f"Skills registered in backend SkillManager are missing from frontend "
        f"SKILL_DISPLAY_INFO: {sorted(missing_in_frontend)}. "
        f"Add matching entries to frontend/components/skills/skill-constants.ts."
    )
    assert not extra_in_frontend, (
        f"Skills present in frontend SKILL_DISPLAY_INFO but not registered in "
        f"backend SkillManager: {sorted(extra_in_frontend)}. "
        f"Either register the skill or add it to HIDDEN_SKILLS."
    )


def test_skill_wizard_visible_matches_expected_hidden_set():
    """
    Sanity check on wizard_visible overrides — the set of skills whose
    wizard_visible=False matches the expected WIZARD_HIDDEN_SKILLS constant at
    the top of this file. If you add wizard_visible=False to a skill, add the
    skill_type to WIZARD_HIDDEN_SKILLS; if you remove it, remove it here too.
    """
    from agent.skills.skill_manager import SkillManager

    sm = SkillManager()
    hidden = {
        skill_type
        for skill_type, cls in sm.registry.items()
        if not getattr(cls, "wizard_visible", True)
    }
    assert hidden == WIZARD_HIDDEN_SKILLS, (
        f"wizard_visible drift: backend says hidden={sorted(hidden)}, "
        f"test expects {sorted(WIZARD_HIDDEN_SKILLS)}. Update either the "
        f"skill class or WIZARD_HIDDEN_SKILLS in this test."
    )


# ---------------------------------------------------------------------------
# Guard 2 — TTS provider catalog drift
# ---------------------------------------------------------------------------

def test_tts_providers_registered_match_frontend_fallback():
    """
    Every TTS provider registered in TTSProviderRegistry must have a matching
    entry in the AudioProvider type union (frontend/components/audio-wizard/defaults.ts)
    so the wizard's static fallback can render the provider before the
    /api/tts-providers live fetch resolves.
    """
    from hub.providers.tts_registry import TTSProviderRegistry

    TTSProviderRegistry.initialize_providers()
    registered = set(TTSProviderRegistry.get_registered_providers())
    assert registered, "TTSProviderRegistry came up empty — registration broken?"

    # Confirm the expected set matches — if you add a provider, update
    # EXPECTED_TTS_PROVIDERS at the top.
    assert registered == EXPECTED_TTS_PROVIDERS, (
        f"TTS provider registry drift: registered={sorted(registered)}, "
        f"test expects {sorted(EXPECTED_TTS_PROVIDERS)}. Update "
        f"EXPECTED_TTS_PROVIDERS in this test (and the frontend fallback) "
        f"when adding/removing a TTS provider."
    )

    defaults_path = FRONTEND / "components" / "audio-wizard" / "defaults.ts"
    assert defaults_path.exists(), f"audio-wizard/defaults.ts not found at {defaults_path}"
    text = _read(defaults_path)

    type_match = re.search(r"export type AudioProvider\s*=\s*([^\n]+)", text)
    assert type_match, "AudioProvider type union not found in defaults.ts"
    frontend_union = set(re.findall(r"'([^']+)'", type_match.group(1)))

    missing_in_frontend = registered - frontend_union
    assert not missing_in_frontend, (
        f"TTS providers registered in backend but missing from frontend "
        f"AudioProvider union: {sorted(missing_in_frontend)}. "
        f"Update frontend/components/audio-wizard/defaults.ts."
    )


# ---------------------------------------------------------------------------
# Guard 3 — PREDEFINED_MODELS single source of truth
# ---------------------------------------------------------------------------

def test_predefined_models_single_source():
    """
    PREDEFINED_MODELS lives in backend/api/routes_provider_instances.py and is
    re-exported by backend/services/model_discovery_service.py. Assert the
    re-export is identity — drift re-introduces the historical Gemini-list
    divergence this test was written to prevent.
    """
    from api.routes_provider_instances import PREDEFINED_MODELS as A
    from services.model_discovery_service import PREDEFINED_MODELS as B
    assert A is B, (
        "services.model_discovery_service.PREDEFINED_MODELS is no longer the "
        "same object as api.routes_provider_instances.PREDEFINED_MODELS. "
        "Someone reintroduced a parallel copy — remove it and re-import."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
