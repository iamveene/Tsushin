"""
Queue API Routes
Provides endpoints for queue status, item details, and cancellation.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db import get_db
from auth_dependencies import get_current_user_required
from models_rbac import User
from models import MessageQueue
from services.message_queue_service import MessageQueueService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/queue", tags=["Queue"])


@router.get("/status")
async def get_queue_status(
    agent_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Get queue status for the current tenant, optionally filtered by agent."""
    service = MessageQueueService(db)
    items = service.get_queue_status(current_user.tenant_id, agent_id)
    return {
        "items": [
            {
                "id": i.id,
                "status": i.status,
                "channel": i.channel,
                "agent_id": i.agent_id,
                "sender_key": i.sender_key,
                "priority": i.priority,
                "retry_count": i.retry_count,
                "queued_at": i.queued_at.isoformat() if i.queued_at else None,
                "processing_started_at": (
                    i.processing_started_at.isoformat()
                    if i.processing_started_at
                    else None
                ),
            }
            for i in items
        ]
    }


@router.get("/item/{queue_id}")
async def get_queue_item(
    queue_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Get details of a specific queue item including its position."""
    service = MessageQueueService(db)
    item = db.get(MessageQueue, queue_id)
    if not item or item.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Queue item not found")

    position = service.get_position(queue_id)
    result = None
    if item.payload and isinstance(item.payload, dict):
        result = item.payload.get("result")
    return {
        "id": item.id,
        "status": item.status,
        "position": position,
        "channel": item.channel,
        "agent_id": item.agent_id,
        "sender_key": item.sender_key,
        "priority": item.priority,
        "retry_count": item.retry_count,
        "error_message": item.error_message,
        "result": result,
        "queued_at": item.queued_at.isoformat() if item.queued_at else None,
        "processing_started_at": (
            item.processing_started_at.isoformat()
            if item.processing_started_at
            else None
        ),
        "completed_at": (
            item.completed_at.isoformat() if item.completed_at else None
        ),
    }


@router.delete("/item/{queue_id}")
async def cancel_queue_item(
    queue_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """Cancel a pending queue item."""
    service = MessageQueueService(db)
    success = service.cancel_item(queue_id, current_user.tenant_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Cannot cancel item (not found, not pending, or wrong tenant)",
        )
    return {"success": True}
