"""
Playground Message Service
Handles message-level operations: edit, delete, regenerate, bookmark, branch, copy.
Phase 14.2: Message-Level Operations
"""

import logging
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from datetime import datetime
import uuid

from models import Memory, Agent, ConversationThread
from agent.agent_service import AgentService
from agent.memory.multi_agent_memory import MultiAgentMemoryManager

logger = logging.getLogger(__name__)


class PlaygroundMessageService:
    """
    Service for message-level operations in playground conversations.

    Supports:
    - Edit user messages (with regeneration)
    - Regenerate assistant responses
    - Delete messages (soft delete)
    - Bookmark messages
    - Branch conversations
    - Copy message content
    """

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)

    def _get_thread_memory(
        self,
        agent_id: int,
        thread: ConversationThread
    ) -> Optional[Memory]:
        """
        Get memory for a thread, trying both with and without sender_ prefix.

        Args:
            agent_id: Agent ID
            thread: ConversationThread object

        Returns:
            Memory object or None
        """
        # Try with "sender_" prefix first (new format)
        memory = self.db.query(Memory).filter(
            Memory.agent_id == agent_id,
            Memory.sender_key == f"sender_{thread.recipient}"
        ).first()

        if not memory:
            # Try without prefix (legacy format)
            memory = self.db.query(Memory).filter(
                Memory.agent_id == agent_id,
                Memory.sender_key == thread.recipient
            ).first()

        return memory

    def _find_message_by_id(
        self,
        messages: List[Dict],
        message_id: str
    ) -> Optional[tuple[int, Dict]]:
        """
        Find message by ID in messages list.
        Handles both explicit message_id and fallback IDs.

        Args:
            messages: List of messages
            message_id: Message ID to find

        Returns:
            Tuple of (index, message) or None
        """
        # First try exact match
        for idx, msg in enumerate(messages):
            if msg.get("message_id") == message_id:
                return (idx, msg)

        # Fallback 1: Try to match by index pattern: msg_{thread_id}_{index}
        # This is what get_thread() generates for messages without IDs
        if message_id.startswith("msg_"):
            parts = message_id.split("_")
            if len(parts) == 3 and parts[2].isdigit():
                # Format: msg_{thread_id}_{index}
                idx = int(parts[2])
                if 0 <= idx < len(messages):
                    # Assign the message_id to this message
                    messages[idx]["message_id"] = message_id
                    return (idx, messages[idx])

        # Fallback 2: Try to match by timestamp+role pattern
        # Frontend might generate: msg_{timestamp}_{role}
        if message_id.startswith("msg_"):
            parts = message_id.split("_")
            if len(parts) >= 3:
                for idx, msg in enumerate(messages):
                    msg_timestamp = msg.get("timestamp", "")
                    msg_role = msg.get("role", "")
                    if msg_role in message_id and msg_timestamp:
                        fallback_id = f"msg_{msg_timestamp}_{msg_role}"
                        if fallback_id == message_id:
                            msg["message_id"] = message_id
                            return (idx, msg)

        return None

    async def edit_message(
        self,
        tenant_id: str,
        user_id: int,
        agent_id: int,
        thread_id: int,
        message_id: str,
        new_content: str,
        regenerate: bool = True
    ) -> Dict[str, Any]:
        """
        Edit a user message.

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            agent_id: Agent ID
            thread_id: Thread ID
            message_id: Message ID to edit
            new_content: New message content
            regenerate: If True, regenerate agent response

        Returns:
            Dict with status and updated messages
        """
        try:
            # Get thread
            thread = self.db.query(ConversationThread).filter(
                ConversationThread.id == thread_id,
                ConversationThread.tenant_id == tenant_id,
                ConversationThread.user_id == user_id,
                ConversationThread.thread_type == "playground"
            ).first()

            if not thread:
                self.logger.error(f"Thread not found: thread_id={thread_id}, tenant_id={tenant_id}, user_id={user_id}")
                return {"status": "error", "error": "Thread not found"}

            # Get memory
            memory = self._get_thread_memory(agent_id, thread)

            if not memory or not memory.messages_json:
                self.logger.error(f"No messages found: agent_id={agent_id}, thread_recipient={thread.recipient}")
                return {"status": "error", "error": "No messages found"}

            messages = memory.messages_json
            self.logger.info(f"Found {len(messages)} messages for thread {thread_id}")
            self.logger.info(f"Looking for message_id: {message_id}")
            self.logger.info(f"Available message IDs: {[m.get('message_id', 'NO_ID') for m in messages]}")

            # Find message to edit
            result = self._find_message_by_id(messages, message_id)
            if not result:
                self.logger.error(f"Message not found: message_id={message_id}")
                return {"status": "error", "error": f"Message not found: {message_id}"}

            msg_idx, msg = result

            # Verify it's a user message
            if msg.get("role") != "user":
                return {"status": "error", "error": "Can only edit user messages"}

            # Store original content if not already edited
            if "original_content" not in msg:
                msg["original_content"] = msg["content"]

            # Update message
            msg["content"] = new_content
            msg["edited_at"] = datetime.utcnow().isoformat() + "Z"
            msg["is_edited"] = True
            messages[msg_idx] = msg

            # If regenerate, remove subsequent messages and generate new response
            if regenerate:
                # Keep messages up to and including the edited message
                messages = messages[:msg_idx + 1]

                # Save truncated messages
                memory.messages_json = messages
                self.db.commit()

                # Regenerate response
                from services.playground_service import PlaygroundService
                playground_service = PlaygroundService(self.db)

                # Get agent config
                agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
                if not agent:
                    return {"status": "error", "error": "Agent not found"}

                # Send message to agent (skip adding user message since it's already edited)
                # Pass thread_id to ensure response goes to correct thread memory
                result = await playground_service.send_message(
                    user_id=user_id,
                    agent_id=agent_id,
                    message_text=new_content,
                    thread_id=thread_id,
                    skip_user_message=True  # Don't add duplicate user message
                )

                if result.get("status") == "success":
                    # Re-query the memory to get fresh data after send_message persisted
                    refreshed_memory = self.db.query(Memory).filter(
                        Memory.id == memory.id
                    ).first()

                    return {
                        "status": "success",
                        "message": "Message edited and response regenerated",
                        "new_response": result.get("message"),
                        "messages": refreshed_memory.messages_json if refreshed_memory else memory.messages_json
                    }
                else:
                    return result
            else:
                # Just update the message without regeneration
                memory.messages_json = messages
                self.db.commit()

                return {
                    "status": "success",
                    "message": "Message edited",
                    "messages": messages
                }

        except Exception as e:
            self.logger.error(f"Error editing message: {e}", exc_info=True)
            self.db.rollback()
            return {"status": "error", "error": str(e)}

    async def regenerate_response(
        self,
        tenant_id: str,
        user_id: int,
        agent_id: int,
        thread_id: int,
        message_id: str
    ) -> Dict[str, Any]:
        """
        Regenerate an assistant response.

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            agent_id: Agent ID
            thread_id: Thread ID
            message_id: Assistant message ID to regenerate

        Returns:
            Dict with status and new response
        """
        try:
            # Get thread
            thread = self.db.query(ConversationThread).filter(
                ConversationThread.id == thread_id,
                ConversationThread.tenant_id == tenant_id,
                ConversationThread.user_id == user_id,
                ConversationThread.thread_type == "playground"
            ).first()

            if not thread:
                return {"status": "error", "error": "Thread not found"}

            # Get memory
            memory = self._get_thread_memory(agent_id, thread)

            if not memory or not memory.messages_json:
                return {"status": "error", "error": "No messages found"}

            messages = memory.messages_json

            # Find assistant message
            result = self._find_message_by_id(messages, message_id)
            if not result:
                return {"status": "error", "error": "Message not found"}

            msg_idx, msg = result

            # Verify it's an assistant message
            if msg.get("role") != "assistant":
                return {"status": "error", "error": "Can only regenerate assistant messages"}

            # Find the preceding user message
            if msg_idx == 0:
                return {"status": "error", "error": "No user message to regenerate from"}

            user_msg = messages[msg_idx - 1]
            if user_msg.get("role") != "user":
                return {"status": "error", "error": "Invalid message sequence"}

            # Truncate messages to before the assistant response
            messages = messages[:msg_idx]
            memory.messages_json = messages
            self.db.commit()

            # Regenerate response
            from services.playground_service import PlaygroundService
            playground_service = PlaygroundService(self.db)

            # Pass thread_id and skip_user_message to prevent duplicate user messages
            result = await playground_service.send_message(
                user_id=user_id,
                agent_id=agent_id,
                message_text=user_msg["content"],
                thread_id=thread_id,
                skip_user_message=True  # User message already in memory
            )

            if result.get("status") == "success":
                # Refresh memory
                self.db.refresh(memory)

                return {
                    "status": "success",
                    "message": "Response regenerated",
                    "new_response": result.get("message"),
                    "messages": memory.messages_json
                }
            else:
                return result

        except Exception as e:
            self.logger.error(f"Error regenerating response: {e}", exc_info=True)
            self.db.rollback()
            return {"status": "error", "error": str(e)}

    async def delete_message(
        self,
        tenant_id: str,
        user_id: int,
        agent_id: int,
        thread_id: int,
        message_id: str,
        delete_subsequent: bool = True
    ) -> Dict[str, Any]:
        """
        Delete a message (soft delete).

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            agent_id: Agent ID
            thread_id: Thread ID
            message_id: Message ID to delete
            delete_subsequent: If True, also delete all subsequent messages

        Returns:
            Dict with status
        """
        try:
            # Get thread
            thread = self.db.query(ConversationThread).filter(
                ConversationThread.id == thread_id,
                ConversationThread.tenant_id == tenant_id,
                ConversationThread.user_id == user_id,
                ConversationThread.thread_type == "playground"
            ).first()

            if not thread:
                return {"status": "error", "error": "Thread not found"}

            # Get memory
            memory = self._get_thread_memory(agent_id, thread)

            if not memory or not memory.messages_json:
                return {"status": "error", "error": "No messages found"}

            messages = memory.messages_json

            # Find message
            result = self._find_message_by_id(messages, message_id)
            if not result:
                return {"status": "error", "error": "Message not found"}

            msg_idx, msg = result

            if delete_subsequent:
                # Delete this message and all subsequent messages
                messages = messages[:msg_idx]
            else:
                # Soft delete just this message
                msg["is_deleted"] = True
                msg["deleted_at"] = datetime.utcnow().isoformat() + "Z"
                messages[msg_idx] = msg

            memory.messages_json = messages
            self.db.commit()

            return {
                "status": "success",
                "message": "Message deleted",
                "messages": messages
            }

        except Exception as e:
            self.logger.error(f"Error deleting message: {e}", exc_info=True)
            self.db.rollback()
            return {"status": "error", "error": str(e)}

    async def bookmark_message(
        self,
        tenant_id: str,
        user_id: int,
        agent_id: int,
        thread_id: int,
        message_id: str,
        bookmarked: bool
    ) -> Dict[str, Any]:
        """
        Toggle bookmark on a message.

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            agent_id: Agent ID
            thread_id: Thread ID
            message_id: Message ID
            bookmarked: Bookmark state

        Returns:
            Dict with status
        """
        try:
            # Get thread
            thread = self.db.query(ConversationThread).filter(
                ConversationThread.id == thread_id,
                ConversationThread.tenant_id == tenant_id,
                ConversationThread.user_id == user_id,
                ConversationThread.thread_type == "playground"
            ).first()

            if not thread:
                return {"status": "error", "error": "Thread not found"}

            # Get memory
            memory = self._get_thread_memory(agent_id, thread)

            if not memory or not memory.messages_json:
                return {"status": "error", "error": "No messages found"}

            messages = memory.messages_json

            # Find message
            result = self._find_message_by_id(messages, message_id)
            if not result:
                return {"status": "error", "error": "Message not found"}

            msg_idx, msg = result

            # Update bookmark
            msg["is_bookmarked"] = bookmarked
            if bookmarked:
                msg["bookmarked_at"] = datetime.utcnow().isoformat() + "Z"
            messages[msg_idx] = msg

            memory.messages_json = messages
            self.db.commit()

            return {
                "status": "success",
                "message": "Bookmark updated",
                "is_bookmarked": bookmarked
            }

        except Exception as e:
            self.logger.error(f"Error bookmarking message: {e}", exc_info=True)
            self.db.rollback()
            return {"status": "error", "error": str(e)}

    async def copy_message(
        self,
        tenant_id: str,
        user_id: int,
        agent_id: int,
        thread_id: int,
        message_id: str
    ) -> Dict[str, Any]:
        """
        Get message content for copying.

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            agent_id: Agent ID
            thread_id: Thread ID
            message_id: Message ID

        Returns:
            Dict with message content
        """
        try:
            # Get thread
            thread = self.db.query(ConversationThread).filter(
                ConversationThread.id == thread_id,
                ConversationThread.tenant_id == tenant_id,
                ConversationThread.user_id == user_id,
                ConversationThread.thread_type == "playground"
            ).first()

            if not thread:
                return {"status": "error", "error": "Thread not found"}

            # Get memory
            memory = self._get_thread_memory(agent_id, thread)

            if not memory or not memory.messages_json:
                return {"status": "error", "error": "No messages found"}

            # Find message
            result = self._find_message_by_id(memory.messages_json, message_id)
            if not result:
                return {"status": "error", "error": "Message not found"}

            _, msg = result

            return {
                "status": "success",
                "content": msg.get("content", "")
            }

        except Exception as e:
            self.logger.error(f"Error copying message: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    async def branch_conversation(
        self,
        tenant_id: str,
        user_id: int,
        agent_id: int,
        thread_id: int,
        message_id: str,
        new_thread_title: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new conversation branch from a specific message.

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            agent_id: Agent ID
            thread_id: Thread ID
            message_id: Message ID to branch from
            new_thread_title: Optional title for new thread

        Returns:
            Dict with new thread data
        """
        try:
            # Get original thread
            thread = self.db.query(ConversationThread).filter(
                ConversationThread.id == thread_id,
                ConversationThread.tenant_id == tenant_id,
                ConversationThread.user_id == user_id,
                ConversationThread.thread_type == "playground"
            ).first()

            if not thread:
                return {"status": "error", "error": "Thread not found"}

            # Get memory
            memory = self._get_thread_memory(agent_id, thread)

            if not memory or not memory.messages_json:
                return {"status": "error", "error": "No messages found"}

            # Find branch point
            result = self._find_message_by_id(memory.messages_json, message_id)
            if not result:
                return {"status": "error", "error": "Message not found"}

            msg_idx, msg = result

            # Get messages up to and including branch point
            branched_messages = memory.messages_json[:msg_idx + 1]

            # Create new thread
            from services.playground_thread_service import PlaygroundThreadService
            thread_service = PlaygroundThreadService(self.db)

            title = new_thread_title or f"Branch from {thread.title}"

            create_result = await thread_service.create_thread(
                tenant_id=tenant_id,
                user_id=user_id,
                agent_id=agent_id,
                title=title,
                folder=thread.folder
            )

            if create_result.get("status") != "success":
                return create_result

            new_thread = create_result["thread"]

            # Copy messages to new thread's memory
            new_recipient = f"playground_u{user_id}_a{agent_id}_t{new_thread['id']}"

            new_memory = Memory(
                agent_id=agent_id,
                sender_key=new_recipient,
                messages_json=branched_messages
            )
            self.db.add(new_memory)
            self.db.commit()

            return {
                "status": "success",
                "message": "Conversation branched",
                "new_thread": new_thread
            }

        except Exception as e:
            self.logger.error(f"Error branching conversation: {e}", exc_info=True)
            self.db.rollback()
            return {"status": "error", "error": str(e)}
