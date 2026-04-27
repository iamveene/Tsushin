"""
Channel Abstraction Layer — Shared Data Types
v0.6.0 Item 32

Channel-agnostic data types for normalized inbound/outbound messaging.
These types are separate from agent.skills.base.InboundMessage (skill triggering).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Attachment:
    """Media attachment from any channel."""
    media_type: str              # "image", "audio", "video", "document"
    url: Optional[str] = None
    local_path: Optional[str] = None
    filename: Optional[str] = None
    mime_type: Optional[str] = None


@dataclass
class InboundMessage:
    """Channel-agnostic inbound message (normalized from any channel).

    Note: This is distinct from agent.skills.base.InboundMessage which is
    used for skill triggering. This type is for cross-channel normalization.
    """
    channel: str                    # "whatsapp", "telegram", "slack", "discord", "playground"
    source_id: str                  # Platform-unique message ID
    sender_key: str                 # Normalized sender identifier
    sender_name: Optional[str]
    chat_id: str                    # Conversation/channel identifier
    text: str
    is_group: bool
    timestamp: datetime
    thread_id: Optional[str] = None
    attachments: List[Attachment] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass
class SendResult:
    """Result of an outbound message send attempt."""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    raw: Optional[dict] = None


@dataclass
class HealthResult:
    """Result of a channel health check."""
    healthy: bool
    status: str              # "connected", "disconnected", "error", "unknown"
    latency_ms: Optional[float] = None
    detail: Optional[str] = None
