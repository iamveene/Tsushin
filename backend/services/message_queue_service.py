"""
Message Queue Service
Handles enqueue, claim, completion, failure, and status queries for async message processing.
"""

import logging
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_

from models import MessageQueue

logger = logging.getLogger(__name__)


class MessageQueueService:
    """Service for managing the message queue."""

    def __init__(self, db: Session):
        self.db = db

    def enqueue(
        self,
        channel: str,
        tenant_id: str,
        agent_id: int,
        sender_key: str,
        payload: dict,
        priority: int = 0,
        message_type: str = "inbound_message",
    ) -> MessageQueue:
        """Queue a message for processing."""
        item = MessageQueue(
            tenant_id=tenant_id,
            channel=channel,
            message_type=message_type,
            agent_id=agent_id,
            sender_key=sender_key,
            payload=payload,
            priority=priority,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        logger.info(
            f"Enqueued message queue item {item.id} "
            f"(type={message_type}, channel={channel}, tenant={tenant_id}, agent={agent_id})"
        )
        return item

    def claim_next(self, tenant_id: str, agent_id: int) -> Optional[MessageQueue]:
        """
        Claim next pending item using SELECT FOR UPDATE SKIP LOCKED.
        This ensures concurrent workers don't claim the same item.
        """
        item = self.db.execute(
            select(MessageQueue)
            .where(
                MessageQueue.tenant_id == tenant_id,
                MessageQueue.agent_id == agent_id,
                MessageQueue.status == "pending",
            )
            .order_by(MessageQueue.priority.desc(), MessageQueue.queued_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        ).scalar_one_or_none()

        if item:
            item.status = "processing"
            item.processing_started_at = datetime.utcnow()
            self.db.commit()
            logger.info(f"Claimed queue item {item.id} for processing")
        return item

    def mark_completed(self, queue_id: int, result: dict = None):
        """Mark a queue item as completed, optionally persisting the result in payload."""
        item = self.db.get(MessageQueue, queue_id)
        if item:
            item.status = "completed"
            item.completed_at = datetime.utcnow()
            if result is not None:
                # Reassign payload dict so SQLAlchemy detects the JSON mutation
                updated_payload = dict(item.payload) if item.payload else {}
                updated_payload["result"] = result
                item.payload = updated_payload
            self.db.commit()
            logger.info(f"Queue item {queue_id} completed")

    def mark_failed(self, queue_id: int, error: str):
        """
        Mark a queue item as failed. If retries exhausted, move to dead_letter.
        Otherwise reset to pending for retry.
        """
        item = self.db.get(MessageQueue, queue_id)
        if item:
            item.retry_count += 1
            item.error_message = error
            if item.retry_count >= item.max_retries:
                item.status = "dead_letter"
                logger.warning(
                    f"Queue item {queue_id} moved to dead_letter after {item.retry_count} retries: {error}"
                )
            else:
                item.status = "pending"
                item.processing_started_at = None
                logger.info(
                    f"Queue item {queue_id} retry {item.retry_count}/{item.max_retries}: {error}"
                )
            self.db.commit()

    def get_position(self, queue_id: int) -> int:
        """
        Get position of item in queue (0 = being processed or not pending).
        Returns the count of items ahead of this one.
        """
        item = self.db.get(MessageQueue, queue_id)
        if not item or item.status != "pending":
            return 0
        count = self.db.query(func.count(MessageQueue.id)).filter(
            MessageQueue.tenant_id == item.tenant_id,
            MessageQueue.agent_id == item.agent_id,
            MessageQueue.status == "pending",
            or_(
                MessageQueue.priority > item.priority,
                and_(
                    MessageQueue.priority == item.priority,
                    MessageQueue.queued_at < item.queued_at,
                ),
            ),
        ).scalar()
        return count

    def get_queue_status(
        self, tenant_id: str, agent_id: int = None
    ) -> List[MessageQueue]:
        """Get all pending/processing items for a tenant, optionally filtered by agent."""
        q = self.db.query(MessageQueue).filter(
            MessageQueue.tenant_id == tenant_id,
            MessageQueue.status.in_(["pending", "processing"]),
        )
        if agent_id:
            q = q.filter(MessageQueue.agent_id == agent_id)
        return (
            q.order_by(MessageQueue.priority.desc(), MessageQueue.queued_at.asc())
            .all()
        )

    def get_pending_agents(self) -> list:
        """
        Get list of (tenant_id, agent_id) pairs that have pending items.
        Used by the worker to know which agents need processing.
        """
        results = (
            self.db.query(MessageQueue.tenant_id, MessageQueue.agent_id)
            .filter(MessageQueue.status == "pending")
            .distinct()
            .all()
        )
        return [(r.tenant_id, r.agent_id) for r in results]

    def reset_stale(self, threshold_seconds: int = 300) -> int:
        """
        Reset processing items older than threshold back to pending.
        This recovers from worker crashes or stuck processing.
        """
        cutoff = datetime.utcnow() - timedelta(seconds=threshold_seconds)
        stale = (
            self.db.query(MessageQueue)
            .filter(
                MessageQueue.status == "processing",
                MessageQueue.processing_started_at < cutoff,
            )
            .all()
        )
        for item in stale:
            item.status = "pending"
            item.processing_started_at = None
            logger.warning(f"Reset stale queue item {item.id} back to pending")
        if stale:
            self.db.commit()
        return len(stale)

    def cancel_item(self, queue_id: int, tenant_id: str) -> bool:
        """Cancel a pending queue item (only if it belongs to the tenant and is pending)."""
        item = self.db.get(MessageQueue, queue_id)
        if item and item.tenant_id == tenant_id and item.status == "pending":
            self.db.delete(item)
            self.db.commit()
            logger.info(f"Cancelled queue item {queue_id}")
            return True
        return False
