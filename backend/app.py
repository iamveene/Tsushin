from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
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
    ],
    force=True  # Ensure config is applied even if root logger was initialized by imports
)

logger = logging.getLogger(__name__)
logger.info(f"Starting {settings.SERVICE_NAME} v{settings.SERVICE_VERSION}")

import email_config  # noqa: F401

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
from api.routes_channels import router as channels_router
from api.routes_triggers import router as triggers_router
from api.routes_channel_event_rules import router as channel_event_rules_router
from api.routes_continuous import router as continuous_router
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
from api.routes_flow_trigger_bindings import router as flow_trigger_bindings_router  # v0.7.0 Wave 4
from api.routes_case_memory import router as case_memory_router  # v0.7.0 Trigger Case Memory MVP
from api.routes_feature_flags import router as feature_flags_router  # v0.7.x — read-only env-flag introspection
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
# Phase I: Agent Builder Batch Endpoints
from api.routes_agent_builder import router as agent_builder_router
# Phase 8: MCP Instance Management
from api.routes_mcp_instances import router as mcp_instances_router
from api.routes_webhook_inbound import router as webhook_inbound_router
from api.routes_webhook_instances import router as webhook_instances_router
from api.routes_email_triggers import router as email_triggers_router
from api.routes_jira_integrations import router as jira_integrations_router
from api.routes_jira_triggers import router as jira_triggers_router
from api.routes_github_triggers import router as github_triggers_router
from api.routes_wizards import router as wizards_router
from api.routes_github_inbound import router as github_inbound_router
from api.routes_github_integrations import router as github_integrations_router
# Playground Feature
from api.routes_playground import router as playground_router
# Phase 14.4: Projects
from api.routes_projects import router as projects_router
# Phase 16: Slash Commands
from api.routes_commands import router as commands_router
from api.routes_user_contact_mapping import router as user_contact_mapping_router
# Phase 7.9: RBAC & Multi-tenancy
from api.routes_tenants import router as tenants_router
from api.routes_tenant_settings import router as tenant_settings_router
from api.routes_default_agents import router as default_agents_router
from api.routes_team import router as team_router
# Plans Management
from api.routes_plans import router as plans_router
# SSO Configuration
from api.routes_sso_config import router as sso_config_router
# Global User Management
from api.routes_global_users import router as global_users_router
# Global Admin: Invitations & Platform SSO (invitation scope + global SSO feature)
from api.routes_admin_invitations import router as admin_invitations_router
from api.routes_admin_sso import router as admin_sso_router
# Toolbox Container Management (Custom Tools)
from api.routes_toolbox import router as toolbox_router
# Skill Integrations (Provider Configuration)
from api.routes_skill_integrations import router as skill_integrations_router, set_engine as set_skill_integrations_engine
# Model Pricing (Cost Estimation Settings)
from api.routes_model_pricing import router as model_pricing_router
# Phase 10.1.1: Telegram Integration
from api.routes_telegram_instances import router as telegram_instances_router
# v0.6.0 Item 33: Slack Integration
from api.routes_slack import router as slack_router
# v0.6.0 Item 34: Discord Integration
from api.routes_discord import router as discord_router
# Phase 17: System AI Configuration
from api.routes_system_ai import router as system_ai_router
# Integration Test Connection endpoints (Groq, Grok, ElevenLabs, etc.)
from api.routes_integrations import router as integrations_router
# Phase 20: Sentinel Security Agent
from api.routes_sentinel import router as sentinel_router, set_engine as set_sentinel_engine
from api.routes_sentinel_exceptions import router as sentinel_exceptions_router, set_engine as set_sentinel_exceptions_engine
# v1.6.0: Sentinel Security Profiles
from api.routes_sentinel_profiles import router as sentinel_profiles_router, set_engine as set_sentinel_profiles_engine
# Message Queue System
from api.routes_queue import router as queue_router
from api.routes_api_clients import router as api_clients_router
from api.routes_audit import router as audit_router
from api.routes_syslog import router as syslog_config_router
# Phase 21: Provider Instance Management
from api.routes_provider_instances import router as provider_instances_router, set_engine as set_provider_instances_engine
# v0.6.0: Vector Store Instance Management
from api.routes_vector_stores import router as vector_stores_router, set_engine as set_vector_stores_engine
# v0.6.0-patch.5: TTS Instance Management (per-tenant Kokoro auto-provisioning)
from api.routes_tts_instances import router as tts_instances_router, set_engine as set_tts_instances_engine
# v0.7.0 Track D: ASR Instance Management (per-tenant Whisper/Speaches auto-provisioning)
from api.routes_asr_instances import router as asr_instances_router, set_engine as set_asr_instances_engine
# v0.6.0-patch.6: SearXNG Instance Management (per-tenant SearXNG auto-provisioning)
from api.routes_searxng_instances import router as searxng_instances_router, set_engine as set_searxng_instances_engine
# Hub Providers catalog (AddIntegrationWizard — live registry)
from api.routes_hub_providers import router as hub_providers_router
# Phase 22: Custom Skills Foundation
from api.routes_custom_skills import router as custom_skills_router, set_engine as set_custom_skills_engine
# Phase 22.4: MCP Server Integration
from api.routes_mcp_servers import router as mcp_servers_router, set_engine as set_mcp_servers_engine
from api.routes_services import router as services_router
from api.routes_agent_communication import router as agent_comm_router, set_engine as set_agent_comm_engine
# v0.6.0 Remote Access (Cloudflare Tunnel)
from api.routes_remote_access import router as remote_access_router
from api.v1.router import v1_router
from middleware.rate_limiter import ApiV1RateLimitMiddleware
from services.queue_worker import start_queue_worker, stop_queue_worker
# Phase 23: Channel Inbound Webhooks (BUG-311, BUG-312, BUG-313)
from api.routes_channel_webhooks import router as channel_webhooks_router
# MCP Health Monitor Service (auto-recovery for keepalive timeouts)
from services.mcp_health_monitor import MCPHealthMonitorService
from services.mcp_container_manager import MCPContainerManager
from services.whatsapp_binding_service import backfill_unambiguous_whatsapp_bindings

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
    engine = get_engine(settings.DATABASE_URL)
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
    set_sentinel_profiles_engine(engine)

    # Phase 21: Provider Instance Management
    set_provider_instances_engine(engine)
    # v0.6.0: Vector Store Instance Management
    set_vector_stores_engine(engine)
    # v0.6.0-patch.5: TTS Instance Management (per-tenant Kokoro auto-provisioning)
    set_tts_instances_engine(engine)
    # v0.7.0 Track D: ASR Instance Management (per-tenant Whisper/Speaches auto-provisioning)
    set_asr_instances_engine(engine)
    # v0.6.0-patch.6: SearXNG Instance Management (per-tenant SearXNG auto-provisioning)
    set_searxng_instances_engine(engine)

    # Phase 22: Custom Skills Foundation
    set_custom_skills_engine(engine)

    # Phase 22.4: MCP Server Integration
    set_mcp_servers_engine(engine)

    # v0.6.0 Item 15: Agent-to-Agent Communication
    set_agent_comm_engine(engine)

    logging.info("Database initialized")

    # v0.6.0-patch.5: Reconcile auto-provisioned Ollama containers.
    # Rows stuck in 'creating'/'provisioning' (e.g. after a host crash) get
    # their container_status synced from the runtime so the UI shows the
    # real state on the next request.
    try:
        from services.ollama_container_manager import startup_reconcile as ollama_startup_reconcile
        ollama_startup_reconcile()  # uses its own db session
    except Exception as e:
        logger.warning(f"Ollama startup reconcile failed: {e}")

    async def _prewarm_embedding_models() -> None:
        """Warm the default embedder off the request path."""
        try:
            from agent.memory.embedding_service import get_shared_embedding_service
            await asyncio.to_thread(get_shared_embedding_service, "all-MiniLM-L6-v2")
            logging.info("Embedding model prewarmed successfully")
        except Exception as e:
            logging.warning(f"Embedding prewarm skipped: {e}")

    asyncio.create_task(_prewarm_embedding_models())

    # Migration: Ensure sandboxed_tools skill exists for agents with tool assignments
    try:
        MigrationSession = sessionmaker(bind=engine)
        migration_db = MigrationSession()
        from services.sandboxed_tool_seeding import ensure_sandboxed_tools_skill, update_existing_tools, deduplicate_tool_commands
        created = ensure_sandboxed_tools_skill(migration_db)
        if created > 0:
            print(f"📦 Migration: Created sandboxed_tools skill for {created} agents")

        # BUG-273: Seed shell skill for every agent (per-agent enable/disable UI)
        from services.shell_skill_seeding import backfill_shell_skill_all_tenants
        shell_created = backfill_shell_skill_all_tenants(migration_db)
        if shell_created > 0:
            print(f"📦 Migration: Created shell skill for {shell_created} agents")

        # BUG-044: Deduplicate tool commands/params before updating from manifests
        dedup_result = deduplicate_tool_commands(migration_db)
        if dedup_result["deleted_commands"] > 0 or dedup_result["deleted_params"] > 0:
            print(f"📦 Dedup: removed {dedup_result['deleted_commands']} duplicate commands, "
                  f"{dedup_result['deleted_params']} duplicate parameters")

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

    # Belt-and-suspenders: ensure the singleton GlobalSSOConfig row exists.
    # Migration 0036 already inserts it on upgrade, but a manual volume
    # restore or a skipped migration would leave admin SSO endpoints with no
    # row to PUT against. This runs on every startup and is a no-op when
    # the row already exists.
    try:
        SSOSession = sessionmaker(bind=engine)
        sso_db = SSOSession()
        from models_rbac import GlobalSSOConfig
        if sso_db.query(GlobalSSOConfig).first() is None:
            sso_db.add(GlobalSSOConfig(
                google_sso_enabled=False,
                auto_provision_users=False,
            ))
            sso_db.commit()
            print("📦 Seeded default GlobalSSOConfig singleton row")
        sso_db.close()
    except Exception as e:
        logging.error(f"GlobalSSOConfig startup seeding failed: {e}")

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

        container_manager = MCPContainerManager()
        reconciled_tenants = set()
        for inst in mcp_instances:
            try:
                container_manager.reconcile_instance(inst, session)
                reconciled_tenants.add(inst.tenant_id)
            except Exception as reconcile_error:
                logging.warning(f"Failed to reconcile MCP instance {inst.id}: {reconcile_error}")

        for tenant_id in reconciled_tenants:
            try:
                linked = backfill_unambiguous_whatsapp_bindings(session, tenant_id)
                if linked:
                    session.commit()
                    print(f"🔗 Backfilled WhatsApp bindings for tenant {tenant_id}: {linked} agent(s)")
            except Exception as binding_error:
                session.rollback()
                logging.warning(f"Failed to backfill WhatsApp bindings for tenant {tenant_id}: {binding_error}")

        app.state.watchers = watchers
        app.state.watcher_tasks = watcher_tasks

        # Initialize WatcherManager for dynamic watcher lifecycle
        from services.watcher_manager import WatcherManager
        app.state.watcher_manager = WatcherManager(app.state)

        # Start a watcher for each instance through the same code path used for
        # dynamic instance creation/restarts. This keeps startup behavior aligned
        # with runtime behavior and avoids stale SQLite-path gating.
        for instance in mcp_instances:
            try:
                print(f"🔄 Processing instance {instance.id} ({instance.instance_type})...")
                if instance.instance_type == "tester":
                    print(f"⚠️  SKIPPING watcher for TESTER instance {instance.id} - tester instances should NOT process messages with agent")
                    continue

                started = await app.state.watcher_manager.start_watcher_for_instance(instance.id, session)
                if started:
                    print(f"✅ MCP Watcher started for AGENT instance {instance.id} (tenant: {instance.tenant_id}, port: {instance.mcp_port})")
                else:
                    print(f"⚠️  Watcher not started for instance {instance.id} (already running or waiting on MCP readiness)")
            except Exception as instance_error:
                logging.error(f"Error starting watcher for instance {instance.id}: {instance_error}", exc_info=True)

        print(f"🎯 Total watchers started: {len(watchers)}")
        print(f"📋 Watcher IDs: {list(watchers.keys())}")
        print("✅ WatcherManager initialized for dynamic instance management")

    except Exception as e:
        logging.error(f"Error starting MCP instance watchers: {e}", exc_info=True)

    # Start MCP Health Monitor Service (auto-recovery for keepalive timeouts)
    mcp_health_monitor = None
    container_manager = None
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

    # v0.6.0 Item 38: Start Channel Health Service (circuit breakers for all channels)
    try:
        from services.channel_health_service import ChannelHealthService
        from services.channel_alert_dispatcher import ChannelAlertDispatcher
        from services.watcher_activity_service import WatcherActivityService
        import settings as app_settings

        if getattr(app_settings, 'CHANNEL_HEALTH_ENABLED', True):
            alert_dispatcher = ChannelAlertDispatcher(get_db_session=SessionLocal)
            channel_health_service = ChannelHealthService(
                get_db_session=SessionLocal,
                container_manager=container_manager if container_manager else MCPContainerManager(),
                watcher_activity_service=WatcherActivityService.get_instance() if hasattr(WatcherActivityService, 'get_instance') else None,
                alert_dispatcher=alert_dispatcher
            )

            # Wire MCPHealthMonitor recovery callback to notify ChannelHealthService
            if mcp_health_monitor and hasattr(mcp_health_monitor, 'on_recovery_triggered'):
                original_callback = mcp_health_monitor.on_recovery_triggered
                def combined_callback(instance_id, reason):
                    if original_callback:
                        original_callback(instance_id, reason)
                    logging.info(f"🔄 Auto-recovery triggered for MCP instance {instance_id}: {reason}")
                    channel_health_service.on_external_recovery("whatsapp", instance_id)
                mcp_health_monitor.on_recovery_triggered = combined_callback

            await channel_health_service.start()
            app.state.channel_health_service = channel_health_service
            logging.info("🏥 Channel Health Service started (circuit breakers enabled for all channels)")
        else:
            logging.info("Channel Health Service disabled via TSN_CHANNEL_HEALTH_ENABLED")

    except Exception as e:
        logging.error(f"Error starting Channel Health Service: {e}", exc_info=True)
        # Non-fatal

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

                    # Fallback: resolve the tenant's Telegram default agent.
                    if not matching_agents and bot_instance:
                        from services.default_agent_service import get_default_agent

                        default_agent_id = get_default_agent(
                            db=request_session,
                            tenant_id=bot_instance.tenant_id,
                            channel_type="telegram",
                            instance_id=telegram_instance_id,
                        )
                        default_agent = (
                            request_session.query(Agent)
                            .filter(Agent.id == default_agent_id)
                            .first()
                            if default_agent_id
                            else None
                        )

                        if default_agent:
                            default_channels = default_agent.enabled_channels if isinstance(default_agent.enabled_channels, list) else (
                                json_lib.loads(default_agent.enabled_channels) if default_agent.enabled_channels else []
                            )
                            if "telegram" in default_channels:
                                matching_agents.append(default_agent)
                                logging.info(
                                    f"Using default agent {default_agent.id} as fallback for Telegram instance {telegram_instance_id}"
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
                    # V060-CHN-006: tenant_id is required or contact lookups fail closed
                    from agent.contact_service_cached import CachedContactService
                    contact_service = CachedContactService(
                        request_session,
                        tenant_id=(bot_instance.tenant_id if bot_instance else None)
                    )

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
                        telegram_instance_id=telegram_instance_id,
                        tenant_id=bot_instance.tenant_id,  # V060-CHN-006
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

    # V060-CHN-002: Initialize Slack Socket Mode Manager
    try:
        from services.slack_socket_mode_manager import SlackSocketModeManager
        slack_socket_manager = SlackSocketModeManager(db_session_factory=SessionLocal)
        app.state.slack_socket_mode_manager = slack_socket_manager
        await slack_socket_manager.start_all()
        logging.info("Slack Socket Mode Manager initialized")
    except Exception as e:
        logging.error(f"Error initializing Slack Socket Mode Manager: {e}", exc_info=True)

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
            refresh_threshold_hours=settings.OAUTH_REFRESH_THRESHOLD_HOURS,
            max_retries=settings.OAUTH_REFRESH_MAX_RETRIES,
            retry_delay=settings.OAUTH_REFRESH_RETRY_DELAY,
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

    # Message Queue Worker (async message processing)
    try:
        await start_queue_worker(engine, poll_interval_ms=500)
        logging.info("Message Queue Worker started (polling every 500ms)")
    except Exception as e:
        logging.error(f"Error starting Message Queue Worker: {e}", exc_info=True)

    # v0.6.0: Start Audit Retention Worker (purges expired audit events daily)
    try:
        from services.audit_retention_worker import start_audit_retention_worker
        start_audit_retention_worker(engine, poll_interval_hours=24)
        logging.info("Audit Retention Worker started (purging every 24h)")
    except Exception as e:
        logging.error(f"Error starting Audit Retention Worker: {e}", exc_info=True)

    # Syslog Forwarder Worker (streams audit events to external syslog servers)
    try:
        from services.syslog_forwarder import start_syslog_forwarder
        start_syslog_forwarder(engine, queue_size=10000, batch_size=50, poll_interval_ms=200)
        logging.info("Syslog Forwarder Worker started")
    except Exception as e:
        logging.error(f"Error starting Syslog Forwarder Worker: {e}", exc_info=True)

    # v0.6.0 Remote Access (Cloudflare Tunnel): initialize the singleton
    # service and, if config.enabled + config.autostart, fire-and-forget
    # autostart. Failures here must never block app startup.
    try:
        from services.cloudflare_tunnel_service import get_cloudflare_tunnel_service
        TunnelSession = sessionmaker(bind=engine)
        tunnel_service = get_cloudflare_tunnel_service(TunnelSession)
        app.state.tunnel_service = tunnel_service
        logging.info(
            "Cloudflare tunnel service initialized (binary=%s)",
            tunnel_service._cloudflared_path or "not found",
        )
        if await tunnel_service.should_autostart():
            asyncio.create_task(tunnel_service.start_autostart())
            logging.info("Cloudflare tunnel autostart requested")
    except Exception as e:
        logging.error(f"Error initializing Cloudflare tunnel service: {e}", exc_info=True)

    # Phase 22.4: Auto-connect active MCP servers on startup
    async def _auto_connect_mcp_servers():
        await asyncio.sleep(5)  # Wait for full startup
        try:
            from hub.mcp.connection_manager import MCPConnectionManager
            from models import MCPServerConfig
            manager = MCPConnectionManager.get_instance()
            AutoConnectSession = sessionmaker(bind=engine)
            db = AutoConnectSession()
            try:
                servers = db.query(MCPServerConfig).filter(
                    MCPServerConfig.is_active == True
                ).all()
                connected = 0
                for server in servers:
                    try:
                        await manager.get_or_connect(server.id, db)
                        logging.info(f"Auto-connected MCP server: {server.server_name} (id={server.id})")
                        connected += 1
                    except Exception as e:
                        logging.warning(f"Failed to auto-connect MCP server {server.server_name}: {e}")
                if servers:
                    logging.info(f"MCP auto-connect: {connected}/{len(servers)} servers connected")
            finally:
                db.close()
        except Exception as e:
            logging.error(f"MCP auto-connect failed: {e}", exc_info=True)

    asyncio.create_task(_auto_connect_mcp_servers())

    # v0.6.0 G3-A: Start MCP Server Periodic Health Check Service
    try:
        from services.mcp_server_health_service import MCPServerHealthCheckService
        app.state.mcp_server_health_service = MCPServerHealthCheckService(engine)
        await app.state.mcp_server_health_service.start()
        logging.info("MCP Server Health Check Service started (interval=180s)")
    except Exception as e:
        logging.error(f"Error starting MCP Server Health Check Service: {e}", exc_info=True)

    # v0.6.0-patch.5: Reconcile TTS instances stuck in 'creating' (e.g. after a crash)
    try:
        from services.kokoro_container_manager import startup_reconcile as kokoro_startup_reconcile
        ReconcileSession = sessionmaker(bind=engine)
        reconcile_db = ReconcileSession()
        try:
            kokoro_startup_reconcile(reconcile_db)
        finally:
            reconcile_db.close()
        logging.info("Kokoro TTS instances reconciled at startup")
    except Exception as e:
        logging.warning(f"Kokoro TTS reconcile failed at startup: {e}")

    # v0.7.0 Track D: Reconcile ASR instances stuck in 'creating'
    try:
        from services.whisper_container_manager import startup_reconcile as whisper_startup_reconcile
        ReconcileSession = sessionmaker(bind=engine)
        reconcile_db = ReconcileSession()
        try:
            whisper_startup_reconcile(reconcile_db)
        finally:
            reconcile_db.close()
        logging.info("Whisper ASR instances reconciled at startup")
    except Exception as e_whisper_reconcile:
        logging.warning(f"Whisper ASR startup reconcile failed (non-fatal): {e_whisper_reconcile}")

    # v0.6.0-patch.6: Reconcile SearXNG instances stuck in 'creating'
    try:
        from services.searxng_container_manager import startup_reconcile as searxng_startup_reconcile
        ReconcileSession = sessionmaker(bind=engine)
        reconcile_db = ReconcileSession()
        try:
            searxng_startup_reconcile(reconcile_db)
        finally:
            reconcile_db.close()
        logging.info("SearXNG instances reconciled at startup")
    except Exception as e_searxng_reconcile:
        logging.warning(f"SearXNG startup reconcile failed (non-fatal): {e_searxng_reconcile}")

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

    # V060-CHN-002: Stop Slack Socket Mode Manager
    if hasattr(app.state, 'slack_socket_mode_manager'):
        try:
            await app.state.slack_socket_mode_manager.stop_all()
            logging.info("Slack Socket Mode Manager stopped")
        except Exception as e:
            logging.error(f"Error stopping Slack Socket Mode Manager: {e}", exc_info=True)

    # v0.6.0 Item 38: Stop Channel Health Service
    if hasattr(app.state, 'channel_health_service'):
        try:
            await app.state.channel_health_service.stop()
            logging.info("🏥 Channel Health Service stopped")
        except Exception as e:
            logging.error(f"Error stopping Channel Health Service: {e}", exc_info=True)

    # Stop MCP Health Monitor Service
    if hasattr(app.state, 'mcp_health_monitor'):
        try:
            await app.state.mcp_health_monitor.stop()
            logging.info("🏥 MCP Health Monitor Service stopped")
        except Exception as e:
            logging.error(f"Error stopping MCP Health Monitor: {e}", exc_info=True)

    # v0.6.0 G3-A: Stop MCP Server Health Check Service
    if hasattr(app.state, 'mcp_server_health_service'):
        try:
            await app.state.mcp_server_health_service.stop()
            logging.info("MCP Server Health Check Service stopped")
        except Exception as e:
            logging.error(f"Error stopping MCP Server Health Check Service: {e}", exc_info=True)

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

    # Stop Message Queue Worker
    try:
        await stop_queue_worker()
        logging.info("Message Queue Worker stopped")
    except Exception as e:
        logging.error(f"Error stopping Message Queue Worker: {e}", exc_info=True)

    # Stop Audit Retention Worker
    try:
        from services.audit_retention_worker import stop_audit_retention_worker
        stop_audit_retention_worker()
        logging.info("Audit Retention Worker stopped")
    except Exception as e:
        logging.error(f"Error stopping Audit Retention Worker: {e}", exc_info=True)

    # Stop Syslog Forwarder Worker
    try:
        from services.syslog_forwarder import stop_syslog_forwarder
        stop_syslog_forwarder()
        logging.info("Syslog Forwarder Worker stopped")
    except Exception as e:
        logging.error(f"Error stopping Syslog Forwarder Worker: {e}", exc_info=True)

    # v0.6.0 Remote Access: stop cloudflared subprocess cleanly so SIGTERM
    # propagates before the DB engine is disposed.
    try:
        if hasattr(app.state, "tunnel_service") and app.state.tunnel_service is not None:
            await app.state.tunnel_service.shutdown()
            logging.info("Cloudflare tunnel service stopped")
    except Exception as e:
        logging.error(f"Error stopping Cloudflare tunnel service: {e}", exc_info=True)

    session.close()
    logging.info("Application shutdown")

# Create app
app = FastAPI(
    title="Tsushin Platform API",
    version="1.0.0",
    description="""
Multi-tenant AI agent platform with flows, hub integrations, and studio builder.

## Authentication

The Public API v1 (`/api/v1/`) supports two authentication methods:

- **OAuth2 Client Credentials**: Exchange `client_id` and `client_secret` at
  `POST /api/v1/oauth/token` for a short-lived JWT bearer token (1 hour).
- **API Key**: Pass the raw client secret directly via the `X-API-Key` header
  (prefix: `tsn_cs_`). No token exchange required.

## Rate Limiting

All `/api/v1/` endpoints (except `/api/v1/oauth/token`) are rate-limited per API client.
Default: **60 requests/minute** (configurable per client). The OAuth token endpoint
has a separate per-IP limit of **10 requests/minute**.

Response headers on every v1 request:
- `X-RateLimit-Limit` — Maximum requests per minute
- `X-RateLimit-Remaining` — Remaining quota in the current window
- `X-Request-Id` — Unique request ID for debugging
- `X-API-Version` — API version (`v1`)

When rate-limited, the API returns **HTTP 429** with a `Retry-After: 60` header.

## Pagination

List endpoints use page-based pagination:
- `page` (1-based, default 1) and `per_page` (default 20, max 100)
- Response envelope: `{"data": [...], "meta": {"total": N, "page": 1, "per_page": 20}}`

## Error Format

Errors return a JSON body with `detail` (string or object) and the appropriate HTTP status code.
OAuth errors follow the RFC 6749 format: `{"error": "...", "error_description": "..."}`.
""".strip(),
    openapi_tags=[
        {"name": "OAuth", "description": "OAuth2 client credentials token exchange"},
        {"name": "Agents API", "description": "Agent CRUD and configuration management"},
        {"name": "Chat API", "description": "Synchronous and asynchronous chat with agents"},
        {"name": "Flows API", "description": "Flow definition CRUD, step management, execution, and run monitoring"},
        {"name": "Hub API", "description": "Provider-agnostic hub integrations (Asana, Gmail, Calendar)"},
        {"name": "Studio API", "description": "Agent Studio builder data and atomic save"},
        {"name": "Resources API", "description": "Read-only listings for skills, tools, personas, and presets"},
    ],
    lifespan=lifespan,
)

# MED-004 FIX: Initialize rate limiter
# Rate limits: login (5/min), signup (3/hr), password reset (3/hr)
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS - Configurable origins via TSN_CORS_ORIGINS env var
# Default: "*" (reflect requesting origin) for backward compatibility / development
# Production: set TSN_CORS_ORIGINS=https://app.example.com,https://admin.example.com
# SEC-005: credentials=True is required for httpOnly cookie auth
_cors_origins_str = os.getenv("TSN_CORS_ORIGINS", "*")
_cors_origin_regex = None
if _cors_origins_str.strip() == "*":
    # SEC-005 / CORS FIX: Use origin reflection instead of literal "*" wildcard.
    # Literal "*" with credentials=True is rejected by browsers.
    # allow_origin_regex=".*" reflects the requesting origin with credentials support.
    _cors_origins = []
    _cors_origin_regex = ".*"
    _cors_allow_credentials = True
else:
    _cors_origins = [origin.strip() for origin in _cors_origins_str.split(",") if origin.strip()]
    _cors_origin_regex = None
    _cors_allow_credentials = True  # Safe to allow credentials with explicit origins

# v0.6.0 Remote Access: append the configured Cloudflare Tunnel hostname to
# the allow list so cross-origin API integrations that target the public URL
# work even when TSN_CORS_ORIGINS is pinned to localhost. Same-origin browser
# traffic (UI loaded from the tunnel hostname calling /api on the same
# hostname) does not require CORS, but explicit origins here protect
# external API consumers. Best-effort; silently skipped if the
# remote_access_config table does not yet exist (fresh install pre-migration).
if _cors_origins:
    _cors_bootstrap = None
    try:
        from sqlalchemy import create_engine as _cors_engine, text as _cors_text
        _cors_bootstrap_url = os.getenv("DATABASE_URL", "")
        if _cors_bootstrap_url:
            # Engine creation must be inside the try/finally so a failure
            # here (rather than only during .connect()) still releases the
            # connection pool properly.
            _cors_bootstrap = _cors_engine(_cors_bootstrap_url)
            with _cors_bootstrap.connect() as _cors_conn:
                _cors_row = _cors_conn.execute(
                    _cors_text(
                        "SELECT tunnel_hostname FROM remote_access_config WHERE id = 1"
                    )
                ).first()
                if _cors_row and _cors_row[0]:
                    _cors_tunnel_origin = f"https://{str(_cors_row[0]).strip().lower()}"
                    if _cors_tunnel_origin not in _cors_origins:
                        _cors_origins.append(_cors_tunnel_origin)
                        logger.info(
                            f"CORS: added tunnel hostname origin {_cors_tunnel_origin}"
                        )
    except Exception as _cors_exc:
        logger.debug(
            f"CORS tunnel-hostname bootstrap skipped (table may not exist yet): {_cors_exc}"
        )
    finally:
        if _cors_bootstrap is not None:
            _cors_bootstrap.dispose()

logger.info(f"CORS origins: {_cors_origins or 'reflect-all'} (credentials={_cors_allow_credentials})")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=_cors_origin_regex,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Requested-With"],
    max_age=86400,  # Cache preflight for 24 hours
)

# Proxy headers — reads X-Forwarded-For/Proto from reverse proxy (Caddy/Nginx)
# Ensures get_remote_address returns real client IP for rate limiting behind proxy.
# No-op when running without a proxy.
# BUG-074 FIX: Use configurable trusted hosts instead of wildcard
_trusted_proxy_hosts = os.environ.get("TSN_TRUSTED_PROXY_HOSTS", "127.0.0.1,::1")
_trusted_hosts_list = [h.strip() for h in _trusted_proxy_hosts.split(",") if h.strip()]
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=_trusted_hosts_list)

# Public API v1: Rate limiting middleware
app.add_middleware(ApiV1RateLimitMiddleware)

# Request ID middleware — generates a UUID per request for log correlation
from services.logging_service import RequestIdMiddleware
app.add_middleware(RequestIdMiddleware)

# Prometheus metrics middleware — tracks request count and duration
from services.metrics_service import PrometheusMiddleware
app.add_middleware(PrometheusMiddleware)


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
    if os.getenv("TSN_ENABLE_HSTS", "").lower() in ("1", "true", "yes"):
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response

# CORS headers for exception handlers — must match the middleware config above
def _cors_headers_for_request(request: Request) -> dict:
    """Build CORS headers consistent with the configured origins."""
    origin = request.headers.get("origin", "")
    if _cors_origin_regex:
        # Reflect requesting origin (SEC-005: supports credentials with any origin)
        if origin:
            return {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS",
                "Access-Control-Allow-Headers": "Authorization, Content-Type, X-API-Key, X-Requested-With",
            }
        return {}
    # Only reflect the origin if it's in the allowed list
    if origin in _cors_origins:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS",
            "Access-Control-Allow-Headers": "Authorization, Content-Type, X-API-Key, X-Requested-With",
        }
    # Origin not allowed — omit CORS headers entirely
    return {}

# Custom exception handlers to ensure CORS headers are always present
# This fixes issues where HTTPException responses don't include CORS headers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions with CORS headers"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=_cors_headers_for_request(request),
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with CORS headers"""
    # Sanitize errors to ensure JSON-serializable (ctx may contain non-serializable objects)
    errors = []
    for err in exc.errors():
        sanitized = {k: v for k, v in err.items() if k != "ctx"}
        if "ctx" in err and isinstance(err["ctx"], dict):
            sanitized["ctx"] = {k: str(v) for k, v in err["ctx"].items()}
        errors.append(sanitized)
    return JSONResponse(
        status_code=422,
        content={"detail": errors},
        headers=_cors_headers_for_request(request),
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions with CORS headers"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers=_cors_headers_for_request(request),
    )

# Include routers
app.include_router(router)
app.include_router(api_keys_router, prefix="/api")
app.include_router(knowledge_router, prefix="/api")
app.include_router(knowledge_base_router, prefix="/api")
app.include_router(shared_memory_router, prefix="/api")
app.include_router(memory_router, prefix="/api")
app.include_router(skills_router, prefix="/api")
app.include_router(channels_router)  # Wizard channel catalog (/api/channels)
app.include_router(triggers_router)  # Trigger catalog (/api/triggers)
app.include_router(channel_event_rules_router)  # Channel routing rules (/api/channels/{type}/{id}/routing-rules)
app.include_router(continuous_router)  # Continuous-agent read APIs (/api/continuous-*)
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
app.include_router(flow_trigger_bindings_router)  # v0.7.0 Wave 4 - Triggers↔Flows binding CRUD

# v0.7.x Trigger Case Memory — case-memory routes are always mounted.
# Per-tenant opt-in is via Agent.vector_store_instance_id binding +
# TriggerRecapConfig.enabled flag — there is no global env kill-switch.
app.include_router(case_memory_router)
# v0.7.x — Read-only /api/feature-flags surface so the frontend can
# gate UI affordances (e.g. case-memory wizard) on env-driven flags
# without baking values into the build.
app.include_router(feature_flags_router)
app.include_router(cache_router)  # Phase 6.11.3 - Cache Management API
app.include_router(analytics_router)  # Phase 7.2 - Token Analytics
app.include_router(auth_router)  # Phase 7.6.3 - Authentication
app.include_router(agents_protected_router)  # Phase 7.6.4 - Protected Agents API (Example)
app.include_router(agent_builder_router)  # Phase I - Agent Builder Batch Endpoints
app.include_router(mcp_instances_router)  # Phase 8 - MCP Instance Management
app.include_router(playground_router)  # Playground Feature
app.include_router(projects_router)  # Phase 14.4: Projects
app.include_router(commands_router)  # Phase 16: Slash Commands
app.include_router(user_contact_mapping_router)  # Playground - User Contact Mapping
app.include_router(tenants_router)  # Phase 7.9 - Tenant Management
app.include_router(tenant_settings_router)  # v0.6.0 - Tenant self-service settings (public_base_url)
app.include_router(default_agents_router)
app.include_router(team_router)  # Phase 7.9 - Team Management
app.include_router(plans_router)  # Plans Management
app.include_router(sso_config_router)  # SSO Configuration
app.include_router(global_users_router)  # Global User Management
app.include_router(admin_invitations_router)  # Global Admin: Invitation Management
app.include_router(admin_sso_router)  # Global Admin: Platform-wide SSO Config
app.include_router(toolbox_router)  # Toolbox Container Management (Custom Tools)
app.include_router(skill_integrations_router, prefix="/api")  # Skill Integrations (Provider Configuration)
app.include_router(model_pricing_router)  # Model Pricing (Cost Estimation Settings)
app.include_router(telegram_instances_router)  # Phase 10.1.1: Telegram Integration
app.include_router(webhook_inbound_router)  # v0.6.0: Webhook-as-Channel (public, HMAC-gated)
app.include_router(webhook_instances_router)  # Webhook trigger CRUD (/api/triggers/webhook/*)
app.include_router(email_triggers_router)  # Email trigger CRUD (/api/triggers/email/*)
app.include_router(jira_integrations_router)  # Jira Tool API integrations (/api/hub/jira-integrations/*)
app.include_router(jira_triggers_router)  # Jira trigger CRUD (/api/triggers/jira/*)
app.include_router(github_triggers_router)  # GitHub trigger CRUD (/api/triggers/github/*)
app.include_router(wizards_router)  # v0.7.0-fix Phase 5: wizard manifest API (/api/wizards/manifests)
app.include_router(github_inbound_router)  # GitHub trigger inbound webhooks (/api/triggers/github/*/inbound)
app.include_router(github_integrations_router)  # GitHub Hub integrations (/api/hub/github-integrations/*)
# v0.6.0 Item 38: Channel Health Monitor
try:
    from api.routes_channel_health import router as channel_health_router
    app.include_router(channel_health_router)
except ImportError:
    logging.warning("Channel health routes not available")
app.include_router(system_ai_router)  # Phase 17: System AI Configuration
app.include_router(integrations_router)  # Integration Test Connection
app.include_router(sentinel_router, prefix="/api")  # Phase 20: Sentinel Security Agent
app.include_router(sentinel_exceptions_router, prefix="/api")  # Phase 20 Enhancement: Sentinel Exceptions
app.include_router(sentinel_profiles_router, prefix="/api")  # v1.6.0: Sentinel Security Profiles
app.include_router(provider_instances_router, prefix="/api", tags=["Provider Instances"])  # Phase 21: Provider Instance Management
app.include_router(vector_stores_router, prefix="/api", tags=["Vector Stores"])  # v0.6.0: Vector Store Instance Management
app.include_router(tts_instances_router, prefix="/api", tags=["TTS Instances"])  # v0.6.0-patch.5: Per-tenant Kokoro TTS auto-provisioning
app.include_router(asr_instances_router, prefix="/api", tags=["ASR Instances"])  # v0.7.0 Track D: Per-tenant Whisper/Speaches ASR auto-provisioning
app.include_router(searxng_instances_router, prefix="/api", tags=["SearXNG Instances"])  # v0.6.0-patch.6: Per-tenant SearXNG auto-provisioning
app.include_router(hub_providers_router)  # AddIntegrationWizard live catalogs (search + travel)
app.include_router(custom_skills_router, prefix="/api", tags=["Custom Skills"])  # Phase 22: Custom Skills Foundation
app.include_router(mcp_servers_router, prefix="/api", tags=["MCP Servers"])  # Phase 22.4: MCP Server Integration
app.include_router(services_router)  # Hub Local Services (Kokoro TTS container management)
app.include_router(queue_router)  # Message Queue System
app.include_router(api_clients_router)  # Public API v1: Client Management (UI-facing)
app.include_router(audit_router)  # v0.6.0: Tenant-Scoped Audit Logs
app.include_router(agent_comm_router, prefix="/api")  # v0.6.0 Item 15: Agent-to-Agent Communication
app.include_router(syslog_config_router)  # v0.6.0: Syslog Forwarding Configuration
app.include_router(remote_access_router)  # v0.6.0: Remote Access (Cloudflare Tunnel)
app.include_router(v1_router)  # Public API v1: All /api/v1/ endpoints
app.include_router(discord_router)  # Phase 23: Discord Bot Integration (BUG-311, BUG-313)
app.include_router(slack_router)  # Phase 23: Slack Workspace Integration (BUG-312)
app.include_router(channel_webhooks_router)  # Phase 23: Channel Inbound Webhooks (Discord interactions, Slack events)


def _build_v1_openapi_schema():
    """Build a public-only OpenAPI schema for SDK generation and docs."""
    return get_openapi(
        title="Tsushin Public API v1",
        version="1.0.0",
        description="Public API v1 only. Use this schema for SDK generation.",
        routes=[
            route
            for route in app.routes
            if getattr(route, "path", "").startswith("/api/v1/")
        ],
    )


@app.get("/api/v1/openapi.json", include_in_schema=False)
def get_v1_openapi():
    """Serve a dedicated Public API v1 schema without legacy/internal routes."""
    if not getattr(app.state, "v1_openapi_schema", None):
        app.state.v1_openapi_schema = _build_v1_openapi_schema()
    return JSONResponse(app.state.v1_openapi_schema)


@app.get("/api/v1/docs", include_in_schema=False)
def get_v1_docs():
    """Serve Swagger UI for the dedicated Public API v1 schema."""
    return get_swagger_ui_html(
        openapi_url="/api/v1/openapi.json",
        title="Tsushin Public API v1 Docs",
    )

# Prometheus metrics endpoint (unauthenticated — scrape target)
from services.metrics_service import metrics_endpoint
app.add_api_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)

# Phase 6.11.2: WebSocket endpoint for real-time updates
# BUG-310: Added JWT authentication and tenant-scoped connection tracking
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time updates.

    BUG-310: Requires JWT authentication. Supports two auth modes:
    1. Query param: /ws?token=<jwt> (legacy, logged as warning)
    2. First-message auth: send {"type": "auth", "token": "<jwt>"} after connect (preferred)

    Unauthenticated connections are rejected with close code 4001.
    Connections are scoped to the tenant extracted from the JWT.
    """
    import asyncio as _asyncio
    import json as _json
    from auth_utils import decode_access_token

    tenant_id = None
    user_id = None

    try:
        # Accept connection first (required by FastAPI before we can send close frames)
        await websocket.accept()

        # Check for token in query params (legacy) or wait for first-message auth (secure)
        query_params = dict(websocket.query_params)
        token = query_params.get("token")

        if token:
            logger.warning("WebSocket /ws using legacy query param auth (insecure) - please update client")
        else:
            # Secure mode: wait for auth message with token
            try:
                auth_data = await _asyncio.wait_for(websocket.receive_text(), timeout=10.0)
                auth_message = _json.loads(auth_data)

                if auth_message.get("type") != "auth":
                    logger.error(f"WebSocket /ws rejected: first message must be auth, got: {auth_message.get('type')}")
                    await websocket.close(code=4001, reason="First message must be auth type")
                    return

                token = auth_message.get("token")
                if not token:
                    logger.error("WebSocket /ws rejected: auth message missing token")
                    await websocket.close(code=4001, reason="Missing token in auth message")
                    return

            except _asyncio.TimeoutError:
                logger.error("WebSocket /ws rejected: auth timeout (10s)")
                await websocket.close(code=4001, reason="Authentication timeout")
                return
            except _json.JSONDecodeError:
                logger.error("WebSocket /ws rejected: invalid auth message format")
                await websocket.close(code=4001, reason="Invalid auth message format")
                return

        # Validate JWT token
        if not token:
            logger.error("WebSocket /ws rejected: no authentication token provided")
            await websocket.close(code=4001, reason="Missing authentication token")
            return

        payload = decode_access_token(token)
        if not payload:
            logger.error("WebSocket /ws rejected: invalid or expired token")
            await websocket.close(code=4003, reason="Invalid or expired token")
            return

        user_id = payload.get("sub") or payload.get("user_id")
        tenant_id = payload.get("tenant_id")

        if not user_id:
            logger.error(f"WebSocket /ws rejected: no user_id in token payload")
            await websocket.close(code=4002, reason="Invalid token payload - missing user_id")
            return

        if not tenant_id:
            logger.error(f"WebSocket /ws rejected: no tenant_id in token payload for user {user_id}")
            await websocket.close(code=4002, reason="Invalid token payload - missing tenant_id")
            return

        user_id = int(user_id) if isinstance(user_id, str) else user_id

        # BUG-671: reject disabled or deleted users before attaching to the
        # realtime stream. Mirrors the /ws/shell/status check.
        try:
            from sqlalchemy.orm import sessionmaker as _sessionmaker
            from models_rbac import User as _User
            _SessionLocal = _sessionmaker(bind=engine)
            _db = _SessionLocal()
            try:
                user_row = _db.query(_User).filter(_User.id == user_id).first()
                if user_row is None:
                    logger.warning(f"WebSocket /ws rejected: user {user_id} not found")
                    await websocket.close(code=4003, reason="User not found")
                    return
                if (not getattr(user_row, "is_active", False)) or (getattr(user_row, "deleted_at", None) is not None):
                    logger.warning(
                        f"WebSocket /ws rejected: user {user_id} is_active={user_row.is_active} "
                        f"deleted_at={getattr(user_row, 'deleted_at', None)}"
                    )
                    await websocket.close(code=4003, reason="Account disabled")
                    return
            finally:
                _db.close()
        except Exception as user_lookup_err:
            logger.error(f"WebSocket /ws user lookup failed: {user_lookup_err}", exc_info=True)
            await websocket.close(code=4003, reason="Authentication failed")
            return

        logger.info(f"WebSocket /ws authenticated: user={user_id}, tenant={tenant_id}")

        # Register with manager (already accepted above, so skip accept in connect)
        # Manually add to tracking structures instead of calling connect() which calls accept()
        ws_manager.active_connections.append(websocket)
        if tenant_id not in ws_manager.tenant_ws_connections:
            ws_manager.tenant_ws_connections[tenant_id] = []
        ws_manager.tenant_ws_connections[tenant_id].append(websocket)
        ws_manager._ws_tenant_map[id(websocket)] = tenant_id
        if user_id not in ws_manager.user_connections:
            ws_manager.user_connections[user_id] = []
        ws_manager.user_connections[user_id].append(websocket)

        # Send auth success confirmation
        await websocket.send_json({"type": "auth_success", "user_id": user_id, "tenant_id": tenant_id})

        # Keep connection alive and handle heartbeats
        while True:
            data = await websocket.receive_text()
            if data.strip() == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, user_id)
    except Exception as e:
        logger.error(f"WebSocket /ws error: {e}", exc_info=True)
        ws_manager.disconnect(websocket, user_id)

# Phase 14.9: WebSocket endpoint for Playground streaming v4
# Phase SEC-002: Fixed token exposure in query parameters (HIGH-001)
@app.websocket("/ws/playground")
async def playground_websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for Playground real-time streaming.

    Supports token-by-token streaming from LLM providers.

    Security: Token is sent in first message after connection (not in URL query params)
    to prevent exposure in browser history, server logs, and referrer headers.
    """
    from services.playground_websocket_service import PlaygroundWebSocketService
    import json

    user_id = None

    try:
        # CRITICAL: Accept connection FIRST (before auth)
        # FastAPI middleware rejects WebSocket with 403 if we don't accept immediately
        await websocket.accept()
        logger.info("WebSocket connection accepted, waiting for auth message...")

        # SEC-005: Support cookie auth (primary), first-message auth, and query param auth (legacy)
        token = None

        # Priority 1: httpOnly cookie (sent automatically with WS upgrade)
        cookie_token = websocket.cookies.get("tsushin_session")
        if cookie_token:
            token = cookie_token
            logger.info("WebSocket auth via httpOnly cookie")

        # Priority 2: Query param (legacy, deprecated)
        if not token:
            query_params = dict(websocket.query_params)
            token = query_params.get("token")
            if token:
                logger.warning("WebSocket using legacy query param auth (insecure) - please update client")

        # Priority 3: First-message auth (only if no cookie/query param token)
        if not token:
            logger.info("Waiting for auth message...")
            try:
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
            global engine
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

            # BUG-671: reject disabled or deleted users before registering
            # the Playground stream.
            from sqlalchemy.orm import sessionmaker as _sessionmaker
            from models_rbac import User as _User
            _SessionLocal = _sessionmaker(bind=engine)
            _db = _SessionLocal()
            try:
                user_row = _db.query(_User).filter(_User.id == user_id).first()
                if user_row is None:
                    logger.warning(f"Playground WebSocket rejected: user {user_id} not found")
                    await websocket.close(code=4003, reason="User not found")
                    return
                if (not getattr(user_row, "is_active", False)) or (getattr(user_row, "deleted_at", None) is not None):
                    logger.warning(
                        f"Playground WebSocket rejected: user {user_id} is_active={user_row.is_active} "
                        f"deleted_at={getattr(user_row, 'deleted_at', None)}"
                    )
                    await websocket.close(code=4003, reason="Account disabled")
                    return
            finally:
                _db.close()

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

        # Initialize service - use short-lived DB sessions per Playground
        # message instead of holding one open for the full WebSocket lifetime.
        from sqlalchemy.orm import sessionmaker
        SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
        ws_service = PlaygroundWebSocketService(SessionLocal, user_id)

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
