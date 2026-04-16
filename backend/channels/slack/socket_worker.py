"""
Slack Socket Mode Worker (v0.6.0 V060-CHN-002).

Opens a persistent WebSocket to Slack using the App-Level Token (xapp-*) and
forwards inbound message events to the message_queue, where the existing
QueueWorker._process_slack_message dispatcher routes them through AgentRouter.

Why Socket Mode?
- No publicly-reachable HTTPS URL required — the bot dials out to Slack.
- Simpler local-development UX than HTTP Events + ngrok.

Lifecycle:
- One worker per active SlackIntegration (mode='socket').
- Started/stopped by SlackSocketModeManager from app.py lifespan and from
  SlackIntegration CRUD endpoints.
- Reconnection is handled by slack-sdk's SocketModeClient internally.

References:
- slack_sdk.socket_mode.aiohttp.SocketModeClient
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SlackSocketModeWorker:
    """Owns one Slack Socket Mode WebSocket for a single SlackIntegration."""

    def __init__(
        self,
        *,
        integration_id: int,
        tenant_id: str,
        bot_token: str,
        app_token: str,
        db_session_factory,
    ) -> None:
        self.integration_id = integration_id
        self.tenant_id = tenant_id
        self._bot_token = bot_token
        self._app_token = app_token
        self._db_session_factory = db_session_factory
        self._client = None  # SocketModeClient
        self._connected = False
        self._stopping = False

    async def start(self) -> bool:
        """Open the Socket Mode WebSocket and register the message handler."""
        try:
            # Imports kept local so the module loads cheaply even when no Slack
            # integration is configured.
            from slack_sdk.web.async_client import AsyncWebClient
            from slack_sdk.socket_mode.aiohttp import SocketModeClient
            from slack_sdk.socket_mode.request import SocketModeRequest
            from slack_sdk.socket_mode.response import SocketModeResponse
        except ImportError as e:
            logger.error(
                "slack-sdk Socket Mode support not available (%s). "
                "Install slack-sdk[aiohttp] to enable Socket Mode workers.",
                e,
            )
            return False

        web_client = AsyncWebClient(token=self._bot_token)

        try:
            auth = await web_client.auth_test()
            bot_user_id = auth.get("user_id")
            workspace = auth.get("team")
            logger.info(
                "Slack Socket Mode auth.test ok (integration=%s, bot_user_id=%s, workspace=%s)",
                self.integration_id, bot_user_id, workspace,
            )
        except Exception as e:
            logger.error(
                "Slack Socket Mode auth.test failed for integration %s: %s",
                self.integration_id, e,
            )
            return False

        client = SocketModeClient(
            app_token=self._app_token,
            web_client=web_client,
        )
        self._client = client

        async def _handle(client, request: SocketModeRequest):
            # slack_sdk passes (client, request) to socket-mode listeners.
            # Always ACK first so Slack doesn't retry.
            try:
                ack = SocketModeResponse(envelope_id=request.envelope_id)
                await client.send_socket_mode_response(ack)
            except Exception as ack_err:
                logger.warning(
                    "Slack Socket Mode ACK failed (integration=%s): %s",
                    self.integration_id, ack_err,
                )

            if request.type != "events_api":
                return

            try:
                self._enqueue_event(request.payload or {})
            except Exception as enqueue_err:
                logger.error(
                    "Slack Socket Mode enqueue failed (integration=%s): %s",
                    self.integration_id, enqueue_err,
                    exc_info=True,
                )

        client.socket_mode_request_listeners.append(_handle)

        try:
            await client.connect()
            self._connected = True
            logger.info(
                "Slack Socket Mode connected (integration_id=%s, tenant=%s)",
                self.integration_id, self.tenant_id,
            )
            return True
        except Exception as e:
            logger.error(
                "Slack Socket Mode connect failed (integration=%s): %s",
                self.integration_id, e,
            )
            return False

    async def stop(self) -> None:
        self._stopping = True
        if self._client is None:
            return
        try:
            await self._client.disconnect()
        except Exception as e:
            logger.warning(
                "Slack Socket Mode disconnect error (integration=%s): %s",
                self.integration_id, e,
            )
        finally:
            self._connected = False
            logger.info(
                "Slack Socket Mode disconnected (integration_id=%s)",
                self.integration_id,
            )

    def _enqueue_event(self, payload: dict) -> None:
        """Mirror the HTTP-Events filter+enqueue logic in routes_channel_webhooks."""
        from models import Agent, SlackIntegration  # noqa: WPS433
        from services.message_queue_service import MessageQueueService  # noqa: WPS433

        event_type = payload.get("type")
        if event_type != "event_callback":
            return
        event = payload.get("event") or {}
        if event.get("type") != "message":
            return
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return
        if not event.get("user") or not event.get("text"):
            return

        db = self._db_session_factory()
        try:
            integration = (
                db.query(SlackIntegration)
                .filter(
                    SlackIntegration.id == self.integration_id,
                    SlackIntegration.is_active == True,
                )
                .first()
            )
            if not integration:
                logger.warning(
                    "Slack Socket Mode received event for inactive/missing integration %s",
                    self.integration_id,
                )
                return

            agent = (
                db.query(Agent)
                .filter(
                    Agent.slack_integration_id == integration.id,
                    Agent.tenant_id == integration.tenant_id,
                )
                .order_by(Agent.id.asc())
                .first()
            )
            if agent is None:
                logger.warning(
                    "Slack Socket Mode message for integration %s dropped: no agent assigned. "
                    "Bind an agent in Hub → Agent → Channels.",
                    self.integration_id,
                )
                return

            sender_key = (
                f"slack:{payload.get('team_id', '')}:{event.get('user', '')}"
            )
            MessageQueueService(db).enqueue(
                channel="slack",
                tenant_id=integration.tenant_id,
                agent_id=agent.id,
                sender_key=sender_key,
                payload={
                    "event": event,
                    "team_id": payload.get("team_id"),
                    "slack_integration_id": integration.id,
                },
            )
        finally:
            db.close()

    @property
    def connected(self) -> bool:
        return self._connected
