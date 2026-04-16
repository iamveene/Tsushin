"""
Feature #12: Slash Command Permission Service

Determines whether a given sender is allowed to use slash commands,
based on per-contact overrides and tenant-level default policy.

Resolution order:
1. Contact explicit override (slash_commands_enabled is not None) -> use it
2. Tenant default policy (slash_commands_default_policy)
3. System fallback: enabled_for_known
"""

import logging
from sqlalchemy.orm import Session
from sqlalchemy import or_

from models import Contact, ContactChannelMapping
from models_rbac import Tenant

logger = logging.getLogger(__name__)


class SlashCommandPermissionService:
    """Evaluates slash command permissions per sender / tenant."""

    SYSTEM_DEFAULT_POLICY = "enabled_for_known"

    def __init__(self, db: Session):
        self.db = db

    def is_allowed(self, sender_key: str, tenant_id: str, channel: str = "whatsapp") -> bool:
        """
        Check if the sender is allowed to use slash commands.

        Args:
            sender_key: Normalized sender identifier (phone number, WhatsApp ID, telegram ID, etc.)
            tenant_id: Tenant ID for policy lookup
            channel: Communication channel (whatsapp, telegram, playground, etc.)

        Returns:
            True if the sender may use slash commands, False otherwise.
        """
        # Playground users always have slash command access
        if channel == "playground":
            return True

        # --- Step 1: Resolve the contact ---
        contact = self._resolve_contact(sender_key, tenant_id)

        # --- Step 2: Check per-contact override ---
        if contact is not None and contact.slash_commands_enabled is not None:
            logger.debug(
                f"[SLASH_PERM] Contact override for '{sender_key}': "
                f"slash_commands_enabled={contact.slash_commands_enabled}"
            )
            return contact.slash_commands_enabled

        # --- Step 3: Get tenant policy ---
        policy = self._get_tenant_policy(tenant_id)

        # --- Step 4: Apply policy ---
        if policy == "disabled":
            return False
        elif policy == "enabled_for_all":
            return True
        elif policy == "enabled_for_known":
            # Contact must exist and be active
            return contact is not None and contact.is_active
        else:
            # Unknown policy string - fall back to system default
            logger.warning(f"[SLASH_PERM] Unknown policy '{policy}' for tenant {tenant_id}, using system default")
            return contact is not None and contact.is_active

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_contact(self, sender_key: str, tenant_id: str) -> Contact | None:
        """
        Resolve a sender_key to a Contact record.

        Uses the same resolution pattern as the router (phone number, WhatsApp ID,
        and ContactChannelMapping).
        """
        sender_normalized = sender_key.split("@")[0].lstrip("+")

        # Method 1: Search by phone number (traditional)
        contact = self.db.query(Contact).filter(
            Contact.tenant_id == tenant_id,
            or_(
                Contact.phone_number == sender_key,
                Contact.phone_number == sender_normalized,
                Contact.phone_number == f"+{sender_normalized}",
            ),
        ).first()

        if contact:
            return contact

        # Method 2: Search by WhatsApp ID
        contact = self.db.query(Contact).filter(
            Contact.tenant_id == tenant_id,
            Contact.whatsapp_id == sender_normalized,
        ).first()

        if contact:
            return contact

        # Method 3: Search by Telegram ID
        contact = self.db.query(Contact).filter(
            Contact.tenant_id == tenant_id,
            Contact.telegram_id == sender_normalized,
        ).first()

        if contact:
            return contact

        # Method 4: Search via ContactChannelMapping
        mapping = self.db.query(ContactChannelMapping).filter(
            ContactChannelMapping.tenant_id == tenant_id,
            ContactChannelMapping.channel_identifier == sender_normalized,
        ).first()

        if mapping:
            contact = self.db.query(Contact).filter(
                Contact.id == mapping.contact_id,
            ).first()
            return contact

        return None

    def _get_tenant_policy(self, tenant_id: str) -> str:
        """Return the slash command default policy for a tenant."""
        tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()

        if tenant and tenant.slash_commands_default_policy:
            return tenant.slash_commands_default_policy

        return self.SYSTEM_DEFAULT_POLICY
