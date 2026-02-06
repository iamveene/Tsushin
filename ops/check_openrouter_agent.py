#!/usr/bin/env python3
"""Check OpenRouter agent configuration."""

import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

# Load environment variables
from dotenv import load_dotenv
env_file = backend_path / ".env"
if env_file.exists():
    load_dotenv(env_file)

db_url = os.getenv('DATABASE_URL')
if not db_url:
    print("ERROR: DATABASE_URL environment variable is required")
    sys.exit(1)
engine = create_engine(db_url)
Session = sessionmaker(bind=engine)
db = Session()

from models import Agent, Persona

# Find OpenRouter agents
agents = db.query(Agent).filter(Agent.model_provider == 'openrouter').all()

print(f'Found {len(agents)} OpenRouter agent(s)\n')

for agent in agents:
    print('=' * 80)
    print(f'Agent: {agent.name}')
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
