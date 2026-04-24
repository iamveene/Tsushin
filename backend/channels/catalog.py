"""Catalogs for conversational channels and event-driven triggers."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List


@dataclass(frozen=True)
class EntryPointInfo:
    """Wizard-facing metadata for a single entry point."""
    id: str                 # Stable channel identifier (e.g. "whatsapp")
    display_name: str       # Human label for the wizard card
    description: str        # One-sentence summary
    requires_setup: bool    # True if the channel needs per-tenant provisioning
    setup_hint: str         # UI hint pointing to the setup flow
    icon_hint: str          # Optional name the frontend maps to an icon

    def to_dict(self) -> dict:
        return asdict(self)


# Ordering matches the frontend fallbacks to keep the visual layout stable.
CHANNEL_CATALOG: List[EntryPointInfo] = [
    EntryPointInfo(
        id="playground",
        display_name="Playground",
        description="Chat in the web playground (always recommended for testing).",
        requires_setup=False,
        setup_hint="Available out of the box — no configuration required.",
        icon_hint="playground",
    ),
    EntryPointInfo(
        id="whatsapp",
        display_name="WhatsApp",
        description="Route incoming WhatsApp DMs/groups to this agent.",
        requires_setup=True,
        setup_hint="Pair via WhatsApp Setup Wizard under Settings -> Channels.",
        icon_hint="whatsapp",
    ),
    EntryPointInfo(
        id="telegram",
        display_name="Telegram",
        description="Route Telegram messages to this agent.",
        requires_setup=True,
        setup_hint="Add a bot token under Settings -> Channels -> Telegram.",
        icon_hint="telegram",
    ),
    EntryPointInfo(
        id="slack",
        display_name="Slack",
        description="Respond to Slack messages and mentions.",
        requires_setup=True,
        setup_hint="Install the Slack app from Settings -> Channels -> Slack.",
        icon_hint="slack",
    ),
    EntryPointInfo(
        id="discord",
        display_name="Discord",
        description="Respond to Discord messages and mentions.",
        requires_setup=True,
        setup_hint="Connect a Discord bot under Settings -> Channels -> Discord.",
        icon_hint="discord",
    ),
]

TRIGGER_CATALOG: List[EntryPointInfo] = [
    EntryPointInfo(
        id="email",
        display_name="Email",
        description="Watch Gmail inbox activity and wake agents from matching messages.",
        requires_setup=True,
        setup_hint="Create an email trigger under Hub -> Communication -> Triggers.",
        icon_hint="gmail",
    ),
    EntryPointInfo(
        id="webhook",
        display_name="Webhook",
        description="Receive signed external events and optionally call back a customer system.",
        requires_setup=True,
        setup_hint="Create a webhook trigger under Hub -> Communication -> Triggers.",
        icon_hint="webhook",
    ),
    EntryPointInfo(
        id="jira",
        display_name="Jira",
        description="Watch Jira issues with JQL and wake agents from matching issues.",
        requires_setup=True,
        setup_hint="Create a Jira trigger under Hub -> Communication -> Triggers.",
        icon_hint="jira",
    ),
    EntryPointInfo(
        id="schedule",
        display_name="Schedule",
        description="Wake agents on cron schedules with structured payloads.",
        requires_setup=True,
        setup_hint="Create a schedule trigger under Hub -> Communication -> Triggers.",
        icon_hint="schedule",
    ),
    EntryPointInfo(
        id="github",
        display_name="GitHub",
        description="Receive signed repository events and wake agents from matching activity.",
        requires_setup=True,
        setup_hint="Create a GitHub trigger under Hub -> Communication -> Triggers.",
        icon_hint="github",
    ),
]


def get_channel_catalog() -> List[EntryPointInfo]:
    """Return the static channel catalog (stable ordering)."""
    return list(CHANNEL_CATALOG)


def get_trigger_catalog() -> List[EntryPointInfo]:
    """Return the static trigger catalog (stable ordering)."""
    return list(TRIGGER_CATALOG)
