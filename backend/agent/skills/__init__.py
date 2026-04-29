"""
Phase 5.0 Skills System
Extensible framework for agent capabilities like audio transcription.

Phase 6.4 Week 5: Added Scheduler Skills
Task 3: Added Knowledge Sharing Skill
Phase 5.5: Added Asana Skill

API Tools Migration: Migrated API Tools to Skills:
- SearchSkill (web_search)
"""

from .base import BaseSkill, InboundMessage, SkillResult
from .skill_manager import SkillManager, get_skill_manager
from .audio_transcript import AudioTranscriptSkill
from .scheduler_skill import SchedulerSkill  # Phase 6.4 Week 5
from .scheduler_query_skill import SchedulerQuerySkill  # Phase 6.4 Week 5
from .knowledge_sharing_skill import KnowledgeSharingSkill  # Task 3
# AsanaSkill removed: Asana is now a provider for the Scheduler skill (via FlowsSkill)
from .search_skill import SearchSkill  # API Tools Migration
from .image_analysis_skill import ImageAnalysisSkill

__all__ = [
    'BaseSkill',
    'InboundMessage',
    'SkillResult',
    'SkillManager',
    'get_skill_manager',
    'AudioTranscriptSkill',
    'SchedulerSkill',
    'SchedulerQuerySkill',
    'KnowledgeSharingSkill',
    'SearchSkill',
    'ImageAnalysisSkill',
]

# v0.7.0 Trigger Case Memory MVP — `find_similar_past_cases` is gated on
# the `TSN_CASE_MEMORY_ENABLED` flag so the skill is invisible (and not
# registered with SkillManager) when the feature is off. Flipping the
# flag requires a backend restart.
try:
    from config.feature_flags import case_memory_enabled as _case_memory_enabled

    if _case_memory_enabled():
        from .find_similar_past_cases import FindSimilarPastCasesSkill  # noqa: F401

        __all__.append("FindSimilarPastCasesSkill")
except Exception:  # noqa: BLE001 — never fail import on flag-eval errors
    pass
