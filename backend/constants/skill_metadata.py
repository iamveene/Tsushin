"""Single source of truth for agent-skill display metadata and validation.

This module exists because three different route files used to maintain their
own copy of ``SKILL_METADATA``. When a new skill was registered in
``SkillManager._register_builtin_skills`` (e.g. ``password_vault``,
``okg_term_memory``, ``ticket_management``, ``code_repository``) but the
duplicate dicts were not updated, the validators in those routes would reject
saves for any agent that already carried such a skill — producing errors like
``invalid skill_type: password_vault`` while editing an unrelated skill.

Layout:
- ``SKILL_METADATA`` carries display-only metadata (category, name,
  description). It is keyed by the canonical ``skill_type`` plus a few legacy
  display aliases ("scheduler", "calendar", "asana", "email") that the Graph
  View uses to relabel ``flows`` / ``gmail`` rows that have a specific
  integration provider.
- ``LEGACY_ALIAS_SKILL_TYPES`` lists the aliases that are accepted as valid
  ``skill_type`` payload values for backward compatibility with rows persisted
  before the canonical names settled. They are not registered as separate
  skill classes in ``SkillManager``.
- ``get_valid_skill_types()`` derives the validator allow-list from the live
  ``SkillManager`` registry plus the aliases — so adding a skill in
  ``skill_manager.py`` automatically opens it for save endpoints.
"""

from __future__ import annotations

from typing import Dict, Set


# Display metadata — keyed by skill_type. Keys must include every registered
# skill in SkillManager (verified by tests/test_skill_registry_integrity.py).
SKILL_METADATA: Dict[str, Dict[str, str]] = {
    # Search
    "web_search": {"category": "search", "name": "Web Search", "description": "Search the web for information"},
    # Audio
    "audio_transcript": {"category": "audio", "name": "Audio Transcript", "description": "Transcribe audio to text"},
    "audio_tts": {"category": "audio", "name": "Text to Speech", "description": "Convert text to speech"},
    # Email — gmail is canonical; "email" is a display alias kept for Graph View
    "gmail": {"category": "email", "name": "Email", "description": "Read and send emails"},
    "email": {"category": "email", "name": "Email", "description": "Read and send emails"},
    # Scheduler/Flows — "flows" is canonical, "scheduler" / "calendar" / "asana"
    # are display aliases the Graph View promotes based on the bound provider.
    "flows": {"category": "automation", "name": "Flows", "description": "Execute automation flows"},
    "scheduler": {"category": "scheduler", "name": "Scheduler", "description": "Schedule events and reminders"},
    "calendar": {"category": "integration", "name": "Calendar", "description": "Manage calendar events"},
    "asana": {"category": "integration", "name": "Asana", "description": "Manage Asana tasks"},
    # Automation
    "automation": {"category": "automation", "name": "Automation", "description": "Multi-step workflow automation"},
    "browser_automation": {"category": "automation", "name": "Browser Automation", "description": "Control web browsers"},
    "shell": {"category": "automation", "name": "Shell", "description": "Execute shell commands"},
    "sandboxed_tools": {"category": "automation", "name": "Sandboxed Tools", "description": "Execute tools in sandboxed environment"},
    # Media
    "image_analysis": {"category": "media", "name": "Image Analysis", "description": "Interpret and extract information from attached images"},
    "image": {"category": "media", "name": "Image Generation", "description": "Generate and edit images"},
    # Travel
    "flight_search": {"category": "flight_search", "name": "Flight Search", "description": "Search for flights"},
    # Behavior / inter-agent
    "adaptive_personality": {"category": "special", "name": "Adaptive Personality", "description": "Dynamic tone adaptation"},
    "knowledge_sharing": {"category": "special", "name": "Knowledge Sharing", "description": "Share knowledge across agents"},
    "agent_switcher": {"category": "special", "name": "Agent Switcher", "description": "Switch between agents in DM"},
    "agent_communication": {"category": "special", "name": "Agent Communication", "description": "Ask other agents questions or delegate tasks"},
    # Memory
    "okg_term_memory": {"category": "memory", "name": "OKG Term Memory", "description": "Structured long-term memory"},
    "find_similar_past_cases": {"category": "memory", "name": "Trigger Case Memory", "description": "Recall similar past cases for trigger context"},
    "team_scratch": {"category": "memory", "name": "Team Scratch", "description": "Shared scratchpad for agent team runs"},
    # Provider-backed skills
    "ticket_management": {"category": "integration", "name": "Ticket Management", "description": "Search and act on tickets (Jira)"},
    "code_repository": {"category": "integration", "name": "Code Repository", "description": "Browse and act on code repositories — repos, PRs, issues, branches, commits, and GitHub Projects boards (GitHub/GitLab)"},
    "password_vault": {"category": "integration", "name": "Password Vault", "description": "Reference secrets from a connected vault (1Password)"},
}


# Aliases that some routes accept as ``skill_type`` payload values for backward
# compatibility, in addition to the canonical names registered in SkillManager.
LEGACY_ALIAS_SKILL_TYPES: Set[str] = {"email", "calendar", "asana"}


# Skill types intentionally excluded from agent-builder/Studio surfaces — the
# UI does not let users add or remove these directly.
EXCLUDED_SKILL_TYPES: Set[str] = {"automation"}


def get_skill_metadata(skill_type: str) -> Dict[str, str]:
    """Return display metadata for a skill_type with a safe synthetic default."""
    return SKILL_METADATA.get(skill_type, {
        "category": "other",
        "name": skill_type.replace("_", " ").title(),
        "description": f"Agent skill: {skill_type}",
    })


def get_valid_skill_types() -> Set[str]:
    """Return the canonical allow-list of ``skill_type`` payload values.

    Derived from the live SkillManager registry plus legacy aliases, so newly
    registered skills automatically pass save-endpoint validation.
    """
    # Local import — SkillManager imports models / SQLAlchemy and we want
    # ``constants.skill_metadata`` to stay import-safe at module-load time.
    from agent.skills import get_skill_manager

    return get_skill_manager().get_registered_skill_types() | LEGACY_ALIAS_SKILL_TYPES
