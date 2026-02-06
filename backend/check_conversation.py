from db import get_engine, get_session
from models import ScheduledEvent, ConversationLog
import json

engine = get_engine('./data/agent.db')

with get_session(engine) as db:
    event = db.query(ScheduledEvent).filter(ScheduledEvent.id == 41).first()

    print(f"Event ID: {event.id}")
    print(f"Event Status: {event.status}")
    print(f"Event Type: {event.event_type}")

    if event.conversation_state:
        state = json.loads(event.conversation_state) if isinstance(event.conversation_state, str) else event.conversation_state
        print(f"\nConversation State:")
        for key, value in state.items():
            if key != 'history':
                print(f"  {key}: {value}")

    logs = db.query(ConversationLog).filter(
        ConversationLog.scheduled_event_id == 41
    ).order_by(ConversationLog.timestamp.asc()).all()

    print(f"\n{len(logs)} conversation logs:")
    for log in logs:
        direction = "OUT" if log.message_direction == "SENT" else "IN"
        print(f"{log.conversation_turn}. [{direction}] {log.message_content[:100]}")
