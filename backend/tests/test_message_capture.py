"""
Tests for conversation message capture persistence.
"""

import os
import sys
import logging
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import Base
from agent.router import AgentRouter
from models import ConversationThread


def _build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


@pytest.mark.asyncio
async def test_conversation_history_persists_with_message_id():
    session = _build_session()
    try:
        thread = ConversationThread(
            recipient="156186787733722@lid",
            status="active",
            current_turn=0,
            max_turns=1,
            agent_id=1
        )
        session.add(thread)
        session.commit()
        session.refresh(thread)

        router = AgentRouter.__new__(AgentRouter)
        router.db = session
        router.logger = logging.getLogger("test")

        result = await router._process_conversation_thread_reply(
            thread=thread,
            sender="156186787733722@lid",
            message_content="Mensagem do bot",
            message_id="msg-1"
        )
        assert result["status"] == "max_turns_reached"

        session.refresh(thread)
        assert len(thread.conversation_history) == 1
        assert thread.conversation_history[0]["message_id"] == "msg-1"

        duplicate = await router._process_conversation_thread_reply(
            thread=thread,
            sender="156186787733722@lid",
            message_content="Mensagem do bot",
            message_id="msg-1"
        )
        assert duplicate["status"] == "duplicate_message"
        session.refresh(thread)
        assert len(thread.conversation_history) == 1
    finally:
        session.close()
