"""
⚠️ DEPRECATED - Phase 6.11: Unified Flows - Flow Creator Service

This service incorrectly routes simple notifications/conversations to the multi-step flow system.

**DO NOT USE THIS SERVICE**

For NOTIFICATION and CONVERSATION types, use SchedulerService instead (scheduled_events table).
Multi-step flows (flow_definition table) should only be created via the flow builder UI at /multi-step-flows.

**Migration Status:**
- SchedulerSkill: ✅ Fixed (now uses SchedulerService)
- This service: ⚠️ Deprecated (kept for reference only)

**See:** FLOW_SYSTEMS_ARCHITECTURE.md for architectural details
"""
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Dict, Any
import json
import logging
import warnings

from models import FlowDefinition, FlowNode
from flows.flow_templates import (
    create_notification_flow,
    create_conversation_flow
)

logger = logging.getLogger(__name__)


class FlowCreatorService:
    """
    Service for creating flows from natural language (agentic initiator).
    Replaces SchedulerService for NOTIFICATION and CONVERSATION types.
    """

    def __init__(self, db_session: Session):
        self.db = db_session

    def create_agentic_flow(
        self,
        event_type: str,
        scheduled_at: datetime,
        payload: Dict[str, Any],
        agent_id: int,
        natural_language_request: str,
        sender: str,
        recurrence_rule: Dict[str, Any] = None
    ) -> FlowDefinition:
        """
        ⚠️ DEPRECATED: Use SchedulerService.create_event() instead.

        This method incorrectly creates multi-step flows for simple notifications/conversations.

        Args:
            event_type: 'NOTIFICATION' or 'CONVERSATION'
            scheduled_at: When to execute (UTC)
            payload: Event-specific data
            agent_id: Agent ID creating the flow
            natural_language_request: Original request text
            sender: Requester's phone number
            recurrence_rule: Optional recurrence config

        Returns:
            Created FlowDefinition
        """
        warnings.warn(
            "FlowCreatorService.create_agentic_flow() is deprecated. "
            "Use SchedulerService.create_event() for NOTIFICATION and CONVERSATION types.",
            DeprecationWarning,
            stacklevel=2
        )
        logger.warning("DEPRECATED: FlowCreatorService.create_agentic_flow() called - use SchedulerService instead")

        try:
            # Generate flow template based on event type
            if event_type == 'NOTIFICATION':
                flow_data = create_notification_flow(
                    reminder_text=payload.get('reminder_text', ''),
                    scheduled_at=scheduled_at,
                    recipient=payload.get('recipient_raw'),
                    sender=sender,
                    agent_id=agent_id,
                    natural_language_request=natural_language_request
                )
            elif event_type == 'CONVERSATION':
                flow_data = create_conversation_flow(
                    objective=payload.get('objective', ''),
                    scheduled_at=scheduled_at,
                    recipient=payload.get('recipient', ''),
                    sender=sender,
                    agent_id=agent_id,
                    natural_language_request=natural_language_request,
                    max_turns=payload.get('max_turns', 10)
                )
            else:
                raise ValueError(f"Unsupported event type: {event_type}")

            # Create FlowDefinition
            flow = FlowDefinition(
                name=flow_data['name'],
                description=flow_data['description'],
                initiator_type=flow_data['initiator_type'],
                initiator_metadata=flow_data['initiator_metadata'],
                flow_type=flow_data['flow_type'],
                is_active=flow_data['is_active']
            )

            self.db.add(flow)
            self.db.flush()  # Get flow.id

            # Create FlowNodes
            for node_data in flow_data['nodes']:
                node = FlowNode(
                    flow_definition_id=flow.id,
                    type=node_data['type'],
                    position=node_data['position'],
                    config_json=json.dumps(node_data['config']),
                    next_node_id=None  # Simple flows have single nodes
                )
                self.db.add(node)

            self.db.commit()

            logger.info(f"Created agentic flow #{flow.id}: {flow.name}")
            return flow

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating agentic flow: {e}", exc_info=True)
            raise

    def format_confirmation(self, flow: FlowDefinition, scheduled_at_brazil: str) -> str:
        """
        Format confirmation message for created flow.

        Args:
            flow: Created FlowDefinition
            scheduled_at_brazil: Scheduled time in Brazil timezone (formatted string)

        Returns:
            Confirmation message
        """
        metadata = flow.initiator_metadata or {}
        flow_type = flow.flow_type

        if flow_type == 'notification':
            # Extract reminder text from first node
            nodes = self.db.query(FlowNode).filter(
                FlowNode.flow_definition_id == flow.id
            ).all()

            reminder_text = "lembrete"
            if nodes:
                config = json.loads(nodes[0].config_json)
                content = config.get('content', '')
                # Extract reminder text from "Hi! Reminder: X" format
                if 'Reminder:' in content:
                    reminder_text = content.split('Reminder:', 1)[1].strip()

            msg = f"✅ Lembrete agendado\n"
            msg += f"   Mensagem: {reminder_text}\n"
            msg += f"   Data/Hora: {scheduled_at_brazil}\n"
            msg += f"   ID do fluxo: {flow.id}"

        elif flow_type == 'conversation':
            # Extract objective from first node
            nodes = self.db.query(FlowNode).filter(
                FlowNode.flow_definition_id == flow.id
            ).all()

            objective = "objetivo da conversa"
            recipient = "destinatário"
            if nodes:
                config = json.loads(nodes[0].config_json)
                objective = config.get('objective', objective)
                recipient = config.get('recipient', recipient)

            msg = f"✅ Conversa agendada com {recipient}\n"
            msg += f"   Objetivo: {objective}\n"
            msg += f"   Data/Hora: {scheduled_at_brazil}\n"
            msg += f"   ID do fluxo: {flow.id}"

        else:
            msg = f"✅ Fluxo agendado: {flow.name}\n"
            msg += f"   Data/Hora: {scheduled_at_brazil}\n"
            msg += f"   ID do fluxo: {flow.id}"

        return msg
