"""
Agent Chat — Public API v1
Provides programmatic chat with agents, identical to Playground experience.
Supports sync and async modes, thread management, and queue polling.
"""

import logging
from datetime import datetime
from typing import Any, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from models import Agent, ConversationThread, Contact
from api.api_auth import ApiCaller, require_api_permission
from api.v1.schemas import COMMON_RESPONSES, NOT_FOUND_RESPONSE
from services.playground_service import PlaygroundService
from services.playground_message_service import PlaygroundMessageService
from services.playground_thread_service import (
    PlaygroundThreadService,
    build_api_channel_id,
    build_api_thread_recipient,
)
from agent.response_helpers import extract_response_text as _extract_response_text

logger = logging.getLogger(__name__)
router = APIRouter()


def _tag_thread_with_api_client(db, thread_id: int, caller) -> None:
    """BUG-367: Tag newly created thread with API client ID for isolation."""
    if thread_id and caller.is_api_client and caller.client_id:
        try:
            thread_record = db.query(ConversationThread).filter(
                ConversationThread.id == thread_id
            ).first()
            if thread_record:
                thread_record.api_client_id = caller.client_id
                db.commit()
        except Exception as e:
            logger.warning(f"Failed to set api_client_id on thread: {e}")


def _validate_thread_access(db, thread_id: int, caller) -> None:
    """BUG-367: Validate thread belongs to caller's tenant AND API client."""
    query = db.query(ConversationThread).filter(
        ConversationThread.id == thread_id,
        ConversationThread.tenant_id == caller.tenant_id,
    )
    # API clients can only see their own threads
    if caller.is_api_client and caller.client_id:
        query = query.filter(ConversationThread.api_client_id == caller.client_id)
    thread = query.first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")


def _build_api_sender_key(caller, thread_id: int, isolation_mode: str) -> str:
    """Build the canonical sender key for API chat processing."""
    if isolation_mode == "isolated":
        return build_api_thread_recipient(
            thread_id=thread_id,
            api_client_id=caller.client_id if caller.is_api_client else None,
            user_id=caller.user_id if not caller.is_api_client else None,
        )

    return build_api_channel_id(
        api_client_id=caller.client_id if caller.is_api_client else None,
        user_id=caller.user_id if not caller.is_api_client else None,
    )


def _sync_api_thread_recipient(db, thread_id: int, caller) -> Optional[str]:
    """Persist the API-specific recipient so later message lookup uses the same key."""
    if not thread_id:
        return None

    thread = db.query(ConversationThread).filter(ConversationThread.id == thread_id).first()
    if not thread:
        return None

    recipient = build_api_thread_recipient(
        thread_id=thread_id,
        api_client_id=caller.client_id if caller.is_api_client else None,
        user_id=caller.user_id if not caller.is_api_client else None,
    )
    if thread.recipient != recipient:
        thread.recipient = recipient
        db.commit()
    return recipient


# ============================================================================
# Schemas
# ============================================================================

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    thread_id: Optional[int] = None
    context: Optional[dict] = None


class ChatResponse(BaseModel):
    status: str
    message: Optional[str] = None
    response: Optional[str] = None  # Alias for message (backward compat)
    agent_name: Optional[str] = None
    thread_id: Optional[int] = None
    tool_used: Optional[str] = None
    execution_time_ms: Optional[int] = None
    processing_time_ms: Optional[int] = None  # Alias for execution_time_ms
    tokens_used: Optional[int] = None
    timestamp: str
    error: Optional[str] = None


class QueuedResponse(BaseModel):
    status: str = "queued"
    queue_id: int
    estimated_wait_seconds: int = 5
    poll_url: str


class QueueStatusResponse(BaseModel):
    status: str
    queue_id: int
    position: Optional[int] = None
    estimated_wait_seconds: Optional[int] = None
    result: Optional[dict] = None
    agentic_scratchpad: Optional[List[dict]] = None


class ThreadSummary(BaseModel):
    id: int
    title: Optional[str]
    created_at: str
    updated_at: Optional[str]
    message_count: int


class ThreadMessage(BaseModel):
    role: str
    content: str
    timestamp: str
    message_id: Optional[str] = None


# ============================================================================
# Endpoints
# ============================================================================

@router.post(
    "/api/v1/agents/{agent_id}/chat",
    response_model=None,
    responses={
        200: {
            "description": "Synchronous chat response",
            "content": {"application/json": {"schema": ChatResponse.model_json_schema()}},
        },
        202: {
            "description": "Async mode — message queued for processing",
            "content": {"application/json": {"schema": QueuedResponse.model_json_schema()}},
        },
        **COMMON_RESPONSES,
        **NOT_FOUND_RESPONSE,
    },
)
async def send_chat_message(
    agent_id: int,
    request: ChatRequest,
    async_mode: bool = Query(False, alias="async", description="Enqueue for async processing"),
    stream: bool = Query(False, description="Enable SSE streaming response"),
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.execute")),
):
    """
    Send a message to an agent and get a response.

    Supports three modes:
    - **Sync** (default): Processes the message and returns the full response.
    - **Async** (`?async=true`): Enqueues the message and returns a queue ID for polling via `GET /api/v1/queue/{id}`.
    - **Stream** (`?stream=true`): Returns an SSE stream with token-by-token response chunks.

    Requires `agents.execute` permission.
    """
    # Validate agent access
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == caller.tenant_id,
        Agent.is_active == True,
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found or not active")

    # Get agent name
    contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()
    agent_name = contact.friendly_name if contact else f"Agent {agent.id}"

    # Handle streaming mode — return SSE stream
    if stream:
        return await _process_stream_sse(agent, agent_name, request, caller, db)

    # Handle async mode — enqueue and return immediately
    if async_mode:
        return await _enqueue_message(agent, agent_name, request, caller, db)

    # Synchronous mode — process and return response
    return await _process_sync(agent, agent_name, request, caller, db)


async def _process_sync(agent, agent_name, request, caller, db):
    """Process a chat message synchronously."""
    import time
    start_time = time.time()

    service = PlaygroundService(db)

    # Handle thread — create new if not specified
    thread_id = request.thread_id
    if thread_id:
        _validate_thread_access(db, thread_id, caller)
    if not thread_id:
        thread_service = PlaygroundThreadService(db)
        thread_data = await thread_service.create_thread(
            tenant_id=caller.tenant_id,
            user_id=caller.user_id or 0,
            agent_id=agent.id,
            title=request.message[:50] + "..." if len(request.message) > 50 else request.message,
        )
        thread_obj = thread_data.get("thread", {})
        thread_id = thread_obj.get("id") if thread_obj else None
        _tag_thread_with_api_client(db, thread_id, caller)
    _sync_api_thread_recipient(db, thread_id, caller)

    isolation_mode = getattr(agent, "memory_isolation_mode", "isolated") or "isolated"
    sender_key = _build_api_sender_key(caller, thread_id, isolation_mode)
    chat_id_override = build_api_channel_id(
        api_client_id=caller.client_id if caller.is_api_client else None,
        user_id=caller.user_id if not caller.is_api_client else None,
    )

    try:
        result = await service.send_message(
            user_id=caller.user_id or 0,
            agent_id=agent.id,
            message_text=request.message,
            thread_id=thread_id,
            tenant_id=caller.tenant_id,
            sender_key=sender_key,
            chat_id_override=chat_id_override,
        )
    except Exception as e:
        logger.error(f"Chat error for agent {agent.id}: {e}", exc_info=True)
        return ChatResponse(
            status="error",
            error=str(e),
            agent_name=agent_name,
            thread_id=thread_id,
            timestamp=datetime.utcnow().isoformat() + "Z",
        )

    execution_time_ms = int((time.time() - start_time) * 1000)

    if result.get("error"):
        return ChatResponse(
            status="error",
            error=result.get("error"),
            agent_name=agent_name,
            thread_id=thread_id,
            execution_time_ms=execution_time_ms,
            processing_time_ms=execution_time_ms,
            timestamp=datetime.utcnow().isoformat() + "Z",
        )

    # Extract token usage from result (agent returns tokens dict with "total" key)
    tokens = result.get("tokens")
    tokens_used = None
    if isinstance(tokens, dict):
        tokens_used = tokens.get("total")
    elif isinstance(tokens, (int, float)):
        tokens_used = int(tokens)

    response_text = _extract_response_text(result)

    return ChatResponse(
        status="success",
        message=response_text,
        response=response_text,
        agent_name=agent_name,
        thread_id=thread_id,
        tool_used=result.get("tool_used"),
        execution_time_ms=execution_time_ms,
        processing_time_ms=execution_time_ms,
        tokens_used=tokens_used,
        timestamp=datetime.utcnow().isoformat() + "Z",
    )


async def _process_stream_sse(agent, agent_name, request, caller, db):
    """Process a chat message with SSE streaming response."""
    import json
    from fastapi.responses import StreamingResponse

    service = PlaygroundService(db)

    # Handle thread
    thread_id = request.thread_id
    if thread_id:
        _validate_thread_access(db, thread_id, caller)
    if not thread_id:
        thread_service = PlaygroundThreadService(db)
        thread_data = await thread_service.create_thread(
            tenant_id=caller.tenant_id,
            user_id=caller.user_id or 0,
            agent_id=agent.id,
            title=request.message[:50] + "..." if len(request.message) > 50 else request.message,
        )
        thread_obj = thread_data.get("thread", {})
        thread_id = thread_obj.get("id") if thread_obj else None
        _tag_thread_with_api_client(db, thread_id, caller)
    _sync_api_thread_recipient(db, thread_id, caller)

    isolation_mode = getattr(agent, "memory_isolation_mode", "isolated") or "isolated"
    sender_key = _build_api_sender_key(caller, thread_id, isolation_mode)
    chat_id_override = build_api_channel_id(
        api_client_id=caller.client_id if caller.is_api_client else None,
        user_id=caller.user_id if not caller.is_api_client else None,
    )

    async def event_generator():
        try:
            async for chunk in service.process_message_streaming(
                user_id=caller.user_id or 0,
                agent_id=agent.id,
                message_text=request.message,
                thread_id=thread_id,
                sender_key=sender_key,
                chat_id_override=chat_id_override,
            ):
                chunk_data = json.dumps(chunk)
                yield f"data: {chunk_data}\n\n"

                if chunk.get("type") in ("done", "error"):
                    break
        except Exception as e:
            logger.error(f"API v1 SSE stream error: {e}", exc_info=True)
            error_data = json.dumps({"type": "error", "error": str(e)})
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _enqueue_message(agent, agent_name, request, caller, db):
    """Enqueue a chat message for async processing."""
    from services.message_queue_service import MessageQueueService

    queue_service = MessageQueueService(db)

    queue_item = queue_service.enqueue(
        tenant_id=caller.tenant_id,
        channel="api",
        agent_id=agent.id,
        sender_key=build_api_channel_id(
            api_client_id=caller.client_id if caller.is_api_client else None,
            user_id=caller.user_id if not caller.is_api_client else None,
        ),
        payload={
            "message": request.message,
            "thread_id": request.thread_id,
            "user_id": caller.user_id or 0,
            "api_client_id": caller.client_id,
        },
    )

    payload = QueuedResponse(
        queue_id=queue_item.id,
        estimated_wait_seconds=5,
        poll_url=f"/api/v1/queue/{queue_item.id}",
    )
    return JSONResponse(status_code=202, content=payload.model_dump())


@router.get(
    "/api/v1/queue/{queue_id}",
    response_model=QueueStatusResponse,
    response_model_exclude_none=True,
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE},
)
async def poll_queue_status(
    queue_id: int,
    include_scratchpad: bool = Query(False, description="Include agentic scratchpad trace when available"),
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.execute")),
):
    """
    Poll the status of a queued chat message.

    Returns the queue item status (`pending`, `processing`, `completed`, or `error`)
    along with queue position and the result when completed.
    Requires `agents.execute` permission.
    """
    from models import MessageQueue

    queue_item = db.query(MessageQueue).filter(
        MessageQueue.id == queue_id,
        MessageQueue.tenant_id == caller.tenant_id,
    ).first()

    if not queue_item:
        raise HTTPException(status_code=404, detail="Queue item not found")

    payload = queue_item.payload if isinstance(queue_item.payload, dict) else {}
    if caller.is_api_client and caller.client_id:
        if payload.get("api_client_id") != caller.client_id:
            raise HTTPException(status_code=404, detail="Queue item not found")

    if queue_item.status == "completed":
        result = payload.get("result") if isinstance(payload, dict) else None
        response_result = result
        if isinstance(result, dict):
            response_result = dict(result)
            response_result.pop("agentic_scratchpad", None)
        response_data: dict[str, Any] = {
            "status": "completed",
            "queue_id": queue_id,
            "result": response_result,
        }
        if include_scratchpad:
            scratchpad = _resolve_queue_scratchpad(db, result, caller)
            if scratchpad is not None:
                response_data["agentic_scratchpad"] = scratchpad
        return QueueStatusResponse(
            **response_data,
        )

    if queue_item.status == "error":
        return QueueStatusResponse(
            status="error",
            queue_id=queue_id,
            result={"error": queue_item.error_message},
        )

    # Still processing
    position = db.query(MessageQueue).filter(
        MessageQueue.status == "pending",
        MessageQueue.id < queue_id,
        MessageQueue.tenant_id == caller.tenant_id,
    ).count()

    return QueueStatusResponse(
        status=queue_item.status,
        queue_id=queue_id,
        position=position,
        estimated_wait_seconds=max(1, position * 3 + 2),
    )


def _resolve_queue_scratchpad(db: Session, result: Optional[dict], caller: ApiCaller) -> Optional[List[dict]]:
    """Resolve a completed queue result's scratchpad without widening queue access."""
    if not isinstance(result, dict):
        return None

    scratchpad = result.get("agentic_scratchpad")
    if isinstance(scratchpad, list):
        return scratchpad

    thread_id = result.get("thread_id")
    if not isinstance(thread_id, int):
        return None

    thread_query = db.query(ConversationThread).filter(
        ConversationThread.id == thread_id,
        ConversationThread.tenant_id == caller.tenant_id,
    )
    if caller.is_api_client and caller.client_id:
        thread_query = thread_query.filter(ConversationThread.api_client_id == caller.client_id)
    elif caller.user_id:
        thread_query = thread_query.filter(ConversationThread.user_id == caller.user_id)

    thread = thread_query.first()
    if isinstance(getattr(thread, "agentic_scratchpad", None), list):
        return thread.agentic_scratchpad
    return None


@router.get(
    "/api/v1/agents/{agent_id}/threads",
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE},
)
async def list_threads(
    agent_id: int,
    limit: int = Query(20, ge=1, le=100, description="Maximum threads to return"),
    offset: int = Query(0, ge=0, description="Number of threads to skip"),
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.read")),
):
    """
    List conversation threads for an agent.

    Returns threads ordered by most recently updated. Requires `agents.read` permission.
    """
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == caller.tenant_id,
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # BUG-367: Scope threads by API client to prevent cross-client access
    thread_query = db.query(ConversationThread).filter(
        ConversationThread.agent_id == agent_id,
        ConversationThread.tenant_id == caller.tenant_id,
    )
    if caller.is_api_client and caller.client_id:
        thread_query = thread_query.filter(
            ConversationThread.api_client_id == caller.client_id
        )
    threads = thread_query.order_by(ConversationThread.updated_at.desc()).offset(offset).limit(limit).all()

    return {
        "data": [
            {
                "id": t.id,
                "title": t.title,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in threads
        ],
    }


@router.get(
    "/api/v1/agents/{agent_id}/threads/{thread_id}/messages",
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE},
)
async def get_thread_messages(
    agent_id: int,
    thread_id: int,
    limit: int = Query(50, ge=1, le=200, description="Maximum messages to return"),
    offset: int = Query(0, ge=0, description="Number of messages to skip"),
    order: str = Query("asc", pattern="^(asc|desc)$", description="Sort order (asc or desc)"),
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.read")),
):
    """
    Get messages from a conversation thread.

    Returns messages with role, content, and timestamp. Supports ascending
    or descending sort order. Requires `agents.read` permission.
    """
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == caller.tenant_id,
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # BUG-367: Scope by API client
    thread_query = db.query(ConversationThread).filter(
        ConversationThread.id == thread_id,
        ConversationThread.agent_id == agent_id,
        ConversationThread.tenant_id == caller.tenant_id,
    )
    if caller.is_api_client and caller.client_id:
        thread_query = thread_query.filter(
            ConversationThread.api_client_id == caller.client_id
        )
    thread = thread_query.first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    message_service = PlaygroundMessageService(db)
    messages = message_service.get_thread_messages(thread_id, limit=limit, offset=offset)

    if order == "desc":
        messages = list(reversed(messages))

    return {
        "data": [
            {
                "role": m.get("role", "unknown"),
                "content": m.get("content", ""),
                "timestamp": m.get("timestamp", ""),
                "message_id": m.get("message_id"),
            }
            for m in messages
        ],
        "meta": {"thread_id": thread_id, "agent_id": agent_id},
    }


@router.delete(
    "/api/v1/agents/{agent_id}/threads/{thread_id}",
    status_code=204,
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE},
)
async def delete_thread(
    agent_id: int,
    thread_id: int,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.write")),
):
    """
    Delete a conversation thread and its messages.

    Permanently removes the thread and all associated messages.
    Requires `agents.write` permission.
    """
    # BUG-367: Scope by API client
    thread_query = db.query(ConversationThread).filter(
        ConversationThread.id == thread_id,
        ConversationThread.agent_id == agent_id,
        ConversationThread.tenant_id == caller.tenant_id,
    )
    if caller.is_api_client and caller.client_id:
        thread_query = thread_query.filter(
            ConversationThread.api_client_id == caller.client_id
        )
    thread = thread_query.first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    db.delete(thread)
    db.commit()
