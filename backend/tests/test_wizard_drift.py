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

    # Surface 2: AudioProviderFields.tsx — `FALLBACK_PROVIDER_CARDS` (cards
    # rendered before the live /api/tts-providers fetch resolves) AND
    # `PROVIDER_COPY` (marketing copy keyed by provider id). Both must contain
    # every backend-registered provider so the offline / first-paint UX matches
    # what the backend will serve a moment later.
    fields_path = FRONTEND / "components" / "audio-wizard" / "AudioProviderFields.tsx"
    assert fields_path.exists(), f"AudioProviderFields.tsx not found at {fields_path}"
    fields_text = _read(fields_path)

    fallback_block = re.search(
        r"FALLBACK_PROVIDER_CARDS[^=]*=\s*\[(.*?)\n\]",
        fields_text,
        re.DOTALL,
    )
    assert fallback_block, "FALLBACK_PROVIDER_CARDS not found in AudioProviderFields.tsx"
    fallback_ids = set(re.findall(r"id:\s*'([^']+)'", fallback_block.group(1)))
    missing_in_fallback = registered - fallback_ids
    assert not missing_in_fallback, (
        f"TTS providers registered in backend but missing from "
        f"FALLBACK_PROVIDER_CARDS: {sorted(missing_in_fallback)}. "
        f"Add a card entry in frontend/components/audio-wizard/AudioProviderFields.tsx."
    )

    copy_block = re.search(
        r"PROVIDER_COPY[^=]*=\s*\{(.*?)\n\}",
        fields_text,
        re.DOTALL,
    )
    assert copy_block, "PROVIDER_COPY not found in AudioProviderFields.tsx"
    copy_ids = set(re.findall(r"^\s*([a-z_]+):\s*\{", copy_block.group(1), re.MULTILINE))
    missing_in_copy = registered - copy_ids
    assert not missing_in_copy, (
        f"TTS providers registered in backend but missing from "
        f"PROVIDER_COPY: {sorted(missing_in_copy)}. "
        f"Add a copy entry in frontend/components/audio-wizard/AudioProviderFields.tsx."
    )

    # Surface 3: VOICE_AGENT_DEFAULTS — system-prompt template per provider.
    # If a provider can be picked it needs a default agent template, otherwise
    # the AudioAgentsWizard New-Agent path can't seed sensible defaults.
    defaults_block = re.search(
        r"VOICE_AGENT_DEFAULTS[^=]*=\s*\{(.*?)\n\}",
        text,
        re.DOTALL,
    )
    assert defaults_block, "VOICE_AGENT_DEFAULTS not found in defaults.ts"
    voice_agent_ids = set(re.findall(r"^\s*([a-z_]+):\s*\{", defaults_block.group(1), re.MULTILINE))
    missing_in_voice_agent = registered - voice_agent_ids
    assert not missing_in_voice_agent, (
        f"TTS providers registered in backend but missing from "
        f"VOICE_AGENT_DEFAULTS: {sorted(missing_in_voice_agent)}. "
        f"Add a defaults entry in frontend/components/audio-wizard/defaults.ts."
    )

    # Surface 4: ProviderWizard's TTS_CLOUD + TTS_LOCAL. This is the Hub →
    # Add Provider → modality=tts → hosting picker → vendor list. Historically
    # this list missed OpenAI + Gemini because the registry exposed them but
    # the wizard's hardcoded array only had ElevenLabs / Kokoro — that drift
    # made tenants unable to add Gemini TTS via the standard provider flow
    # despite the backend supporting it.
    pw_path = FRONTEND / "components" / "provider-wizard" / "steps" / "StepVendorSelect.tsx"
    assert pw_path.exists(), f"StepVendorSelect.tsx not found at {pw_path}"
    pw_text = _read(pw_path)

    tts_cloud_block = re.search(
        r"TTS_CLOUD[^=]*=\s*\[(.*?)\n\]",
        pw_text,
        re.DOTALL,
    )
    assert tts_cloud_block, "TTS_CLOUD not found in StepVendorSelect.tsx"
    tts_cloud_ids = set(re.findall(r"id:\s*'([^']+)'", tts_cloud_block.group(1)))

    tts_local_block = re.search(
        r"TTS_LOCAL[^=]*=\s*\[(.*?)\n\]",
        pw_text,
        re.DOTALL,
    )
    assert tts_local_block, "TTS_LOCAL not found in StepVendorSelect.tsx"
    tts_local_ids = set(re.findall(r"id:\s*'([^']+)'", tts_local_block.group(1)))

    pw_combined = tts_cloud_ids | tts_local_ids
    missing_in_pw = registered - pw_combined
    assert not missing_in_pw, (
        f"TTS providers registered in backend but missing from ProviderWizard "
        f"TTS_CLOUD + TTS_LOCAL: {sorted(missing_in_pw)}. "
        f"Add the vendor card in "
        f"frontend/components/provider-wizard/steps/StepVendorSelect.tsx."
    )

    # Surface 5: ProviderWizard's StepProgress save branch. Cloud TTS providers
    # whose key is persisted via /api/api-keys (i.e. NOT Kokoro, which has its
    # own TTSInstance path) must be enumerated in the save-branch condition,
    # otherwise the wizard finalize step will silently fall through to the LLM
    # /api/provider-instances path, which then 400s on missing available_models.
    progress_path = FRONTEND / "components" / "provider-wizard" / "steps" / "StepProgress.tsx"
    assert progress_path.exists(), f"StepProgress.tsx not found at {progress_path}"
    progress_text = _read(progress_path)

    # Look for the TTS-cloud branch condition. Format: a guard clause referencing
    # `draft.modality === 'tts'` plus an OR-chain of `draft.vendor === '<id>'`.
    save_branch = re.search(
        r"draft\.modality\s*===\s*'tts'\s*&&\s*\(([^)]+)\)",
        progress_text,
    )
    assert save_branch, (
        "Could not locate the cloud-TTS save branch in StepProgress.tsx — "
        "if you refactored the conditional shape, update this regex."
    )
    save_vendor_ids = set(re.findall(r"draft\.vendor\s*===\s*'([^']+)'", save_branch.group(1)))

    cloud_tts = registered - {"kokoro"}  # Kokoro has its own TTSInstance path
    missing_in_save = cloud_tts - save_vendor_ids
    assert not missing_in_save, (
        f"Cloud TTS providers in backend registry but missing from the cloud "
        f"save branch in StepProgress.tsx: {sorted(missing_in_save)}. The "
        f"save will silently fall through to the LLM provider-instances path "
        f"and 400 on missing available_models. Add the vendor to the OR-chain."
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


# ---------------------------------------------------------------------------
# Guard 4 — memory_isolation_mode literal consolidation
# ---------------------------------------------------------------------------

# Sites that historically hardcoded the literal tuple/regex for
# memory_isolation_mode. After consolidation they must import from
# constants.agent_config instead of repeating the literal tuple.
# Paths are relative to the backend package root — resolved against the
# host repo layout (`REPO_ROOT/backend/...`) or the container layout
# (`/app/...`, i.e. the parent of this test file's dir) at runtime.
_MEMORY_ISOLATION_SITES = (
    "api/v1/routes_studio.py",
    "api/routes_agent_builder.py",
    "api/v1/routes_agents.py",
    "models.py",
)


def _resolve_backend_site(rel_path: str) -> Path:
    """Return the absolute path to ``rel_path`` inside the backend package,
    regardless of whether the test runs from the host repo or inside the
    backend container (where the backend lives at ``/app``)."""
    # Host layout: <repo_root>/backend/<rel_path>
    host_path = REPO_ROOT / "backend" / rel_path
    if host_path.exists():
        return host_path
    # Container layout: parent of tests dir == backend package root (/app)
    container_path = Path(__file__).resolve().parents[1] / rel_path
    return container_path


# Regex intentionally tolerant of single OR double quotes and whitespace
# variations; matches the historical tuple literal regardless of style.
_MEMORY_ISOLATION_TUPLE_RE = re.compile(
    r"\(\s*['\"]isolated['\"]\s*,\s*['\"]shared['\"]\s*,\s*['\"]channel_isolated['\"]\s*\)"
)

# Historical regex-form used in the Pydantic Field pattern.
_MEMORY_ISOLATION_REGEX_LITERAL = re.compile(
    r"\^\(\s*isolated\s*\|\s*shared\s*\|\s*channel_isolated\s*\)\$"
)


def test_memory_isolation_modes_constant_source_of_truth():
    """
    MEMORY_ISOLATION_MODES must be the single source of truth. The constant
    itself must remain exactly ("isolated", "shared", "channel_isolated") —
    if you're adding a 4th mode, update this test and every consumer in one
    sweep so nothing silently diverges.
    """
    from constants.agent_config import MEMORY_ISOLATION_MODES

    assert MEMORY_ISOLATION_MODES == ("isolated", "shared", "channel_isolated"), (
        f"MEMORY_ISOLATION_MODES drifted: {MEMORY_ISOLATION_MODES!r}. "
        f"Update this test and audit all consumers if adding/removing a mode."
    )


def test_memory_isolation_literal_not_duplicated():
    """
    The 4 historical sites that hardcoded ('isolated', 'shared',
    'channel_isolated') — inline validation guards in routes, the Pydantic
    Field pattern, and the models.py column comment — must now reference
    MEMORY_ISOLATION_MODES instead of repeating the literal tuple / regex.
    """
    for rel_path in _MEMORY_ISOLATION_SITES:
        path = _resolve_backend_site(rel_path)
        assert path.exists(), f"Expected {path} to exist (rel={rel_path})"
        text = _read(path)

        tuple_hits = _MEMORY_ISOLATION_TUPLE_RE.findall(text)
        assert not tuple_hits, (
            f"{rel_path} still hardcodes the memory_isolation_mode literal "
            f"tuple ('isolated', 'shared', 'channel_isolated'). Import "
            f"MEMORY_ISOLATION_MODES from constants.agent_config instead."
        )

        regex_hits = _MEMORY_ISOLATION_REGEX_LITERAL.findall(text)
        assert not regex_hits, (
            f"{rel_path} still hardcodes the memory_isolation_mode pattern "
            f"regex '^(isolated|shared|channel_isolated)$'. Build it "
            f"dynamically from MEMORY_ISOLATION_MODES instead."
        )


# ---------------------------------------------------------------------------
# Guard 5 — Channel catalog drift
# ---------------------------------------------------------------------------

def test_channel_catalog_frontend_fallback_matches_backend():
    """
    Every channel registered in ``backend/channels/catalog.CHANNEL_CATALOG``
    must also appear in the frontend fallback array inside
    ``frontend/components/agent-wizard/steps/StepChannels.tsx``. The frontend
    uses that array when the live ``/api/channels`` fetch fails; drift means
    an outage would hide a channel that the wizard otherwise supports.

    Also asserts every backend entry carries a non-empty display_name so a
    silently-blank UI card can't ship.
    """
    from channels.catalog import CHANNEL_CATALOG

    assert CHANNEL_CATALOG, "CHANNEL_CATALOG is empty — registration broken?"

    backend_ids: Set[str] = set()
    for ch in CHANNEL_CATALOG:
        assert ch.id, "Channel with missing id in CHANNEL_CATALOG"
        assert ch.display_name and ch.display_name.strip(), (
            f"Channel {ch.id!r} has empty display_name — every wizard card "
            f"needs a human-readable label."
        )
        backend_ids.add(ch.id)

    step_path = FRONTEND / "components" / "agent-wizard" / "steps" / "StepChannels.tsx"
    assert step_path.exists(), f"StepChannels.tsx not found at {step_path}"
    text = _read(step_path)

    fallback_match = re.search(
        r"const CHANNELS:\s*\{[^}]*\}\[\]\s*=\s*\[(.*?)\n\]",
        text,
        re.DOTALL,
    )
    assert fallback_match, (
        "Fallback CHANNELS array not found in StepChannels.tsx. If you "
        "refactored the fallback shape, update this regex too."
    )
    frontend_ids = set(re.findall(r"id:\s*'([^']+)'", fallback_match.group(1)))

    missing_in_frontend = backend_ids - frontend_ids
    extra_in_frontend = frontend_ids - backend_ids

    assert not missing_in_frontend, (
        f"Channels registered in backend CHANNEL_CATALOG are missing from "
        f"the frontend fallback in StepChannels.tsx: "
        f"{sorted(missing_in_frontend)}. Add matching entries to the "
        f"CHANNELS array so offline/degraded mode still renders them."
    )
    assert not extra_in_frontend, (
        f"Channels present in StepChannels.tsx fallback but not in backend "
        f"CHANNEL_CATALOG: {sorted(extra_in_frontend)}. Either register "
        f"them in backend/channels/catalog.py or remove them from the "
        f"frontend fallback."
    )


# ---------------------------------------------------------------------------
# Guard 6 — Provider vendor catalog drift
# ---------------------------------------------------------------------------

def test_provider_vendors_frontend_fallback_matches_backend():
    """
    The static VENDORS fallback in ProviderInstanceModal.tsx must cover the
    same vendor IDs as backend VALID_VENDORS / SUPPORTED_VENDORS. When the
    live /api/providers/vendors fetch fails (offline/degraded mode), the modal
    falls back to this array — if it drifts, a new vendor won't appear in the
    dropdown on a degraded tenant.
    """
    from api.routes_provider_instances import VALID_VENDORS, VENDOR_DISPLAY_NAMES
    from services.provider_instance_service import SUPPORTED_VENDORS

    # Backend-side parity: the two backend sets must agree, and every
    # backend vendor needs a display name so the endpoint has something to
    # return.
    assert set(SUPPORTED_VENDORS) == VALID_VENDORS, (
        f"Backend vendor set drift: SUPPORTED_VENDORS={sorted(SUPPORTED_VENDORS)} "
        f"vs VALID_VENDORS={sorted(VALID_VENDORS)}. Keep these aligned — "
        f"VALID_VENDORS gates POST /provider-instances and SUPPORTED_VENDORS "
        f"gates ProviderInstanceService.create_instance."
    )
    missing_display = VALID_VENDORS - set(VENDOR_DISPLAY_NAMES.keys())
    assert not missing_display, (
        f"Vendors missing from VENDOR_DISPLAY_NAMES: {sorted(missing_display)}. "
        f"Add a human-readable label so /api/providers/vendors returns it."
    )

    modal_path = FRONTEND / "components" / "providers" / "ProviderInstanceModal.tsx"
    assert modal_path.exists(), f"ProviderInstanceModal.tsx not found at {modal_path}"
    text = _read(modal_path)

    # Match the static fallback array entries: `{ id: 'openai', ... }`.
    fallback_block = re.search(
        r"const VENDORS:\s*VendorInfo\[\]\s*=\s*\[(.*?)\n\]",
        text,
        re.DOTALL,
    )
    assert fallback_block, (
        "Static VENDORS: VendorInfo[] fallback array not found in "
        "ProviderInstanceModal.tsx. The modal must keep a fallback for "
        "offline/degraded mode — if you removed it, add it back."
    )
    frontend_ids = set(re.findall(r"id:\s*'([^']+)'", fallback_block.group(1)))

    missing_in_frontend = VALID_VENDORS - frontend_ids
    extra_in_frontend = frontend_ids - VALID_VENDORS

    assert not missing_in_frontend, (
        f"Vendors in backend VALID_VENDORS missing from frontend VENDORS "
        f"fallback: {sorted(missing_in_frontend)}. Add them to "
        f"ProviderInstanceModal.tsx — otherwise degraded-mode users can't "
        f"pick the vendor."
    )
    assert not extra_in_frontend, (
        f"Vendors in frontend VENDORS fallback missing from backend "
        f"VALID_VENDORS: {sorted(extra_in_frontend)}. Either register the "
        f"vendor backend-side or drop it from the fallback."
    )


# ---------------------------------------------------------------------------
# Guard 7 — Ollama curated models shared-module single-source
# ---------------------------------------------------------------------------

def test_ollama_curated_models_imported_from_shared_module():
    """
    Both the Hub Ollama panel (frontend/app/hub/page.tsx) and the Ollama
    setup wizard (frontend/components/ollama/OllamaSetupWizard.tsx) must
    import their curated model list from frontend/lib/ollama-curated-models
    — not redeclare it inline. This prevents the two surfaces from offering
    different model catalogs.
    """
    shared_path = FRONTEND / "lib" / "ollama-curated-models.ts"
    assert shared_path.exists(), (
        f"Shared Ollama curated-models module missing at {shared_path}. "
        f"Both the Hub panel and the setup wizard depend on it."
    )
    shared_text = _read(shared_path)
    assert "export const OLLAMA_CURATED_MODELS" in shared_text, (
        "OLLAMA_CURATED_MODELS export missing from "
        "frontend/lib/ollama-curated-models.ts."
    )
    # At least the historically-curated 7 models must be present.
    shared_ids = set(re.findall(r"id:\s*'([^']+)'", shared_text))
    expected_min = {
        "llama3.2:1b", "llama3.2:3b", "qwen2.5:3b", "qwen2.5:7b",
        "deepseek-r1:7b", "phi3.5:3.8b", "mistral:7b",
    }
    missing = expected_min - shared_ids
    assert not missing, (
        f"Historically-curated Ollama models missing from shared module: "
        f"{sorted(missing)}. Don't remove the base curation without "
        f"updating this guard."
    )

    # Both call-sites must import from the shared module (not redeclare).
    wizard_path = FRONTEND / "components" / "ollama" / "OllamaSetupWizard.tsx"
    hub_path = FRONTEND / "app" / "hub" / "page.tsx"

    for path, expected_symbol in (
        (wizard_path, "OLLAMA_CURATED_MODELS"),
        (hub_path, "OLLAMA_CURATED_MODEL_IDS"),
    ):
        assert path.exists(), f"{path} not found"
        text = _read(path)
        import_ok = re.search(
            r"from\s+['\"][^'\"]*ollama-curated-models['\"]",
            text,
        )
        assert import_ok, (
            f"{path.name} does not import from lib/ollama-curated-models. "
            f"Redeclaring the curated model list re-introduces the drift "
            f"this guard was written to prevent."
        )
        assert expected_symbol in text, (
            f"{path.name} does not reference {expected_symbol} from the "
            f"shared module."
        )


# ---------------------------------------------------------------------------
# Guard — AddIntegrationWizard provider catalog drift (search + travel)
# ---------------------------------------------------------------------------

def _addintegration_fallback_ids() -> Set[str]:
    """
    Parse ``frontend/components/integrations/AddIntegrationWizard.tsx`` and
    return the set of provider ids in the ``FALLBACK_PROVIDERS`` array.

    This helper is used by both the search-provider and flight-provider
    drift guards below.
    """
    wizard_path = FRONTEND / "components" / "integrations" / "AddIntegrationWizard.tsx"
    assert wizard_path.exists(), f"AddIntegrationWizard.tsx not found at {wizard_path}"
    text = _read(wizard_path)

    block = re.search(
        r"FALLBACK_PROVIDERS:\s*ProviderMeta\[\]\s*=\s*\[(.*?)^\]",
        text,
        re.DOTALL | re.MULTILINE,
    )
    assert block, "FALLBACK_PROVIDERS array not found in AddIntegrationWizard.tsx"
    return set(re.findall(r"id:\s*'([^']+)'", block.group(1)))


def test_search_providers_registered_match_wizard_fallback():
    """
    Every provider registered in ``SearchProviderRegistry`` must also appear
    in the ``FALLBACK_PROVIDERS`` array of
    ``frontend/components/integrations/AddIntegrationWizard.tsx``. The wizard
    fetches the live catalog from ``/api/hub/search-providers`` at mount but
    falls back to this static array when that endpoint is unreachable —
    so the fallback must stay in lockstep with the backend registry.
    """
    from hub.providers.search_registry import SearchProviderRegistry

    SearchProviderRegistry.initialize_providers()
    registered = set(SearchProviderRegistry.get_registered_providers())
    assert registered, "SearchProviderRegistry came up empty — registration broken?"

    fallback_ids = _addintegration_fallback_ids()

    missing_in_frontend = registered - fallback_ids
    assert not missing_in_frontend, (
        f"Search providers registered in backend SearchProviderRegistry are "
        f"missing from the AddIntegrationWizard fallback array: "
        f"{sorted(missing_in_frontend)}. Add matching rows to "
        f"frontend/components/integrations/AddIntegrationWizard.tsx so "
        f"offline/degraded mode still renders them."
    )


def test_flight_providers_registered_match_wizard_fallback():
    """
    Every provider registered in ``FlightProviderRegistry`` must also appear
    in the ``FALLBACK_PROVIDERS`` array of AddIntegrationWizard. Same
    rationale as the search-provider guard above.
    """
    from hub.providers.registry import FlightProviderRegistry

    FlightProviderRegistry.initialize_providers()
    registered = set(FlightProviderRegistry.get_registered_providers())
    assert registered, "FlightProviderRegistry came up empty — registration broken?"

    fallback_ids = _addintegration_fallback_ids()

    missing_in_frontend = registered - fallback_ids
    assert not missing_in_frontend, (
        f"Flight providers registered in backend FlightProviderRegistry are "
        f"missing from the AddIntegrationWizard fallback array: "
        f"{sorted(missing_in_frontend)}. Add matching rows to "
        f"frontend/components/integrations/AddIntegrationWizard.tsx."
    )


# ---------------------------------------------------------------------------
# Guard 8 — Productivity catalog drift
# ---------------------------------------------------------------------------

def test_productivity_catalog_frontend_fallback_matches_backend():
    """
    Every service in ``backend/hub/productivity_catalog.PRODUCTIVITY_CATALOG``
    must have a matching entry in the ``FALLBACK_SERVICES`` array inside
    ``frontend/components/integrations/ProductivityWizard.tsx``. The wizard
    renders the fallback when the live ``/api/hub/productivity-services``
    fetch fails (offline/degraded boot), and drift would mean a service
    registered in the backend catalog is invisible in the picker.

    Also asserts every backend entry carries a non-empty display_name and a
    recognised category so a silently-blank or mis-categorised card can't
    ship.
    """
    from hub.productivity_catalog import PRODUCTIVITY_CATALOG

    assert PRODUCTIVITY_CATALOG, "PRODUCTIVITY_CATALOG is empty — registration broken?"

    valid_categories = {"calendar", "email", "tasks", "knowledge_base"}
    backend_ids: Set[str] = set()
    for svc in PRODUCTIVITY_CATALOG:
        assert svc.id, "Productivity entry with missing id"
        assert svc.display_name and svc.display_name.strip(), (
            f"Productivity entry {svc.id!r} has empty display_name."
        )
        assert svc.category in valid_categories, (
            f"Productivity entry {svc.id!r} has unknown category "
            f"{svc.category!r}. Allowed: {sorted(valid_categories)}."
        )
        backend_ids.add(svc.id)

    wizard_path = FRONTEND / "components" / "integrations" / "ProductivityWizard.tsx"
    assert wizard_path.exists(), f"ProductivityWizard.tsx not found at {wizard_path}"
    text = _read(wizard_path)

    fallback_match = re.search(
        r"const FALLBACK_SERVICES[^=]*=\s*\[(.*?)\n\]",
        text,
        re.DOTALL,
    )
    assert fallback_match, (
        "Fallback FALLBACK_SERVICES array not found in ProductivityWizard.tsx. "
        "If you refactored the fallback shape, update this regex too."
    )
    frontend_ids = set(re.findall(r"id:\s*'([^']+)'", fallback_match.group(1)))

    missing_in_frontend = backend_ids - frontend_ids
    extra_in_frontend = frontend_ids - backend_ids

    assert not missing_in_frontend, (
        f"Productivity services registered in backend PRODUCTIVITY_CATALOG "
        f"are missing from the frontend FALLBACK_SERVICES array in "
        f"ProductivityWizard.tsx: {sorted(missing_in_frontend)}. Add matching "
        f"entries so offline mode still renders them."
    )
    assert not extra_in_frontend, (
        f"Services present in ProductivityWizard.tsx fallback but not in "
        f"backend PRODUCTIVITY_CATALOG: {sorted(extra_in_frontend)}. Either "
        f"register them in backend/hub/productivity_catalog.py or remove "
        f"from the frontend fallback."
    )


# ---------------------------------------------------------------------------
# Guard 9 — ChannelsWizard fallback vs. backend channel catalog
# ---------------------------------------------------------------------------

def test_channels_wizard_fallback_matches_backend():
    """
    Sibling to Guard 5. Guard 5 asserts the Agent Wizard's StepChannels
    fallback matches backend CHANNEL_CATALOG; this one does the same for the
    Hub > Communication tab's ChannelsWizard (the "+ Add Channel" launcher).
    The two fallbacks aren't literally the same array — ChannelsWizard drops
    'playground' (not actionable from the Hub) and adds 'gmail' (inbound
    email-as-channel) — but every *actionable* channel id registered in
    CHANNEL_CATALOG must appear in the ChannelsWizard fallback.
    """
    from channels.catalog import CHANNEL_CATALOG

    actionable_backend_ids = {ch.id for ch in CHANNEL_CATALOG if ch.requires_setup}

    wizard_path = FRONTEND / "components" / "integrations" / "ChannelsWizard.tsx"
    assert wizard_path.exists(), f"ChannelsWizard.tsx not found at {wizard_path}"
    text = _read(wizard_path)

    fallback_match = re.search(
        r"const FALLBACK_CHANNELS[^=]*=\s*\[(.*?)\n\]",
        text,
        re.DOTALL,
    )
    assert fallback_match, (
        "Fallback FALLBACK_CHANNELS array not found in ChannelsWizard.tsx. "
        "If you refactored the fallback shape, update this regex too."
    )
    # ``id: '…'`` fields — the wizard's channel_id (typed union) mirrors id.
    frontend_ids = set(re.findall(r"id:\s*'([^']+)'", fallback_match.group(1)))

    missing_in_wizard = actionable_backend_ids - frontend_ids
    assert not missing_in_wizard, (
        f"Actionable channels in backend CHANNEL_CATALOG are missing from "
        f"the ChannelsWizard FALLBACK_CHANNELS array: "
        f"{sorted(missing_in_wizard)}. Every channel the backend accepts "
        f"setup for must also be offered in the + Add Channel launcher."
    )

    # The wizard is allowed to include channels beyond CHANNEL_CATALOG (e.g.
    # 'gmail' which is a productivity service re-exposed as an inbound
    # channel). Enforce the extras stay on an explicit allowlist so new
    # drift doesn't slip in under this exception.
    wizard_extras = frontend_ids - actionable_backend_ids
    allowed_extras = {"gmail"}
    unexpected_extras = wizard_extras - allowed_extras
    assert not unexpected_extras, (
        f"ChannelsWizard fallback has channel ids not in CHANNEL_CATALOG "
        f"and not on the extras allowlist ({sorted(allowed_extras)}): "
        f"{sorted(unexpected_extras)}. Either register them in "
        f"backend/channels/catalog.py or extend the allowlist in this test."
    )


# ---------------------------------------------------------------------------
# Guard 10 — Gemini TTS model catalog drift
# ---------------------------------------------------------------------------

def test_gemini_tts_models_frontend_fallback_matches_backend():
    """
    GeminiTTSProvider.SUPPORTED_MODELS is the authoritative catalog of Gemini
    TTS preview models. The frontend's offline fallback in
    `frontend/components/audio-wizard/defaults.ts` (`GEMINI_TTS_MODELS`) must
    list the same model_ids — otherwise a degraded /api/tts-providers/gemini/models
    response will surface a different set than what the backend can actually
    invoke, causing silent fallback to the default model on save.
    """
    from hub.providers.gemini_tts_provider import GeminiTTSProvider

    backend_models = set(GeminiTTSProvider.SUPPORTED_MODELS.keys())
    assert backend_models, "GeminiTTSProvider.SUPPORTED_MODELS is empty"
    assert GeminiTTSProvider.DEFAULT_MODEL in backend_models, (
        f"DEFAULT_MODEL='{GeminiTTSProvider.DEFAULT_MODEL}' is not in SUPPORTED_MODELS"
    )

    defaults_path = FRONTEND / "components" / "audio-wizard" / "defaults.ts"
    assert defaults_path.exists(), f"defaults.ts not found at {defaults_path}"
    text = _read(defaults_path)

    block = re.search(
        r"GEMINI_TTS_MODELS[^=]*=\s*\[(.*?)\n\]",
        text,
        re.DOTALL,
    )
    assert block, (
        "GEMINI_TTS_MODELS array not found in defaults.ts. If you renamed it, "
        "update this regex too."
    )
    frontend_models = set(re.findall(r"id:\s*'([^']+)'", block.group(1)))

    assert backend_models == frontend_models, (
        f"GEMINI_TTS_MODELS drift: backend SUPPORTED_MODELS={sorted(backend_models)}, "
        f"frontend GEMINI_TTS_MODELS={sorted(frontend_models)}. "
        f"Add/remove the matching entry in defaults.ts."
    )

    # Default-model constant in defaults.ts must match the backend default.
    default_match = re.search(
        r"GEMINI_TTS_DEFAULT_MODEL\s*=\s*'([^']+)'",
        text,
    )
    assert default_match, "GEMINI_TTS_DEFAULT_MODEL constant missing in defaults.ts"
    assert default_match.group(1) == GeminiTTSProvider.DEFAULT_MODEL, (
        f"Default model drift: backend='{GeminiTTSProvider.DEFAULT_MODEL}', "
        f"frontend='{default_match.group(1)}'."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
