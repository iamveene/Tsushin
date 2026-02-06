from db import get_engine, get_session
from models import ScheduledEvent
from datetime import datetime

engine = get_engine('./data/agent.db')

with get_session(engine) as db:
    # Get all ACTIVE conversation events
    active_convs = db.query(ScheduledEvent).filter(
        ScheduledEvent.event_type == 'CONVERSATION',
        ScheduledEvent.status == 'ACTIVE'
    ).all()

    print(f"Found {len(active_convs)} active conversations")

    for event in active_convs:
        print(f"Completing Event {event.id}")
        event.status = 'COMPLETED'
        event.completed_at = datetime.utcnow()

    db.commit()
    print(f"✅ Completed {len(active_convs)} conversations")
