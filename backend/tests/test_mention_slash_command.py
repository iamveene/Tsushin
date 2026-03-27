"""
Tests for Feature #11: WhatsApp Group Slash Commands via Agent Mention.

Tests the extract_mention_and_command method in ContactService and
the CachedContactService delegation.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, Contact, Agent
from agent.contact_service import ContactService
from agent.contact_service_cached import CachedContactService


def _build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _seed_agent(session, agent_name="TestBot"):
    """Create an agent contact and associated Agent record."""
    contact = Contact(
        friendly_name=agent_name,
        phone_number="5500000000001",
        whatsapp_id="bot001",
        role="agent",
        is_active=True,
        is_dm_trigger=False,
    )
    session.add(contact)
    session.flush()

    agent = Agent(
        contact_id=contact.id,
        system_prompt="You are a test bot.",
        is_active=True,
        is_default=False,
    )
    session.add(agent)
    session.commit()
    return contact, agent


# ---- ContactService.extract_mention_and_command ----

def test_basic_mention_and_command():
    """@TestBot /help should return (contact, '/help')"""
    session = _build_session()
    contact, _ = _seed_agent(session, "TestBot")
    service = ContactService(session)

    result = service.extract_mention_and_command("@TestBot /help")
    assert result is not None
    agent_contact, cmd = result
    assert agent_contact.id == contact.id
    assert cmd == "/help"
    session.close()


def test_mention_with_tool_command():
    """@TestBot /tool nmap quick_scan target=scanme.nmap.org"""
    session = _build_session()
    contact, _ = _seed_agent(session, "TestBot")
    service = ContactService(session)

    result = service.extract_mention_and_command(
        "@TestBot /tool nmap quick_scan target=scanme.nmap.org"
    )
    assert result is not None
    agent_contact, cmd = result
    assert agent_contact.id == contact.id
    assert cmd == "/tool nmap quick_scan target=scanme.nmap.org"
    session.close()


def test_no_mention_returns_none():
    """/help with no mention should return None."""
    session = _build_session()
    _seed_agent(session, "TestBot")
    service = ContactService(session)

    result = service.extract_mention_and_command("/help")
    assert result is None
    session.close()


def test_mention_without_slash_returns_none():
    """@TestBot hello should return None (no slash command)."""
    session = _build_session()
    _seed_agent(session, "TestBot")
    service = ContactService(session)

    result = service.extract_mention_and_command("@TestBot hello")
    assert result is None
    session.close()


def test_unknown_agent_mention_returns_none():
    """@UnknownBot /help should return None."""
    session = _build_session()
    _seed_agent(session, "TestBot")
    service = ContactService(session)

    result = service.extract_mention_and_command("@UnknownBot /help")
    assert result is None
    session.close()


def test_user_mention_returns_none():
    """@SomeUser /help should return None when SomeUser is a user, not an agent."""
    session = _build_session()
    # Create a user contact (not an agent)
    user_contact = Contact(
        friendly_name="SomeUser",
        phone_number="5500000000002",
        whatsapp_id="user001",
        role="user",
        is_active=True,
        is_dm_trigger=False,
    )
    session.add(user_contact)
    session.commit()

    service = ContactService(session)
    result = service.extract_mention_and_command("@SomeUser /help")
    assert result is None
    session.close()


def test_mention_with_leading_whitespace():
    """Leading whitespace should be stripped."""
    session = _build_session()
    contact, _ = _seed_agent(session, "TestBot")
    service = ContactService(session)

    result = service.extract_mention_and_command("  @TestBot /commands  ")
    assert result is not None
    agent_contact, cmd = result
    assert agent_contact.id == contact.id
    assert cmd == "/commands"
    session.close()


def test_mention_case_insensitive():
    """@testbot /help should match TestBot (case-insensitive)."""
    session = _build_session()
    contact, _ = _seed_agent(session, "TestBot")
    service = ContactService(session)

    result = service.extract_mention_and_command("@testbot /help")
    assert result is not None
    agent_contact, cmd = result
    assert agent_contact.id == contact.id
    session.close()


# ---- CachedContactService delegation ----

def test_cached_service_delegates_extract():
    """CachedContactService should delegate to ContactService."""
    session = _build_session()
    contact, _ = _seed_agent(session, "TestBot")
    cached = CachedContactService(session)

    result = cached.extract_mention_and_command("@TestBot /help")
    assert result is not None
    agent_contact, cmd = result
    assert agent_contact.id == contact.id
    assert cmd == "/help"
    session.close()


def test_slash_in_middle_of_text_not_matched():
    """Text with @ and / but not in @name /cmd pattern should not match."""
    session = _build_session()
    _seed_agent(session, "TestBot")
    service = ContactService(session)

    result = service.extract_mention_and_command("Hey @TestBot check http://example.com")
    assert result is None
    session.close()
