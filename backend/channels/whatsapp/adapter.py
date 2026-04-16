"""
WhatsApp Channel Adapter
v0.6.0 Item 32

Wraps the existing MCPSender and MCP instance resolution logic behind
the ChannelAdapter contract. No behavioral changes — delegates to the
same transport objects the router used directly.
"""

import re
import logging
import time
from typing import ClassVar, Optional

from channels.base import ChannelAdapter
from channels.types import SendResult, HealthResult


class WhatsAppChannelAdapter(ChannelAdapter):
    """WhatsApp channel via MCP container bridge."""

    channel_type: ClassVar[str] = "whatsapp"
    delivery_mode: ClassVar[str] = "pull"
    supports_threads: ClassVar[bool] = False
    supports_reactions: ClassVar[bool] = False
    supports_rich_formatting: ClassVar[bool] = False
    supports_media: ClassVar[bool] = True
    text_chunk_limit: ClassVar[int] = 4096

    def __init__(self, db_session, mcp_sender, mcp_instance_id: Optional[int], logger: logging.Logger):
        """
        Args:
            db_session: SQLAlchemy Session for MCP instance queries
            mcp_sender: MCPSender instance for outbound messages
            mcp_instance_id: WhatsApp MCP instance ID for this router context
            logger: Logger instance
        """
        self.db = db_session
        self.mcp_sender = mcp_sender
        self.mcp_instance_id = mcp_instance_id
        self.logger = logger

    async def start(self) -> None:
        """No-op — WhatsApp MCP container lifecycle is managed externally."""
        pass

    async def stop(self) -> None:
        """No-op — WhatsApp MCP container lifecycle is managed externally."""
        pass

    async def send_message(
        self,
        to: str,
        text: str,
        *,
        media_path: Optional[str] = None,
        **kwargs
    ) -> SendResult:
        """Send message via WhatsApp MCP bridge.

        Args:
            to: Recipient phone number or WhatsApp JID
            text: Message text
            media_path: Optional media file path
            **kwargs: Expects 'agent_id' for MCP URL resolution
        """
        agent_id = kwargs.get("agent_id")

        if not self.validate_recipient(to):
            return SendResult(
                success=False,
                error=f"Invalid WhatsApp recipient: {to}"
            )

        if not agent_id:
            self.logger.debug("WhatsApp send without agent_id — using default MCP instance")

        mcp_url, api_secret = self._resolve_mcp_instance(agent_id) if agent_id else (None, None)

        if agent_id and mcp_url and not await self._check_mcp_connection(agent_id, mcp_url):
            return SendResult(
                success=False,
                error=f"MCP not connected for agent {agent_id}"
            )

        try:
            success = await self.mcp_sender.send_message(
                to,
                text,
                media_path=media_path,
                api_url=mcp_url,
                api_secret=api_secret
            )
            return SendResult(success=success)
        except Exception as e:
            self.logger.error(f"WhatsApp send error: {e}", exc_info=True)
            return SendResult(success=False, error=str(e))

    async def health_check(self) -> HealthResult:
        """Check WhatsApp MCP connection health."""
        try:
            if not self.mcp_instance_id:
                return HealthResult(healthy=False, status="disconnected", detail="No MCP instance configured")

            from models import WhatsAppMCPInstance
            instance = self.db.query(WhatsAppMCPInstance).get(self.mcp_instance_id)
            if not instance:
                return HealthResult(healthy=False, status="disconnected", detail="MCP instance not found")

            start = time.time()
            is_healthy, health_data = await self.mcp_sender.check_health(api_url=instance.mcp_api_url)
            latency = (time.time() - start) * 1000

            return HealthResult(
                healthy=is_healthy,
                status="connected" if is_healthy else "disconnected",
                latency_ms=round(latency, 1),
                detail=health_data.get("error") if not is_healthy else None
            )
        except Exception as e:
            return HealthResult(healthy=False, status="error", detail=str(e))

    def validate_recipient(self, recipient: str) -> bool:
        """Validate WhatsApp recipient format (phone number or JID)."""
        if '@' in recipient:
            return True
        if re.match(r'^\+?\d{10,15}$', recipient):
            return True
        normalized = recipient.split('@')[0].lstrip('+')
        if normalized.isdigit() and len(normalized) <= 10 and not recipient.startswith('+'):
            self.logger.error(
                f"BLOCKED: Telegram ID '{recipient}' cannot be used as WhatsApp recipient"
            )
            return False
        return True

    def _resolve_mcp_instance(self, agent_id: int) -> tuple:
        """Resolve MCP API URL and secret for an agent.
        Mirrors router._resolve_mcp_instance logic exactly.
        """
        from models import WhatsAppMCPInstance, Agent

        default_url = "http://127.0.0.1:8080/api"

        try:
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                return (default_url, None)

            if agent.whatsapp_integration_id:
                instance = self.db.query(WhatsAppMCPInstance).filter(
                    WhatsAppMCPInstance.id == agent.whatsapp_integration_id,
                    WhatsAppMCPInstance.status.in_(["running", "starting"])
                ).first()
                if instance:
                    return (instance.mcp_api_url, instance.api_secret)

            if not agent.tenant_id:
                return (default_url, None)

            instance = self.db.query(WhatsAppMCPInstance).filter(
                WhatsAppMCPInstance.tenant_id == agent.tenant_id,
                WhatsAppMCPInstance.instance_type == "agent",
                WhatsAppMCPInstance.status.in_(["running", "starting"])
            ).first()

            if instance:
                return (instance.mcp_api_url, instance.api_secret)
            return (default_url, None)

        except Exception as e:
            self.logger.error(f"Error resolving MCP URL for agent {agent_id}: {e}", exc_info=True)
            return (default_url, None)

    async def _check_mcp_connection(self, agent_id: int, mcp_api_url: str) -> bool:
        """Check if MCP instance is connected before sending.
        Mirrors router._check_mcp_connection logic exactly.
        """
        import httpx

        # Backward compatibility: skip check for None or default URL
        if not mcp_api_url or mcp_api_url == "http://127.0.0.1:8080/api":
            return True

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{mcp_api_url}/health")

            if response.status_code == 200:
                data = response.json()
                connected = data.get("connected", False)

                if not connected:
                    self.logger.warning(
                        f"MCP instance for agent {agent_id} is NOT authenticated. "
                        f"Skipping message send to prevent queue buildup."
                    )
                    return False

                return True
            else:
                self.logger.warning(
                    f"MCP health check failed for agent {agent_id}: HTTP {response.status_code}"
                )
                return False
        except Exception as e:
            self.logger.error(
                f"Failed to check MCP connection for agent {agent_id}: {e}",
                exc_info=True
            )
            return False
