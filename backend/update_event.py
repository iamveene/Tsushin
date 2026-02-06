from db import get_engine, get_session
from models import ScheduledEvent
from datetime import datetime

engine = get_engine('./data/agent.db')

with get_session(engine) as db:
    event = db.query(ScheduledEvent).filter(ScheduledEvent.id == 41).first()

    if not event:
        print("Event 41 not found")
    else:
        # Set next_execution_at to 11:16am BRT = 14:16 UTC
        next_exec_utc = datetime(2025, 10, 6, 14, 16, 0)
        event.next_execution_at = next_exec_utc
        db.commit()
        print(f"Updated event 41 next_execution_at to {next_exec_utc} UTC (11:16am BRT)")
