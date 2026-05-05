"""Outbound dispatch helpers shared by channel-aware callers."""

from __future__ import annotations

from channels.base import Channel
from channels.trigger import Trigger


async def dispatch_outbound(
    entrypoint,
    *,
    recipient: str,
    message_text: str,
    media_path: str | None = None,
    agent_id: int | None = None,
    **kwargs,
):
    if isinstance(entrypoint, Channel):
        return await entrypoint.send_message(
            to=recipient,
            text=message_text,
            media_path=media_path,
            agent_id=agent_id,
            **kwargs,
        )

    if isinstance(entrypoint, Trigger):
        return await entrypoint.notify_external_system(
            {
                "to": recipient,
                "text": message_text,
                "media_path": media_path,
                "agent_id": agent_id,
                **kwargs,
            }
        )

    raise TypeError(f"Unsupported entry point: {type(entrypoint)!r}")
