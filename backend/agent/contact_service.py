"""
Contact Service - Handles user/agent identification and mention detection
Phase 4.2: Contact Management System
"""

from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from models import Contact
import re


class ContactService:
    """
    Service for managing contacts and identifying users/agents in messages.
    Provides mention detection and user recognition capabilities.
    """

    def __init__(self, db: Session):
        self.db = db
        # CACHE REMOVED: Query database directly for reliability
        # No more stale data issues after updates

    def reload_contacts(self):
        """No-op: Cache removed, queries are always fresh"""
        pass

    def get_agent_contacts(self) -> List[Contact]:
        """Get all active agent contacts"""
        return self.db.query(Contact).filter(
            Contact.is_active == True,
            Contact.role == "agent"
        ).all()

    def get_user_contacts(self) -> List[Contact]:
        """Get all active user contacts"""
        return self.db.query(Contact).filter(
            Contact.is_active == True,
            Contact.role == "user"
        ).all()

    def get_dm_trigger_contacts(self) -> List[Contact]:
        """
        Get all contacts that should trigger agent responses in direct messages.
        Phase 4.3: Contacts with is_dm_trigger=True

        Returns:
            List of Contact objects with is_dm_trigger enabled
        """
        return self.db.query(Contact).filter(
            Contact.is_active == True,
            Contact.is_dm_trigger == True
        ).all()

    def identify_sender(self, sender: str, sender_name: str = None) -> Optional[Contact]:
        """
        Identify a sender by their phone number or WhatsApp ID.

        Args:
            sender: Phone number or WhatsApp ID (e.g., "5500000000001" or "123456789012345")
            sender_name: Optional sender name from WhatsApp

        Returns:
            Contact object if found, None otherwise
        """
        # Normalize sender (remove + prefix)
        sender_normalized = sender.lstrip("+")

        # Search by phone number (query database directly)
        contact = self.db.query(Contact).filter(
            Contact.is_active == True,
            Contact.phone_number.like(f"%{sender_normalized}")
        ).first()
        if contact:
            return contact

        # Search by WhatsApp ID (query database directly)
        contact = self.db.query(Contact).filter(
            Contact.is_active == True,
            Contact.whatsapp_id == sender_normalized
        ).first()

        return contact

    def detect_mentions(self, message_body: str) -> List[Contact]:
        """
        Detect all mentions in a message body.
        Supports formats: @FriendlyName, @whatsapp_id, @phone_number

        Args:
            message_body: The message text to scan for mentions

        Returns:
            List of Contact objects that were mentioned
        """
        mentioned_contacts = []
        message_lower = message_body.lower()

        # Find all @mention patterns (word characters, numbers, or +)
        mention_pattern = r'@([\w+]+)'
        mentions = re.findall(mention_pattern, message_body, re.IGNORECASE)

        for mention in mentions:
            # Try to match against each contact
            contact = self._find_contact_by_mention(mention)
            if contact and contact not in mentioned_contacts:
                mentioned_contacts.append(contact)

        return mentioned_contacts

    def _find_contact_by_mention(self, mention: str) -> Optional[Contact]:
        """
        Find a contact by a mention string (without @ symbol).
        Tries: friendly_name, whatsapp_id, phone_number, and agent keywords

        For agent contacts, also checks the agent's configured keywords to support
        mentions like @cythel matching an agent with keyword "cythel".
        """
        mention_normalized = mention.lstrip("+").lower()

        # Get all active contacts (query database directly)
        contacts = self.db.query(Contact).filter(Contact.is_active == True).all()

        for contact in contacts:
            # Check friendly name (case-insensitive)
            if contact.friendly_name.lower() == mention_normalized:
                return contact

            # Check WhatsApp ID
            if contact.whatsapp_id and contact.whatsapp_id == mention_normalized:
                return contact

            # Check phone number (with and without + prefix)
            if contact.phone_number:
                phone_normalized = contact.phone_number.lstrip("+")
                if phone_normalized == mention_normalized:
                    return contact

            # For agent contacts, also check agent keywords
            # This allows @cythel to match an agent with keyword "cythel"
            if contact.role == "agent":
                from models import Agent
                import json

                agent = self.db.query(Agent).filter(
                    Agent.contact_id == contact.id,
                    Agent.is_active == True
                ).first()

                if agent and agent.keywords:
                    # Parse keywords (handle both list and JSON string)
                    keywords = agent.keywords if isinstance(agent.keywords, list) else (
                        json.loads(agent.keywords) if agent.keywords else []
                    )

                    # Check if mention matches any keyword (case-insensitive)
                    for keyword in keywords:
                        if keyword.lower() == mention_normalized:
                            return contact

        return None

    def is_agent_mentioned(self, message_body: str) -> bool:
        """
        Check if any agent is mentioned in the message.

        Args:
            message_body: The message text to scan

        Returns:
            True if any agent is mentioned, False otherwise
        """
        mentioned = self.detect_mentions(message_body)
        return any(contact.role == "agent" for contact in mentioned)

    def get_mentioned_agent(self, message_body: str) -> Optional[Contact]:
        """
        Get the first agent mentioned in the message.

        Returns:
            First agent Contact found, or None
        """
        mentioned = self.detect_mentions(message_body)
        for contact in mentioned:
            if contact.role == "agent":
                return contact
        return None

    def format_contacts_for_context(self, agent_id: Optional[int] = None) -> str:
        """
        Format contacts into a context string for the AI agent.
        Includes both users and the agent's own identity.

        Args:
            agent_id: Agent ID to inject identity for.
                     REQUIRED to prevent contamination.
                     If None, logs critical error and returns minimal context.

        Returns:
            Formatted string with contact information
        """
        lines = ["# Contact Directory\n"]

        # CRITICAL FIX 2026-01-17: agent_id is REQUIRED to prevent contamination
        # The old fallback that injected ALL agents caused identity contamination
        # where agents would adopt other agents' identities (e.g., @movl)
        if not agent_id:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(
                "CRITICAL: format_contacts_for_context called without agent_id! "
                "This causes identity contamination. Returning minimal context."
            )
            # Return minimal context to prevent contamination
            return "# Contact Directory\n\n## Your Identity:\n- You are an AI assistant\n"

        # Inject ONLY the CURRENT agent's identity
        from models import Agent
        agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
        if agent and agent.contact_id:
            agent_contact = self.db.query(Contact).filter(Contact.id == agent.contact_id).first()
            if agent_contact:
                lines.append("## Your Identity:")
                lines.append(f"- Name: {agent_contact.friendly_name}")
                if agent_contact.whatsapp_id:
                    lines.append(f"  WhatsApp ID: {agent_contact.whatsapp_id}")
                if agent_contact.phone_number:
                    lines.append(f"  Phone: {agent_contact.phone_number}")
                lines.append("")
        else:
            # Agent not found or no contact assigned
            lines.append("## Your Identity:")
            lines.append(f"- Agent ID: {agent_id}")
            lines.append("")

        # Known users
        users = self.get_user_contacts()
        if users:
            lines.append("## Known Users:")
            for user in users:
                lines.append(f"- {user.friendly_name}")
                if user.whatsapp_id:
                    lines.append(f"  WhatsApp ID: {user.whatsapp_id}")
                if user.phone_number:
                    lines.append(f"  Phone: {user.phone_number}")
                if user.notes:
                    lines.append(f"  Notes: {user.notes}")
                lines.append("")

        return "\n".join(lines)

    def resolve_identifier(self, identifier: str) -> Optional[Contact]:
        """
        Resolve a contact by any identifier (name, @mention, phone, WhatsApp ID).

        Args:
            identifier: Contact identifier (e.g., "@Alice", "Alice", "+1234567890")

        Returns:
            Contact if found, None otherwise
        """
        if not identifier:
            return None

        # Remove @ prefix if present
        identifier = identifier.lstrip("@")

        # Use existing _find_contact_by_mention logic
        return self._find_contact_by_mention(identifier)

    def enrich_message_with_sender_info(self, message: Dict) -> Dict:
        """
        Enrich a message dictionary with sender contact information.

        Args:
            message: Message dict with 'sender' and 'sender_name' fields

        Returns:
            Message dict with added 'sender_contact' field if found
        """
        sender = message.get("sender", "")
        sender_name = message.get("sender_name", "")

        contact = self.identify_sender(sender, sender_name)
        if contact:
            message["sender_contact"] = {
                "id": contact.id,
                "friendly_name": contact.friendly_name,
                "role": contact.role
            }

        return message
