"""
Phase 6.11: Unified Flows - Flow Templates
Provides template builders for common flow patterns (notifications, conversations).
"""
from datetime import datetime
from typing import Dict, Any, Optional


def create_notification_flow(
    reminder_text: str,
    scheduled_at: datetime,
    recipient: Optional[str],
    sender: str,
    agent_id: int,
    natural_language_request: str
) -> Dict[str, Any]:
    """
    Create a notification flow template (replaces ScheduledEvent NOTIFICATION).

    Args:
        reminder_text: The reminder message content
        scheduled_at: When to send the reminder
        recipient: Phone number/WhatsApp ID of recipient (or None for sender)
        sender: Phone number of the requester
        agent_id: Agent ID that created this flow
        natural_language_request: Original natural language request

    Returns:
        Dict with flow definition structure
    """
    return {
        "name": f"🔔 {reminder_text[:50]}",
        "description": f"Agentic reminder: {reminder_text}",
        "initiator_type": "agentic",
        "initiator_metadata": {
            "natural_language_request": natural_language_request,
            "sender": sender,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "agent_id": agent_id
        },
        "flow_type": "notification",
        "is_active": True,
        "nodes": [
            {
                "id": 1,
                "type": "Trigger",
                "position": 1,
                "config": {
                    "type": "time",
                    "scheduled_at": scheduled_at.isoformat(),
                    "agent_id": agent_id,
                    "context_fields": {
                        "reminder_text": reminder_text,
                        "recipient": recipient or sender
                    }
                }
            },
            {
                "id": 2,
                "type": "Message",
                "position": 2,
                "config": {
                    "channel": "whatsapp",
                    "recipients": [recipient or sender],
                    "message_template": f"Hi! Reminder: {reminder_text}"
                }
            }
        ],
        "edges": []  # Linear flow
    }


def create_conversation_flow(
    objective: str,
    scheduled_at: datetime,
    recipient: str,
    sender: str,
    agent_id: int,
    natural_language_request: str,
    max_turns: int = 10
) -> Dict[str, Any]:
    """
    Create an AI-driven conversation flow template (replaces ScheduledEvent CONVERSATION).

    Args:
        objective: Conversation objective/goal
        scheduled_at: When to initiate the conversation
        recipient: Phone number/WhatsApp ID of conversation partner
        sender: Phone number of the requester
        agent_id: Agent ID that will conduct the conversation
        natural_language_request: Original natural language request
        max_turns: Maximum conversation turns

    Returns:
        Dict with flow definition structure
    """
    return {
        "name": f"💬 {objective[:50]}",
        "description": f"Agentic conversation: {objective}",
        "initiator_type": "agentic",
        "initiator_metadata": {
            "natural_language_request": natural_language_request,
            "sender": sender,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "agent_id": agent_id
        },
        "flow_type": "conversation",
        "is_active": True,
        "nodes": [
            {
                "id": 1,
                "type": "Trigger",
                "position": 1,
                "config": {
                    "type": "time",
                    "scheduled_at": scheduled_at.isoformat(),
                    "agent_id": agent_id,
                    "context_fields": {
                        "objective": objective,
                        "recipient": recipient
                    }
                }
            },
            {
                "id": 2,
                "type": "Conversation",
                "position": 2,
                "config": {
                    "agent_id": agent_id,
                    "recipient": recipient,
                    "objective": objective,
                    "context": {},
                    "max_turns": max_turns,
                    "accept_audio": False
                }
            }
        ],
        "edges": []  # Linear flow
    }


def create_workflow_flow(
    name: str,
    description: str,
    nodes: list,
    edges: list,
    trigger: Dict[str, Any],
    initiator_type: str = "programmatic"
) -> Dict[str, Any]:
    """
    Create a complex workflow flow (multi-step, programmatic).

    Args:
        name: Flow name
        description: Flow description
        nodes: List of node definitions
        edges: List of edge definitions
        trigger: Trigger configuration
        initiator_type: 'programmatic' (UI) or 'agentic' (AI)

    Returns:
        Dict with flow definition structure
    """
    return {
        "name": name,
        "description": description,
        "initiator_type": initiator_type,
        "initiator_metadata": {},
        "flow_type": "workflow",
        "is_active": True,
        "trigger": trigger,
        "nodes": nodes,
        "edges": edges
    }
