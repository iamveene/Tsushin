from db import get_engine, get_session
from models import ScheduledEvent
from datetime import datetime

engine = get_engine('./data/agent.db')

with get_session(engine) as db:
    event = db.query(ScheduledEvent).filter(ScheduledEvent.id == 41).first()

    if not event:
        print("Event 41 not found")
    else:
        print(f"Event ID: {event.id}")
        print(f"Status: {event.status}")
        print(f"Scheduled at: {event.scheduled_at}")
        print(f"Next execution at: {event.next_execution_at}")
        print(f"Type: {type(event.next_execution_at)}")
        print(f"Current UTC: {datetime.utcnow()}")
        print(f"Comparison: {event.next_execution_at} <= {datetime.utcnow()} = {event.next_execution_at <= datetime.utcnow()}")
