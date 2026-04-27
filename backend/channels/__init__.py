"""
Channel Abstraction Layer
v0.6.0 Item 32

Provides a unified interface for all messaging channels (WhatsApp, Telegram,
Slack, Discord, Playground). Each channel implements the ChannelAdapter contract
and registers with the ChannelRegistry for dispatch.

Usage:
    from channels import ChannelAdapter, ChannelRegistry, SendResult, HealthResult
    from channels.types import InboundMessage, Attachment
"""

from channels.base import ChannelAdapter
from channels.registry import ChannelRegistry
from channels.types import (
    Attachment,
    HealthResult,
    InboundMessage,
    SendResult,
)

__all__ = [
    "ChannelAdapter",
    "ChannelRegistry",
    "Attachment",
    "HealthResult",
    "InboundMessage",
    "SendResult",
]
