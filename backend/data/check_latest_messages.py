#!/usr/bin/env python3
import sys
import json
sys.path.insert(0, '/app')
from db import get_engine
from models import Agent, Memory
from sqlalchemy.orm import sessionmaker

db_path = '/app/data/agent.db'
engine = get_engine(db_path)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

try:
    # Get agent 21 memory
    memory = db.query(Memory).filter(Memory.agent_id == 21).first()

    if memory and memory.messages_json:
        messages = memory.messages_json
        print(f"Total messages: {len(messages)}")
        print("\nLast 3 messages:")
        print("="*80)
        for msg in messages[-3:]:
            print(f"\n[{msg['role'].upper()}] {msg.get('timestamp', 'N/A')}")
            print(f"{msg['content'][:200]}...")
            print("-"*80)
    else:
        print("No messages found")

finally:
    db.close()
