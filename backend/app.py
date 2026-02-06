from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
# MED-004 FIX: Rate limiting for authentication endpoints
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging
import asyncio
from contextlib import asynccontextmanager
import os
import sys
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker, Session

# Load environment
load_dotenv()

# Import settings (after dotenv loads)
import settings

# Configure stdout/stderr for UTF-8 (Windows compatibility)
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

# Setup logging with TSN configuration (UTF-8 encoding for Unicode support)
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s - [%(name)s] - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(settings.LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)
logger.info(f"Starting {settings.SERVICE_NAME} v{settings.SERVICE_VERSION}")

from db import get_engine, init_database
from models import Config
from mcp_reader.watcher import MCPWatcher
from mcp_reader.filters import MessageFilter
from agent.router import AgentRouter
from api.routes import router, set_engine, get_db
from api.routes_api_keys import router as api_keys_router, set_engine as set_api_keys_engine
from api.routes_knowledge import router as knowledge_router, set_engine as set_knowledge_engine
from api.routes_knowledge_base import router as knowledge_base_router, set_engine as set_knowledge_base_engine
from api.routes_shared_memory import router as shared_memory_router, set_engine as set_shared_memory_engine
from api.routes_memory import router as memory_router, set_engine as set_memory_engine
from api.routes_skills import router as skills_router, set_engine as set_skills_engine
from api.routes_sandboxed_tools import router as sandboxed_tools_router, set_engine as set_sandboxed_tools_engine
from api.routes_agents import router as agents_router, set_engine as set_agents_engine
# Phase 5.1 Persona System - Import added last to avoid conflicts
from api.routes_personas import router as personas_router, set_engine as set_personas_engine
# Prompts & Patterns Admin UI
from api.routes_prompts import router as prompts_router, set_engine as set_prompts_engine
# Phase 6.4 Scheduler System
from api.routes_scheduler import router as scheduler_router, set_engine as set_scheduler_engine
from scheduler.worker import start_scheduler_worker, stop_scheduler_worker
# Phase 6.6 Multi-Step Flows
from api.routes_flows import router as flows_router, set_engine as set_flows_engine
# Phase 6.11 Scheduled Flow Executor
# Phase 6.11.2 WebSocket Manager
from websocket_manager import manager as ws_manager
from flows.scheduled_flow_executor import start_flow_executor, stop_flow_executor
# Phase 6.11.3 Cache Management API
from api.routes_cache import router as cache_router
# Hub Integration System (Asana, Slack, etc.)
from api.routes_hub import router as hub_router
# Shell Skill (Phase 18: Remote Command Execution)
from api.routes_shell import router as shell_router
from api.shell_approval_routes import router as shell_approval_router, set_engine as set_shell_approval_engine
# Shell Skill WebSocket (Phase 18.4: WebSocket C2)
from api.shell_websocket import router as shell_ws_router, set_engine as set_shell_ws_engine
# Watcher Activity WebSocket (Phase 8: Graph View Real-time Activity)
from api.watcher_activity_websocket import router as watcher_activity_ws_router
from services.beacon_connection_service import start_beacon_service, stop_beacon_service
# Google Integrations (Gmail, Calendar)
from api.routes_google import router as google_router
# OAuth Token Refresh Worker
from hub.oauth_token_refresh_worker import start_oauth_refresh_worker, stop_oauth_refresh_worker
# Phase 19: Stale Flow Cleanup (BUG-FLOWS-002)
from flows.stale_flow_cleanup import start_stale_flow_cleanup, stop_stale_flow_cleanup
# Phase 7.2: Token Analytics
from api.routes_analytics import router as analytics_router
# Phase 7.6.3: Authentication
from auth_routes import router as auth_router
# Phase 7.6.4: Protected Endpoints (Example)
from api.routes_agents_protected import router as agents_protected_router
# Phase 8: MCP Instance Management
from api.routes_mcp_instances import router as mcp_instances_router
# Playground Feature
from api.routes_playground import router as playground_router
# Phase 14.4: Projects
from api.routes_projects import router as projects_router
# Phase 16: Slash Commands
from api.routes_commands import router as commands_router
from api.routes_user_contact_mapping import router as user_contact_mapping_router
# Phase 7.9: RBAC & Multi-tenancy
from api.routes_tenants import router as tenants_router
from api.routes_team import router as team_router
# Plans Management
from api.routes_plans import router as plans_router
# SSO Configuration
from api.routes_sso_config import router as sso_config_router
# Global User Management
from api.routes_global_users import router as global_users_router
# Toolbox Container Management (Custom Tools)
from api.routes_toolbox import router as toolbox_router
# Skill Integrations (Provider Configuration)
from api.routes_skill_integrations import router as skill_integrations_router, set_engine as set_skill_integrations_engine
# Model Pricing (Cost Estimation Settings)
from api.routes_model_pricing import router as model_pricing_router
# Phase 10.1.1: Telegram Integration
from api.routes_telegram_instances import router as telegram_instances_router
# Phase 17: System AI Configuration
from api.routes_system_ai import router as system_ai_router
# Phase 20: Sentinel Security Agent
from api.routes_sentinel import router as sentinel_router, set_engine as set_sentinel_engine
from api.routes_sentinel_exceptions import router as sentinel_exceptions_router, set_engine as set_sentinel_exceptions_engine
# MCP Health Monitor Service (auto-recovery for keepalive timeouts)
from services.mcp_health_monitor import MCPHealthMonitorService
from services.mcp_container_manager import MCPContainerManager

# Global engine and watcher
engine = None
watcher = None  # Legacy: single watcher (deprecated)
watchers = {}  # Phase 8: Multiple watchers (dict: instance_id -> watcher)
watcher_task = None  # Legacy: single watcher task (deprecated)
watcher_tasks = {}  # Phase 8: Multiple watcher tasks (dict: instance_id -> task)
flow_executor_task = None  # Phase 6.11

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    global engine, watcher, watcher_task, watchers, watcher_tasks, flow_executor_task

    # Initialize database
    engine = get_engine(os.getenv("INTERNAL_DB_PATH"))
    init_database(engine)
    set_engine(engine)

    # Phase 7.6.3: Set global engine for auth routes
    from db import set_global_engine
    set_global_engine(engine)
    set_api_keys_engine(engine)
    set_knowledge_engine(engine)
    set_knowledge_base_engine(engine)
    set_shared_memory_engine(engine)
    set_memory_engine(engine)
    set_skills_engine(engine)
    set_sandboxed_tools_engine(engine)
    set_agents_engine(engine)
    set_personas_engine(engine)  # Phase 5.1
    set_prompts_engine(engine)  # Prompts & Patterns Admin UI

    # Hub Integration System
    from api.routes_hub import set_engine as set_hub_engine
    set_hub_engine(engine)

    # Shell Skill (Phase 18)
    from api.routes_shell import set_engine as set_shell_engine
    set_shell_engine(engine)
    set_shell_ws_engine(engine)  # Phase 18.4: Shell WebSocket C2
    # Note: watcher_activity_ws uses JWT token auth, no engine needed
    set_shell_approval_engine(engine)  # Phase 5: Shell Approval Workflow
    set_scheduler_engine(engine)  # Phase 6.4
    set_flows_engine(engine)  # Phase 6.6
    set_skill_integrations_engine(engine)  # Skill Integrations

    # Phase 7.2: Token Analytics
    from api.routes_analytics import set_engine as set_analytics_engine
    set_analytics_engine(engine)

    # Phase 20: Sentinel Security Agent
    set_sentinel_engine(engine)
    set_sentinel_exceptions_engine(engine)

    logging.info("Database initialized")

    # Migration: Ensure sandboxed_tools skill exists for agents with tool assignments
    try:
        MigrationSession = sessionmaker(bind=engine)
        migration_db = MigrationSession()
        from services.sandboxed_tool_seeding import ensure_sandboxed_tools_skill, update_existing_tools
        created = ensure_sandboxed_tools_skill(migration_db)
        if created > 0:
            print(f"📦 Migration: Created sandboxed_tools skill for {created} agents")

        # Update existing tools from manifests (picks up template/prompt changes)
        from models_rbac import Tenant
        tenants = migration_db.query(Tenant).all()
        for tenant in tenants:
            updated = update_existing_tools(tenant.id, migration_db)
            if updated:
                print(f"📦 Updated {len(updated)} tool manifests for tenant {tenant.id}")

        migration_db.close()
    except Exception as e:
        logging.error(f"Sandboxed tools skill migration failed: {e}")

    # Start MCP watcher
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        config = session.query(Config).first()

        if config and config.messages_db_path and os.path.exists(config.messages_db_path):
            # Parse JSON fields
            import json as json_lib
            contact_mappings = json_lib.loads(config.contact_mappings) if config.contact_mappings else {}
            group_keywords = json_lib.loads(config.group_keywords) if config.group_keywords else []
            # Note: enabled_tools and enable_google_search deprecated - using Skills system

            # Phase 6.11.3: Initialize CachedContactService for faster lookups
            from agent.contact_service_cached import CachedContactService
            contact_service = CachedContactService(session)

            # Store CachedContactService in app.state for cache management
            # This allows routes to clear cache after contact updates
            app.state.contact_service = contact_service

            # FIX: Collect group filters from ALL active agents (not just global config)
            # This ensures newly created agents with per-agent filters work correctly
            from models import Agent
            all_group_filters = set(config.group_filters or [])  # Start with global filters

            # Add per-agent group filters
            active_agents = session.query(Agent).filter(Agent.is_active == True).all()
            for agent in active_agents:
                if agent.trigger_group_filters:
                    agent_filters = json_lib.loads(agent.trigger_group_filters) if isinstance(agent.trigger_group_filters, str) else agent.trigger_group_filters
                    if agent_filters:
                        all_group_filters.update(agent_filters)

            logging.info(f"Watcher initialized with group filters: {sorted(all_group_filters)}")

            message_filter = MessageFilter(
                group_filters=list(all_group_filters),
                number_filters=config.number_filters or [],
                agent_number=config.agent_number,
                dm_auto_mode=config.dm_auto_mode,
                agent_phone_number=config.agent_phone_number,
                agent_name=config.agent_name,
                group_keywords=group_keywords,
                contact_service=contact_service,  # Phase 4.2
                db_session=session  # Phase 6.4 Week 3: For checking active conversations
            )

            config_dict = {
                "model_provider": config.model_provider,
                "model_name": config.model_name,
                "system_prompt": config.system_prompt,
                "memory_size": config.memory_size,
                "contact_mappings": contact_mappings,
                "maintenance_mode": config.maintenance_mode,
                "maintenance_message": config.maintenance_message,
                "context_message_count": config.context_message_count,
                "context_char_limit": config.context_char_limit,
                # Phase 4.1: Semantic search
                "enable_semantic_search": getattr(config, "enable_semantic_search", False),
                "semantic_search_results": getattr(config, "semantic_search_results", 5),
                "semantic_similarity_threshold": getattr(config, "semantic_similarity_threshold", 0.3)
            }

            # Create MCP reader for context fetching
            from mcp_reader.sqlite_reader import MCPDatabaseReader
            mcp_reader = MCPDatabaseReader(config.messages_db_path, contact_mappings=contact_mappings)

            agent_router = AgentRouter(session, config_dict, mcp_reader=mcp_reader)

            # LEGACY: Single watcher disabled - now using Phase 8 multi-watcher architecture
            # watcher = MCPWatcher(
            #     db_path=config.messages_db_path,
            #     message_filter=message_filter,
            #     on_message_callback=agent_router.route_message,
            #     poll_interval_ms=settings.POLL_INTERVAL_MS,
            #     contact_mappings=contact_mappings,
            #     db_session=session
            # )
            # app.state.watcher = watcher
            # app.state.watcher_session = session
            # watcher_task = asyncio.create_task(watcher.start())

            logging.info("Legacy single watcher disabled - using Phase 8 multi-watcher")
        else:
            logging.warning("Legacy MCP database path not configured (expected - using Phase 8 multi-watcher)")

    except Exception as e:
        logging.error(f"Error starting watcher: {e}", exc_info=True)

    # Phase 8: Start watchers for all active MCP instances
    try:
        from models import WhatsAppMCPInstance, Agent
        import json as json_lib

        # Query active MCP instances
        # Query active MCP instances
        mcp_instances = session.query(WhatsAppMCPInstance).filter(
            WhatsAppMCPInstance.status.in_(["running", "starting"])
        ).all()

        # Use print for startup logs (logging.info doesn't show due to uvicorn config override)
        print(f"📊 Found {len(mcp_instances)} active MCP instances")
        for inst in mcp_instances:
            print(f"  - Instance {inst.id}: {inst.phone_number} ({inst.status}, type={inst.instance_type})")

        # Start a watcher for each instance
        for instance in mcp_instances:
            try:
                print(f"🔄 Processing instance {instance.id} ({instance.instance_type})...")

                # Check if messages DB exists
                if not os.path.exists(instance.messages_db_path):
                    print(f"❌ Messages DB not found for instance {instance.id}: {instance.messages_db_path}")
                    continue

                print(f"✅ Messages DB exists for instance {instance.id}")

                # Get config for this instance
                config = session.query(Config).first()
                if not config:
                    logging.warning(f"No config found, skipping instance {instance.id}")
                    continue

                # Parse JSON fields
                contact_mappings = json_lib.loads(config.contact_mappings) if config.contact_mappings else {}
                group_keywords = json_lib.loads(config.group_keywords) if config.group_keywords else []

                # Initialize CachedContactService (reuse existing if available)
                from agent.contact_service_cached import CachedContactService
                if not hasattr(app.state, 'contact_service'):
                    contact_service = CachedContactService(session)
                    app.state.contact_service = contact_service
                else:
                    contact_service = app.state.contact_service

                # Collect group filters from active agents for this tenant
                all_group_filters = set(config.group_filters or [])
                active_agents = session.query(Agent).filter(
                    Agent.is_active == True,
                    Agent.tenant_id == instance.tenant_id
                ).all()

                for agent in active_agents:
                    if agent.trigger_group_filters:
                        agent_filters = json_lib.loads(agent.trigger_group_filters) if isinstance(agent.trigger_group_filters, str) else agent.trigger_group_filters
                        if agent_filters:
                            all_group_filters.update(agent_filters)

                # Create message filter
                # SAFETY FIX: Force dm_auto_mode=False for QA/User Phone instance (Instance 25 or matching phone)
                # This ensures the bot never auto-replies to DMs on the user's personal phone, even if global setting is ON.
                print(f"📋 Checking instance {instance.id} (phone: {instance.phone_number})")
                # Check if this is a QA/testing instance using env var
                qa_phone = os.getenv('QA_PHONE_NUMBER', '')
                is_qa_instance = (str(instance.id) == "25" or (qa_phone and qa_phone in str(instance.phone_number)))
                effective_dm_mode = False if is_qa_instance else config.dm_auto_mode

                if is_qa_instance:
                    print(f"🔒 ENFORCING SAFE MODE (dm_auto_mode=False) for QA/User instance {instance.id}")
                else:
                    print(f"Normal mode for instance {instance.id} (dm_auto_mode={effective_dm_mode})")

                message_filter = MessageFilter(
                    group_filters=list(all_group_filters),
                    number_filters=config.number_filters or [],
                    agent_number=config.agent_number,
                    dm_auto_mode=effective_dm_mode,
                    agent_phone_number=instance.phone_number,  # Use instance phone number
                    agent_name=config.agent_name,
                    group_keywords=group_keywords,
                    contact_service=contact_service,
                    db_session=session
                )

                # Create config dict
                # Note: enabled_tools and enable_google_search have been deprecated - using Skills system instead
                config_dict = {
                    "model_provider": config.model_provider,
                    "model_name": config.model_name,
                    "system_prompt": config.system_prompt,
                    "memory_size": config.memory_size,
                    "contact_mappings": contact_mappings,
                    "maintenance_mode": config.maintenance_mode,
                    "maintenance_message": config.maintenance_message,
                    "context_message_count": config.context_message_count,
                    "context_char_limit": config.context_char_limit,
                    "enable_semantic_search": getattr(config, "enable_semantic_search", False),
                    "semantic_search_results": getattr(config, "semantic_search_results", 5),
                    "semantic_similarity_threshold": getattr(config, "semantic_similarity_threshold", 0.3)
                }

                # CRITICAL SAFETY CHECK: Only create agent router for AGENT instances
                # TESTER instances should NEVER have an agent router - they are for QA/testing only
                if instance.instance_type == "tester":
                    print(f"⚠️  SKIPPING watcher for TESTER instance {instance.id} - tester instances should NOT process messages with agent")
                    continue

                print(f"🚀 Creating watcher for AGENT instance {instance.id}...")

                # Create MCP reader - prefer HTTP API over SQLite to bypass Docker filesystem sync issues
                # The API reader fetches messages directly from the MCP container's HTTP endpoint,
                # which is more reliable than reading from bind-mounted SQLite files on Docker Desktop macOS
                from mcp_reader.api_reader import MCPAPIReader
                from mcp_reader.sqlite_reader import MCPDatabaseReader

                # Phase Security-1: Pass API secret for authentication
                api_reader = MCPAPIReader(
                    instance.mcp_api_url,
                    contact_mappings=contact_mappings,
                    api_secret=instance.api_secret
                )

                # Check if API is available, fallback to SQLite if not
                print(f"🔍 Checking API availability for instance {instance.id}: {instance.mcp_api_url}")
                if api_reader.is_available():
                    mcp_reader = api_reader
                    print(f"📡 Using HTTP API reader for instance {instance.id} (bypassing filesystem sync)")
                else:
                    mcp_reader = MCPDatabaseReader(instance.messages_db_path, contact_mappings=contact_mappings)
                    print(f"⚠️  Using SQLite reader for instance {instance.id} (API not available)")

                # Create agent router (only for agent instances)
                # Phase 10: Pass mcp_instance_id for channel-based agent filtering
                instance_agent_router = AgentRouter(session, config_dict, mcp_reader=mcp_reader, mcp_instance_id=instance.id)

                # Determine starting timestamp to prevent message replay
                # For NEW instances (created within last 5 minutes), use creation time to skip history sync
                # For EXISTING instances, use None to continue from DB timestamp
                from datetime import datetime, timedelta
                starting_timestamp = None
                if instance.created_at:
                    age_minutes = (datetime.utcnow() - instance.created_at).total_seconds() / 60
                    if age_minutes < 5:
                        # New instance - skip messages older than creation time
                        starting_timestamp = instance.created_at.strftime("%Y-%m-%d %H:%M:%S+00:00")
                        logging.info(f"🆕 Instance {instance.id} is new ({age_minutes:.1f}min old), will skip history sync messages")

                # Create watcher (only for agent instances) with the selected reader
                delay_seconds = getattr(config, "whatsapp_conversation_delay_seconds", None)
                if delay_seconds is None:
                    delay_seconds = settings.WHATSAPP_CONVERSATION_DELAY_SECONDS

                instance_watcher = MCPWatcher(
                    reader=mcp_reader,  # Pass the reader directly (API or SQLite)
                    message_filter=message_filter,
                    on_message_callback=instance_agent_router.route_message,
                    poll_interval_ms=settings.POLL_INTERVAL_MS,
                    contact_mappings=contact_mappings,
                    db_session=session,
                    starting_timestamp=starting_timestamp,
                    whatsapp_conversation_delay_seconds=delay_seconds
                )

                # Start watcher task
                print(f"▶️  Starting watcher task for instance {instance.id}...")
                instance_watcher_task = asyncio.create_task(instance_watcher.start())

                # Store watcher and task
                watchers[instance.id] = instance_watcher
                watcher_tasks[instance.id] = instance_watcher_task

                print(f"✅ MCP Watcher started for AGENT instance {instance.id} (tenant: {instance.tenant_id}, port: {instance.mcp_port})")

            except Exception as instance_error:
                logging.error(f"Error starting watcher for instance {instance.id}: {instance_error}", exc_info=True)

        # Store watchers in app.state for management
        app.state.watchers = watchers
        app.state.watcher_tasks = watcher_tasks

        # Initialize WatcherManager for dynamic watcher lifecycle
        from services.watcher_manager import WatcherManager
        app.state.watcher_manager = WatcherManager(app.state)

        print(f"🎯 Total watchers started: {len(watchers)}")
        print(f"📋 Watcher IDs: {list(watchers.keys())}")
        print("✅ WatcherManager initialized for dynamic instance management")

    except Exception as e:
        logging.error(f"Error starting MCP instance watchers: {e}", exc_info=True)

    # Start MCP Health Monitor Service (auto-recovery for keepalive timeouts)
    mcp_health_monitor = None
    try:
        # Initialize container manager for health checks and restarts
        container_manager = MCPContainerManager()

        # Create health monitor with session factory
        mcp_health_monitor = MCPHealthMonitorService(
            get_db_session=SessionLocal,
            container_manager=container_manager,
            watcher_manager=app.state.watcher_manager if hasattr(app.state, 'watcher_manager') else None,
            on_recovery_triggered=lambda instance_id, reason: logging.info(
                f"🔄 Auto-recovery triggered for MCP instance {instance_id}: {reason}"
            )
        )

        # Start the health monitor
        await mcp_health_monitor.start()
        app.state.mcp_health_monitor = mcp_health_monitor

        logging.info("🏥 MCP Health Monitor Service started (auto-recovery enabled)")

    except Exception as e:
        logging.error(f"Error starting MCP Health Monitor: {e}", exc_info=True)
        # Non-fatal - app can run without health monitor

    # Phase 10.1.1: Initialize Telegram Watcher Manager
    try:
        from services.telegram_watcher_manager import TelegramWatcherManager
        from models import TelegramBotInstance, Agent
        from telegram_integration.sender import TelegramSender
        from services.telegram_bot_service import TelegramBotService
        import json as json_lib

        # Message handler callback for Telegram
        async def handle_telegram_message(message: dict, trigger_type: str):
            """Handle incoming Telegram messages and route to appropriate agent."""
            try:
                # Extract Telegram-specific info
                telegram_id = message.get("telegram_id")
                chat_id = message.get("chat_id")
                telegram_username = message.get("sender_username")
                sender_name = message.get("sender_name")

                # Find which bot instance received this message
                # The chat_id in the callback context should match bot configuration
                # We need to find the agent configured with the matching telegram_integration_id

                # Get session for this request
                request_session = SessionLocal()
                try:
                    # Find agents configured for Telegram with this specific bot
                    # The telegram_instance_id should be passed in message context from watcher
                    telegram_instance_id = message.get("_telegram_instance_id")
                    if not telegram_instance_id:
                        logging.warning("No telegram_instance_id in message context")
                        return

                    # Phase 10.1.1: Auto-populate contact from Telegram message
                    # Get bot instance to determine tenant
                    bot_instance = request_session.query(TelegramBotInstance).get(telegram_instance_id)
                    if bot_instance and telegram_id:
                        from services.contact_auto_populate_service import ContactAutoPopulateService

                        contact_service = ContactAutoPopulateService(request_session)
                        contact = await contact_service.ensure_contact_from_telegram(
                            telegram_id=telegram_id,
                            sender_name=sender_name,
                            telegram_username=telegram_username,
                            tenant_id=bot_instance.tenant_id,
                            user_id=1  # System user
                        )
                        logging.info(f"Contact ensured: {contact.friendly_name} (ID: {contact.id})")
                    elif not telegram_id:
                        logging.warning("No telegram_id in message, skipping contact auto-populate")

                    # Find agent configured with this Telegram bot
                    agents = request_session.query(Agent).filter(
                        Agent.telegram_integration_id == telegram_instance_id,
                        Agent.is_active == True
                    ).all()

                    # Check if telegram is in enabled_channels
                    matching_agents = []
                    for agent in agents:
                        enabled_channels = agent.enabled_channels if isinstance(agent.enabled_channels, list) else (
                            json_lib.loads(agent.enabled_channels) if agent.enabled_channels else []
                        )
                        if "telegram" in enabled_channels:
                            matching_agents.append(agent)

                    # Fallback: if no agents explicitly linked, try default agent for this tenant
                    if not matching_agents and bot_instance:
                        default_agent = request_session.query(Agent).filter(
                            Agent.tenant_id == bot_instance.tenant_id,
                            Agent.is_default == True,
                            Agent.is_active == True
                        ).first()

                        if default_agent:
                            default_channels = default_agent.enabled_channels if isinstance(default_agent.enabled_channels, list) else (
                                json_lib.loads(default_agent.enabled_channels) if default_agent.enabled_channels else []
                            )
                            if "telegram" in default_channels:
                                matching_agents.append(default_agent)
                                logging.info(
                                    f"Using default agent {default_agent.id} as fallback for Telegram instance {telegram_instance_id}"
                                )
                                # Auto-fix: link this instance to the default agent for future messages
                                default_agent.telegram_integration_id = telegram_instance_id
                                request_session.commit()
                                logging.info(
                                    f"Auto-linked Telegram instance {telegram_instance_id} to default agent {default_agent.id}"
                                )

                    if not matching_agents:
                        logging.warning(f"No agent configured for Telegram instance {telegram_instance_id}")
                        return

                    # Use first matching agent (in future could support multiple agents per bot)
                    agent = matching_agents[0]

                    # Get config
                    config = request_session.query(Config).first()
                    if not config:
                        logging.error("No config found")
                        return

                    # Parse JSON fields
                    contact_mappings = json_lib.loads(config.contact_mappings) if config.contact_mappings else {}

                    # Initialize CachedContactService
                    from agent.contact_service_cached import CachedContactService
                    contact_service = CachedContactService(request_session)

                    # Create config dict
                    config_dict = {
                        "model_provider": config.model_provider,
                        "model_name": config.model_name,
                        "system_prompt": config.system_prompt,
                        "memory_size": config.memory_size,
                        "contact_mappings": contact_mappings,
                        "maintenance_mode": config.maintenance_mode,
                        "maintenance_message": config.maintenance_message,
                        "context_message_count": config.context_message_count,
                        "context_char_limit": config.context_char_limit,
                        "enable_semantic_search": getattr(config, "enable_semantic_search", False),
                        "semantic_search_results": getattr(config, "semantic_search_results", 5),
                        "semantic_similarity_threshold": getattr(config, "semantic_similarity_threshold", 0.3)
                    }

                    # Create agent router with telegram_instance_id
                    telegram_router = AgentRouter(
                        request_session,
                        config_dict,
                        mcp_reader=None,
                        telegram_instance_id=telegram_instance_id
                    )

                    # Route message
                    await telegram_router.route_message(message, trigger_type)

                    # Send response if router generated one
                    if hasattr(telegram_router, '_telegram_response'):
                        response_text = telegram_router._telegram_response

                        # Get bot instance for sending
                        bot_instance = request_session.query(TelegramBotInstance).get(telegram_instance_id)
                        if bot_instance:
                            # Decrypt token and send
                            telegram_service = TelegramBotService(request_session)
                            token = telegram_service._decrypt_token(
                                bot_instance.bot_token_encrypted,
                                bot_instance.tenant_id
                            )

                            sender = TelegramSender(token)
                            await sender.send_message(
                                chat_id=int(chat_id),
                                message=response_text
                            )

                finally:
                    request_session.close()

            except Exception as e:
                logging.error(f"Error handling Telegram message: {e}", exc_info=True)

        # Initialize Telegram Watcher Manager
        telegram_watcher_manager = TelegramWatcherManager(
            db_session_factory=SessionLocal,
            message_callback=handle_telegram_message
        )
        app.state.telegram_watcher_manager = telegram_watcher_manager

        # Start watchers for all active Telegram bots
        await telegram_watcher_manager.start_all()

        logging.info("Telegram Watcher Manager initialized")

    except Exception as e:
        logging.error(f"Error initializing Telegram Watcher Manager: {e}", exc_info=True)

    # Start scheduler worker (Phase 6.4) for scheduled_event table
    try:
        start_scheduler_worker(engine, poll_interval_seconds=10)
        logging.info("Scheduler Worker started (polling every 10s)")
    except Exception as e:
        logging.error(f"Error starting scheduler worker: {e}", exc_info=True)

    # Start OAuth token refresh worker (proactive refresh)
    try:
        start_oauth_refresh_worker(
            engine,
            poll_interval_minutes=settings.OAUTH_REFRESH_POLL_MINUTES,
            refresh_threshold_hours=settings.OAUTH_REFRESH_THRESHOLD_HOURS
        )
        logging.info(
            "OAuth Token Refresh Worker started (polling every %s min, threshold %s h)",
            settings.OAUTH_REFRESH_POLL_MINUTES,
            settings.OAUTH_REFRESH_THRESHOLD_HOURS
        )
    except Exception as e:
        logging.error(f"Error starting OAuth token refresh worker: {e}", exc_info=True)

    # Start scheduled flow executor (Phase 6.11) for flow_definition table
    try:
        flow_executor_task = start_flow_executor(session, poll_interval_seconds=10)
        logging.info("Scheduled Flow Executor started (polling every 10s)")
    except Exception as e:
        logging.error(f"Error starting scheduled flow executor: {e}", exc_info=True)

    # Phase 19: Start Stale Flow Cleanup Service (BUG-FLOWS-002)
    try:
        await start_stale_flow_cleanup(
            get_db_session=SessionLocal,
            stale_threshold_seconds=settings.STALE_FLOW_THRESHOLD_SECONDS,
            check_interval_seconds=settings.STALE_FLOW_CHECK_INTERVAL_SECONDS,
            conversation_stale_seconds=settings.STALE_CONVERSATION_THRESHOLD_SECONDS
        )
        logging.info(
            f"Stale Flow Cleanup Service started "
            f"(threshold: {settings.STALE_FLOW_THRESHOLD_SECONDS}s, "
            f"interval: {settings.STALE_FLOW_CHECK_INTERVAL_SECONDS}s)"
        )
    except Exception as e:
        logging.error(f"Error starting stale flow cleanup service: {e}", exc_info=True)

    # Phase 18.4: Start Beacon Connection Service (WebSocket C2 health monitoring)
    try:
        await start_beacon_service(engine)
        logging.info("🐚 Beacon Connection Service started (WebSocket C2 health monitoring)")
    except Exception as e:
        logging.error(f"Error starting Beacon Connection Service: {e}", exc_info=True)

    yield

    # Shutdown
    # Legacy single watcher
    if watcher:
        watcher.stop()
    if watcher_task:
        watcher_task.cancel()
        try:
            await watcher_task
        except asyncio.CancelledError:
            pass

    # Phase 8: Stop all MCP instance watchers
    for instance_id, instance_watcher in watchers.items():
        try:
            instance_watcher.stop()
            logging.info(f"Stopped watcher for instance {instance_id}")
        except Exception as e:
            logging.error(f"Error stopping watcher for instance {instance_id}: {e}")

    for instance_id, instance_task in watcher_tasks.items():
        try:
            instance_task.cancel()
            await instance_task
        except asyncio.CancelledError:
            logging.debug(f"Watcher task for instance {instance_id} cancelled")
        except Exception as e:
            logging.error(f"Error cancelling watcher task for instance {instance_id}: {e}")

    # Phase 10.1.1: Stop Telegram Watcher Manager
    if hasattr(app.state, 'telegram_watcher_manager'):
        try:
            await app.state.telegram_watcher_manager.stop_all()
            logging.info("Telegram Watcher Manager stopped")
        except Exception as e:
            logging.error(f"Error stopping Telegram Watcher Manager: {e}", exc_info=True)

    # Stop MCP Health Monitor Service
    if hasattr(app.state, 'mcp_health_monitor'):
        try:
            await app.state.mcp_health_monitor.stop()
            logging.info("🏥 MCP Health Monitor Service stopped")
        except Exception as e:
            logging.error(f"Error stopping MCP Health Monitor: {e}", exc_info=True)

    # Phase 18.4: Stop Beacon Connection Service
    try:
        await stop_beacon_service()
        logging.info("🐚 Beacon Connection Service stopped")
    except Exception as e:
        logging.error(f"Error stopping Beacon Connection Service: {e}", exc_info=True)

    # Stop scheduler worker (Phase 6.4)
    try:
        stop_scheduler_worker()
    except Exception as e:
        logging.error(f"Error stopping scheduler worker: {e}", exc_info=True)

    # Stop OAuth token refresh worker
    try:
        stop_oauth_refresh_worker()
    except Exception as e:
        logging.error(f"Error stopping OAuth token refresh worker: {e}", exc_info=True)

    # Stop scheduled flow executor (Phase 6.11)
    try:
        stop_flow_executor()
        if flow_executor_task:
            flow_executor_task.cancel()
            try:
                await flow_executor_task
            except asyncio.CancelledError:
                pass
    except Exception as e:
        logging.error(f"Error stopping scheduled flow executor: {e}", exc_info=True)

    # Phase 19: Stop Stale Flow Cleanup Service (BUG-FLOWS-002)
    try:
        await stop_stale_flow_cleanup()
        logging.info("Stale Flow Cleanup Service stopped")
    except Exception as e:
        logging.error(f"Error stopping stale flow cleanup service: {e}", exc_info=True)

    session.close()
    logging.info("Application shutdown")

# Create app
app = FastAPI(title="Agentic WhatsApp Bot", lifespan=lifespan)

# MED-004 FIX: Initialize rate limiter
# Rate limits: login (5/min), signup (3/hr), password reset (3/hr)
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS - Allow all origins for development
# Using wildcard for simplicity - credentials sent via Authorization header
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Must be False when using wildcard
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=86400,  # Cache preflight for 24 hours
)


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses"""
    response = await call_next(request)
    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"
    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"
    # XSS protection (legacy browsers)
    response.headers["X-XSS-Protection"] = "1; mode=block"
    # Referrer policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Permissions policy (disable sensitive features)
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    # Content Security Policy - restrictive but allows API usage
    # Note: Adjust 'self' and add specific domains as needed for production
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' wss: https:; frame-ancestors 'none'"
    return response

# Custom exception handlers to ensure CORS headers are always present
# This fixes issues where HTTPException responses don't include CORS headers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions with CORS headers"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with CORS headers"""
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions with CORS headers"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )

# Include routers
app.include_router(router)
app.include_router(api_keys_router, prefix="/api")
app.include_router(knowledge_router, prefix="/api")
app.include_router(knowledge_base_router, prefix="/api")
app.include_router(shared_memory_router, prefix="/api")
app.include_router(memory_router, prefix="/api")
app.include_router(skills_router, prefix="/api")
app.include_router(sandboxed_tools_router, prefix="/api", tags=["Sandboxed Tools"])
app.include_router(agents_router, prefix="/api")
app.include_router(personas_router)  # Phase 5.1 - Persona API
app.include_router(prompts_router)  # Prompts & Patterns Admin UI
app.include_router(scheduler_router)  # Phase 6.4 - Scheduler API
app.include_router(hub_router, prefix="/api")  # Hub Integration System
app.include_router(shell_router, prefix="/api")  # Shell Skill (Phase 18: Remote Command Execution)
app.include_router(shell_approval_router, prefix="/api")  # Shell Approval Workflow (Phase 5)
app.include_router(shell_ws_router)  # Shell Skill WebSocket (Phase 18.4: WebSocket C2)
app.include_router(watcher_activity_ws_router)  # Watcher Activity WebSocket (Phase 8: Graph View)
app.include_router(google_router, prefix="/api")  # Google Integrations (Gmail, Calendar)
app.include_router(flows_router)  # Phase 6.6 - Multi-Step Flows API
app.include_router(cache_router)  # Phase 6.11.3 - Cache Management API
app.include_router(analytics_router)  # Phase 7.2 - Token Analytics
app.include_router(auth_router)  # Phase 7.6.3 - Authentication
app.include_router(agents_protected_router)  # Phase 7.6.4 - Protected Agents API (Example)
app.include_router(mcp_instances_router)  # Phase 8 - MCP Instance Management
app.include_router(playground_router)  # Playground Feature
app.include_router(projects_router)  # Phase 14.4: Projects
app.include_router(commands_router)  # Phase 16: Slash Commands
app.include_router(user_contact_mapping_router)  # Playground - User Contact Mapping
app.include_router(tenants_router)  # Phase 7.9 - Tenant Management
app.include_router(team_router)  # Phase 7.9 - Team Management
app.include_router(plans_router)  # Plans Management
app.include_router(sso_config_router)  # SSO Configuration
app.include_router(global_users_router)  # Global User Management
app.include_router(toolbox_router)  # Toolbox Container Management (Custom Tools)
app.include_router(skill_integrations_router, prefix="/api")  # Skill Integrations (Provider Configuration)
app.include_router(model_pricing_router)  # Model Pricing (Cost Estimation Settings)
app.include_router(telegram_instances_router)  # Phase 10.1.1: Telegram Integration
app.include_router(system_ai_router)  # Phase 17: System AI Configuration
app.include_router(sentinel_router, prefix="/api")  # Phase 20: Sentinel Security Agent
app.include_router(sentinel_exceptions_router, prefix="/api")  # Phase 20 Enhancement: Sentinel Exceptions

# Phase 6.11.2: WebSocket endpoint for real-time updates
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await ws_manager.connect(websocket)
    try:
        # Keep connection alive and handle heartbeats
        while True:
            data = await websocket.receive_text()
            # Echo back heartbeat
            if data.strip() == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        ws_manager.disconnect(websocket)

# Phase 14.9: WebSocket endpoint for Playground streaming v4
# Phase SEC-002: Fixed token exposure in query parameters (HIGH-001)
@app.websocket("/ws/playground")
async def playground_websocket_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
    """
    WebSocket endpoint for Playground real-time streaming.

    Supports token-by-token streaming from LLM providers.

    Security: Token is sent in first message after connection (not in URL query params)
    to prevent exposure in browser history, server logs, and referrer headers.
    """
    from fastapi import Query
    from auth_service import AuthService
    from services.playground_websocket_service import PlaygroundWebSocketService
    import json

    user_id = None

    try:
        # CRITICAL: Accept connection FIRST (before auth)
        # FastAPI middleware rejects WebSocket with 403 if we don't accept immediately
        await websocket.accept()
        logger.info("WebSocket connection accepted, waiting for auth message...")

        # HIGH-001 FIX: Support both first-message auth (secure) and query param auth (legacy)
        # New clients send token in first message; old clients may still use query params
        query_params = dict(websocket.query_params)
        token = query_params.get("token")

        if token:
            # Legacy mode: token in query params (will be deprecated)
            logger.warning("WebSocket using legacy query param auth (insecure) - please update client")
        else:
            # Secure mode: wait for auth message with token
            logger.info("Waiting for auth message...")
            try:
                # Wait for first message (should be auth)
                auth_data = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
                auth_message = json.loads(auth_data)

                if auth_message.get("type") != "auth":
                    logger.error(f"WebSocket rejected: First message must be auth, got: {auth_message.get('type')}")
                    await websocket.close(code=4001, reason="First message must be auth type")
                    return

                token = auth_message.get("token")
                if not token:
                    logger.error("WebSocket rejected: Auth message missing token")
                    await websocket.close(code=4001, reason="Missing token in auth message")
                    return

                logger.info("Received auth token via secure first-message method")

            except asyncio.TimeoutError:
                logger.error("WebSocket rejected: Auth timeout")
                await websocket.close(code=4001, reason="Authentication timeout")
                return
            except json.JSONDecodeError:
                logger.error("WebSocket rejected: Invalid auth message format")
                await websocket.close(code=4001, reason="Invalid auth message format")
                return

        logger.info(f"WebSocket connection attempt with token: {bool(token)}")

        # Authenticate user from token
        if not token:
            logger.error("WebSocket rejected: Missing authentication token")
            await websocket.close(code=4001, reason="Missing authentication token")
            return

        # Verify JWT token
        try:
            from auth_utils import decode_access_token
            # Decode token directly (doesn't need DB)
            payload = decode_access_token(token)
            if not payload:
                logger.error(f"WebSocket auth error: token decode failed")
                await websocket.close(code=4003, reason="Invalid token")
                return

            # Token payload uses "sub" for user_id (standard JWT claim)
            user_id = payload.get("sub") or payload.get("user_id")
            if not user_id:
                logger.error(f"WebSocket auth error: no user_id in payload: {payload}")
                await websocket.close(code=4002, reason="Invalid token payload")
                return
            # Convert to int if string
            user_id = int(user_id) if isinstance(user_id, str) else user_id
            logger.info(f"WebSocket auth successful for user {user_id}")
        except Exception as auth_error:
            logger.error(f"WebSocket auth error: {auth_error}", exc_info=True)
            await websocket.close(code=4003, reason="Authentication failed")
            return

        # Register with manager (connection already accepted)
        websocket_already_accepted = True  # Track that we already accepted
        if user_id not in ws_manager.user_connections:
            ws_manager.user_connections[user_id] = []
        ws_manager.user_connections[user_id].append(websocket)
        ws_manager.active_connections.append(websocket)
        logger.info(f"Playground WebSocket registered for user {user_id}")

        # Send connection confirmation
        await websocket.send_json({"type": "connected", "user_id": user_id})

        # Initialize service - use global engine variable
        from sqlalchemy.orm import sessionmaker
        global engine
        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()

        try:
            ws_service = PlaygroundWebSocketService(db, user_id)

            # Handle incoming messages
            while True:
                data = await websocket.receive_text()

                try:
                    message = json.loads(data)
                    message_type = message.get("type")

                    if message_type == "ping":
                        # Heartbeat
                        await websocket.send_json({"type": "pong"})

                    elif message_type == "chat":
                        # Stream chat response
                        agent_id = message.get("agent_id")
                        thread_id = message.get("thread_id")
                        user_message = message.get("message")

                        if not agent_id or not user_message:
                            await websocket.send_json({
                                "type": "error",
                                "error": "Missing agent_id or message"
                            })
                            continue

                        # Process and stream response
                        async for chunk in ws_service.process_streaming_message(
                            agent_id=agent_id,
                            thread_id=thread_id,
                            message=user_message,
                            websocket=websocket
                        ):
                            await websocket.send_json(chunk)

                    else:
                        await websocket.send_json({
                            "type": "error",
                            "error": f"Unknown message type: {message_type}"
                        })

                except json.JSONDecodeError:
                    await websocket.send_json({
                        "type": "error",
                        "error": "Invalid JSON message"
                    })
                except Exception as msg_error:
                    logger.error(f"Error processing WebSocket message: {msg_error}", exc_info=True)
                    await websocket.send_json({
                        "type": "error",
                        "error": str(msg_error)
                    })

        finally:
            db.close()

    except WebSocketDisconnect:
        logger.info(f"Playground WebSocket disconnected for user {user_id}")
        ws_manager.disconnect(websocket, user_id=user_id)
    except Exception as e:
        logger.error(f"Playground WebSocket error: {e}", exc_info=True)
        ws_manager.disconnect(websocket, user_id=user_id)

# Make WebSocket manager available to other modules
app.state.ws_manager = ws_manager

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.APP_HOST,
        port=settings.APP_PORT
    )

# trigger reload - Testing Phase 4.8
