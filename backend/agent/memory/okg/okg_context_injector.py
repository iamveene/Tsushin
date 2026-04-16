"""
v0.6.0 Item 3: OKG Context Injector — Layer 5 auto-recall integration.

Hooks into AgentMemorySystem.get_context() to automatically inject
relevant OKG memories into the agent's prompt context.

All injected content is HTML-escaped and wrapped in XML tags
to prevent prompt injection through stored memories.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class OKGContextInjector:
    """
    Auto-recall: searches OKG memories for each incoming message
    and formats results as an XML block for prompt context injection.
    """

    def __init__(self, okg_service):
        """
        Args:
            okg_service: OKGMemoryService instance for this agent
        """
        self._okg = okg_service

    async def get_context_block(
        self,
        user_id: str,
        current_message: str,
        limit: int = 5,
        min_confidence: float = 0.3,
    ) -> Optional[str]:
        """
        Auto-recall: search OKG for relevant memories and format as XML.

        Args:
            user_id: Sender key / user identifier
            current_message: The current message to find relevant memories for
            limit: Maximum number of memories to include
            min_confidence: Minimum confidence threshold

        Returns:
            XML string with <long_term_memory> block, or None if no relevant memories
        """
        if not current_message or not current_message.strip():
            return None

        try:
            memories = await self._okg.recall(
                query=current_message,
                user_id=user_id,
                limit=limit,
                min_confidence=min_confidence,
            )
        except Exception as e:
            logger.warning(f"OKG auto-recall failed (fail-open): {e}")
            return None

        if not memories:
            return None

        return self._okg.format_as_xml(memories)
