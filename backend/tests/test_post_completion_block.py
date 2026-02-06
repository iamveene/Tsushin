"""
Tests for post-completion blocking logic.
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db import Base
import logging

from agent.router import AgentRouter
from models import ConversationThread


def _build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_blocks_recent_completed_thread():
    session = _build_session()
    try:
        thread = ConversationThread(
            recipient="156186787733722@lid",
            status="completed",
            current_turn=5,
            max_turns=20,
            agent_id=1,
            completed_at=datetime.utcnow()
        )
        session.add(thread)
        session.commit()

        router = AgentRouter.__new__(AgentRouter)
        router.db = session
        router.logger = logging.getLogger("test")
        assert router._should_block_post_completion("156186787733722@lid") is True
    finally:
        session.close()


def test_does_not_block_old_completed_thread():
    session = _build_session()
    try:
        thread = ConversationThread(
            recipient="156186787733722@lid",
            status="completed",
            current_turn=5,
            max_turns=20,
            agent_id=1,
            completed_at=datetime.utcnow() - timedelta(minutes=10)
        )
        session.add(thread)
        session.commit()

        router = AgentRouter.__new__(AgentRouter)
        router.db = session
        router.logger = logging.getLogger("test")
        assert router._should_block_post_completion("156186787733722@lid") is False
    finally:
        session.close()
