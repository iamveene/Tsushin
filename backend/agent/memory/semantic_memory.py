"""
Semantic Memory Service - Combines ring buffer with vector semantic search

Provides hybrid memory:
- Recent messages from ring buffer (temporal context)
- Semantically relevant messages from vector store (contextual relevance)
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime
import importlib.util

# Import SenderMemory from agent/memory.py
import os
import sys
# Get the absolute path to the backend directory
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
memory_file = os.path.join(backend_dir, "agent", "memory.py")
spec = importlib.util.spec_from_file_location("sender_memory", memory_file)
sender_memory_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sender_memory_module)
SenderMemory = sender_memory_module.SenderMemory

from .embedding_service import EmbeddingService
from .vector_store import VectorStore
from .vector_store_manager import get_vector_store


class SemanticMemoryService:
    """
    Hybrid memory service combining ring buffer and semantic search.

    Attributes:
        ring_buffer: SenderMemory instance for recent messages
        vector_store: VectorStore for semantic search
        embedding_service: EmbeddingService for generating embeddings
        logger: Logger instance
    """

    def __init__(
        self,
        persist_directory: str,
        max_ring_buffer_size: int = 10,
        enable_semantic: bool = True,
        vector_store_override=None,
    ):
        """
        Initialize semantic memory service.

        Args:
            persist_directory: Directory for ChromaDB persistence
            max_ring_buffer_size: Max messages in ring buffer per sender
            enable_semantic: Whether to enable semantic search
            vector_store_override: Optional ProviderBridgeStore to use instead of ChromaDB default.
                                  When provided, replaces the VectorStoreManager-managed store.
                                  v0.6.1: Enables external vector store backends.
        """
        self.logger = logging.getLogger(__name__)
        self.enable_semantic = enable_semantic

        # Initialize ring buffer (always active)
        self.ring_buffer = SenderMemory(max_size=max_ring_buffer_size)
        self.logger.info(f"Ring buffer initialized (size: {max_ring_buffer_size})")

        # Initialize semantic search components (if enabled)
        if self.enable_semantic:
            if vector_store_override is not None:
                # v0.6.1: Use external vector store provider via bridge
                self.vector_store = vector_store_override
                self.embedding_service = vector_store_override.embedding_service
                self.logger.info("Semantic search enabled (using external vector store provider)")
            else:
                # Default: Use VectorStore manager (ChromaDB)
                self.vector_store = get_vector_store(persist_directory, embedding_model="all-MiniLM-L6-v2")
                self.embedding_service = self.vector_store.embedding_service
                self.logger.info("Semantic search enabled (using VectorStore manager)")
        else:
            self.embedding_service = None
            self.vector_store = None
            self.logger.info("Semantic search disabled")

    async def add_message(
        self,
        sender_key: str,
        role: str,
        content: str,
        message_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Add a message to both ring buffer and vector store.

        Args:
            sender_key: Sender identifier
            role: Message role ('user' or 'assistant')
            content: Message content
            message_id: Optional unique message ID
            metadata: Optional additional metadata
        """
        # Always add to ring buffer (including metadata for tool output tracking)
        self.ring_buffer.add_message(sender_key, role, content, metadata, message_id)

        # Add to vector store if semantic search is enabled and it's a user message
        if self.enable_semantic and role == 'user' and message_id:
            try:
                msg_metadata = metadata or {}
                msg_metadata['timestamp'] = datetime.utcnow().isoformat() + "Z"
                msg_metadata['role'] = role

                await self.vector_store.add_message(
                    message_id=message_id,
                    sender_key=sender_key,
                    text=content,
                    metadata=msg_metadata
                )
                self.logger.debug(f"Added message {message_id} to vector store")
            except Exception as e:
                self.logger.error(f"Failed to add message to vector store: {e}")

    async def get_context(
        self,
        sender_key: str,
        current_message: str,
        max_semantic_results: int = 5,
        similarity_threshold: float = 0.3,
        decay_config=None
    ) -> Dict:
        """
        Get hybrid context: recent messages + semantically relevant messages.

        Args:
            sender_key: Sender identifier
            current_message: Current message to find context for
            max_semantic_results: Max semantic search results
            similarity_threshold: Minimum similarity score (0-1, lower distance = more similar)
            decay_config: Optional DecayConfig for temporal decay and MMR reranking

        Returns:
            Dictionary containing:
                - recent_messages: List of recent messages from ring buffer
                - semantic_messages: List of semantically relevant messages
                - all_messages: Combined and deduplicated list
        """
        context = {
            'recent_messages': [],
            'semantic_messages': [],
            'all_messages': []
        }

        # Get recent messages from ring buffer
        recent = self.ring_buffer.get_messages(sender_key)
        context['recent_messages'] = recent

        # Determine if decay is active
        decay_enabled = (
            decay_config is not None
            and getattr(decay_config, 'enabled', False)
        )

        # Get semantically relevant messages (if enabled)
        if self.enable_semantic and current_message:
            try:
                if decay_enabled:
                    # Over-fetch for decay filtering + MMR reranking
                    fetch_limit = max_semantic_results * 3
                    results, query_embedding, result_embeddings = \
                        await self.vector_store.search_similar_with_embeddings(
                            query_text=current_message,
                            sender_key=sender_key,
                            limit=fetch_limit
                        )
                else:
                    results = await self.vector_store.search_similar(
                        query_text=current_message,
                        sender_key=sender_key,
                        limit=max_semantic_results
                    )

                semantic_messages = []
                accessed_ids = []

                if decay_enabled:
                    from .temporal_decay import (
                        apply_decay_to_score, compute_freshness_label,
                        should_archive, mmr_rerank
                    )
                    now = datetime.utcnow()

                    # Build candidates with decayed scores
                    candidates = []
                    for idx, result in enumerate(results):
                        distance = result['distance']
                        raw_similarity = 1 / (1 + distance)

                        if raw_similarity < similarity_threshold:
                            continue

                        # Parse last_accessed_at from metadata
                        la_str = result.get('last_accessed_at')
                        last_accessed = None
                        if la_str:
                            try:
                                last_accessed = datetime.fromisoformat(la_str.replace('Z', ''))
                            except (ValueError, AttributeError):
                                pass

                        decayed = apply_decay_to_score(
                            raw_similarity, last_accessed, now, decay_config.decay_lambda
                        )

                        if should_archive(decayed, decay_config.archive_threshold):
                            continue

                        freshness = compute_freshness_label(
                            last_accessed, now, decay_config.decay_lambda,
                            decay_config.archive_threshold
                        )

                        emb = result_embeddings[idx] if idx < len(result_embeddings) else []

                        candidates.append({
                            'role': result.get('role', 'user'),
                            'content': result['text'],
                            'similarity': raw_similarity,
                            'decayed_score': decayed,
                            'message_id': result['message_id'],
                            'embedding': emb,
                            'freshness': freshness['freshness'],
                            'decay_factor': freshness['decay_factor'],
                            'days_since_access': freshness['days_since_access'],
                        })

                    # Apply MMR reranking
                    if candidates and query_embedding:
                        reranked = mmr_rerank(
                            candidates, query_embedding,
                            mmr_lambda=decay_config.mmr_lambda,
                            top_k=max_semantic_results
                        )
                    else:
                        reranked = candidates[:max_semantic_results]

                    for c in reranked:
                        sem_msg = {
                            'role': c['role'],
                            'content': c['content'],
                            'similarity': c['similarity'],
                            'decayed_score': c['decayed_score'],
                            'message_id': c['message_id'],
                            'freshness': c['freshness'],
                            'decay_factor': c['decay_factor'],
                            'days_since_access': c['days_since_access'],
                        }
                        semantic_messages.append(sem_msg)
                        accessed_ids.append(c['message_id'])

                    # Update access times for returned results
                    if accessed_ids:
                        try:
                            self.vector_store.update_access_time(accessed_ids)
                        except Exception as e:
                            self.logger.warning(f"Failed to update access times: {e}")

                else:
                    # Original behavior (no decay)
                    for result in results:
                        distance = result['distance']
                        similarity = 1 / (1 + distance)

                        if similarity >= similarity_threshold:
                            semantic_messages.append({
                                'role': result.get('role', 'user'),
                                'content': result['text'],
                                'similarity': similarity,
                                'message_id': result['message_id']
                            })

                context['semantic_messages'] = semantic_messages
                self.logger.debug(f"Found {len(semantic_messages)} semantic matches above threshold")

            except Exception as e:
                self.logger.error(f"Semantic search failed: {e}")

        # Combine messages (deduplicate by content)
        all_messages = []
        seen_content = set()

        # Add recent messages first (highest priority)
        for msg in recent:
            content = msg['content']
            if content not in seen_content:
                all_messages.append(msg)
                seen_content.add(content)

        # Add semantic messages (lower priority, skip duplicates)
        for msg in context['semantic_messages']:
            content = msg['content']
            if content not in seen_content:
                all_messages.append(msg)
                seen_content.add(content)

        context['all_messages'] = all_messages

        return context

    def clear_sender(self, sender_key: str) -> None:
        """
        Clear all memory for a sender.

        Args:
            sender_key: Sender identifier
        """
        # Clear ring buffer
        self.ring_buffer.clear(sender_key)

        # Clear vector store
        if self.enable_semantic:
            try:
                self.vector_store.delete_by_sender(sender_key)
                self.logger.info(f"Cleared all memory for {sender_key}")
            except Exception as e:
                self.logger.error(f"Failed to clear vector store: {e}")

    def get_stats(self) -> Dict:
        """
        Get memory statistics.

        Returns:
            Dictionary with statistics
        """
        stats = {
            'ring_buffer_senders': len(self.ring_buffer.memories),
            'semantic_enabled': self.enable_semantic
        }

        if self.enable_semantic:
            vector_stats = self.vector_store.get_stats()
            stats.update({
                'vector_store_messages': vector_stats['total_messages'],
                'vector_store_collection': vector_stats['collection_name']
            })

        return stats

    def format_context_for_agent(self, context: Dict, contact_service=None) -> str:
        """
        Format context dictionary into a string for agent consumption.
        Phase 4.2: Enhanced with contact information.

        Args:
            context: Context dictionary from get_context()
            contact_service: Optional ContactService for user identification

        Returns:
            Formatted string with conversation history
        """
        lines = []

        # Add recent conversation
        if context['recent_messages']:
            lines.append("Recent conversation:")
            for msg in context['recent_messages']:
                role = msg['role'].upper()
                content = msg['content']

                # Add sender identification if available (Phase 4.2)
                sender_info = msg.get('sender_name', '')
                if sender_info:
                    lines.append(f"  [{role} - {sender_info}] {content}")
                else:
                    lines.append(f"  [{role}] {content}")

        # Add semantically relevant messages
        if context['semantic_messages']:
            lines.append("\nRelevant past messages:")
            for msg in context['semantic_messages']:
                similarity = msg.get('similarity', 0)
                content = msg['content']
                sender_info = msg.get('sender_name', '')

                if sender_info:
                    lines.append(f"  [PAST - {similarity:.0%} - {sender_info}] {content}")
                else:
                    lines.append(f"  [PAST - {similarity:.0%}] {content}")

        return "\n".join(lines) if lines else "No previous context"

    async def add_user_aware_message(
        self,
        sender_key: str,
        role: str,
        content: str,
        message_id: Optional[str] = None,
        contact_service=None,
        sender_identifier: Optional[str] = None
    ) -> None:
        """
        Phase 4.2: Add a message with user identification.

        Args:
            sender_key: Sender identifier (chat_id or phone)
            role: Message role ('user' or 'assistant')
            content: Message content
            message_id: Optional unique message ID
            contact_service: ContactService for user lookup
            sender_identifier: Sender's phone/whatsapp_id for identification
        """
        metadata = {}

        # Identify sender if contact service is available
        if contact_service and sender_identifier:
            contact = contact_service.identify_sender(sender_identifier)
            if contact:
                metadata['sender_name'] = contact.friendly_name
                metadata['sender_id'] = contact.id
                metadata['sender_role'] = contact.role

        await self.add_message(sender_key, role, content, message_id, metadata)
