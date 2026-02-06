"""
Phase 5.0 Skills System
Extensible framework for agent capabilities like audio transcription.

Phase 6.4 Week 5: Added Scheduler Skills
Task 3: Added Knowledge Sharing Skill
Phase 5.5: Added Asana Skill

API Tools Migration: Migrated API Tools to Skills:
- SearchSkill (web_search)
- WeatherSkill (weather)
- WebScrapingSkill (web_scraping)
"""

from .base import BaseSkill, InboundMessage, SkillResult
from .skill_manager import SkillManager, get_skill_manager
from .audio_transcript import AudioTranscriptSkill
from .scheduler_skill import SchedulerSkill  # Phase 6.4 Week 5
from .scheduler_query_skill import SchedulerQuerySkill  # Phase 6.4 Week 5
from .knowledge_sharing_skill import KnowledgeSharingSkill  # Task 3
# AsanaSkill removed: Asana is now a provider for the Scheduler skill (via FlowsSkill)
from .search_skill import SearchSkill  # API Tools Migration
from .weather_skill import WeatherSkill  # API Tools Migration
from .web_scraping_skill import WebScrapingSkill  # API Tools Migration

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
    'WeatherSkill',
    'WebScrapingSkill'
]
