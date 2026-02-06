"""
Tests for contamination handling in SchedulerService.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db import Base
from scheduler.scheduler_service import SchedulerService


def _build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_sanitize_ai_reply_blocks_contamination():
    session = _build_session()
    try:
        scheduler = SchedulerService(session)
        contaminated = "@movl: Posso ajudar?"
        assert scheduler._sanitize_ai_reply(1, contaminated) == ""
    finally:
        session.close()
