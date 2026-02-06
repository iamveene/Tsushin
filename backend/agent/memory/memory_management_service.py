"""
Memory Management Service for Phase 5.0
Provides inspection, cleaning, and reset capabilities for agent memory.
"""

from typing import List, Dict, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
import json
import logging

from models import Memory, SemanticKnowledge, Agent, Contact
from agent.memory.vector_store import VectorStore
from agent.memory.embedding_service import EmbeddingService
from agent.memory.vector_store_manager import get_vector_store
from agent.contact_service import ContactService

logger = logging.getLogger(__name__)


class MemoryStats:
    """Memory statistics for an agent"""
    def __init__(self, total_conversations: int, total_messages: int,
                 total_embeddings: int, storage_size_mb: float):
        self.total_conversations = total_conversations
        self.total_messages = total_messages
        self.total_embeddings = total_embeddings
        self.storage_size_mb = storage_size_mb

    def to_dict(self):
        return {
            "total_conversations": self.total_conversations,
            "total_messages": self.total_messages,
            "total_embeddings": self.total_embeddings,
            "storage_size_mb": self.storage_size_mb
        }


class ConversationSummary:
    """Summary of a conversation"""
    def __init__(self, sender_key: str, sender_name: Optional[str],
                 message_count: int, last_activity: str):
        self.sender_key = sender_key
        self.sender_name = sender_name
        self.message_count = message_count
        self.last_activity = last_activity

    def to_dict(self):
        return {
            "sender_key": self.sender_key,
            "sender_name": self.sender_name,
            "message_count": self.message_count,
            "last_activity": self.last_activity
        }


class ConversationDetails:
    """Detailed conversation data"""
    def __init__(self, sender_key: str, working_memory: List[Dict],
                 episodic_memory: List[Dict], semantic_facts: Dict):
        self.sender_key = sender_key
        self.working_memory = working_memory
        self.episodic_memory = episodic_memory
        self.semantic_facts = semantic_facts

    def to_dict(self):
        return {
            "sender_key": self.sender_key,
            "working_memory": self.working_memory,
            "episodic_memory": self.episodic_memory,
            "semantic_facts": self.semantic_facts
        }


class CleanReport:
    """Report from cleaning old messages"""
    def __init__(self, deleted_count: int, preview: List[str]):
        self.deleted_count = deleted_count
        self.preview = preview

    def to_dict(self):
        return {
            "deleted_count": self.deleted_count,
            "preview": self.preview
        }


class MemoryManagementService:
    """Service for managing agent memory"""

    def __init__(self, db: Session, agent_id: int):
        """
        Initialize memory management service for specific agent.

        Args:
            db: Database session
            agent_id: ID of the agent to manage memory for
        """
        self.db = db
        self.agent_id = agent_id

        # Initialize contact service for resolving friendly names
        self.contact_service = ContactService(db)

        # Get MCP database path for group name resolution
        from models import Config
        config = db.query(Config).first()
        self.mcp_db_path = config.messages_db_path if config else None

        # Get agent's ChromaDB path from database
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if agent and agent.chroma_db_path:
            persist_dir = agent.chroma_db_path
        else:
            # Fallback to default path
            persist_dir = f"./data/chroma/agent_{agent_id}"

        # Use VectorStore manager to prevent ChromaDB singleton conflicts
        self.vector_store = get_vector_store(persist_dir, embedding_model="all-MiniLM-L6-v2")
        # Get embedding service from the vector store
        self.embedding_service = self.vector_store.embedding_service
        # Use the same collection name as VectorStore (hardcoded "whatsapp_messages")
        self.collection_name = "whatsapp_messages"

        logger.info(f"MemoryManagementService initialized for agent {agent_id} with ChromaDB: {persist_dir} (using VectorStore manager)")

    def _resolve_sender_display_name(self, sender_key: str) -> str:
        """
        Resolve sender_key to a human-readable display name.

        Handles multiple formats:
        - DM: "5500000000001" → "Alice"
        - Group with sender: "5500000000001-1522245159@g.us" → "Alice @ Archive"
        - Group only: "120363415734826771@g.us" → "Travels 2026"

        Args:
            sender_key: Sender key from Memory table

        Returns:
            Human-readable display name
        """
        # Parse sender_key format
        contact_name = None
        group_name = None

        if "@g.us" in sender_key:
            # Group format
            if "-" in sender_key.split("@")[0]:
                # Format: phone-groupjid@g.us (e.g., "5527998656661-1522245159@g.us")
                # WhatsApp stores the FULL compound key as the group JID in chats table
                parts = sender_key.split("-")
                phone = parts[0]

                # Resolve contact
                contact = self.contact_service.resolve_identifier(phone)
                if contact:
                    contact_name = contact.friendly_name

                # Resolve group using FULL sender_key (it's stored as-is in MCP database)
                group_name = self._get_group_name(sender_key)
            else:
                # Format: groupjid@g.us (no specific sender)
                group_name = self._get_group_name(sender_key)
        else:
            # DM format: phone number
            contact = self.contact_service.resolve_identifier(sender_key)
            if contact:
                contact_name = contact.friendly_name

        # Build display name
        if contact_name and group_name:
            return f"{contact_name} @ {group_name}"
        elif contact_name:
            return contact_name
        elif group_name:
            return group_name
        else:
            # Fallback to original sender_key
            return sender_key

    def _get_group_name(self, group_jid: str) -> Optional[str]:
        """
        Get group name from MCP database.

        Args:
            group_jid: Group JID (e.g., "1522245159@g.us")

        Returns:
            Group name or None if not found
        """
        if not self.mcp_db_path:
            return None

        try:
            import sqlite3
            conn = sqlite3.connect(f"file:{self.mcp_db_path}?mode=ro", uri=True, timeout=5)
            cursor = conn.cursor()

            # Query chats table for group name
            cursor.execute(
                "SELECT name FROM chats WHERE jid = ? LIMIT 1",
                (group_jid,)
            )
            result = cursor.fetchone()
            conn.close()

            if result:
                return result[0]
        except Exception as e:
            logger.warning(f"Failed to get group name for {group_jid}: {e}")

        return None

    async def get_memory_stats(self) -> MemoryStats:
        """
        Get memory statistics for the agent.

        Returns:
            MemoryStats object with conversation and message counts
        """
        try:
            # Count conversations (unique sender_keys for this agent)
            conversations = self.db.query(Memory)\
                .filter(Memory.agent_id == self.agent_id)\
                .all()

            total_conversations = len(conversations)

            # Count total messages across all conversations
            total_messages = 0
            for conv in conversations:
                messages_json = conv.messages_json
                try:
                    # Handle both string JSON and already-parsed lists
                    if isinstance(messages_json, str):
                        messages = json.loads(messages_json) if messages_json else []
                    elif isinstance(messages_json, list):
                        messages = messages_json
                    else:
                        messages = []

                    total_messages += len(messages)
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Invalid JSON in memory for {conv.sender_key}: {e}")
                    continue

            # Count embeddings in vector store
            total_embeddings = 0
            storage_size_mb = 0.0

            try:
                stats = self.vector_store.get_stats()  # get_stats() takes no parameters
                total_embeddings = stats.get("total_messages", 0)
                # Estimate storage size (each embedding ~384 floats * 4 bytes)
                storage_size_mb = (total_embeddings * 384 * 4) / (1024 * 1024)
            except Exception as e:
                logger.warning(f"Could not get vector store stats: {e}")

            return MemoryStats(
                total_conversations=total_conversations,
                total_messages=total_messages,
                total_embeddings=total_embeddings,
                storage_size_mb=round(storage_size_mb, 2)
            )

        except Exception as e:
            logger.error(f"Error getting memory stats: {e}", exc_info=True)
            raise

    async def list_conversations(self) -> List[ConversationSummary]:
        """
        List all conversations for the agent.

        Returns:
            List of ConversationSummary objects
        """
        try:
            conversations = self.db.query(Memory)\
                .filter(Memory.agent_id == self.agent_id)\
                .order_by(Memory.updated_at.desc())\
                .all()

            summaries = []
            for conv in conversations:
                sender_key = conv.sender_key

                # Count messages
                messages_json = conv.messages_json
                try:
                    # Handle both string JSON and already-parsed lists
                    if isinstance(messages_json, str):
                        messages = json.loads(messages_json) if messages_json else []
                    elif isinstance(messages_json, list):
                        messages = messages_json
                    else:
                        messages = []

                    message_count = len(messages)
                except (json.JSONDecodeError, TypeError):
                    message_count = 0

                # Resolve friendly name with enhanced context (DM, group, group+sender)
                sender_name = self._resolve_sender_display_name(sender_key)

                summaries.append(ConversationSummary(
                    sender_key=sender_key,
                    sender_name=sender_name,
                    message_count=message_count,
                    last_activity=conv.updated_at.isoformat() if conv.updated_at else ""
                ))

            return summaries

        except Exception as e:
            logger.error(f"Error listing conversations: {e}", exc_info=True)
            raise

    async def get_conversation(self, sender_key: str) -> ConversationDetails:
        """
        Get detailed conversation data.

        Args:
            sender_key: The sender identifier (without agent_id prefix)

        Returns:
            ConversationDetails object with all memory layers
        """
        try:
            # 1. Get working memory (ring buffer) from Memory table
            memory_record = self.db.query(Memory)\
                .filter(and_(
                    Memory.agent_id == self.agent_id,
                    Memory.sender_key == sender_key
                ))\
                .first()

            working_memory = []
            if memory_record:
                messages_json = memory_record.messages_json
                try:
                    # Handle both string JSON and already-parsed lists
                    if isinstance(messages_json, str):
                        messages = json.loads(messages_json) if messages_json else []
                    elif isinstance(messages_json, list):
                        messages = messages_json
                    else:
                        messages = []

                    working_memory = messages
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Invalid JSON in memory for {full_memory_key}: {e}")

            # 2. Get episodic memory (vector store) - most recent/relevant
            episodic_memory = []
            try:
                # Search for messages from this sender
                if working_memory:
                    # Use most recent message as query
                    last_message = working_memory[-1].get("content", "")
                    results = await self.vector_store.search_with_metadata(
                        collection_name=self.collection_name,
                        query_text=last_message,
                        n_results=5,
                        filter_metadata={"sender_key": sender_key}
                    )

                    for result in results:
                        episodic_memory.append({
                            "content": result["text"],
                            "similarity": result["similarity"],
                            "timestamp": result.get("metadata", {}).get("timestamp", "")
                        })
            except Exception as e:
                logger.warning(f"Could not retrieve episodic memory: {e}")

            # 3. Get semantic facts from SemanticKnowledge table
            semantic_facts = {}
            try:
                facts = self.db.query(SemanticKnowledge)\
                    .filter(and_(
                        SemanticKnowledge.agent_id == self.agent_id,
                        SemanticKnowledge.user_id == sender_key
                    ))\
                    .all()

                for fact in facts:
                    topic = fact.topic or "general"
                    if topic not in semantic_facts:
                        semantic_facts[topic] = {}
                    semantic_facts[topic][fact.key] = {
                        "value": fact.value,
                        "confidence": fact.confidence,
                        "learned_at": fact.learned_at.isoformat() if fact.learned_at else ""
                    }
            except Exception as e:
                logger.warning(f"Could not retrieve semantic facts: {e}")

            return ConversationDetails(
                sender_key=sender_key,
                working_memory=working_memory,
                episodic_memory=episodic_memory,
                semantic_facts=semantic_facts
            )

        except Exception as e:
            logger.error(f"Error getting conversation details: {e}", exc_info=True)
            raise

    async def delete_conversation(self, sender_key: str) -> bool:
        """
        Delete all memory for a specific conversation.

        Args:
            sender_key: The sender identifier (without agent_id prefix)

        Returns:
            True if successful
        """
        try:
            # 1. Delete from Memory table (ring buffer)
            deleted_rows = self.db.query(Memory)\
                .filter(and_(
                    Memory.agent_id == self.agent_id,
                    Memory.sender_key == sender_key
                ))\
                .delete()

            logger.info(f"Deleted {deleted_rows} memory records for agent {self.agent_id}, sender {sender_key}")

            # 2. Delete from vector store (episodic memory)
            try:
                self.vector_store.delete_by_metadata(
                    collection_name=self.collection_name,
                    filter_metadata={"sender_key": sender_key}
                )
                logger.info(f"Deleted vector embeddings for {sender_key}")
            except Exception as e:
                logger.warning(f"Could not delete from vector store: {e}")

            # 3. Delete from SemanticKnowledge table
            deleted_facts = self.db.query(SemanticKnowledge)\
                .filter(and_(
                    SemanticKnowledge.agent_id == self.agent_id,
                    SemanticKnowledge.user_id == sender_key
                ))\
                .delete()

            logger.info(f"Deleted {deleted_facts} semantic facts for {sender_key}")

            # Commit all deletions
            self.db.commit()

            return True

        except Exception as e:
            logger.error(f"Error deleting conversation: {e}", exc_info=True)
            self.db.rollback()
            raise

    async def clean_old_messages(self, older_than_days: int, dry_run: bool = True) -> CleanReport:
        """
        Clean messages older than specified days.

        Args:
            older_than_days: Delete messages older than this many days
            dry_run: If True, only preview what would be deleted

        Returns:
            CleanReport with deletion count and preview
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)

            # Find old conversations
            old_conversations = self.db.query(Memory)\
                .filter(and_(
                    Memory.agent_id == self.agent_id,
                    Memory.updated_at < cutoff_date
                ))\
                .all()

            preview = []
            for conv in old_conversations[:10]:  # Preview first 10
                sender_key = conv.sender_key
                # Resolve friendly name
                contact = self.contact_service.lookup_by_identifier(sender_key)
                if contact:
                    display_name = contact.friendly_name
                else:
                    display_name = sender_key
                preview.append(f"{display_name} (last active: {conv.updated_at})")

            if not dry_run:
                # Actually delete
                for conv in old_conversations:
                    await self.delete_conversation(conv.sender_key)

                logger.info(f"Cleaned {len(old_conversations)} old conversations")

            return CleanReport(
                deleted_count=len(old_conversations),
                preview=preview
            )

        except Exception as e:
            logger.error(f"Error cleaning old messages: {e}", exc_info=True)
            raise

    async def reset_agent_memory(self) -> Dict:
        """
        Delete ALL memory for the agent (nuclear option).

        Returns:
            Dict with reset statistics
        """
        try:
            # 1. Count before deletion
            conversations_count = self.db.query(Memory)\
                .filter(Memory.agent_id == self.agent_id)\
                .count()

            facts_count = self.db.query(SemanticKnowledge)\
                .filter(SemanticKnowledge.agent_id == self.agent_id)\
                .count()

            # 2. Delete from Memory table
            self.db.query(Memory)\
                .filter(Memory.agent_id == self.agent_id)\
                .delete()

            # 3. Delete from SemanticKnowledge table
            self.db.query(SemanticKnowledge)\
                .filter(SemanticKnowledge.agent_id == self.agent_id)\
                .delete()

            # 4. Delete entire vector store collection
            try:
                self.vector_store.delete_collection(self.collection_name)
                logger.info(f"Deleted vector store collection {self.collection_name}")
            except Exception as e:
                logger.warning(f"Could not delete vector collection: {e}")

            # Commit all deletions
            self.db.commit()

            logger.info(f"Reset complete for agent {self.agent_id}: "
                       f"{conversations_count} conversations, {facts_count} facts deleted")

            return {
                "success": True,
                "conversations_deleted": conversations_count,
                "facts_deleted": facts_count,
                "message": f"All memory reset for agent {self.agent_id}"
            }

        except Exception as e:
            logger.error(f"Error resetting agent memory: {e}", exc_info=True)
            self.db.rollback()
            raise
