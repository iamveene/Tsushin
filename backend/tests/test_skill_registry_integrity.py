"""Guardrail tests for the skill metadata / validator contract.

These exist because the system previously kept three duplicate
``SKILL_METADATA`` dicts in three different route files, which drifted out of
sync with ``SkillManager._register_builtin_skills`` and produced
``invalid skill_type: password_vault`` errors on save.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_every_registered_skill_has_display_metadata():
    """Every skill SkillManager registers must have a SKILL_METADATA entry."""
    from agent.skills import get_skill_manager
    from constants.skill_metadata import SKILL_METADATA

    registered = get_skill_manager().get_registered_skill_types()
    missing = registered - set(SKILL_METADATA.keys())
    assert not missing, (
        f"Skills are registered in SkillManager but missing display "
        f"metadata in constants/skill_metadata.SKILL_METADATA: {sorted(missing)}. "
        "Add an entry for each missing skill_type to prevent Graph View "
        "label drift."
    )


def test_validator_accepts_every_registered_skill():
    """``get_valid_skill_types`` must cover every registered skill_type.

    If this fails, save endpoints will reject saves for agents carrying the
    missing skill_type with a 400 ``invalid skill_type`` error.
    """
    from agent.skills import get_skill_manager
    from constants.skill_metadata import get_valid_skill_types

    registered = get_skill_manager().get_registered_skill_types()
    valid = get_valid_skill_types()
    missing = registered - valid
    assert not missing, (
        f"Skills are registered in SkillManager but rejected by "
        f"get_valid_skill_types: {sorted(missing)}. Save endpoints in "
        "routes_agent_builder.py and v1/routes_studio.py will return 400 "
        "for any agent that carries one of these skills."
    )


def test_password_vault_is_accepted():
    """Regression: ``password_vault`` was the original drift symptom."""
    from constants.skill_metadata import SKILL_METADATA, get_valid_skill_types

    assert "password_vault" in SKILL_METADATA
    assert "password_vault" in get_valid_skill_types()


def test_okg_term_memory_is_accepted():
    """Regression: ``okg_term_memory`` shared the same drift as password_vault."""
    from constants.skill_metadata import SKILL_METADATA, get_valid_skill_types

    assert "okg_term_memory" in SKILL_METADATA
    assert "okg_term_memory" in get_valid_skill_types()


def test_legacy_aliases_remain_acceptable():
    """``calendar`` / ``asana`` / ``email`` are display-only aliases — saves
    using them as ``skill_type`` should not break existing rows."""
    from constants.skill_metadata import get_valid_skill_types

    valid = get_valid_skill_types()
    for alias in ("calendar", "asana", "email"):
        assert alias in valid, (
            f"Legacy alias '{alias}' is no longer in the validator allow-list; "
            "this will break stored AgentSkill rows that still use the alias."
        )
