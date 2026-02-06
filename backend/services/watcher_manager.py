"""
Dynamic Watcher Management Service
Phase 8.1: Issue #0 - Dynamic watcher lifecycle management

Manages watcher creation/deletion when MCP instances are created/deleted,
eliminating the need for backend restarts.
"""

import asyncio
import logging
import json
from sqlalchemy.orm import Session
from typing import Optional

from models import WhatsAppMCPInstance, Config, Agent
from mcp_reader.watcher import MCPWatcher
from mcp_reader.filters import MessageFilter
from mcp_reader.sqlite_reader import MCPDatabaseReader
from mcp_reader.api_reader import MCPAPIReader
from agent.router import AgentRouter
import settings

logger = logging.getLogger(__name__)


class WatcherManager:
    """Manages dynamic watcher lifecycle"""

    def __init__(self, app_state):
        """
        Initialize watcher manager

        Args:
            app_state: FastAPI app.state object (stores watchers dict)
        """
        self.app_state = app_state
        if not hasattr(app_state, 'watchers'):
            app_state.watchers = {}
        if not hasattr(app_state, 'watcher_tasks'):
            app_state.watcher_tasks = {}

    async def start_watcher_for_instance(self, instance_id: int, db: Session) -> bool:
        """
        Create and start watcher for a specific MCP instance

        Args:
            instance_id: MCP instance ID
            db: Database session

        Returns:
            bool: True if watcher started successfully

        Raises:
            ValueError: Instance not found or invalid
        """
        try:
            # Check if watcher already exists
            if instance_id in self.app_state.watchers:
                logger.warning(f"Watcher already exists for instance {instance_id}, skipping")
                return False

            # Get instance from DB
            instance = db.query(WhatsAppMCPInstance).filter(
                WhatsAppMCPInstance.id == instance_id
            ).first()

            if not instance:
                raise ValueError(f"Instance {instance_id} not found")

            if instance.status not in ["running", "starting"]:
                logger.warning(f"Instance {instance_id} status is {instance.status}, not starting watcher")
                return False

            # Get config
            config = db.query(Config).first()
            if not config:
                raise ValueError("No config found in database")

            # Parse JSON fields
            contact_mappings = json.loads(config.contact_mappings) if config.contact_mappings else {}
            group_keywords = json.loads(config.group_keywords) if config.group_keywords else []
            # Note: enabled_tools deprecated - tools now handled via Skills system

            # Initialize contact service (reuse if exists)
            from agent.contact_service_cached import CachedContactService
            if not hasattr(self.app_state, 'contact_service'):
                contact_service = CachedContactService(db)
                self.app_state.contact_service = contact_service
            else:
                contact_service = self.app_state.contact_service

            # Phase 17: Instance-Level Message Filtering
            # Use instance-specific filters if configured, otherwise fall back to global config

            # Parse instance filters (may be JSON strings or lists)
            def parse_json_field(field):
                if field is None:
                    return None
                if isinstance(field, list):
                    return field
                if isinstance(field, str):
                    return json.loads(field) if field else None
                return None

            instance_group_filters = parse_json_field(instance.group_filters)
            instance_number_filters = parse_json_field(instance.number_filters)
            instance_group_keywords = parse_json_field(instance.group_keywords)
            instance_dm_auto_mode = getattr(instance, 'dm_auto_mode', None)

            # Determine which filters to use (instance takes precedence over global)
            use_instance_filters = (
                instance_group_filters is not None or
                instance_number_filters is not None or
                instance_group_keywords is not None or
                instance_dm_auto_mode is not None
            )

            if use_instance_filters:
                logger.info(f"Using instance-level filters for instance {instance.id}")
                base_group_filters = set(instance_group_filters or [])
                base_number_filters = instance_number_filters or []
                base_group_keywords = instance_group_keywords or []
                base_dm_auto_mode = instance_dm_auto_mode if instance_dm_auto_mode is not None else False
            else:
                logger.info(f"Using global config filters for instance {instance.id}")
                base_group_filters = set(config.group_filters or [])
                base_number_filters = config.number_filters or []
                base_group_keywords = group_keywords
                base_dm_auto_mode = config.dm_auto_mode

            # Collect additional group filters from active agents for this tenant
            all_group_filters = base_group_filters.copy()
            active_agents = db.query(Agent).filter(
                Agent.is_active == True,
                Agent.tenant_id == instance.tenant_id
            ).all()

            for agent in active_agents:
                if agent.trigger_group_filters:
                    agent_filters = json.loads(agent.trigger_group_filters) if isinstance(agent.trigger_group_filters, str) else agent.trigger_group_filters
                    if agent_filters:
                        all_group_filters.update(agent_filters)

            # Create message filter
            message_filter = MessageFilter(
                group_filters=list(all_group_filters),
                number_filters=base_number_filters,
                agent_number=config.agent_number,
                dm_auto_mode=base_dm_auto_mode,
                agent_phone_number=instance.phone_number,
                agent_name=config.agent_name,
                group_keywords=base_group_keywords,
                contact_service=contact_service,
                db_session=db
            )

            # Create config dict
            # Note: enabled_tools and enable_google_search deprecated - using Skills system instead
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

            # Create MCP reader - prefer HTTP API over SQLite to bypass Docker filesystem sync issues
            # The API reader fetches messages directly from the MCP container's HTTP endpoint,
            # which is more reliable than reading from bind-mounted SQLite files on Docker Desktop macOS
            # Phase Security-1: Pass API secret for authentication
            api_reader = MCPAPIReader(
                instance.mcp_api_url,
                contact_mappings=contact_mappings,
                api_secret=instance.api_secret
            )

            # Check if API is available, fallback to SQLite if not
            if api_reader.is_available():
                mcp_reader = api_reader
                logger.info(f"📡 Using HTTP API reader for instance {instance_id} (bypassing filesystem sync)")
            else:
                mcp_reader = MCPDatabaseReader(instance.messages_db_path, contact_mappings=contact_mappings)
                logger.warning(f"⚠️  Using SQLite reader for instance {instance_id} (API not available)")

            # Create agent router
            # Phase 10: Pass mcp_instance_id for channel-based agent filtering
            agent_router = AgentRouter(db, config_dict, mcp_reader=mcp_reader, mcp_instance_id=instance_id)

            # Determine starting timestamp to prevent message replay on new instances
            # For dynamically started watchers, use creation time if instance is new
            from datetime import datetime, timedelta
            starting_timestamp = None
            if instance.created_at:
                age_minutes = (datetime.utcnow() - instance.created_at).total_seconds() / 60
                if age_minutes < 5:
                    # New instance - skip messages older than creation time
                    starting_timestamp = instance.created_at.strftime("%Y-%m-%d %H:%M:%S+00:00")
                    logger.info(f"🆕 Instance {instance_id} is new ({age_minutes:.1f}min old), will skip history sync messages")

            # Create watcher with the selected reader (API or SQLite)
            delay_seconds = config.whatsapp_conversation_delay_seconds
            if delay_seconds is None:
                delay_seconds = settings.WHATSAPP_CONVERSATION_DELAY_SECONDS
            watcher = MCPWatcher(
                reader=mcp_reader,  # Pass the reader directly instead of db_path
                message_filter=message_filter,
                on_message_callback=agent_router.route_message,
                poll_interval_ms=settings.POLL_INTERVAL_MS,
                contact_mappings=contact_mappings,
                db_session=db,
                starting_timestamp=starting_timestamp,
                whatsapp_conversation_delay_seconds=delay_seconds
            )

            # Start watcher task
            watcher_task = asyncio.create_task(watcher.start())

            # Store in app state
            self.app_state.watchers[instance_id] = watcher
            self.app_state.watcher_tasks[instance_id] = watcher_task

            logger.info(f"✅ Watcher started dynamically for instance {instance_id} (tenant: {instance.tenant_id}, port: {instance.mcp_port})")

            return True

        except Exception as e:
            logger.error(f"Failed to start watcher for instance {instance_id}: {e}", exc_info=True)
            return False

    async def pause_watcher_for_instance(self, instance_id: int) -> bool:
        """
        Pause watcher for a specific MCP instance (Bug Fix 2026-01-06)

        Args:
            instance_id: MCP instance ID

        Returns:
            bool: True if watcher paused successfully
        """
        try:
            if instance_id not in self.app_state.watchers:
                logger.warning(f"No watcher found for instance {instance_id}, skipping")
                return False

            watcher = self.app_state.watchers[instance_id]
            watcher.pause()

            logger.info(f"⏸  Watcher paused for instance {instance_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to pause watcher for instance {instance_id}: {e}", exc_info=True)
            return False

    async def resume_watcher_for_instance(self, instance_id: int) -> bool:
        """
        Resume watcher for a specific MCP instance (Bug Fix 2026-01-06)

        Args:
            instance_id: MCP instance ID

        Returns:
            bool: True if watcher resumed successfully
        """
        try:
            if instance_id not in self.app_state.watchers:
                logger.warning(f"No watcher found for instance {instance_id}, skipping")
                return False

            watcher = self.app_state.watchers[instance_id]
            watcher.resume()

            logger.info(f"▶️  Watcher resumed for instance {instance_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to resume watcher for instance {instance_id}: {e}", exc_info=True)
            return False

    def get_watcher_status(self, instance_id: int) -> dict:
        """
        Get watcher status for a specific instance (Bug Fix 2026-01-06)

        Args:
            instance_id: MCP instance ID

        Returns:
            dict: Watcher status (running, paused)
        """
        if instance_id not in self.app_state.watchers:
            return {"exists": False, "running": False, "paused": False}

        watcher = self.app_state.watchers[instance_id]
        return {
            "exists": True,
            "running": watcher.running,
            "paused": watcher.paused
        }

    async def stop_watcher_for_instance(self, instance_id: int) -> bool:
        """
        Stop and remove watcher for a specific MCP instance

        Args:
            instance_id: MCP instance ID

        Returns:
            bool: True if watcher stopped successfully
        """
        try:
            if instance_id not in self.app_state.watchers:
                logger.warning(f"No watcher found for instance {instance_id}, skipping")
                return False

            # Get watcher and task
            watcher = self.app_state.watchers[instance_id]
            watcher_task = self.app_state.watcher_tasks[instance_id]

            # Stop watcher
            watcher.stop()

            # Cancel task
            watcher_task.cancel()
            try:
                await watcher_task
            except asyncio.CancelledError:
                pass

            # Remove from app state
            del self.app_state.watchers[instance_id]
            del self.app_state.watcher_tasks[instance_id]

            logger.info(f"✅ Watcher stopped dynamically for instance {instance_id}")

            return True

        except Exception as e:
            logger.error(f"Failed to stop watcher for instance {instance_id}: {e}", exc_info=True)
            return False

    def reload_instance_filter(self, instance_id: int) -> bool:
        """
        Hot-reload message filter for a specific MCP instance

        Phase 17: Instance-Level Message Filtering
        Called when instance filter settings are updated via API.

        Args:
            instance_id: MCP instance ID

        Returns:
            bool: True if filter reloaded successfully
        """
        try:
            if instance_id not in self.app_state.watchers:
                logger.warning(f"No watcher found for instance {instance_id}, skipping filter reload")
                return False

            watcher = self.app_state.watchers[instance_id]

            # Get fresh instance data from database
            from db import get_db
            db = next(get_db())

            try:
                instance = db.query(WhatsAppMCPInstance).filter(
                    WhatsAppMCPInstance.id == instance_id
                ).first()

                if not instance:
                    logger.error(f"Instance {instance_id} not found in database")
                    return False

                config = db.query(Config).first()
                if not config:
                    logger.error("No config found")
                    return False

                # Parse instance filters
                def parse_json_field(field):
                    if field is None:
                        return None
                    if isinstance(field, list):
                        return field
                    if isinstance(field, str):
                        return json.loads(field) if field else None
                    return None

                instance_group_filters = parse_json_field(instance.group_filters)
                instance_number_filters = parse_json_field(instance.number_filters)
                instance_group_keywords = parse_json_field(instance.group_keywords)
                instance_dm_auto_mode = getattr(instance, 'dm_auto_mode', None)

                # Determine which filters to use
                use_instance_filters = (
                    instance_group_filters is not None or
                    instance_number_filters is not None or
                    instance_group_keywords is not None or
                    instance_dm_auto_mode is not None
                )

                if use_instance_filters:
                    base_group_filters = set(instance_group_filters or [])
                    base_number_filters = instance_number_filters or []
                    base_group_keywords = instance_group_keywords or []
                    base_dm_auto_mode = instance_dm_auto_mode if instance_dm_auto_mode is not None else False
                else:
                    base_group_filters = set(config.group_filters or [])
                    base_number_filters = config.number_filters or []
                    base_group_keywords = json.loads(config.group_keywords) if config.group_keywords else []
                    base_dm_auto_mode = config.dm_auto_mode

                # Add agent-specific group filters
                all_group_filters = base_group_filters.copy()
                active_agents = db.query(Agent).filter(
                    Agent.is_active == True,
                    Agent.tenant_id == instance.tenant_id
                ).all()

                for agent in active_agents:
                    if agent.trigger_group_filters:
                        agent_filters = json.loads(agent.trigger_group_filters) if isinstance(agent.trigger_group_filters, str) else agent.trigger_group_filters
                        if agent_filters:
                            all_group_filters.update(agent_filters)

                # Update watcher's filter
                watcher.filter.update_filters(
                    group_filters=list(all_group_filters),
                    number_filters=base_number_filters,
                    agent_number=config.agent_number,
                    dm_auto_mode=base_dm_auto_mode,
                    agent_phone_number=instance.phone_number,
                    agent_name=config.agent_name,
                    group_keywords=base_group_keywords
                )

                logger.info(f"✅ Filter reloaded for instance {instance_id}: groups={len(all_group_filters)}, numbers={len(base_number_filters)}, keywords={len(base_group_keywords)}")
                return True

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Failed to reload filter for instance {instance_id}: {e}", exc_info=True)
            return False
