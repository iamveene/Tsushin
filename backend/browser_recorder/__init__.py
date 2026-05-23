"""Browser Automation Recorder package.

Authors flows by recording a real Chromium session (CDP screencast) and
compiling captured actions into the existing browser_automation FlowNode
config_json shape — no schema migration, no new step type.

See .private/BROWSER_RECORDER_RESEARCH.md for the design rationale.
"""

from .models import RecordedEvent, RecordingSession, RecordingDriver
from .session_manager import SessionRegistry, get_registry

__all__ = [
    "RecordedEvent",
    "RecordingSession",
    "RecordingDriver",
    "SessionRegistry",
    "get_registry",
]
