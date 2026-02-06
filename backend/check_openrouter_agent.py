#!/usr/bin/env python3
"""Check OpenRouter agent configuration."""

import sys
from pathlib import Path

# Ensure we're in the backend directory
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

# Use the app's existing database connection
from db import get_db
from models import Agent, Persona, Contact

# Get database session
db = next(get_db())

# Find OpenRouter agents
agents = db.query(Agent).filter(Agent.model_provider == 'openrouter').all()

print(f'Found {len(agents)} OpenRouter agent(s)\n')

for agent in agents:
    # Get agent name from Contact
    contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()
    agent_name = contact.friendly_name if contact else f"Agent {agent.id}"

    print('=' * 80)
    print(f'Agent: {agent_name}')
    print('=' * 80)
    print(f'ID: {agent.id}')
    print(f'Provider: {agent.model_provider}')
    print(f'Model: {agent.model_name}')
    print(f'Persona ID: {agent.persona_id}')
    print(f'Enabled Channels: {agent.enabled_channels}')
    print(f'\nSystem Prompt:')
    print('-' * 80)
    print(agent.system_prompt)
    print('-' * 80)

    if agent.persona_id:
        persona = db.query(Persona).filter(Persona.id == agent.persona_id).first()
        if persona:
            print(f'\n--- PERSONA: {persona.name} ---')
            print(f'Role: {persona.role}')
            print(f'Role Description: {persona.role_description}')
            print(f'\nCustom Tone:')
            print('-' * 80)
            print(persona.custom_tone)
            print('-' * 80)
    print('\n')

db.close()
