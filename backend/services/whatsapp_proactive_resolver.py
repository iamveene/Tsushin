"""
WhatsApp Proactive ID Resolution Service

Resolves phone numbers to WhatsApp IDs proactively using the IsOnWhatsApp API.
This enables the system to match incoming messages from WhatsApp IDs to contacts
that only have phone numbers stored.

Phase: WhatsApp ID Proactive Resolution
"""

import logging
import asyncio
import httpx
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from models import Contact, WhatsAppMCPInstance, ContactChannelMapping
from services.contact_channel_mapping_service import ContactChannelMappingService

logger = logging.getLogger(__name__)


class WhatsAppProactiveResolver:
    """
    Proactively resolves phone numbers to WhatsApp IDs.

    This service:
    1. Queries contacts with phone numbers but no WhatsApp ID
    2. Calls the MCP /api/check-numbers endpoint to resolve them
    3. Updates contacts with the resolved WhatsApp IDs
    """

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def close(self):
        """Close HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    def _get_active_mcp_instance(self, tenant_id: str) -> Optional[WhatsAppMCPInstance]:
        """
        Get an active WhatsApp MCP instance for the tenant.

        Returns the first running and authenticated instance.
        """
        instances = self.db.query(WhatsAppMCPInstance).filter(
            WhatsAppMCPInstance.tenant_id == tenant_id,
            WhatsAppMCPInstance.status == 'running',
            WhatsAppMCPInstance.health_status == 'healthy'
        ).all()

        if not instances:
            self.logger.warning(f"No active MCP instance found for tenant {tenant_id}")
            return None

        # Return first healthy instance
        return instances[0]

    async def resolve_phone_number(
        self,
        phone_number: str,
        tenant_id: str,
        mcp_instance: Optional[WhatsAppMCPInstance] = None
    ) -> Optional[str]:
        """
        Resolve a single phone number to WhatsApp ID.

        Args:
            phone_number: Phone number to resolve (e.g., "+5500000000001")
            tenant_id: Tenant ID for MCP instance selection
            mcp_instance: Optional specific MCP instance to use

        Returns:
            WhatsApp JID (e.g., "5500000000001@s.whatsapp.net") if registered, None otherwise
        """
        if not mcp_instance:
            mcp_instance = self._get_active_mcp_instance(tenant_id)

        if not mcp_instance:
            self.logger.error(f"Cannot resolve phone number: no active MCP instance for tenant {tenant_id}")
            return None

        try:
            client = await self._get_http_client()

            # Call the check-numbers endpoint
            response = await client.post(
                f"{mcp_instance.mcp_api_url}/check-numbers",
                json={"phone_numbers": [phone_number]},
                headers={"Content-Type": "application/json"}
            )

            if response.status_code != 200:
                self.logger.error(
                    f"MCP check-numbers failed: HTTP {response.status_code} - {response.text}"
                )
                return None

            data = response.json()

            if not data.get("success"):
                self.logger.error(f"MCP check-numbers returned error: {data.get('message')}")
                return None

            results = data.get("results", [])
            if results and results[0].get("is_registered"):
                jid = results[0].get("jid")
                self.logger.info(f"✅ Resolved {phone_number} → {jid}")
                return jid
            else:
                self.logger.info(f"❌ Phone number {phone_number} not registered on WhatsApp")
                return None

        except httpx.TimeoutException:
            self.logger.error(f"Timeout calling MCP check-numbers for {phone_number}")
            return None
        except Exception as e:
            self.logger.error(f"Error resolving phone number {phone_number}: {e}", exc_info=True)
            return None

    async def resolve_contact(
        self,
        contact_id: int,
        tenant_id: str,
        force: bool = False
    ) -> Optional[str]:
        """
        Resolve WhatsApp ID for a specific contact.

        Args:
            contact_id: Contact ID to resolve
            tenant_id: Tenant ID
            force: If True, re-resolve even if already has WhatsApp ID

        Returns:
            Resolved WhatsApp JID or None
        """
        contact = self.db.query(Contact).filter(
            Contact.id == contact_id,
            Contact.tenant_id == tenant_id
        ).first()

        if not contact:
            self.logger.warning(f"Contact {contact_id} not found for tenant {tenant_id}")
            return None

        # Skip if already has WhatsApp ID (unless force)
        if contact.whatsapp_id and not force:
            self.logger.debug(f"Contact {contact.friendly_name} already has WhatsApp ID: {contact.whatsapp_id}")
            return contact.whatsapp_id

        # Need phone number to resolve
        if not contact.phone_number:
            self.logger.debug(f"Contact {contact.friendly_name} has no phone number to resolve")
            return None

        # Resolve the phone number
        jid = await self.resolve_phone_number(contact.phone_number, tenant_id)

        if jid:
            # Update contact with resolved WhatsApp ID
            await self._update_contact_whatsapp_id(contact, jid, tenant_id)
            return jid

        return None

    async def _update_contact_whatsapp_id(
        self,
        contact: Contact,
        jid: str,
        tenant_id: str
    ):
        """
        Update a contact with the resolved WhatsApp ID.

        Performs dual-write to both legacy column and channel mapping table.
        """
        try:
            # Extract just the user ID from JID (e.g., "5500000000001@s.whatsapp.net" → "5500000000001")
            whatsapp_id = jid.split("@")[0] if "@" in jid else jid

            # Update legacy column
            contact.whatsapp_id = whatsapp_id
            contact.updated_at = datetime.utcnow()

            # Phase 10.2: Also update/add channel mapping
            mapping_service = ContactChannelMappingService(self.db)

            # Check if whatsapp mapping already exists
            existing_mappings = mapping_service.get_channel_mappings(contact.id, channel_type='whatsapp')

            if existing_mappings:
                # Update existing mapping
                existing = existing_mappings[0]
                if existing.channel_identifier != whatsapp_id:
                    mapping_service.remove_channel_mapping_by_id(existing.id)
                    mapping_service.add_channel_mapping(
                        contact_id=contact.id,
                        channel_type='whatsapp',
                        channel_identifier=whatsapp_id,
                        tenant_id=tenant_id
                    )
            else:
                # Add new mapping
                mapping_service.add_channel_mapping(
                    contact_id=contact.id,
                    channel_type='whatsapp',
                    channel_identifier=whatsapp_id,
                    tenant_id=tenant_id
                )

            self.db.commit()
            self.db.refresh(contact)

            self.logger.info(
                f"🔗 Updated contact '{contact.friendly_name}' with WhatsApp ID: {whatsapp_id}"
            )

        except Exception as e:
            self.db.rollback()
            self.logger.error(
                f"Failed to update contact {contact.friendly_name} with WhatsApp ID: {e}",
                exc_info=True
            )

    async def resolve_all_contacts(
        self,
        tenant_id: str,
        batch_size: int = 50
    ) -> Dict[str, Any]:
        """
        Resolve WhatsApp IDs for all contacts with phone numbers but no WhatsApp ID.

        Args:
            tenant_id: Tenant ID
            batch_size: Number of contacts to process per batch (max 50 due to API limits)

        Returns:
            Dict with resolution statistics
        """
        # Get MCP instance first
        mcp_instance = self._get_active_mcp_instance(tenant_id)
        if not mcp_instance:
            return {
                "success": False,
                "error": "No active MCP instance available",
                "resolved": 0,
                "failed": 0,
                "skipped": 0
            }

        # Query contacts needing resolution
        contacts = self.db.query(Contact).filter(
            Contact.tenant_id == tenant_id,
            Contact.phone_number.isnot(None),
            Contact.phone_number != "",
            (Contact.whatsapp_id.is_(None) | (Contact.whatsapp_id == ""))
        ).all()

        if not contacts:
            self.logger.info(f"No contacts need WhatsApp ID resolution for tenant {tenant_id}")
            return {
                "success": True,
                "resolved": 0,
                "failed": 0,
                "skipped": 0,
                "message": "No contacts need resolution"
            }

        self.logger.info(f"Found {len(contacts)} contacts needing WhatsApp ID resolution")

        resolved = 0
        failed = 0

        # Process in batches
        for i in range(0, len(contacts), batch_size):
            batch = contacts[i:i + batch_size]
            phone_numbers = [c.phone_number for c in batch]

            try:
                client = await self._get_http_client()

                response = await client.post(
                    f"{mcp_instance.mcp_api_url}/check-numbers",
                    json={"phone_numbers": phone_numbers},
                    headers={"Content-Type": "application/json"}
                )

                if response.status_code != 200:
                    self.logger.error(f"Batch resolution failed: HTTP {response.status_code}")
                    failed += len(batch)
                    continue

                data = response.json()

                if not data.get("success"):
                    self.logger.error(f"Batch resolution error: {data.get('message')}")
                    failed += len(batch)
                    continue

                results = data.get("results", [])

                # Match results back to contacts
                for j, result in enumerate(results):
                    if j >= len(batch):
                        break

                    contact = batch[j]

                    if result.get("is_registered") and result.get("jid"):
                        await self._update_contact_whatsapp_id(
                            contact,
                            result["jid"],
                            tenant_id
                        )
                        resolved += 1
                    else:
                        failed += 1
                        self.logger.debug(
                            f"Contact '{contact.friendly_name}' phone not registered on WhatsApp"
                        )

            except Exception as e:
                self.logger.error(f"Batch resolution error: {e}", exc_info=True)
                failed += len(batch)

        return {
            "success": True,
            "resolved": resolved,
            "failed": failed,
            "skipped": 0,
            "total": len(contacts)
        }


# Background task helper for async resolution
def resolve_contact_background(
    db_session_factory,
    contact_id: int,
    tenant_id: str
):
    """
    Fire-and-forget background task to resolve a contact's WhatsApp ID.

    This is called after contact creation/update to asynchronously resolve
    the WhatsApp ID without blocking the API response.

    Args:
        db_session_factory: SQLAlchemy session factory
        contact_id: Contact ID to resolve
        tenant_id: Tenant ID
    """
    async def _resolve():
        db = db_session_factory()
        try:
            resolver = WhatsAppProactiveResolver(db)
            await resolver.resolve_contact(contact_id, tenant_id)
            await resolver.close()
        except Exception as e:
            logger.error(f"Background resolution failed for contact {contact_id}: {e}")
        finally:
            db.close()

    # Run in background
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_resolve())
        else:
            asyncio.run(_resolve())
    except RuntimeError:
        # No event loop, create one
        asyncio.run(_resolve())
