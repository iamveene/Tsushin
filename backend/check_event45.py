from db import get_engine, get_session
from models import ScheduledEvent
import json

engine = get_engine('./data/agent.db')

with get_session(engine) as db:
    event = db.query(ScheduledEvent).filter(ScheduledEvent.id == 45).first()

    if event:
        print(f"Event ID: {event.id}")
        print(f"Status: {event.status}")
        print(f"Scheduled at: {event.scheduled_at}")
        print(f"Executed at: {event.last_executed_at}")

        if event.conversation_state:
            state = json.loads(event.conversation_state) if isinstance(event.conversation_state, str) else event.conversation_state
            print(f"\nConversation History:")
            for msg in state.get('conversation_history', []):
                direction = "AGENT" if msg['sender'] == 'agent' else "USER"
                content = msg['message'][:150]
                print(f"  Turn {msg['turn']} [{direction}]: {content}")
    else:
        print("Event 45 not found")
