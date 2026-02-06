"""
Playground WebSocket Service for Real-Time Streaming (Phase 14.9)

Handles WebSocket-based streaming chat for the Playground interface.
"""
import logging
from typing import Optional, AsyncGenerator, Dict, Any
from sqlalchemy.orm import Session
from fastapi import WebSocket, HTTPException
from datetime import datetime

from models import Agent, ConversationThread
from models_rbac import User
from services.playground_service import PlaygroundService

logger = logging.getLogger(__name__)


class PlaygroundWebSocketService:
    """Handles WebSocket streaming for Playground chat"""

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        self.playground_service = PlaygroundService(db)
        self.logger = logging.getLogger(__name__)

    async def process_streaming_message(
        self,
        agent_id: int,
        message: str,
        websocket: WebSocket,
        thread_id: Optional[int] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process a message with streaming response.

        Args:
            agent_id: Target agent ID
            message: User message text
            websocket: WebSocket connection
            thread_id: Optional thread ID for context

        Yields:
            Streaming chunks: {"type": "token", "content": str}
            Final metadata: {"type": "done", "message_id": int, ...}
        """
        try:
            # Get user
            user = self.db.query(User).filter(User.id == self.user_id).first()
            if not user:
                yield {"type": "error", "error": "User not found"}
                return

            # Get agent
            agent = self.db.query(Agent).filter(
                Agent.id == agent_id,
                Agent.tenant_id == user.tenant_id
            ).first()

            if not agent:
                yield {"type": "error", "error": f"Agent {agent_id} not found"}
                return

            # Get or create thread
            if thread_id:
                thread = self.db.query(ConversationThread).filter(
                    ConversationThread.id == thread_id,
                    ConversationThread.user_id == self.user_id,
                    ConversationThread.agent_id == agent_id
                ).first()

                if not thread:
                    yield {"type": "error", "error": f"Thread {thread_id} not found"}
                    return
            else:
                # Create new thread with default title (will be auto-renamed after first exchange)
                from services.playground_thread_service import PlaygroundThreadService
                thread_service = PlaygroundThreadService(self.db)

                # Get agent name for default title
                from models import Contact
                contact = self.db.query(Contact).filter(Contact.id == agent.contact_id).first() if agent else None
                agent_name = contact.friendly_name if contact else f"Bot"
                default_title = f"New Conversation ({agent_name})"

                thread = await thread_service.create_thread(
                    tenant_id=user.tenant_id,
                    user_id=self.user_id,
                    agent_id=agent_id,
                    title=default_title
                )

                if thread.get("status") != "success":
                    yield {"type": "error", "error": thread.get("error", "Failed to create thread")}
                    return

                thread_id = thread["thread"].get("id")
                thread = self.db.query(ConversationThread).filter(ConversationThread.id == thread_id).first()

                # Notify about new thread
                yield {
                    "type": "thread_created",
                    "thread_id": thread_id,
                    "title": thread.title
                }

            # Update thread activity
            thread.updated_at = datetime.utcnow()
            self.db.commit()

            # Send "thinking" indicator
            yield {"type": "thinking", "agent_id": agent_id}

            # Use the streaming method from PlaygroundService
            accumulated_response = ""
            token_usage = None
            message_id = None

            async for chunk in self.playground_service.process_message_streaming(
                user_id=self.user_id,
                agent_id=agent_id,
                message_text=message,
                thread_id=thread_id
            ):
                chunk_type = chunk.get("type")
                self.logger.warning(f"[WS Debug] Received chunk type: {chunk_type}, thread_id={thread_id}")

                if chunk_type == "token":
                    # Stream token to client
                    accumulated_response += chunk.get("content", "")
                    yield chunk

                elif chunk_type == "done":
                    # Final metadata
                    token_usage = chunk.get("token_usage")
                    message_id = chunk.get("message_id")

                    # Auto-rename thread based on first message
                    thread_renamed = False
                    new_thread_title = None

                    if thread_id:
                        from services.playground_thread_service import PlaygroundThreadService
                        from models import Memory

                        # Check if this is a fresh thread (only 2 messages: user + assistant)
                        current_thread = self.db.query(ConversationThread).filter(
                            ConversationThread.id == thread_id
                        ).first()

                        if current_thread:
                            # Count messages from Memory table (where they're actually stored)
                            memory_sender_key = f"sender_{current_thread.recipient}"
                            memory = self.db.query(Memory).filter(
                                Memory.agent_id == agent_id,
                                Memory.sender_key == memory_sender_key
                            ).first()

                            message_count = len(memory.messages_json) if memory and memory.messages_json else 0
                            self.logger.warning(f"[Auto-rename WS] Thread {thread_id}: memory_key={memory_sender_key}, message_count={message_count}")

                            # Only auto-rename after first exchange (2 messages: user + assistant)
                            if message_count <= 2:
                                thread_service = PlaygroundThreadService(self.db)
                                rename_result = await thread_service.auto_rename_thread_from_message(
                                    thread_id=thread_id,
                                    first_message=message
                                )

                                if rename_result.get("status") == "success":
                                    thread_renamed = True
                                    new_thread_title = rename_result.get("new_title")
                                    self.logger.warning(f"[Auto-rename WS] Thread {thread_id} renamed to: {new_thread_title}")
                            else:
                                self.logger.warning(f"[Auto-rename WS] Thread {thread_id} skipped: already has {message_count} messages")

                    # Send completion with rename info
                    # FIX 2026-01-30: Include agent_id for frontend to use in loadThreads callback
                    yield {
                        "type": "done",
                        "message_id": message_id,
                        "thread_id": thread_id,
                        "agent_id": agent_id,
                        "token_usage": token_usage,
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "thread_renamed": thread_renamed,
                        "new_thread_title": new_thread_title
                    }

                elif chunk_type == "error":
                    # Error occurred during streaming
                    yield chunk
                    return

            self.logger.info(
                f"Streamed message for user {self.user_id}, agent {agent_id}, "
                f"thread {thread_id}: {len(accumulated_response)} chars"
            )

        except Exception as e:
            self.logger.error(f"Error in streaming message: {e}", exc_info=True)
            yield {
                "type": "error",
                "error": str(e)
            }
