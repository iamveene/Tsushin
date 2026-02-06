"""
Tests for contact resolution normalization.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, Contact, ConversationThread
from agent.contact_service_cached import CachedContactService
from mcp_reader.filters import MessageFilter


def _build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_cached_contact_service_normalizes_whatsapp_id():
    session = _build_session()
    try:
        contact = Contact(
            id=1,
            friendly_name="JT",
            phone_number="5511916663866",
            whatsapp_id="156186787733722",
            is_active=True,
            is_dm_trigger=True
        )
        session.add(contact)
        session.commit()

        service = CachedContactService(session)
        resolved = service.identify_sender("156186787733722@lid")

        assert resolved is not None
        assert resolved.friendly_name == "JT"
    finally:
        session.close()


def test_message_filter_detects_active_conversation_for_lid_sender():
    session = _build_session()
    try:
        thread = ConversationThread(
            id=1,
            recipient="156186787733722@lid",
            status="active",
            current_turn=1,
            max_turns=10,
            agent_id=1
        )
        session.add(thread)
        session.commit()

        msg_filter = MessageFilter(
            group_filters=[],
            number_filters=[],
            dm_auto_mode=False,
            contact_service=None,
            db_session=session
        )

        trigger = msg_filter.should_trigger({
            "is_group": False,
            "sender": "156186787733722@lid",
            "body": "Oi"
        })

        assert trigger == "conversation"
    finally:
        session.close()
