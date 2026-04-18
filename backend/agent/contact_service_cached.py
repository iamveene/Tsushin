"""
Phase 6.11.3: Cached Contact Service

Implements LRU caching for contact lookups to reduce database queries.

Performance Goals:
- 80%+ cache hit rate (most messages from same senders)
- ~50-100ms saved per cache hit
- 1000 entry capacity with 5-minute TTL
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
import logging
from sqlalchemy import or_
from models import Contact, ContactChannelMapping

logger = logging.getLogger(__name__)


class CachedContactService:
    """
    Contact service with LRU caching (Phase 6.11.3).

    Cache Strategy:
    - LRU cache with TTL (5 minutes)
    - 1000 entry maximum
    - Auto-eviction on expiry
    - Manual clear on contact updates

    Expected Performance:
    - 80%+ cache hit rate (most messages from same senders)
    - ~50-100ms saved per cache hit
    - Reduced database load
    """

    def __init__(self, db, tenant_id: Optional[str] = None):
        """
        V060-CHN-006: tenant_id is required to prevent cross-tenant contact leakage.
        Accepted as Optional for backward-compat with call sites that don't yet
        pass it, but strongly-typed routing paths should always supply it.
        When tenant_id is None, _fetch_from_db returns None (fail-closed) instead
        of leaking contacts from other tenants.
        """
        self.db = db
        self.tenant_id = tenant_id
        self._cache: Dict[str, Tuple[datetime, Optional[Contact]]] = {}
        self._cache_ttl = timedelta(minutes=5)
        self._cache_hits = 0
        self._cache_misses = 0
        self._max_cache_size = 1000
        self.logger = logging.getLogger(__name__)

    def identify_sender(self, identifier: str) -> Optional[Contact]:
        """
        Identify sender with caching.

        Args:
            identifier: Phone number or WhatsApp ID

        Returns:
            Contact object or None
        """
        now = datetime.utcnow()

        candidates = self._build_identifier_candidates(identifier)
        if not candidates:
            return None

        # V060-CHN-006: Scope cache keys by tenant_id so two tenants with the
        # same raw identifier (e.g., phone number) can't share cached hits.
        tenant_prefix = f"{self.tenant_id or '__no_tenant__'}::"

        # Check cache for any known identifier
        for candidate in candidates:
            cache_key = tenant_prefix + candidate
            if cache_key in self._cache:
                cached_time, contact = self._cache[cache_key]
                if now - cached_time < self._cache_ttl:
                    self._cache_hits += 1
                    if contact:
                        self.logger.debug(f"Contact cache HIT for {candidate[:10]}...")
                        return contact
                    continue
                else:
                    del self._cache[cache_key]
                    self.logger.debug(f"Contact cache EXPIRED for {candidate[:10]}...")

        # Cache miss - fetch from database across candidates
        self._cache_misses += 1
        self.logger.debug(f"Contact cache MISS for {candidates[0][:10]}..., querying DB")
        for candidate in candidates:
            contact = self._fetch_from_db(candidate)
            if contact:
                for alias in candidates:
                    self._cache[tenant_prefix + alias] = (now, contact)
                self._evict_if_needed(now)
                return contact

        # Store negative result for all candidates to prevent repeated lookups
        for alias in candidates:
            self._cache[tenant_prefix + alias] = (now, None)
        self._evict_if_needed(now)

        return None

    def _build_identifier_candidates(self, identifier: str) -> list:
        if not identifier:
            return []

        candidates = []
        for candidate in [
            identifier,
            identifier.split("@")[0],
        ]:
            if candidate and candidate not in candidates:
                candidates.append(candidate)

        normalized = candidates[-1].lstrip("+")
        if normalized and normalized not in candidates:
            candidates.append(normalized)

        normalized_full = identifier.lstrip("+")
        if normalized_full and normalized_full not in candidates:
            candidates.append(normalized_full)

        digit_candidates = []
        for candidate in list(candidates):
            digits = "".join(ch for ch in candidate if ch.isdigit())
            if digits and digits not in candidates and digits not in digit_candidates:
                digit_candidates.append(digits)
            if digits.startswith("55") and len(digits) > 11:
                stripped = digits[2:]
                if stripped not in candidates and stripped not in digit_candidates:
                    digit_candidates.append(stripped)
            elif digits and len(digits) in (10, 11):
                with_country = f"55{digits}"
                if with_country not in candidates and with_country not in digit_candidates:
                    digit_candidates.append(with_country)

        candidates.extend(digit_candidates)

        return candidates

    def _fetch_from_db(self, identifier: str) -> Optional[Contact]:
        """Fetch contact from database (Phase 10.1.1: Added telegram_id support).

        V060-CHN-006: Queries are scoped to self.tenant_id. When tenant_id is
        unset, this returns None (fail-closed) so we never leak contacts across
        tenants. Legacy rows with NULL tenant_id are intentionally unreachable
        via tenant-scoped lookups.
        """
        if not self.tenant_id:
            self.logger.warning(
                "CachedContactService._fetch_from_db called without tenant_id — "
                "refusing to query untenanted contacts (V060-CHN-006 fail-closed)."
            )
            return None

        phone_variants = [identifier]
        if identifier and identifier.isdigit():
            phone_variants.append(f"+{identifier}")

        contact = self.db.query(Contact).filter(
            Contact.tenant_id == self.tenant_id,
            or_(
                Contact.phone_number.in_(phone_variants),
                Contact.phone_number.like(f"%{identifier}"),
                Contact.whatsapp_id == identifier,
                Contact.telegram_id == identifier,  # Phase 10.1.1
            )
        ).first()

        if contact:
            return contact

        # Fallback: Search channel mappings (Slack, Discord, etc.) — tenant-scoped
        mapping = self.db.query(ContactChannelMapping).filter(
            ContactChannelMapping.tenant_id == self.tenant_id,
            or_(
                ContactChannelMapping.channel_identifier == identifier,
                ContactChannelMapping.channel_identifier.like(f"%:{identifier}")
            )
        ).first()

        if mapping:
            return self.db.query(Contact).filter(
                Contact.id == mapping.contact_id,
                Contact.tenant_id == self.tenant_id,
                Contact.is_active == True
            ).first()

        return None

    def _evict_if_needed(self, now: datetime):
        """Evict expired or excess entries"""
        # Remove expired entries
        expired = [
            key for key, (cached_time, _) in self._cache.items()
            if now - cached_time > self._cache_ttl
        ]
        for key in expired:
            del self._cache[key]

        if expired:
            self.logger.debug(f"Evicted {len(expired)} expired cache entries")

        # If still too large, remove oldest entries (LRU)
        if len(self._cache) > self._max_cache_size:
            sorted_entries = sorted(
                self._cache.items(),
                key=lambda x: x[1][0]  # Sort by timestamp
            )
            to_remove = len(self._cache) - self._max_cache_size
            for key, _ in sorted_entries[:to_remove]:
                del self._cache[key]

            self.logger.info(f"Evicted {to_remove} LRU cache entries (max size reached)")

    def clear_cache(self):
        """Clear all cached entries (use after contact updates)"""
        cache_size = len(self._cache)
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0
        self.logger.info(f"Contact cache cleared ({cache_size} entries removed)")

    def get_cache_stats(self) -> Dict:
        """Get cache performance statistics"""
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total * 100) if total > 0 else 0

        return {
            "cache_size": len(self._cache),
            "max_size": self._max_cache_size,
            "ttl_minutes": int(self._cache_ttl.total_seconds() / 60),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "total_requests": total,
            "hit_rate_percent": round(hit_rate, 2)
        }

    # Delegate other methods to base ContactService if needed
    def get_mentioned_agent(self, message_text: str):
        """Delegate to base implementation (no caching needed)"""
        from agent.contact_service import ContactService
        base_service = ContactService(self.db, tenant_id=self.tenant_id)  # V060-CHN-006
        return base_service.get_mentioned_agent(message_text)

    def extract_mention_and_command(self, message_body: str):
        """Delegate to base implementation (no caching needed)"""
        from agent.contact_service import ContactService
        base_service = ContactService(self.db, tenant_id=self.tenant_id)  # V060-CHN-006
        return base_service.extract_mention_and_command(message_body)

    def resolve_identifier(self, identifier: str):
        """Delegate with caching"""
        return self.identify_sender(identifier)

    def get_all_contacts(self):
        """Get all contacts (no caching - infrequent operation)"""
        from agent.contact_service import ContactService
        base_service = ContactService(self.db, tenant_id=self.tenant_id)  # V060-CHN-006
        return base_service.get_all_contacts()

    def create_contact(self, *args, **kwargs):
        """Create contact and clear cache"""
        from agent.contact_service import ContactService
        base_service = ContactService(self.db, tenant_id=self.tenant_id)  # V060-CHN-006
        result = base_service.create_contact(*args, **kwargs)
        self.clear_cache()
        return result

    def update_contact(self, *args, **kwargs):
        """Update contact and clear cache"""
        from agent.contact_service import ContactService
        base_service = ContactService(self.db, tenant_id=self.tenant_id)  # V060-CHN-006
        result = base_service.update_contact(*args, **kwargs)
        self.clear_cache()
        return result

    def delete_contact(self, *args, **kwargs):
        """Delete contact and clear cache"""
        from agent.contact_service import ContactService
        base_service = ContactService(self.db, tenant_id=self.tenant_id)  # V060-CHN-006
        result = base_service.delete_contact(*args, **kwargs)
        self.clear_cache()
        return result

    def format_contacts_for_context(self, agent_id=None):
        """Format contacts for AI context (no caching - infrequent operation)"""
        from agent.contact_service import ContactService
        base_service = ContactService(self.db, tenant_id=self.tenant_id)  # V060-CHN-006
        return base_service.format_contacts_for_context(agent_id)

    def detect_mentions(self, message_body: str):
        """Detect mentions (no caching - per-message operation)"""
        from agent.contact_service import ContactService
        base_service = ContactService(self.db, tenant_id=self.tenant_id)  # V060-CHN-006
        return base_service.detect_mentions(message_body)

    def get_agent_contacts(self):
        """Get agent contacts (no caching - infrequent operation)"""
        from agent.contact_service import ContactService
        base_service = ContactService(self.db, tenant_id=self.tenant_id)  # V060-CHN-006
        return base_service.get_agent_contacts()

    def get_user_contacts(self):
        """Get user contacts (no caching - infrequent operation)"""
        from agent.contact_service import ContactService
        base_service = ContactService(self.db, tenant_id=self.tenant_id)  # V060-CHN-006
        return base_service.get_user_contacts()

    def get_dm_trigger_contacts(self):
        """Get DM trigger contacts (no caching - infrequent operation)"""
        from agent.contact_service import ContactService
        base_service = ContactService(self.db, tenant_id=self.tenant_id)  # V060-CHN-006
        return base_service.get_dm_trigger_contacts()

    def enrich_message_with_sender_info(self, message):
        """Enrich message with sender info (uses caching via identify_sender)"""
        sender = message.get("sender", "")
        sender_name = message.get("sender_name", "")

        contact = self.identify_sender(sender)  # Uses cache
        if contact:
            message["sender_contact"] = {
                "id": contact.id,
                "friendly_name": contact.friendly_name,
                "role": contact.role
            }

        return message
