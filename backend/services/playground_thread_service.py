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
        return f"playground_u{user_id}_a{agent_id}_t{thread_id}"

    def _generate_thread_title(self, first_message: Optional[str] = None) -> str:
        """
        Generate thread title from first message or timestamp.

        Args:
            first_message: First user message (optional)

        Returns:
            Thread title
        """
        if first_message:
            # Use first 50 chars of message
            title = first_message[:50]
            if len(first_message) > 50:
                title += "..."
            return title
        else:
            # Use timestamp
            return f"Conversation at {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"

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
                # Get message count from memory
                # Note: Memory sender_key has "sender_" prefix, but thread.recipient does not
                sender_key = f"sender_{thread.recipient}" if not thread.recipient.startswith("sender_") else thread.recipient

                self.logger.info(f"[DEBUG] Thread {thread.id}: recipient={thread.recipient}, sender_key={sender_key}")

                memory = self.db.query(Memory).filter(
                    Memory.agent_id == thread.agent_id,
                    Memory.sender_key == sender_key
                ).first()

                message_count = len(memory.messages_json) if memory and memory.messages_json else 0
                self.logger.info(f"[DEBUG] Thread {thread.id}: memory={memory is not None}, message_count={message_count}")

                # Get last message preview
                last_message = ""
                if memory and memory.messages_json and len(memory.messages_json) > 0:
                    last_msg = memory.messages_json[-1]
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
            thread = self.db.query(ConversationThread).filter(
                ConversationThread.id == thread_id,
                ConversationThread.tenant_id == tenant_id,
                ConversationThread.user_id == user_id,
                ConversationThread.thread_type == "playground"
            ).first()

            if not thread:
                self.logger.warning(f"[get_thread] Thread {thread_id} not found for user {user_id}")
                return None

            self.logger.info(f"[get_thread] Loading thread {thread_id}: recipient={thread.recipient}, agent_id={thread.agent_id}")

            # IMPORTANT: Playground stores messages in the Memory table
            # The recipient field contains the sender_key (e.g., "playground_u4_a3_t17")
            # BUT Memory table stores it with "sender_" prefix (e.g., "sender_playground_u4_a3_t17")
            # This is because MultiAgentMemoryManager prepends "sender_" to all sender_keys

            # Get agent to check memory_isolation_mode
            agent = self.db.query(Agent).filter(Agent.id == thread.agent_id).first()

            messages = []

            # If agent has "shared" memory mode, all messages are in one shared memory pool
            if agent and agent.memory_isolation_mode == "shared":
                memory = self.db.query(Memory).filter(
                    Memory.agent_id == thread.agent_id,
                    Memory.sender_key == "shared"
                ).first()

                if memory and memory.messages_json:
                    # Shared memory contains ALL messages - need to filter by thread
                    # For now, return all messages (this is a known limitation of shared mode)
                    messages = memory.messages_json
                    self.logger.info(f"[get_thread] Loaded {len(messages)} messages from shared memory")
            else:
                # FIX 2026-01-31: Enhanced sender_key lookup with comprehensive fallbacks
                # Build comprehensive list of possible sender_keys
                memory_sender_keys = [
                    f"sender_{thread.recipient}",  # Primary format: sender_playground_u{id}_a{id}_t{id}
                    thread.recipient,  # Fallback: without sender_ prefix
                ]

                # Add legacy/alternative formats
                if "_" in thread.recipient:
                    # Try without last segment: playground_u4_a3_t17 → playground_u4_a3
                    parts = thread.recipient.split("_")
                    if len(parts) > 2:
                        truncated_key = "_".join(parts[:-1])
                        memory_sender_keys.append(f"sender_{truncated_key}")
                        memory_sender_keys.append(truncated_key)

                # Check if user has a contact mapping (cross-channel memory)
                # If so, messages might be stored under phone number or contact-based key
                from models import UserContactMapping, Contact
                user_contact_mapping = self.db.query(UserContactMapping).filter(
                    UserContactMapping.user_id == user_id
                ).first()

                if user_contact_mapping:
                    contact = self.db.query(Contact).filter(
                        Contact.id == user_contact_mapping.contact_id
                    ).first()

                    if contact:
                        # Add contact-based sender_keys (lower priority for playground threads)
                        if contact.phone_number:
                            memory_sender_keys.append(f"sender_{contact.phone_number}")
                            memory_sender_keys.append(contact.phone_number)
                        if contact.whatsapp_id:
                            memory_sender_keys.append(f"sender_{contact.whatsapp_id}")
                            memory_sender_keys.append(contact.whatsapp_id)
                        # Also try contact_id format
                        memory_sender_keys.append(f"sender_contact_{contact.id}")
                        memory_sender_keys.append(f"contact_{contact.id}")
                        self.logger.info(f"[get_thread] User has contact mapping, added keys for contact {contact.id}")

                self.logger.info(f"[get_thread] Trying {len(memory_sender_keys)} sender_keys: {memory_sender_keys}")

                memory = None
                for idx, key in enumerate(memory_sender_keys):
                    self.logger.debug(f"[get_thread] Attempt {idx+1}/{len(memory_sender_keys)}: {key}")
                    memory = self.db.query(Memory).filter(
                        Memory.agent_id == thread.agent_id,
                        Memory.sender_key == key
                    ).first()
                    if memory and memory.messages_json:
                        self.logger.info(f"✓ Found {len(memory.messages_json)} messages with key: {key}")
                        break
                    else:
                        self.logger.debug(f"✗ No messages with key: {key}")

                # Ultimate fallback: scan all Memory records for this agent
                if not memory or not memory.messages_json:
                    self.logger.warning(f"[get_thread] All sender_keys failed, scanning all Memory for agent {thread.agent_id}")

                    all_memories = self.db.query(Memory).filter(
                        Memory.agent_id == thread.agent_id
                    ).all()

                    for mem in all_memories:
                        if mem.messages_json:
                            # Check if any message has metadata.thread_id matching our thread
                            for msg in mem.messages_json:
                                metadata = msg.get("metadata", {})
                                if isinstance(metadata, dict) and metadata.get("thread_id") == thread_id:
                                    memory = mem
                                    self.logger.info(f"✓ Found messages via full scan in sender_key: {mem.sender_key}")
                                    break
                            if memory:
                                break

                if memory and memory.messages_json:
                    messages = memory.messages_json
                elif thread.conversation_history:
                    # Fallback to thread's conversation_history if Memory is empty
                    # This handles older threads or threads created differently
                    messages = thread.conversation_history
                    self.logger.info(f"[get_thread] Using conversation_history fallback: {len(messages)} messages")
                else:
                    # No messages found after all fallbacks - return error indicator
                    self.logger.error(f"NO MESSAGES FOUND for thread {thread_id} after all fallbacks")
                    self.logger.error(f"Tried {len(memory_sender_keys)} sender_keys, full Memory scan, and conversation_history")

                    return {
                        "id": thread.id,
                        "title": thread.title,
                        "folder": thread.folder,
                        "status": thread.status,
                        "is_archived": thread.is_archived,
                        "agent_id": thread.agent_id,
                        "messages": [],
                        "error_code": "NO_MESSAGES_FOUND",
                        "error_message": f"Could not locate messages for thread {thread_id}. Tried {len(memory_sender_keys)} sender_keys and full Memory scan.",
                        "created_at": thread.created_at.isoformat() if thread.created_at else None,
                        "updated_at": thread.updated_at.isoformat() if thread.updated_at else None
                    }

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
            thread = self.db.query(ConversationThread).filter(
                ConversationThread.id == thread_id,
                ConversationThread.tenant_id == tenant_id,
                ConversationThread.user_id == user_id,
                ConversationThread.thread_type == "playground"
            ).first()

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
            thread = self.db.query(ConversationThread).filter(
                ConversationThread.id == thread_id,
                ConversationThread.thread_type == "playground"
            ).first()

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
            thread = self.db.query(ConversationThread).filter(
                ConversationThread.id == thread_id,
                ConversationThread.tenant_id == tenant_id,
                ConversationThread.user_id == user_id,
                ConversationThread.thread_type == "playground"
            ).first()

            if not thread:
                return {
                    "status": "error",
                    "error": "Thread not found"
                }

            # Delete associated memory - try both with and without sender_ prefix
            # Memory is stored with sender_ prefix (e.g., "sender_playground_u4_a3_t17")
            # but thread.recipient doesn't have the prefix
            possible_sender_keys = [
                f"sender_{thread.recipient}",  # Primary format
                thread.recipient,  # Fallback
            ]
            for sender_key in possible_sender_keys:
                memory = self.db.query(Memory).filter(
                    Memory.agent_id == thread.agent_id,
                    Memory.sender_key == sender_key
                ).first()
                if memory:
                    self.db.delete(memory)
                    self.logger.info(f"Deleted memory with sender_key: {sender_key}")
                    break

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
