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
from datetime import datetime, timedelta
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

            # Call the check-numbers endpoint with Bearer auth (Phase Security-1)
            from services.mcp_auth_service import get_auth_headers
            auth_headers = get_auth_headers(mcp_instance.api_secret)
            response = await client.post(
                f"{mcp_instance.mcp_api_url}/check-numbers",
                json={"phone_numbers": [phone_number]},
                headers={"Content-Type": "application/json", **auth_headers}
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

        jid: Optional[str] = None

        # Skip phone→JID resolution if already done (unless force).
        if contact.whatsapp_id and not force:
            self.logger.debug(f"Contact {contact.friendly_name} already has WhatsApp ID: {contact.whatsapp_id}")
            jid = contact.whatsapp_id
        elif contact.phone_number:
            jid = await self.resolve_phone_number(contact.phone_number, tenant_id)
            if jid:
                await self._update_contact_whatsapp_id(contact, jid, tenant_id)
        else:
            self.logger.debug(f"Contact {contact.friendly_name} has no phone number to resolve")

        # WhatsApp's modern @lid sender identifiers are not returned by /check-numbers,
        # which only resolves to phone-style @s.whatsapp.net JIDs. Bind any LID seen in
        # recent chat history so dispatcher routing works without depending on the
        # name-match heuristic at first inbound.
        try:
            await self._bind_lid_from_recent_chats(contact, tenant_id)
        except Exception as e:
            self.logger.debug(
                f"LID binding skipped for contact {contact.friendly_name}: {e}"
            )

        return jid

    async def _fetch_directory_name(
        self,
        phone_number: str,
        mcp_instance: WhatsAppMCPInstance,
    ) -> Optional[str]:
        """Look up the WhatsApp directory display name for a phone via MCP /contacts.

        The display name there ("Gisele Espini") is what WhatsApp itself shows the
        bot — distinct from the operator's nickname for the contact ("Giza"). It's
        the missing bridge for LID matching when chat metadata uses the WhatsApp
        name (e.g., "Gisele E.") and the Tsushin contact uses a nickname.
        """
        if not phone_number:
            return None
        digits = "".join(ch for ch in phone_number if ch.isdigit())
        if not digits:
            return None
        try:
            client = await self._get_http_client()
            from services.mcp_auth_service import get_auth_headers

            response = await client.get(
                f"{mcp_instance.mcp_api_url}/contacts",
                params={"q": digits},
                headers=get_auth_headers(mcp_instance.api_secret),
            )
            if response.status_code != 200:
                return None
            data = response.json()
            if not data.get("success"):
                return None
            for entry in data.get("contacts", []) or []:
                # MCP may return phones formatted with +/spaces/hyphens — normalize to
                # bare digits before comparing, otherwise stored phones with formatting
                # silently fail the directory match.
                entry_digits = "".join(ch for ch in str(entry.get("phone") or "") if ch.isdigit())
                if entry_digits == digits:
                    name = (entry.get("name") or "").strip()
                    if name and name != digits:  # MCP returns phone as name if no display name
                        return name
            return None
        except Exception as e:
            self.logger.debug(f"MCP /contacts directory lookup failed: {e}")
            return None

    @staticmethod
    def _name_words(value: str) -> set[str]:
        """Tokenize a name into matchable words: lowercased, alpha-only, ≥3 chars.

        Filters punctuation ("E." → dropped) and short noise tokens. Used for
        word-overlap matching between operator nicknames, WhatsApp directory
        names, and chat-display names that all reference the same person but
        with different surface forms.
        """
        words: set[str] = set()
        for raw in (value or "").split():
            cleaned = "".join(ch for ch in raw.lower() if ch.isalpha())
            if len(cleaned) >= 3:
                words.add(cleaned)
        return words

    async def _bind_lid_from_recent_chats(
        self,
        contact: Contact,
        tenant_id: str,
        scan_limit: int = 500,
        scan_days: int = 30,
    ) -> Optional[str]:
        """Scan recent MCP messages for an @lid chat that matches this contact.

        WhatsApp's contact directory (/api/contacts) only returns @s.whatsapp.net JIDs,
        not the @lid identifiers used in inbound message envelopes. The chats table on
        the MCP container holds the LID↔chat-name mapping, but is not exposed as its
        own endpoint, so we scan the recent /api/messages stream and look for any
        @lid chat whose chat_name shares a meaningful word with either the operator's
        friendly_name or the WhatsApp directory name resolved from the contact's phone.
        Any unambiguous match is written into contact_channel_mapping so layer-2 LID
        lookups resolve directly without relying on the dispatcher's name-match
        fallback at first inbound.
        """
        if not contact.friendly_name and not contact.phone_number:
            return None

        mcp_instance = self._get_active_mcp_instance(tenant_id)
        if not mcp_instance:
            return None

        # MCP /messages returns oldest-first; pass `since` to bias toward recent traffic
        # where the contact's @lid is most likely to appear.
        since = (datetime.utcnow() - timedelta(days=scan_days)).strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            client = await self._get_http_client()
            from services.mcp_auth_service import get_auth_headers

            response = await client.get(
                f"{mcp_instance.mcp_api_url}/messages",
                params={"limit": scan_limit, "since": since},
                headers=get_auth_headers(mcp_instance.api_secret),
            )
            if response.status_code != 200:
                return None
            data = response.json()
            if not data.get("success"):
                return None
        except Exception as e:
            self.logger.debug(f"MCP /messages scan failed: {e}")
            return None

        # Build the union of name words from operator nickname AND WhatsApp directory.
        # Operator may use a nickname unrelated to the WhatsApp display name, and the
        # LID chat name may be yet another shortened form — covering all three forms
        # is what makes nickname-only contacts resolve correctly.
        target_words: set[str] = set()
        if contact.friendly_name:
            target_words |= self._name_words(contact.friendly_name)
        if contact.phone_number:
            directory_name = await self._fetch_directory_name(contact.phone_number, mcp_instance)
            if directory_name:
                target_words |= self._name_words(directory_name)

        if not target_words:
            return None

        # Score each candidate LID by how many target words its chat_name shares.
        # Keep only the highest-scoring tier and reject if that tier still has
        # multiple distinct LIDs — ambiguity at peak score means we can't tell
        # them apart safely. This handles both directions:
        #   * Common-first-name false positive ("Ana"-only overlap): if a more
        #     specific candidate exists with a 2-word overlap (e.g., "Ana Lima"
        #     ∩ "Ana L. Lima"), it outranks the single-word match.
        #   * Single-word truthy match ("Giza"/"Gisele Espini" ∩ "Gisele E."):
        #     no other candidate competes, so the lone LID at score=1 wins.
        scored: dict[str, tuple[int, str]] = {}  # lid -> (overlap_count, chat_name)
        for msg in data.get("messages", []) or []:
            chat_jid = (msg.get("chat_jid") or "")
            chat_name = (msg.get("chat_name") or "").strip()
            if not chat_jid.endswith("@lid") or not chat_name:
                continue
            chat_words = self._name_words(chat_name)
            shared = chat_words & target_words
            if not shared:
                continue
            lid = chat_jid.split("@", 1)[0]
            if not lid:
                continue
            prev = scored.get(lid)
            if prev is None or len(shared) > prev[0]:
                scored[lid] = (len(shared), chat_name)

        if not scored:
            return None

        max_overlap = max(score for score, _ in scored.values())
        top_tier = {lid: name for lid, (score, name) in scored.items() if score == max_overlap}

        if len(top_tier) > 1:
            self.logger.warning(
                f"[LID PRE-BIND] Ambiguous LID match for contact "
                f"'{contact.friendly_name}' at overlap={max_overlap}: "
                f"{list(top_tier.items())} — skipping to avoid binding the "
                f"wrong identity. Will rely on first-inbound name-match path."
            )
            return None

        lid, chat_name = next(iter(top_tier.items()))
        seen_lids = top_tier  # preserved name retained for downstream code paths

        try:
            mapping_service = ContactChannelMappingService(self.db)
            existing = mapping_service.get_channel_mappings(contact.id, channel_type='whatsapp')
            if any(m.channel_identifier == lid for m in existing):
                return lid

            mapping_service.add_channel_mapping(
                contact_id=contact.id,
                channel_type='whatsapp',
                channel_identifier=lid,
                channel_metadata={
                    "discovered_from": "lid_pre_bind",
                    "matched_chat_name": chat_name,
                },
                tenant_id=tenant_id,
            )
            self.db.commit()
            self.logger.info(
                f"🔗 [LID PRE-BIND] Linked LID {lid} to contact "
                f"'{contact.friendly_name}' (matched chat_name '{chat_name}')"
            )
            return lid
        except Exception as e:
            self.db.rollback()
            self.logger.warning(f"[LID PRE-BIND] Failed to write channel_mapping: {e}")
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

                from services.mcp_auth_service import get_auth_headers
                auth_headers = get_auth_headers(mcp_instance.api_secret)
                response = await client.post(
                    f"{mcp_instance.mcp_api_url}/check-numbers",
                    json={"phone_numbers": phone_numbers},
                    headers={"Content-Type": "application/json", **auth_headers}
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
