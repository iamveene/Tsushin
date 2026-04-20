"""
Playground WebSocket Service for Real-Time Streaming (Phase 14.9)

Handles WebSocket-based streaming chat for the Playground interface.
"""
import logging
from contextlib import contextmanager
from typing import Optional, AsyncGenerator, Dict, Any, Callable
from sqlalchemy.orm import Session
from fastapi import WebSocket
from datetime import datetime

from models import Agent, ConversationThread, Contact
from models_rbac import User
from services.playground_service import PlaygroundService

logger = logging.getLogger(__name__)


class PlaygroundWebSocketService:
    """Handles WebSocket streaming for Playground chat"""

    def __init__(self, db_or_session_factory: Session | Callable[[], Session], user_id: int):
        self.user_id = user_id
        self.logger = logging.getLogger(__name__)
        self._db: Optional[Session] = None
        self._session_factory: Optional[Callable[[], Session]] = None

        if callable(db_or_session_factory):
            self._session_factory = db_or_session_factory
        else:
            self._db = db_or_session_factory

    @contextmanager
    def _session_scope(self):
        """Yield a DB session, creating a short-lived one when needed."""
        if self._db is not None:
            yield self._db
            return

        if self._session_factory is None:
            raise RuntimeError("PlaygroundWebSocketService is missing a DB session factory")

        db = self._session_factory()
        try:
            yield db
        finally:
            try:
                db.rollback()
            except Exception:
                pass
            db.close()

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
            with self._session_scope() as db:
                playground_service = PlaygroundService(db)

                # Get user
                user = db.query(User).filter(User.id == self.user_id).first()
                if not user:
                    yield {"type": "error", "error": "User not found"}
                    return

                # Get agent
                agent = db.query(Agent).filter(
                    Agent.id == agent_id,
                    Agent.tenant_id == user.tenant_id
                ).first()

                if not agent:
                    yield {"type": "error", "error": f"Agent {agent_id} not found"}
                    return

                # Get or create thread
                if thread_id:
                    thread = db.query(ConversationThread).filter(
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
                    thread_service = PlaygroundThreadService(db)

                    # Get agent name for default title
                    contact = db.query(Contact).filter(Contact.id == agent.contact_id).first() if agent else None
                    agent_name = contact.friendly_name if contact else "Bot"
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
                    thread = db.query(ConversationThread).filter(ConversationThread.id == thread_id).first()

                    # Notify about new thread
                    yield {
                        "type": "thread_created",
                        "thread_id": thread_id,
                        "title": thread.title
                    }

                # Update thread activity
                thread.updated_at = datetime.utcnow()
                db.commit()

                # Send "thinking" indicator with agent metadata
                contact = db.query(Contact).filter(Contact.id == agent.contact_id).first() if agent else None
                agent_name = contact.friendly_name if contact else f"Agent {agent_id}"
                yield {
                    "type": "thinking",
                    "agent_id": agent_id,
                    "agent_name": agent_name,
                    "avatar": getattr(agent, 'avatar', None),
                }

                # Use the streaming method from PlaygroundService
                accumulated_response = ""
                token_usage = None
                message_id = None

                async for chunk in playground_service.process_message_streaming(
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
                        image_url = chunk.get("image_url")  # Phase 6: Image generation

                        # Auto-rename thread based on first message
                        thread_renamed = False
                        new_thread_title = None

                        if thread_id:
                            from services.playground_thread_service import PlaygroundThreadService

                            # Ensure clean DB session before post-streaming queries
                            try:
                                db.rollback()
                            except Exception:
                                pass

                            # Check if this is a fresh thread (only 2 messages: user + assistant)
                            current_thread = db.query(ConversationThread).filter(
                                ConversationThread.id == thread_id
                            ).first()

                            if current_thread:
                                message_count = PlaygroundThreadService(db).count_thread_messages(current_thread)
                                self.logger.warning(
                                    f"[Auto-rename WS] Thread {thread_id}: "
                                    f"recipient={current_thread.recipient}, message_count={message_count}"
                                )

                                # Only auto-rename after first exchange (2 messages: user + assistant)
                                if message_count <= 2:
                                    thread_service = PlaygroundThreadService(db)
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

                        # Invoke post-response hooks (knowledge sharing, OKG auto-capture, etc.)
                        if accumulated_response:
                            try:
                                from agent.ai_client import AIClient
                                from services.system_ai_config import get_system_ai_config
                                sender_key = f"playground_u{self.user_id}_a{agent_id}_t{thread_id}"
                                agent = db.query(Agent).filter(Agent.id == agent_id).first()
                                system_provider, system_model, system_provider_instance_id = get_system_ai_config(db)
                                ai_client = AIClient(
                                    provider=(agent.model_provider if agent and agent.model_provider else system_provider),
                                    model_name=(agent.model_name if agent and agent.model_name else system_model),
                                    db=db,
                                    tenant_id=agent.tenant_id if agent else None,
                                    provider_instance_id=(
                                        agent.provider_instance_id
                                        if agent and agent.provider_instance_id
                                        else system_provider_instance_id
                                    ),
                                )
                                await playground_service._invoke_post_response_hooks(
                                    agent_id=agent_id,
                                    user_message=message,
                                    agent_response=accumulated_response,
                                    context={
                                        "sender_key": sender_key,
                                        "sender_name": f"Playground User {self.user_id}",
                                        "is_group": False,
                                        "chat_id": sender_key,
                                    },
                                    ai_client=ai_client,
                                )
                            except Exception as e:
                                self.logger.error(f"Post-response hooks error (non-blocking): {e}")

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
                            "new_thread_title": new_thread_title,
                            "image_url": image_url,  # Phase 6: Image generation
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
