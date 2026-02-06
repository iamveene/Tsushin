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
from models import Contact

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

    def __init__(self, db):
        self.db = db
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

        # Check cache for any known identifier
        for candidate in candidates:
            if candidate in self._cache:
                cached_time, contact = self._cache[candidate]
                if now - cached_time < self._cache_ttl:
                    self._cache_hits += 1
                    if contact:
                        self.logger.debug(f"Contact cache HIT for {candidate[:10]}...")
                        return contact
                    continue
                else:
                    del self._cache[candidate]
                    self.logger.debug(f"Contact cache EXPIRED for {candidate[:10]}...")

        # Cache miss - fetch from database across candidates
        self._cache_misses += 1
        self.logger.debug(f"Contact cache MISS for {candidates[0][:10]}..., querying DB")
        for candidate in candidates:
            contact = self._fetch_from_db(candidate)
            if contact:
                for alias in candidates:
                    self._cache[alias] = (now, contact)
                self._evict_if_needed(now)
                return contact

        # Store negative result for all candidates to prevent repeated lookups
        for alias in candidates:
            self._cache[alias] = (now, None)
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

        return candidates

    def _fetch_from_db(self, identifier: str) -> Optional[Contact]:
        """Fetch contact from database (Phase 10.1.1: Added telegram_id support)"""
        contact = self.db.query(Contact).filter(
            (Contact.phone_number == identifier) |
            (Contact.whatsapp_id == identifier) |
            (Contact.telegram_id == identifier)  # Phase 10.1.1
        ).first()

        return contact

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
        base_service = ContactService(self.db)
        return base_service.get_mentioned_agent(message_text)

    def resolve_identifier(self, identifier: str):
        """Delegate with caching"""
        return self.identify_sender(identifier)

    def get_all_contacts(self):
        """Get all contacts (no caching - infrequent operation)"""
        from agent.contact_service import ContactService
        base_service = ContactService(self.db)
        return base_service.get_all_contacts()

    def create_contact(self, *args, **kwargs):
        """Create contact and clear cache"""
        from agent.contact_service import ContactService
        base_service = ContactService(self.db)
        result = base_service.create_contact(*args, **kwargs)
        self.clear_cache()
        return result

    def update_contact(self, *args, **kwargs):
        """Update contact and clear cache"""
        from agent.contact_service import ContactService
        base_service = ContactService(self.db)
        result = base_service.update_contact(*args, **kwargs)
        self.clear_cache()
        return result

    def delete_contact(self, *args, **kwargs):
        """Delete contact and clear cache"""
        from agent.contact_service import ContactService
        base_service = ContactService(self.db)
        result = base_service.delete_contact(*args, **kwargs)
        self.clear_cache()
        return result

    def format_contacts_for_context(self, agent_id=None):
        """Format contacts for AI context (no caching - infrequent operation)"""
        from agent.contact_service import ContactService
        base_service = ContactService(self.db)
        return base_service.format_contacts_for_context(agent_id)

    def detect_mentions(self, message_body: str):
        """Detect mentions (no caching - per-message operation)"""
        from agent.contact_service import ContactService
        base_service = ContactService(self.db)
        return base_service.detect_mentions(message_body)

    def get_agent_contacts(self):
        """Get agent contacts (no caching - infrequent operation)"""
        from agent.contact_service import ContactService
        base_service = ContactService(self.db)
        return base_service.get_agent_contacts()

    def get_user_contacts(self):
        """Get user contacts (no caching - infrequent operation)"""
        from agent.contact_service import ContactService
        base_service = ContactService(self.db)
        return base_service.get_user_contacts()

    def get_dm_trigger_contacts(self):
        """Get DM trigger contacts (no caching - infrequent operation)"""
        from agent.contact_service import ContactService
        base_service = ContactService(self.db)
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
