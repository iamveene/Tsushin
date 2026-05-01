import logging
import sys
import types
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

if "docker" not in sys.modules:
    docker_stub = types.ModuleType("docker")
    docker_stub.DockerClient = object
    docker_stub.errors = types.SimpleNamespace(NotFound=Exception)
    sys.modules["docker"] = docker_stub

import models_rbac  # noqa: F401 - registers RBAC relationships for Base metadata
from models import Base, Agent, Contact, ContactChannelMapping, UserAgentSession
from agent.contact_resolver import ContactResolver
from agent.contact_service_cached import CachedContactService


def _install_router_import_stubs():
    """Keep this focused router test independent from optional runtime packages."""
    dummy_modules = {
        "agent.agent_service": {
            "AgentService": type("AgentService", (), {"__init__": lambda self, *args, **kwargs: None}),
        },
        "agent.memory": {},
        "agent.memory.multi_agent_memory": {
            "MultiAgentMemoryManager": type("MultiAgentMemoryManager", (), {"__init__": lambda self, *args, **kwargs: None}),
        },
        "agent.memory.tool_output_buffer": {
            "get_tool_output_buffer": lambda: None,
        },
        "mcp_sender": {
            "MCPSender": type("MCPSender", (), {"__init__": lambda self, *args, **kwargs: None}),
        },
        "agent.skills": {
            "get_skill_manager": lambda *args, **kwargs: types.SimpleNamespace(registry={}),
            "InboundMessage": type("InboundMessage", (), {}),
        },
        "mcp_reader.media_downloader": {
            "MediaDownloader": type("MediaDownloader", (), {"__init__": lambda self, *args, **kwargs: None}),
        },
        "analytics.token_tracker": {
            "TokenTracker": type("TokenTracker", (), {"__init__": lambda self, *args, **kwargs: None}),
        },
        "services.slash_command_service": {
            "SlashCommandService": type("SlashCommandService", (), {}),
        },
        "services.group_sender_resolver": {
            "GroupSenderResolver": type("GroupSenderResolver", (), {}),
        },
        "services.watcher_activity_service": {
            "emit_agent_processing_async": lambda *args, **kwargs: None,
        },
        "agent.utils": {
            "summarize_tool_result": lambda result: str(result),
        },
    }

    for module_name, attributes in dummy_modules.items():
        module = types.ModuleType(module_name)
        for attribute_name, attribute_value in attributes.items():
            setattr(module, attribute_name, attribute_value)
        if module_name == "agent.memory":
            module.__path__ = []
        sys.modules.setdefault(module_name, module)


_install_router_import_stubs()
from agent.router import AgentRouter


TENANT_ID = "tenant-a"
PHONE = "5527999616279"
LID = "259029628641423"


def _build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Contact.__table__,
            ContactChannelMapping.__table__,
            Agent.__table__,
            UserAgentSession.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    return Session()


def _build_router(session, tenant_id=TENANT_ID, mcp_instance_id=1):
    router = object.__new__(AgentRouter)
    router.db = session
    router.config = {"memory_size": 10}
    router.logger = logging.getLogger(__name__)
    router.tenant_id = tenant_id
    router.mcp_instance_id = mcp_instance_id
    router.telegram_instance_id = None
    router.webhook_instance_id = None
    router.contact_service = CachedContactService(session, tenant_id=tenant_id)
    return router


def _seed_contact(session):
    contact = Contact(
        friendly_name="Vini",
        phone_number=f"+{PHONE}",
        whatsapp_id=LID,
        role="user",
        is_active=True,
        is_dm_trigger=True,
        tenant_id=TENANT_ID,
    )
    session.add(contact)
    session.flush()

    session.add_all([
        ContactChannelMapping(
            contact_id=contact.id,
            channel_type="phone",
            channel_identifier=PHONE,
            tenant_id=TENANT_ID,
        ),
        ContactChannelMapping(
            contact_id=contact.id,
            channel_type="whatsapp",
            channel_identifier=LID,
            tenant_id=TENANT_ID,
        ),
    ])
    session.flush()
    return contact


def _seed_agent(session, name, is_default=False):
    agent_contact = Contact(
        friendly_name=name,
        role="agent",
        is_active=True,
        is_dm_trigger=False,
        tenant_id=TENANT_ID,
    )
    session.add(agent_contact)
    session.flush()

    agent = Agent(
        contact_id=agent_contact.id,
        system_prompt=f"You are {name}.",
        keywords=[],
        enabled_channels=["whatsapp"],
        is_active=True,
        is_default=is_default,
        tenant_id=TENANT_ID,
        model_provider="openai",
        model_name="gpt-test",
    )
    session.add(agent)
    session.flush()
    return agent


def _seed_world(session):
    user_contact = _seed_contact(session)
    movl = _seed_agent(session, "movl", is_default=True)
    transcript = _seed_agent(session, "Transcript")
    session.commit()
    return user_contact, movl, transcript


def test_whatsapp_lid_audio_uses_newer_phone_session_and_syncs_aliases():
    session = _build_session()
    try:
        _, movl, transcript = _seed_world(session)
        old = datetime.utcnow() - timedelta(days=3)
        new = datetime.utcnow()
        session.add_all([
            UserAgentSession(
                user_identifier=LID,
                agent_id=movl.id,
                created_at=old,
                updated_at=old,
            ),
            UserAgentSession(
                user_identifier=PHONE,
                agent_id=transcript.id,
                created_at=new,
                updated_at=new,
            ),
        ])
        session.commit()

        router = _build_router(session)
        message = {
            "sender": LID,
            "chat_id": f"{LID}@lid",
            "body": "",
            "is_group": False,
            "channel": "whatsapp",
            "media_type": "audio",
        }

        _, agent_id, agent_name = router._select_agent(message, "dm")

        assert agent_id == transcript.id
        assert agent_name == "Transcript"
        assert session.query(UserAgentSession).filter_by(user_identifier=LID).one().agent_id == transcript.id
        assert session.query(UserAgentSession).filter_by(user_identifier=PHONE).one().agent_id == transcript.id
    finally:
        session.close()


def test_whatsapp_phone_text_uses_newer_lid_session_and_syncs_aliases():
    session = _build_session()
    try:
        _, movl, transcript = _seed_world(session)
        old = datetime.utcnow() - timedelta(days=3)
        new = datetime.utcnow()
        session.add_all([
            UserAgentSession(
                user_identifier=PHONE,
                agent_id=movl.id,
                created_at=old,
                updated_at=old,
            ),
            UserAgentSession(
                user_identifier=LID,
                agent_id=transcript.id,
                created_at=new,
                updated_at=new,
            ),
        ])
        session.commit()

        router = _build_router(session)
        message = {
            "sender": PHONE,
            "chat_id": f"{PHONE}@s.whatsapp.net",
            "body": "hello",
            "is_group": False,
            "channel": "whatsapp",
        }

        _, agent_id, agent_name = router._select_agent(message, "dm")

        assert agent_id == transcript.id
        assert agent_name == "Transcript"
        assert session.query(UserAgentSession).filter_by(user_identifier=PHONE).one().agent_id == transcript.id
        assert session.query(UserAgentSession).filter_by(user_identifier=LID).one().agent_id == transcript.id
    finally:
        session.close()


def test_session_aliases_do_not_rewrite_group_chat_keys():
    session = _build_session()
    try:
        contact, _, _ = _seed_world(session)
        router = _build_router(session)
        message = {
            "sender": LID,
            "chat_id": "120363000000000000@g.us",
            "body": "group text",
            "is_group": True,
            "channel": "whatsapp",
        }

        aliases = router._get_direct_message_session_aliases(
            message,
            sender_key=router._get_sender_key(message),
            contact=contact,
        )

        assert aliases == ["120363000000000000@g.us"]
    finally:
        session.close()


def test_memory_key_resolves_phone_and_lid_to_same_contact():
    session = _build_session()
    try:
        contact, _, transcript = _seed_world(session)
        resolver = ContactResolver(session)

        phone_key = resolver.get_memory_key(
            agent_id=transcript.id,
            sender=PHONE,
            whatsapp_id=PHONE,
            tenant_id=TENANT_ID,
        )
        lid_key = resolver.get_memory_key(
            agent_id=transcript.id,
            sender=LID,
            whatsapp_id=LID,
            tenant_id=TENANT_ID,
        )

        assert phone_key == f"agent_{transcript.id}:contact_{contact.id}"
        assert lid_key == f"agent_{transcript.id}:contact_{contact.id}"
        assert phone_key == lid_key
    finally:
        session.close()
