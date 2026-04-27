"""
Channel Catalog — single source of truth for channel metadata surfaced by the
Agent Wizard (and any UI that needs to render the set of supported channels).

Historically the channel list was hardcoded in
``frontend/components/agent-wizard/steps/StepChannels.tsx``; adding a new
backend channel required a parallel frontend edit, which drifted silently.
This module + ``api.routes_channels`` give the frontend a live catalog to
fetch from, while the frontend keeps a static fallback for offline mode.

If you add a new channel adapter under ``backend/channels/<name>/``:
  1. Add a new ``ChannelInfo`` entry below.
  2. Update the fallback array in ``StepChannels.tsx``.
  3. ``backend/tests/test_wizard_drift.py`` will assert the two stay in sync.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List


@dataclass(frozen=True)
class ChannelInfo:
    """Wizard-facing metadata for a single channel."""
    id: str                 # Stable channel identifier (e.g. "whatsapp")
    display_name: str       # Human label for the wizard card
    description: str        # One-sentence summary
    requires_setup: bool    # True if the channel needs per-tenant provisioning
    setup_hint: str         # UI hint pointing to the setup flow
    icon_hint: str          # Optional name the frontend maps to an icon

    def to_dict(self) -> dict:
        return asdict(self)


# Seeded with the same 6 channels the wizard renders today. Ordering matches
# StepChannels.tsx so visual parity is preserved when the frontend falls back
# to its local copy.
CHANNEL_CATALOG: List[ChannelInfo] = [
    ChannelInfo(
        id="playground",
        display_name="Playground",
        description="Chat in the web playground (always recommended for testing).",
        requires_setup=False,
        setup_hint="Available out of the box — no configuration required.",
        icon_hint="playground",
    ),
    ChannelInfo(
        id="whatsapp",
        display_name="WhatsApp",
        description="Route incoming WhatsApp DMs/groups to this agent.",
        requires_setup=True,
        setup_hint="Pair via WhatsApp Setup Wizard under Settings -> Channels.",
        icon_hint="whatsapp",
    ),
    ChannelInfo(
        id="telegram",
        display_name="Telegram",
        description="Route Telegram messages to this agent.",
        requires_setup=True,
        setup_hint="Add a bot token under Settings -> Channels -> Telegram.",
        icon_hint="telegram",
    ),
    ChannelInfo(
        id="slack",
        display_name="Slack",
        description="Respond to Slack messages and mentions.",
        requires_setup=True,
        setup_hint="Install the Slack app from Settings -> Channels -> Slack.",
        icon_hint="slack",
    ),
    ChannelInfo(
        id="discord",
        display_name="Discord",
        description="Respond to Discord messages and mentions.",
        requires_setup=True,
        setup_hint="Connect a Discord bot under Settings -> Channels -> Discord.",
        icon_hint="discord",
    ),
    ChannelInfo(
        id="webhook",
        display_name="Webhook",
        description="Expose a webhook endpoint for custom integrations.",
        requires_setup=True,
        setup_hint="Create a webhook under Settings -> Channels -> Webhooks.",
        icon_hint="webhook",
    ),
]


def get_channel_catalog() -> List[ChannelInfo]:
    """Return the static channel catalog (stable ordering)."""
    return list(CHANNEL_CATALOG)
