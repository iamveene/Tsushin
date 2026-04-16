"""
Playground Thread Service
Handles CRUD operations for playground conversation threads.
Phase 14.1: Conversation Thread Management
"""

import logging
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from datetime import datetime
import json

from models import ConversationThread, Memory, Agent
from models_rbac import User

logger = logging.getLogger(__name__)


def build_playground_thread_recipient(user_id: int, agent_id: int, thread_id: int) -> str:
    """Canonical playground thread recipient key."""
    return f"playground_u{user_id}_a{agent_id}_t{thread_id}"


def build_api_thread_recipient(thread_id: int, api_client_id: Optional[str] = None, user_id: Optional[int] = None) -> str:
    """Canonical API v1 thread recipient key."""
    if api_client_id:
        return f"api_client_{api_client_id}_thread_{thread_id}"
    if user_id is not None:
        return f"api_user_{user_id}_thread_{thread_id}"
    return f"api_thread_{thread_id}"


def build_playground_channel_id(user_id: int) -> str:
    """Canonical shared channel ID for Playground conversations."""
    return f"playground_{user_id}"


def build_api_channel_id(api_client_id: Optional[str] = None, user_id: Optional[int] = None) -> str:
    """Canonical shared channel ID for API conversations."""
    if api_client_id:
        return f"api_client_{api_client_id}"
    if user_id is not None:
        return f"api_user_{user_id}"
    return "api"


def get_agent_memory_isolation_mode(agent: Optional[Agent]) -> str:
    """Normalize the configured memory isolation mode for an agent."""
    return getattr(agent, "memory_isolation_mode", "isolated") or "isolated"


def sync_playground_thread_recipient(thread: ConversationThread) -> str:
    """Ensure playground thread recipients always use the canonical format."""
    if thread.thread_type == "playground" and thread.user_id is not None:
        recipient = build_playground_thread_recipient(thread.user_id, thread.agent_id, thread.id)
        thread.recipient = recipient
        return recipient
    return thread.recipient


def resolve_playground_identity(
    *,
    user_id: int,
    agent_id: int,
    isolation_mode: str,
    thread_id: Optional[int] = None,
    thread_recipient: Optional[str] = None,
    sender_key_override: Optional[str] = None,
    chat_id_override: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """
    Resolve the canonical sender/chat identifiers for Playground memory access.

    Rules:
    - isolated: thread-specific sender key
    - channel_isolated: channel-shared sender key with thread metadata
    - shared: global shared sender key with thread metadata
    """
    chat_id = chat_id_override or build_playground_channel_id(user_id)
    canonical_thread_recipient = thread_recipient or (
        build_playground_thread_recipient(user_id, agent_id, thread_id)
        if thread_id is not None else None
    )

    if isolation_mode == "shared":
        sender_key = "shared"
    elif sender_key_override:
        sender_key = sender_key_override
    elif isolation_mode == "channel_isolated":
        sender_key = chat_id
    else:
        sender_key = canonical_thread_recipient

    return {
        "sender_key": sender_key,
        "chat_id": chat_id,
        "thread_recipient": canonical_thread_recipient,
    }


class PlaygroundThreadService:
    """
    Service for managing playground conversation threads.

    Each thread represents a separate conversation session between a user and an agent.
    Threads maintain their own memory context via unique sender_key format.
    """

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)

    def _generate_sender_key(self, user_id: int, agent_id: int, thread_id: int) -> str:
        """
        Generate unique sender_key for thread memory isolation.

        Format: playground_u{user_id}_a{agent_id}_t{thread_id}

        Args:
            user_id: User ID
            agent_id: Agent ID
            thread_id: Thread ID

        Returns:
            Unique sender key for this thread
        """
        return build_playground_thread_recipient(user_id, agent_id, thread_id)

    def get_thread_record(
        self,
        thread_id: int,
        *,
        tenant_id: Optional[str] = None,
        user_id: Optional[int] = None,
        agent_id: Optional[int] = None,
    ) -> Optional[ConversationThread]:
        """Load a playground thread with optional ownership filters."""
        query = self.db.query(ConversationThread).filter(
            ConversationThread.id == thread_id,
            ConversationThread.thread_type == "playground",
        )

        if tenant_id is not None:
            query = query.filter(ConversationThread.tenant_id == tenant_id)
        if user_id is not None:
            query = query.filter(ConversationThread.user_id == user_id)
        if agent_id is not None:
            query = query.filter(ConversationThread.agent_id == agent_id)

        thread = query.first()
        if thread:
            sync_playground_thread_recipient(thread)
        return thread

    def count_thread_messages(self, thread: ConversationThread) -> int:
        """Count messages using the same isolation semantics used for thread views."""
        return len(self._get_thread_messages_from_memory(thread))

    def _get_thread_channel_id(self, thread: ConversationThread) -> str:
        """Resolve the channel-scoped memory identifier for a thread."""
        if thread.api_client_id:
            return build_api_channel_id(api_client_id=thread.api_client_id)
        if thread.user_id is not None:
            return build_playground_channel_id(thread.user_id)
        return thread.recipient

    def _filter_messages_for_thread(self, messages: List[Dict[str, Any]], thread_id: int) -> List[Dict[str, Any]]:
        """Keep only messages that belong to a specific thread when metadata is present."""
        filtered = [
            msg for msg in messages
            if not isinstance(msg.get("metadata"), dict)
            or msg["metadata"].get("thread_id") is None
            or msg["metadata"].get("thread_id") == thread_id
        ]
        return filtered or messages

    def _find_memory_record(self, thread: ConversationThread, isolation_mode: str) -> Optional[Memory]:
        """Locate the underlying memory record for a thread."""
        candidate_keys: List[str] = []

        if isolation_mode == "shared":
            candidate_keys = ["shared", f"agent_{thread.agent_id}:shared"]
        elif isolation_mode == "channel_isolated":
            channel_id = self._get_thread_channel_id(thread)
            candidate_keys = [f"channel_{channel_id}"]
        else:
            candidate_keys = [
                f"sender_{thread.recipient}",
                thread.recipient,
            ]

        # BUG-LOG-015: belt-and-suspenders tenant_id filter alongside agent_id.
        # ConversationThread.tenant_id is the source of truth for this query's scope.
        for key in candidate_keys:
            memory = self.db.query(Memory).filter(
                Memory.agent_id == thread.agent_id,
                Memory.tenant_id == thread.tenant_id,
                Memory.sender_key == key,
            ).first()
            if memory:
                return memory

        if isolation_mode == "isolated":
            return (
                self.db.query(Memory)
                .filter(
                    Memory.agent_id == thread.agent_id,
                    Memory.tenant_id == thread.tenant_id,
                    Memory.sender_key.like(f"%{thread.recipient}%"),
                )
                .first()
            )

        return None

    def _get_thread_messages_from_memory(self, thread: ConversationThread) -> List[Dict[str, Any]]:
        """Load thread messages with the correct isolation semantics."""
        agent = self.db.query(Agent).filter(Agent.id == thread.agent_id).first()
        isolation_mode = get_agent_memory_isolation_mode(agent)

        memory = self._find_memory_record(thread, isolation_mode)
        if not memory or not memory.messages_json:
            return []

        raw_messages = memory.messages_json or []
        if isolation_mode in ("shared", "channel_isolated"):
            return self._filter_messages_for_thread(raw_messages, thread.id)
        return raw_messages

    def _generate_thread_title(self, message: str, max_length: int = 50) -> str:
        """Generate a clean thread title from the first user message."""
        text = message.strip()

        # Strip common greetings
        greetings = ['hello', 'hi', 'hey', 'good morning', 'good afternoon',
                     'good evening', 'greetings', 'howdy']
        lower = text.lower()
        for g in greetings:
            if lower.startswith(g):
                text = text[len(g):].lstrip(' ,!.').strip()
                break

        if not text:
            return None  # Keep default title

        # Take first sentence
        for sep in ['. ', '? ', '! ', '\n']:
            idx = text.find(sep)
            if 0 < idx < max_length:
                text = text[:idx]
                break

        # Truncate if too long
        if len(text) > max_length:
            text = text[:max_length].rsplit(' ', 1)[0] + '...'

        return text[0].upper() + text[1:] if text else None

    async def create_thread(
        self,
        tenant_id: str,
        user_id: int,
        agent_id: int,
        title: Optional[str] = None,
        folder: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new conversation thread.

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            agent_id: Agent ID
            title: Optional thread title (auto-generated if not provided)
            folder: Optional folder name

        Returns:
            Dict with thread data
        """
        try:
            # Verify agent exists
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                return {
                    "status": "error",
                    "error": f"Agent {agent_id} not found"
                }

            # Create thread
            thread = ConversationThread(
                tenant_id=tenant_id,
                user_id=user_id,
                agent_id=agent_id,
                thread_type="playground",
                title=title or "New Conversation",
                folder=folder,
                recipient=f"playground_user_{user_id}",  # Temporary, will be updated with thread_id
                status="active",
                is_archived=False
            )

            self.db.add(thread)
            self.db.flush()  # Get thread ID

            # Update recipient with proper sender_key format
            thread.recipient = self._generate_sender_key(user_id, agent_id, thread.id)
            self.db.commit()
            self.db.refresh(thread)

            self.logger.info(f"Created playground thread {thread.id} for user {user_id}, agent {agent_id}")

            return {
                "status": "success",
                "thread": {
                    "id": thread.id,
                    "title": thread.title,
                    "folder": thread.folder,
                    "status": thread.status,
                    "is_archived": thread.is_archived,
                    "agent_id": thread.agent_id,
                    "recipient": thread.recipient,
                    "created_at": thread.created_at.isoformat() if thread.created_at else None,
                    "updated_at": thread.updated_at.isoformat() if thread.updated_at else None,
                    "message_count": 0
                }
            }

        except Exception as e:
            self.logger.error(f"Error creating thread: {e}", exc_info=True)
            self.db.rollback()
            return {
                "status": "error",
                "error": str(e)
            }

    async def list_threads(
        self,
        tenant_id: str,
        user_id: int,
        agent_id: Optional[int] = None,
        include_archived: bool = False,
        folder: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List all threads for a user.

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            agent_id: Optional filter by agent
            include_archived: Include archived threads
            folder: Optional filter by folder

        Returns:
            List of thread dicts
        """
        try:
            query = self.db.query(ConversationThread).filter(
                ConversationThread.tenant_id == tenant_id,
                ConversationThread.user_id == user_id,
                ConversationThread.thread_type == "playground"
            )

            if agent_id:
                query = query.filter(ConversationThread.agent_id == agent_id)

            if not include_archived:
                query = query.filter(ConversationThread.is_archived == False)

            if folder:
                query = query.filter(ConversationThread.folder == folder)

            threads = query.order_by(ConversationThread.updated_at.desc()).all()

            result = []
            for thread in threads:
                thread_messages = self._get_thread_messages_from_memory(thread)
                message_count = len(thread_messages)

                last_message = ""
                if thread_messages:
                    last_msg = thread_messages[-1]
                    last_message = last_msg.get("content", "")[:100]

                result.append({
                    "id": thread.id,
                    "title": thread.title,
                    "folder": thread.folder,
                    "status": thread.status,
                    "is_archived": thread.is_archived,
                    "agent_id": thread.agent_id,
                    "recipient": thread.recipient,  # For Memory Inspector sender_key filtering
                    "message_count": message_count,
                    "last_message_preview": last_message,
                    "created_at": thread.created_at.isoformat() if thread.created_at else None,
                    "updated_at": thread.updated_at.isoformat() if thread.updated_at else None
                })

            return result

        except Exception as e:
            self.logger.error(f"Error listing threads: {e}", exc_info=True)
            return []

    async def get_thread(
        self,
        thread_id: int,
        tenant_id: str,
        user_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get thread details.

        Args:
            thread_id: Thread ID
            tenant_id: Tenant ID
            user_id: User ID (for permission check)

        Returns:
            Thread dict or None if not found
        """
        try:
            thread = self.get_thread_record(
                thread_id,
                tenant_id=tenant_id,
                user_id=user_id,
            )

            if not thread:
                self.logger.warning(f"[get_thread] Thread {thread_id} not found for user {user_id}")
                return None

            self.logger.info(f"[get_thread] Loading thread {thread_id}: recipient={thread.recipient}, agent_id={thread.agent_id}")
            messages = self._get_thread_messages_from_memory(thread)
            if not messages and thread.conversation_history:
                messages = thread.conversation_history
                self.logger.info(f"[get_thread] Using conversation_history fallback: {len(messages)} messages")

            # Format messages to match PlaygroundMessage interface
            formatted_messages = []
            for msg in messages:
                formatted_msg = {
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", ""),
                    "timestamp": msg.get("timestamp", ""),
                    "message_id": msg.get("message_id", f"msg_{thread.id}_{len(formatted_messages)}"),
                    "is_bookmarked": msg.get("is_bookmarked", False),
                    "is_edited": msg.get("is_edited", False),
                    "edited_at": msg.get("edited_at"),
                    "bookmarked_at": msg.get("bookmarked_at"),
                    "original_content": msg.get("original_content")
                }
                # Include optional fields if present
                if "audio_url" in msg:
                    formatted_msg["audio_url"] = msg["audio_url"]
                if "audio_duration" in msg:
                    formatted_msg["audio_duration"] = msg["audio_duration"]
                if "edit_history" in msg:
                    formatted_msg["edit_history"] = msg["edit_history"]
                # Extract kb_used from metadata or top-level
                if "kb_used" in msg:
                    formatted_msg["kb_used"] = msg["kb_used"]
                elif "metadata" in msg and isinstance(msg["metadata"], dict) and "kb_used" in msg["metadata"]:
                    formatted_msg["kb_used"] = msg["metadata"]["kb_used"]
                formatted_messages.append(formatted_msg)

            return {
                "id": thread.id,
                "title": thread.title,
                "folder": thread.folder,
                "status": thread.status,
                "is_archived": thread.is_archived,
                "agent_id": thread.agent_id,
                "recipient": thread.recipient,  # For Memory Inspector sender_key filtering
                "messages": formatted_messages,
                "created_at": thread.created_at.isoformat() if thread.created_at else None,
                "updated_at": thread.updated_at.isoformat() if thread.updated_at else None
            }

        except Exception as e:
            self.logger.error(f"Error getting thread {thread_id}: {e}", exc_info=True)
            return None

    async def update_thread(
        self,
        thread_id: int,
        tenant_id: str,
        user_id: int,
        title: Optional[str] = None,
        folder: Optional[str] = None,
        is_archived: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Update thread metadata.

        Args:
            thread_id: Thread ID
            tenant_id: Tenant ID
            user_id: User ID (for permission check)
            title: New title
            folder: New folder
            is_archived: Archive status

        Returns:
            Dict with status
        """
        try:
            thread = self.get_thread_record(
                thread_id,
                tenant_id=tenant_id,
                user_id=user_id,
            )

            if not thread:
                return {
                    "status": "error",
                    "error": "Thread not found"
                }

            if title is not None:
                thread.title = title

            if folder is not None:
                thread.folder = folder

            if is_archived is not None:
                thread.is_archived = is_archived

            thread.updated_at = datetime.utcnow()
            self.db.commit()

            self.logger.info(f"Updated thread {thread_id}")

            return {
                "status": "success",
                "thread": {
                    "id": thread.id,
                    "title": thread.title,
                    "folder": thread.folder,
                    "status": thread.status,
                    "is_archived": thread.is_archived,
                    "agent_id": thread.agent_id,
                    "created_at": thread.created_at.isoformat() if thread.created_at else None,
                    "updated_at": thread.updated_at.isoformat()
                }
            }

        except Exception as e:
            self.logger.error(f"Error updating thread {thread_id}: {e}", exc_info=True)
            self.db.rollback()
            return {
                "status": "error",
                "error": str(e)
            }

    async def auto_rename_thread_from_message(
        self,
        thread_id: int,
        first_message: str
    ) -> Dict[str, Any]:
        """
        Auto-rename thread based on first user message.
        Only renames if current title is a default one.

        Args:
            thread_id: Thread ID
            first_message: First user message content

        Returns:
            Dict with status and new title if renamed
        """
        try:
            thread = self.get_thread_record(thread_id)

            if not thread:
                return {
                    "status": "error",
                    "error": "Thread not found"
                }

            # Only auto-rename if title is still a default one
            # Default titles: "General Conversation", "New Conversation", "New Conversation (Agent Name)"
            current_title = thread.title or ""
            is_default_title = (
                current_title.startswith("General Conversation") or
                current_title.startswith("New Conversation") or
                current_title == ""
            )

            if not is_default_title:
                # Thread was already manually renamed, don't auto-rename
                return {
                    "status": "skipped",
                    "message": "Thread already has custom title"
                }

            # Generate new title from message
            # Clean message: remove line breaks, trim whitespace
            cleaned_message = " ".join(first_message.split())
            new_title = self._generate_thread_title(cleaned_message)

            # If title generation returns None (e.g., message was just a greeting), skip rename
            if new_title is None:
                return {
                    "status": "skipped",
                    "message": "Message did not produce a meaningful title"
                }

            # Update thread title
            thread.title = new_title
            thread.updated_at = datetime.utcnow()
            self.db.commit()

            self.logger.info(f"Auto-renamed thread {thread_id} to: {new_title}")

            return {
                "status": "success",
                "new_title": new_title,
                "thread_id": thread_id
            }

        except Exception as e:
            self.logger.error(f"Error auto-renaming thread {thread_id}: {e}", exc_info=True)
            self.db.rollback()
            return {
                "status": "error",
                "error": str(e)
            }

    async def delete_thread(
        self,
        thread_id: int,
        tenant_id: str,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Delete a thread and its associated memory.

        Args:
            thread_id: Thread ID
            tenant_id: Tenant ID
            user_id: User ID (for permission check)

        Returns:
            Dict with status
        """
        try:
            thread = self.get_thread_record(
                thread_id,
                tenant_id=tenant_id,
                user_id=user_id,
            )

            if not thread:
                return {
                    "status": "error",
                    "error": "Thread not found"
                }

            agent = self.db.query(Agent).filter(Agent.id == thread.agent_id).first()
            isolation_mode = get_agent_memory_isolation_mode(agent)
            memory = self._find_memory_record(thread, isolation_mode)

            if memory:
                if isolation_mode in ("shared", "channel_isolated") and memory.messages_json:
                    retained_messages = [
                        msg for msg in (memory.messages_json or [])
                        if not isinstance(msg.get("metadata"), dict)
                        or msg["metadata"].get("thread_id") != thread_id
                    ]
                    if retained_messages:
                        memory.messages_json = retained_messages
                    else:
                        self.db.delete(memory)
                else:
                    self.db.delete(memory)

            # Delete thread
            self.db.delete(thread)
            self.db.commit()

            self.logger.info(f"Deleted thread {thread_id} and associated memory")

            return {
                "status": "success",
                "message": "Thread deleted successfully"
            }

        except Exception as e:
            self.logger.error(f"Error deleting thread {thread_id}: {e}", exc_info=True)
            self.db.rollback()
            return {
                "status": "error",
                "error": str(e)
            }

    async def export_thread(
        self,
        thread_id: int,
        tenant_id: str,
        user_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Export thread as JSON.

        Args:
            thread_id: Thread ID
            tenant_id: Tenant ID
            user_id: User ID (for permission check)

        Returns:
            Thread export dict or None
        """
        try:
            thread_data = await self.get_thread(thread_id, tenant_id, user_id)

            if not thread_data:
                return None

            # Get agent name
            agent = self.db.query(Agent).filter(Agent.id == thread_data["agent_id"]).first()
            agent_name = f"Agent {thread_data['agent_id']}"
            if agent:
                from models import Contact
                contact = self.db.query(Contact).filter(Contact.id == agent.contact_id).first()
                agent_name = contact.friendly_name if contact else agent_name

            export = {
                "thread_id": thread_data["id"],
                "title": thread_data["title"],
                "agent_name": agent_name,
                "agent_id": thread_data["agent_id"],
                "created_at": thread_data["created_at"],
                "updated_at": thread_data["updated_at"],
                "message_count": len(thread_data["messages"]),
                "messages": thread_data["messages"],
                "exported_at": datetime.utcnow().isoformat() + "Z"
            }

            return export

        except Exception as e:
            self.logger.error(f"Error exporting thread {thread_id}: {e}", exc_info=True)
            return None

    async def get_or_create_default_thread(
        self,
        tenant_id: str,
        user_id: int,
        agent_id: int
    ) -> Dict[str, Any]:
        """
        Get the default (active) thread for a user-agent pair, or create one if none exists.

        This ensures backward compatibility with existing playground conversations.

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            agent_id: Agent ID

        Returns:
            Thread dict
        """
        try:
            # Look for existing active thread
            thread = self.db.query(ConversationThread).filter(
                ConversationThread.tenant_id == tenant_id,
                ConversationThread.user_id == user_id,
                ConversationThread.agent_id == agent_id,
                ConversationThread.thread_type == "playground",
                ConversationThread.is_archived == False
            ).order_by(ConversationThread.updated_at.desc()).first()

            if thread:
                return {
                    "status": "success",
                    "thread": {
                        "id": thread.id,
                        "title": thread.title,
                        "folder": thread.folder,
                        "status": thread.status,
                        "is_archived": thread.is_archived,
                        "agent_id": thread.agent_id,
                        "recipient": thread.recipient,
                        "created_at": thread.created_at.isoformat() if thread.created_at else None,
                        "updated_at": thread.updated_at.isoformat() if thread.updated_at else None
                    }
                }

            # No thread found, create default thread
            result = await self.create_thread(
                tenant_id=tenant_id,
                user_id=user_id,
                agent_id=agent_id,
                title="General Conversation"
            )

            if result.get("status") == "success":
                thread_data = result["thread"]
                thread_data["recipient"] = self._generate_sender_key(user_id, agent_id, thread_data["id"])

            return result

        except Exception as e:
            self.logger.error(f"Error getting/creating default thread: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e)
            }
