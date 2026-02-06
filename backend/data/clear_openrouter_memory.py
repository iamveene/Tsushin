#!/usr/bin/env python3
"""Clear memory and facts for OpenRouter agent."""

import sys
import os
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, '/app')

# Initialize database connection
from db import get_engine, get_session
from models import Agent, Memory, SemanticKnowledge, Contact

# Get database path from environment (default to agent.db where agent table is stored)
db_path = os.getenv('DATABASE_PATH', '/app/data/agent.db')
engine = get_engine(db_path)

# Get session from context manager
from sqlalchemy.orm import sessionmaker
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

try:
    # Find OpenRouter agent
    agent = db.query(Agent).filter(Agent.model_provider == 'openrouter').first()

    if agent:
        # Get agent name from Contact
        contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()
        agent_name = contact.friendly_name if contact else f"Agent {agent.id}"

        print(f'Found OpenRouter agent: ID={agent.id}, Name={agent_name}')

        # Count memory and facts before clearing
        memory_count = db.query(Memory).filter(Memory.agent_id == agent.id).count()
        fact_count = db.query(SemanticKnowledge).filter(SemanticKnowledge.agent_id == agent.id).count()

        print(f'Memory records before: {memory_count}')
        print(f'Semantic knowledge records before: {fact_count}')

        # Clear memory and facts
        deleted_memory = db.query(Memory).filter(Memory.agent_id == agent.id).delete()
        deleted_facts = db.query(SemanticKnowledge).filter(SemanticKnowledge.agent_id == agent.id).delete()
        db.commit()

        print(f'✅ Deleted {deleted_memory} memory records')
        print(f'✅ Deleted {deleted_facts} semantic knowledge records')
        print(f'✅ Successfully cleared all memory and facts for {agent_name}')
    else:
        print('❌ No OpenRouter agent found')
        # List agents for debugging
        all_agents = db.query(Agent).all()
        print(f'\nAvailable agents ({len(all_agents)}):')
        for a in all_agents[:10]:
            contact = db.query(Contact).filter(Contact.id == a.contact_id).first()
            name = contact.friendly_name if contact else f"Agent {a.id}"
            print(f'  - ID={a.id}, Provider={a.model_provider}, Name={name}')

finally:
    db.close()
