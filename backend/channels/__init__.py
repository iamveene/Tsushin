"""
Channel Abstraction Layer
v0.6.0 Item 32

Provides the shared contracts for conversational Channels and event-driven
Triggers plus the per-router registry used for dispatch.

Usage:
    from channels import Channel, ChannelAdapter, Trigger, ChannelRegistry, SendResult, HealthResult
    from channels.types import InboundMessage, Attachment
"""

from channels.base import Channel, ChannelAdapter, EntryPoint
from channels.registry import ChannelRegistry
from channels.trigger import Trigger
from channels.types import (
    Attachment,
    HealthResult,
    InboundMessage,
    SendResult,
    TriggerEvent,
)

__all__ = [
    "EntryPoint",
    "Channel",
    "ChannelAdapter",
    "Trigger",
    "ChannelRegistry",
    "Attachment",
    "HealthResult",
    "InboundMessage",
    "SendResult",
    "TriggerEvent",
]
