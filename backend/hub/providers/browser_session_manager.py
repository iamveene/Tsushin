"""
Browser Session Manager — Phase 35a

Singleton that caches live PlaywrightProvider instances keyed by
(tenant_id, agent_id, sender_key) to persist browser state across
multiple tool calls within a conversation.

Sessions auto-expire after configurable idle timeout (default 300s).
A background cleanup loop evicts expired sessions every 60 seconds.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

SessionKey = Tuple[str, int, str]  # (tenant_id, agent_id, sender_key)


@dataclass
class BrowserSession:
    """A live browser session with its provider and metadata."""
    provider: object  # PlaywrightProvider — avoid circular import
    session_key: SessionKey
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_used_at: datetime = field(default_factory=datetime.utcnow)
    ttl_seconds: int = 300

    def is_expired(self) -> bool:
        return (datetime.utcnow() - self.last_used_at).total_seconds() > self.ttl_seconds

    def touch(self) -> None:
        self.last_used_at = datetime.utcnow()


class BrowserSessionManager:
    """
    Application-scoped singleton for browser session caching.

    Usage:
        mgr = BrowserSessionManager.instance()
        session = await mgr.get_or_create(tenant_id, agent_id, sender_key, config)
        provider = session.provider  # reuse across conversation turns
    """
    _instance: Optional["BrowserSessionManager"] = None

    def __init__(self):
        self._sessions: Dict[SessionKey, BrowserSession] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    @classmethod
    def instance(cls) -> "BrowserSessionManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for tests)."""
        cls._instance = None

    async def get_or_create(
        self,
        tenant_id: str,
        agent_id: int,
        sender_key: str,
        config: "BrowserConfig",
        ttl_seconds: int = 300,
        max_sessions: int = 3,
        provider_factory=None,
    ) -> BrowserSession:
        """
        Return an existing live session or create a fresh one.

        Args:
            tenant_id: Tenant identifier
            agent_id: Agent ID
            sender_key: Sender identifier (channel-specific)
            config: BrowserConfig for provider initialization
            ttl_seconds: Idle timeout in seconds
            max_sessions: Max concurrent sessions (enforced globally)
            provider_factory: Optional callable(config) -> provider. Defaults to PlaywrightProvider.
        """
        key: SessionKey = (str(tenant_id), agent_id, sender_key)
        async with self._lock:
            session = self._sessions.get(key)
            if session and not session.is_expired() and session.provider.is_initialized():
                session.touch()
                logger.debug(f"Reusing browser session for {key}")
                return session

            # Evict stale session if present
            if session:
                await self._close_session_unlocked(session)
                self._sessions.pop(key, None)

            # Enforce max sessions
            if len(self._sessions) >= max_sessions:
                from .browser_automation_provider import BrowserErrorCode
                raise BrowserSessionLimitError(
                    f"Maximum {max_sessions} concurrent browser sessions reached. "
                    "Close an existing session first."
                )

            # Create fresh provider + session
            if provider_factory is None:
                from .playwright_provider import PlaywrightProvider
                provider_factory = PlaywrightProvider
            provider = provider_factory(config)
            await provider.initialize()

            session = BrowserSession(
                provider=provider,
                session_key=key,
                ttl_seconds=ttl_seconds,
            )
            self._sessions[key] = session
            self._ensure_cleanup_running()
            logger.info(f"Created new browser session for {key}")
            return session

    async def close_session(self, tenant_id: str, agent_id: int, sender_key: str) -> bool:
        """Explicitly close a session. Returns True if a session was found and closed."""
        key: SessionKey = (str(tenant_id), agent_id, sender_key)
        async with self._lock:
            session = self._sessions.pop(key, None)
            if session:
                await self._close_session_unlocked(session)
                return True
            return False

    async def _close_session_unlocked(self, session: BrowserSession) -> None:
        """Close a session's provider. Must be called while holding _lock."""
        try:
            await session.provider.cleanup()
        except Exception as e:
            logger.warning(f"Error closing session {session.session_key}: {e}")

    def _ensure_cleanup_running(self) -> None:
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        """Background task: evict sessions idle beyond TTL every 60 seconds."""
        while True:
            await asyncio.sleep(60)
            expired_keys = []
            async with self._lock:
                for key, session in list(self._sessions.items()):
                    if session.is_expired():
                        expired_keys.append(key)
                        await self._close_session_unlocked(session)
                for key in expired_keys:
                    self._sessions.pop(key, None)
            if expired_keys:
                logger.info(f"Evicted {len(expired_keys)} expired browser sessions")
            if not self._sessions:
                break  # Stop loop when empty; restarts on next get_or_create

    @property
    def active_session_count(self) -> int:
        return len(self._sessions)


class BrowserSessionLimitError(Exception):
    """Raised when max concurrent session limit is reached."""
    pass
