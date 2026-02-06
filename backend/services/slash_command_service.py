"""
Phase 16: Slash Command Service

Centralized service for detecting and executing slash commands.
Supports multilingual commands and works across all channels.
"""

import re
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from functools import lru_cache

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class SlashCommandService:
    """
    Service for managing and executing slash commands.

    Features:
    - Pattern matching with regex support
    - Multilingual command detection
    - Command aliasing
    - Built-in and custom handlers
    - Cross-channel support
    - Command caching for performance
    """

    # Cache for compiled patterns
    _pattern_cache: Dict[str, List[Tuple[re.Pattern, Dict]]] = {}

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)

    # =========================================================================
    # Command Registry
    # =========================================================================

    def get_commands(
        self,
        tenant_id: str,
        category: Optional[str] = None,
        language_code: Optional[str] = None,
        include_disabled: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get available slash commands.

        Args:
            tenant_id: Tenant ID
            category: Filter by category
            language_code: Filter by language
            include_disabled: Include disabled commands
        """
        from models import SlashCommand

        query = self.db.query(SlashCommand).filter(
            SlashCommand.tenant_id.in_([tenant_id, "_system"])
        )

        if category:
            query = query.filter(SlashCommand.category == category)

        if language_code:
            query = query.filter(SlashCommand.language_code == language_code)

        if not include_disabled:
            query = query.filter(SlashCommand.is_enabled == True)

        commands = query.order_by(SlashCommand.sort_order, SlashCommand.command_name).all()

        # Tenant commands override system commands
        result = {}
        for cmd in commands:
            key = f"{cmd.command_name}_{cmd.language_code}"
            if cmd.tenant_id == tenant_id or key not in result:
                # Parse aliases if it's a JSON string (SQLite stores JSON as text)
                aliases = cmd.aliases if cmd.aliases else []
                if isinstance(aliases, str):
                    try:
                        aliases = json.loads(aliases)
                    except (json.JSONDecodeError, TypeError):
                        aliases = []

                result[key] = {
                    "id": cmd.id,
                    "category": cmd.category,
                    "command_name": cmd.command_name,
                    "language_code": cmd.language_code,
                    "pattern": cmd.pattern,
                    "aliases": aliases,
                    "description": cmd.description,
                    "help_text": cmd.help_text,
                    "is_enabled": cmd.is_enabled,
                    "handler_type": cmd.handler_type,
                    "sort_order": cmd.sort_order
                }

        return list(result.values())

    def get_commands_by_category(
        self,
        tenant_id: str,
        language_code: str = "en"
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get commands organized by category for UI display."""
        commands = self.get_commands(tenant_id, language_code=language_code)

        by_category = {}
        for cmd in commands:
            cat = cmd["category"]
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(cmd)

        return by_category

    # =========================================================================
    # Command Detection
    # =========================================================================

    def _get_compiled_patterns(self, tenant_id: str) -> List[Tuple[re.Pattern, Dict]]:
        """Get compiled regex patterns for command matching."""
        cache_key = tenant_id

        if cache_key in self._pattern_cache:
            return self._pattern_cache[cache_key]

        commands = self.get_commands(tenant_id)
        patterns = []

        for cmd in commands:
            try:
                pattern = re.compile(cmd["pattern"], re.IGNORECASE)
                patterns.append((pattern, cmd))

                # Also compile aliases
                for alias in cmd.get("aliases", []):
                    # Replace command name in pattern with alias
                    alias_pattern = cmd["pattern"].replace(
                        cmd["command_name"].split()[0],
                        alias
                    )
                    try:
                        alias_compiled = re.compile(alias_pattern, re.IGNORECASE)
                        patterns.append((alias_compiled, cmd))
                    except re.error:
                        pass
            except re.error as e:
                self.logger.warning(f"Invalid pattern for command {cmd['command_name']}: {e}")

        self._pattern_cache[cache_key] = patterns
        return patterns

    def detect_command(
        self,
        message: str,
        tenant_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Detect if a message is a slash command.

        Args:
            message: The message text
            tenant_id: Tenant ID for command lookup

        Returns:
            Dict with command info and matched groups, or None if not a command
        """
        if not message or not message.startswith("/"):
            return None

        message = message.strip()
        patterns = self._get_compiled_patterns(tenant_id)

        for pattern, cmd in patterns:
            match = pattern.match(message)
            if match:
                return {
                    "command": cmd,
                    "groups": match.groups(),
                    "full_match": match.group(0),
                    "args": message[len(match.group(0)):].strip()
                }

        return None

    def is_command(self, message: str) -> bool:
        """Quick check if message looks like a command."""
        return bool(message and message.startswith("/"))

    # =========================================================================
    # Command Execution
    # =========================================================================

    async def execute_command(
        self,
        message: str,
        tenant_id: str,
        agent_id: int,
        sender_key: str,
        channel: str = "playground",
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Execute a slash command.

        Args:
            message: The command message
            tenant_id: Tenant ID
            agent_id: Current agent ID
            sender_key: User identifier
            channel: Channel type (playground, whatsapp, etc.)
            user_id: Optional user ID (for playground)

        Returns:
            Dict with execution result
        """
        detection = self.detect_command(message, tenant_id)

        if not detection:
            return {
                "status": "not_command",
                "message": message
            }

        cmd = detection["command"]
        handler_type = cmd.get("handler_type", "built-in")

        if handler_type == "built-in":
            return await self._execute_builtin(
                cmd=cmd,
                groups=detection["groups"],
                args=detection["args"],
                tenant_id=tenant_id,
                agent_id=agent_id,
                sender_key=sender_key,
                channel=channel,
                user_id=user_id
            )
        elif handler_type == "custom":
            return await self._execute_custom(cmd, detection)
        elif handler_type == "webhook":
            return await self._execute_webhook(cmd, detection)
        else:
            return {
                "status": "error",
                "error": f"Unknown handler type: {handler_type}"
            }

    async def _execute_builtin(
        self,
        cmd: Dict,
        groups: tuple,
        args: str,
        tenant_id: str,
        agent_id: int,
        sender_key: str,
        channel: str,
        user_id: Optional[int]
    ) -> Dict[str, Any]:
        """Execute a built-in command handler."""
        command_name = cmd["command_name"].lower()
        category = cmd["category"]

        # Route to appropriate handler based on category and command
        handlers = {
            # Invocation commands
            ("invocation", "invoke"): self._handle_invoke,
            ("invocation", "invocar"): self._handle_invoke,

            # Project commands
            ("project", "project enter"): self._handle_project_enter,
            ("project", "projeto entrar"): self._handle_project_enter,
            ("project", "project exit"): self._handle_project_exit,
            ("project", "projeto sair"): self._handle_project_exit,
            ("project", "project list"): self._handle_project_list,
            ("project", "projeto listar"): self._handle_project_list,
            ("project", "project info"): self._handle_project_info,

            # Agent commands
            ("agent", "agent info"): self._handle_agent_info,
            ("agent", "agent skills"): self._handle_agent_skills,
            ("agent", "agent list"): self._handle_agent_list,

            # Memory commands
            ("memory", "memory clear"): self._handle_memory_clear,
            ("memory", "memoria limpar"): self._handle_memory_clear,
            ("memory", "memory status"): self._handle_memory_status,
            ("memory", "facts list"): self._handle_facts_list,

            # System commands
            ("system", "commands"): self._handle_commands_list,
            ("system", "help"): self._handle_help,
            ("system", "status"): self._handle_status,
            ("system", "shortcuts"): self._handle_shortcuts,
            # BUG-014 Fix: Tools listing command
            ("system", "tools"): self._handle_tools_list,
            ("system", "ferramentas"): self._handle_tools_list,

            # Tool output injection commands
            ("tool", "inject"): self._handle_inject,
            ("tool", "inject list"): self._handle_inject,
            ("tool", "inject clear"): self._handle_inject,
            ("tool", "injetar"): self._handle_inject,
            ("tool", "recall"): self._handle_inject,

            # Flows/Automation commands
            ("flows", "flows run"): self._handle_flows_run,
            ("flows", "flows list"): self._handle_flows_list,

            # Scheduler commands
            ("scheduler", "scheduler info"): self._handle_scheduler_info,
            ("scheduler", "scheduler list"): self._handle_scheduler_list,
            ("scheduler", "scheduler create"): self._handle_scheduler_create,
            ("scheduler", "scheduler update"): self._handle_scheduler_update,
            ("scheduler", "scheduler delete"): self._handle_scheduler_delete,

            # Thread control commands
            ("thread", "thread end"): self._handle_thread_end,
            ("thread", "thread encerrar"): self._handle_thread_end,
            ("thread", "thread list"): self._handle_thread_list,
            ("thread", "thread status"): self._handle_thread_status,

            # Shell commands (Phase 18.3) - Only /shell is supported
            # Using programmatic execution (fire-and-forget), bypasses agentic mode
            ("tool", "shell"): self._handle_shell,

            # Email commands - programmatic Gmail access (zero AI tokens)
            ("email", "email info"): self._handle_email_info,
            ("email", "email list"): self._handle_email_list,
            ("email", "email read"): self._handle_email_read,
            ("email", "email inbox"): self._handle_email_inbox,
            ("email", "email search"): self._handle_email_search,
            ("email", "email unread"): self._handle_email_unread,

            # Weather commands - programmatic weather access (zero AI tokens)
            ("tool", "weather"): self._handle_weather,
            ("tool", "weather forecast"): self._handle_weather_forecast,

            # Search commands - programmatic web search (zero AI tokens)
            ("tool", "search"): self._handle_search,
        }

        handler = handlers.get((category, command_name))

        if handler:
            return await handler(
                groups=groups,
                args=args,
                tenant_id=tenant_id,
                agent_id=agent_id,
                sender_key=sender_key,
                channel=channel,
                user_id=user_id
            )

        # Fallback for tool commands - pass to tool execution
        if category == "tool":
            return await self._handle_tool_command(
                cmd=cmd,
                groups=groups,
                args=args,
                tenant_id=tenant_id,
                agent_id=agent_id,
                sender_key=sender_key
            )

        return {
            "status": "error",
            "error": f"No handler for command: {command_name}"
        }

    async def _execute_custom(self, cmd: Dict, detection: Dict) -> Dict[str, Any]:
        """Execute a custom command handler."""
        # Custom handlers are defined in handler_config
        handler_config = json.loads(cmd.get("handler_config", "{}"))

        return {
            "status": "custom",
            "command": cmd["command_name"],
            "config": handler_config,
            "args": detection["groups"]
        }

    async def _execute_webhook(self, cmd: Dict, detection: Dict) -> Dict[str, Any]:
        """Execute a webhook command handler."""
        handler_config = json.loads(cmd.get("handler_config", "{}"))
        webhook_url = handler_config.get("url")

        if not webhook_url:
            return {"status": "error", "error": "No webhook URL configured"}

        # TODO: Implement webhook call
        return {
            "status": "webhook",
            "command": cmd["command_name"],
            "url": webhook_url,
            "args": detection["groups"]
        }

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _resolve_agent_name(self, agent_name_input: str, tenant_id: str) -> Optional[tuple]:
        """
        Resolve agent name to Agent object with fuzzy matching.

        Returns:
            Tuple of (Agent, agent_name) or None if not found
        """
        from models import Agent, Contact

        agents = self.db.query(Agent).filter(
            Agent.tenant_id == tenant_id,
            Agent.is_active == True
        ).all()

        # Try exact match first
        for agent in agents:
            contact = self.db.query(Contact).filter(Contact.id == agent.contact_id).first()
            if contact and contact.friendly_name.lower() == agent_name_input.lower():
                return (agent, contact.friendly_name)

        # Try partial match (case-insensitive)
        for agent in agents:
            contact = self.db.query(Contact).filter(Contact.id == agent.contact_id).first()
            if contact and agent_name_input.lower() in contact.friendly_name.lower():
                return (agent, contact.friendly_name)

        return None

    # =========================================================================
    # Built-in Command Handlers
    # =========================================================================

    async def _handle_invoke(self, **kwargs) -> Dict[str, Any]:
        """
        Handle /invoke agent_name.

        Resolves the agent name, updates the UserAgentSession to persist the switch,
        and returns the agent ID for the frontend.
        """
        from models import Agent, Contact, UserAgentSession

        groups = kwargs.get("groups", ())
        agent_name_input = groups[0] if groups else ""
        tenant_id = kwargs.get("tenant_id")
        sender_key = kwargs.get("sender_key")
        channel = kwargs.get("channel", "playground")
        user_id = kwargs.get("user_id")

        if not agent_name_input:
            return {
                "status": "error",
                "action": "switch_agent",
                "message": "❌ **Usage:** `/invoke <agent_name>`\n\n**Example:** `/invoke kira`"
            }

        # Resolve agent name to ID
        resolved = self._resolve_agent_name(agent_name_input, tenant_id)

        if not resolved:
            # Get list of available agents for error message
            agents = self.db.query(Agent).filter(
                Agent.tenant_id == tenant_id,
                Agent.is_active == True
            ).all()

            agent_names = []
            for agent in agents:
                contact = self.db.query(Contact).filter(Contact.id == agent.contact_id).first()
                if contact:
                    agent_names.append(contact.friendly_name)

            return {
                "status": "error",
                "action": "switch_agent",
                "message": f"❌ **Agent '{agent_name_input}' not found.**\n\n**Available agents:**\n{', '.join(agent_names)}"
            }

        target_agent, agent_name = resolved

        # Update UserAgentSession to persist the switch
        try:
            session = self.db.query(UserAgentSession).filter(
                UserAgentSession.user_identifier == sender_key
            ).first()

            if session:
                session.agent_id = target_agent.id
                self.logger.info(f"Updated UserAgentSession for {sender_key} to agent {target_agent.id}")
            else:
                session = UserAgentSession(
                    user_identifier=sender_key,
                    agent_id=target_agent.id
                )
                self.db.add(session)
                self.logger.info(f"Created UserAgentSession for {sender_key} with agent {target_agent.id}")

            self.db.commit()

            return {
                "status": "success",
                "action": "switch_agent",
                "agent_name": agent_name,
                "agent_id": target_agent.id,
                "data": {
                    "agent_id": target_agent.id
                },
                "message": f"🔄 **Switched to agent:** {agent_name}\n\nYour messages will now go to this agent."
            }
        except Exception as e:
            self.logger.error(f"Error switching to agent {agent_name}: {e}", exc_info=True)
            self.db.rollback()
            return {
                "status": "error",
                "action": "switch_agent",
                "message": f"❌ **Failed to switch to agent {agent_name}:**\n{str(e)}"
            }

    async def _handle_project_enter(self, **kwargs) -> Dict[str, Any]:
        """Handle /project enter project_name."""
        from services.project_command_service import ProjectCommandService

        groups = kwargs.get("groups", ())
        project_name = groups[0] if groups else ""
        tenant_id = kwargs.get("tenant_id")
        agent_id = kwargs.get("agent_id")
        sender_key = kwargs.get("sender_key")
        channel = kwargs.get("channel")

        service = ProjectCommandService(self.db)
        result = await service.execute_enter(
            tenant_id=tenant_id,
            sender_key=sender_key,
            agent_id=agent_id,
            channel=channel,
            project_identifier=project_name
        )

        # Add action for frontend to handle
        if result.get("status") == "success" or result.get("status") == "already_in_project":
            result["action"] = "project_entered"
            result["data"] = {
                "project_id": result.get("project_id"),
                "project_name": result.get("project_name")
            }

        return result

    async def _handle_project_exit(self, **kwargs) -> Dict[str, Any]:
        """Handle /project exit."""
        from services.project_command_service import ProjectCommandService

        tenant_id = kwargs.get("tenant_id")
        agent_id = kwargs.get("agent_id")
        sender_key = kwargs.get("sender_key")
        channel = kwargs.get("channel")

        service = ProjectCommandService(self.db)
        result = await service.execute_exit(
            tenant_id=tenant_id,
            sender_key=sender_key,
            agent_id=agent_id,
            channel=channel
        )

        # Add action for frontend to handle
        if result.get("status") == "success":
            result["action"] = "project_exited"

        return result

    async def _handle_project_list(self, **kwargs) -> Dict[str, Any]:
        """Handle /project list."""
        from services.project_command_service import ProjectCommandService

        tenant_id = kwargs.get("tenant_id")
        agent_id = kwargs.get("agent_id")
        sender_key = kwargs.get("sender_key")

        service = ProjectCommandService(self.db)
        result = await service.execute_list(
            tenant_id=tenant_id,
            sender_key=sender_key,
            agent_id=agent_id
        )

        return result

    async def _handle_project_info(self, **kwargs) -> Dict[str, Any]:
        """Handle /project info."""
        from services.project_command_service import ProjectCommandService
        from models import UserProjectSession, Project

        tenant_id = kwargs.get("tenant_id")
        agent_id = kwargs.get("agent_id")
        sender_key = kwargs.get("sender_key")
        channel = kwargs.get("channel")

        # Get current session
        session = self.db.query(UserProjectSession).filter(
            UserProjectSession.tenant_id == tenant_id,
            UserProjectSession.sender_key == sender_key,
            UserProjectSession.agent_id == agent_id,
            UserProjectSession.channel == channel
        ).first()

        if not session or not session.project_id:
            return {
                "status": "success",
                "message": "ℹ️ You are not currently in any project."
            }

        project = self.db.query(Project).filter(Project.id == session.project_id).first()

        if not project:
            return {
                "status": "success",
                "message": "❌ Project not found."
            }

        from services.project_memory_service import ProjectMemoryService
        memory_service = ProjectMemoryService(self.db)
        stats = await memory_service.get_memory_stats(project.id)

        return {
            "status": "success",
            "action": "project_info",
            "project": {
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "documents": stats["kb_document_count"],
                "facts": stats["fact_count"],
                "conversations": stats["conversation_count"]
            },
            "message": f"""📁 **Project: {project.name}**
{project.description or ''}

📊 **Statistics:**
• Documents: {stats['kb_document_count']}
• Facts: {stats['fact_count']}
• Conversations: {stats['conversation_count']}
• Memory entries: {stats['semantic_memory_count']}"""
        }

    async def _handle_agent_switch(self, **kwargs) -> Dict[str, Any]:
        """
        Handle /switch agent_name.

        Resolves the agent name, updates the UserAgentSession to persist the switch,
        and returns the agent ID for the frontend.
        """
        from models import Agent, Contact, UserAgentSession

        groups = kwargs.get("groups", ())
        agent_name_input = groups[0] if groups else ""
        tenant_id = kwargs.get("tenant_id")
        sender_key = kwargs.get("sender_key")
        channel = kwargs.get("channel", "playground")
        user_id = kwargs.get("user_id")

        if not agent_name_input:
            return {
                "status": "error",
                "action": "switch_agent",
                "message": "❌ **Usage:** `/switch <agent_name>`\n\n**Example:** `/switch kira`"
            }

        # Resolve agent name to ID
        resolved = self._resolve_agent_name(agent_name_input, tenant_id)

        if not resolved:
            # Get list of available agents for error message
            agents = self.db.query(Agent).filter(
                Agent.tenant_id == tenant_id,
                Agent.is_active == True
            ).all()

            agent_names = []
            for agent in agents:
                contact = self.db.query(Contact).filter(Contact.id == agent.contact_id).first()
                if contact:
                    agent_names.append(contact.friendly_name)

            return {
                "status": "error",
                "action": "switch_agent",
                "message": f"❌ **Agent '{agent_name_input}' not found.**\n\n**Available agents:**\n{', '.join(agent_names)}"
            }

        target_agent, agent_name = resolved

        # Update UserAgentSession to persist the switch
        try:
            session = self.db.query(UserAgentSession).filter(
                UserAgentSession.user_identifier == sender_key
            ).first()

            if session:
                session.agent_id = target_agent.id
                self.logger.info(f"Updated UserAgentSession for {sender_key} to agent {target_agent.id}")
            else:
                session = UserAgentSession(
                    user_identifier=sender_key,
                    agent_id=target_agent.id
                )
                self.db.add(session)
                self.logger.info(f"Created UserAgentSession for {sender_key} with agent {target_agent.id}")

            self.db.commit()

            return {
                "status": "success",
                "action": "switch_agent",
                "agent_name": agent_name,
                "agent_id": target_agent.id,
                "data": {
                    "agent_id": target_agent.id
                },
                "message": f"🔄 **Switched to agent:** {agent_name}\n\nYour messages will now go to this agent."
            }
        except Exception as e:
            self.logger.error(f"Error switching to agent {agent_name}: {e}", exc_info=True)
            self.db.rollback()
            return {
                "status": "error",
                "action": "switch_agent",
                "message": f"❌ **Failed to switch to agent {agent_name}:**\n{str(e)}"
            }

    async def _handle_agent_info(self, **kwargs) -> Dict[str, Any]:
        """Handle /agent info."""
        from models import Agent, Contact

        agent_id = kwargs.get("agent_id")
        agent = self.db.query(Agent).filter(Agent.id == agent_id).first()

        if not agent:
            return {
                "status": "error",
                "action": "agent_info",
                "error": "Agent not found",
                "message": "❌ Agent not found"
            }

        # Get agent name from contact
        contact = self.db.query(Contact).filter(Contact.id == agent.contact_id).first()
        agent_name = contact.friendly_name if contact else f"Agent {agent.id}"

        return {
            "status": "success",
            "action": "agent_info",
            "agent": {
                "id": agent.id,
                "name": agent_name,
                "model": agent.model_name,
                "provider": agent.model_provider
            },
            "message": f"""🤖 **Agent: {agent_name}**

• Model: {agent.model_name}
• Provider: {agent.model_provider}
• Status: {'🟢 Active' if agent.is_active else '⚪ Inactive'}"""
        }

    async def _handle_agent_skills(self, **kwargs) -> Dict[str, Any]:
        """Handle /agent skills."""
        from models import Agent, AgentSkill

        agent_id = kwargs.get("agent_id")

        skills = self.db.query(AgentSkill).filter(
            AgentSkill.agent_id == agent_id,
            AgentSkill.is_enabled == True
        ).all()

        skill_names = [s.skill_type for s in skills]

        return {
            "status": "success",
            "action": "agent_skills",
            "skills": skill_names,
            "message": f"""⚡ **Active Skills:**

{chr(10).join(f'• {s}' for s in skill_names) if skill_names else '• No skills enabled'}"""
        }

    async def _handle_agent_list(self, **kwargs) -> Dict[str, Any]:
        """Handle /agent list - show all agents with their configuration."""
        from models import Agent, Contact, AgentSkill, SandboxedTool
        from sqlalchemy.orm import joinedload

        tenant_id = kwargs.get("tenant_id")

        try:
            # Query agents for the current tenant
            query = self.db.query(Agent).filter(Agent.is_active == True)
            if tenant_id:
                query = query.filter(Agent.tenant_id == tenant_id)
            agents = query.all()

            if not agents:
                return {
                    "status": "success",
                    "action": "agent_list",
                    "agents": [],
                    "message": "📋 No agents available."
                }

            agent_list = []
            lines = ["📋 **Available Agents:**\n"]

            for agent in agents:
                # Get agent name from contact
                contact = self.db.query(Contact).filter(Contact.id == agent.contact_id).first()
                agent_name = contact.friendly_name if contact else f"Agent {agent.id}"

                # Get enabled skills
                skills = self.db.query(AgentSkill).filter(
                    AgentSkill.agent_id == agent.id,
                    AgentSkill.is_enabled == True
                ).all()
                skill_names = [s.skill_type for s in skills]
                skills_str = ", ".join(skill_names) if skill_names else "None"

                # Get tools count (from agent's custom tools if available)
                # Note: Tool association varies by implementation
                tools_count = 0
                try:
                    # Try to get tools from AgentToolMapping or similar
                    from models import AgentSandboxedTool
                    tools_count = self.db.query(AgentSandboxedTool).filter(
                        AgentSandboxedTool.agent_id == agent.id
                    ).count()
                except:
                    pass

                # Build agent info
                status_icon = "🟢" if agent.is_active else "⚪"
                model_info = f"{agent.model_provider}/{agent.model_name}"

                agent_info = {
                    "id": agent.id,
                    "name": agent_name,
                    "status": "enabled" if agent.is_active else "disabled",
                    "model": model_info,
                    "skills": skill_names,
                    "tools_count": tools_count
                }
                agent_list.append(agent_info)

                # Format for message display
                lines.append(f"\n**{status_icon} {agent_name}**")
                lines.append(f"  • Model: `{model_info}`")
                lines.append(f"  • Skills: {skills_str}")
                if tools_count > 0:
                    lines.append(f"  • Tools: {tools_count}")

            return {
                "status": "success",
                "action": "agent_list",
                "agents": agent_list,
                "message": "\n".join(lines)
            }

        except Exception as e:
            self.logger.error(f"Error in _handle_agent_list: {e}", exc_info=True)
            return {
                "status": "error",
                "action": "agent_list",
                "error": f"Failed to list agents: {str(e)}",
                "message": f"❌ Failed to list agents: {str(e)}"
            }

    async def _handle_memory_clear(self, **kwargs) -> Dict[str, Any]:
        """Handle /memory clear."""
        return {
            "status": "success",
            "action": "clear_memory",
            "message": "🧹 Conversation memory cleared."
        }

    async def _handle_memory_status(self, **kwargs) -> Dict[str, Any]:
        """Handle /memory status."""
        return {
            "status": "success",
            "action": "memory_status",
            "message": "📊 Memory status retrieved."
        }

    async def _handle_facts_list(self, **kwargs) -> Dict[str, Any]:
        """Handle /facts list."""
        return {
            "status": "success",
            "action": "list_facts",
            "message": "📋 Listing learned facts..."
        }

    async def _handle_commands_list(self, **kwargs) -> Dict[str, Any]:
        """Handle /commands."""
        tenant_id = kwargs.get("tenant_id")

        commands_by_cat = self.get_commands_by_category(tenant_id)

        # Define category display order (unlisted categories appear at end)
        category_order = [
            "invocation",
            "project",
            "agent",
            "memory",
            "system",
            "email",
            "scheduler",
            "flows",
            "tool",
        ]

        # Sort categories by order, then alphabetically for unlisted ones
        def category_sort_key(cat):
            try:
                return (0, category_order.index(cat))
            except ValueError:
                return (1, cat)

        sorted_categories = sorted(commands_by_cat.keys(), key=category_sort_key)

        lines = ["📋 **Available Commands:**\n"]
        for cat in sorted_categories:
            cmds = commands_by_cat[cat]
            lines.append(f"\n**{cat.upper()}**")
            for cmd in cmds:
                aliases = cmd.get("aliases", [])
                alias_str = f" ({', '.join(aliases)})" if aliases else ""
                lines.append(f"• `/{cmd['command_name']}`{alias_str} - {cmd.get('description', '')}")

        # Add helpful footer
        lines.append("\n\n💡 **Tip:** Use `/help <command>` to see detailed syntax and examples.")
        lines.append("Examples: `/help scheduler create`, `/help project enter`")

        return {
            "status": "success",
            "action": "list_commands",
            "commands": commands_by_cat,
            "message": "\n".join(lines)
        }

    async def _handle_help(self, **kwargs) -> Dict[str, Any]:
        """Handle /help [command]."""
        groups = kwargs.get("groups", ())
        command_name = groups[0].strip() if groups and groups[0] else ""
        tenant_id = kwargs.get("tenant_id")

        if command_name:
            # Handle special case: /help all - show all commands with syntax
            if command_name.lower() == "all":
                commands = self.get_commands(tenant_id)
                commands_by_cat = {}
                for cmd in commands:
                    cat = cmd.get("category", "other").upper()
                    if cat not in commands_by_cat:
                        commands_by_cat[cat] = []
                    commands_by_cat[cat].append(cmd)

                lines = ["📚 **All Commands with Syntax**\n"]
                for cat in sorted(commands_by_cat.keys()):
                    lines.append(f"\n**{cat}**")
                    for cmd in commands_by_cat[cat]:
                        help_text = cmd.get('help_text', '')
                        # Extract just the usage line if available
                        usage = help_text.split('\n')[0] if help_text else f"/{cmd['command_name']}"
                        lines.append(f"• {usage}")

                return {
                    "status": "success",
                    "action": "help_all",
                    "message": "\n".join(lines)
                }

            # Get specific command help
            commands = self.get_commands(tenant_id)
            for cmd in commands:
                if cmd["command_name"].lower() == command_name.lower():
                    return {
                        "status": "success",
                        "action": "help",
                        "command": cmd,
                        "message": f"""❓ **Help: /{cmd['command_name']}**

{cmd.get('description', '')}

{cmd.get('help_text', '')}"""
                    }

            return {
                "status": "success",
                "action": "help",
                "message": f"❓ Command `/{command_name}` not found. Use `/commands` to see available commands."
            }

        return {
            "status": "success",
            "action": "help",
            "message": """❓ **Help**

Type `/commands` to see all available commands.
Type `/help <command>` for help on a specific command.
Type `/help all` to see syntax for all commands.

**Quick Tips:**
• Commands start with `/`
• Most commands have aliases for quick access
• Commands work across all channels

**Examples:**
• `/help scheduler create`
• `/help project enter`
• `/help tool`"""
        }

    async def _handle_status(self, **kwargs) -> Dict[str, Any]:
        """Handle /status."""
        from models import Agent, UserProjectSession

        agent_id = kwargs.get("agent_id")
        sender_key = kwargs.get("sender_key")
        tenant_id = kwargs.get("tenant_id")
        channel = kwargs.get("channel")

        agent = self.db.query(Agent).filter(Agent.id == agent_id).first()

        # Check if in project
        session = self.db.query(UserProjectSession).filter(
            UserProjectSession.tenant_id == tenant_id,
            UserProjectSession.sender_key == sender_key,
            UserProjectSession.agent_id == agent_id,
            UserProjectSession.channel == channel
        ).first()

        project_status = "Not in project"
        if session and session.project_id:
            from models import Project
            project = self.db.query(Project).filter(Project.id == session.project_id).first()
            if project:
                project_status = f"📁 {project.name}"

        return {
            "status": "success",
            "action": "status",
            "message": f"""📊 **System Status**

🤖 **Agent:** {agent.name if agent else 'Unknown'}
📺 **Channel:** {channel}
📁 **Project:** {project_status}
⏰ **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M')}"""
        }

    async def _handle_shortcuts(self, **kwargs) -> Dict[str, Any]:
        """Handle /shortcuts."""
        return {
            "status": "success",
            "action": "shortcuts",
            "message": """⌨️ **Keyboard Shortcuts**

| Shortcut | Action |
|----------|--------|
| `⌘K` | Command palette |
| `⌘.` | Toggle cockpit mode |
| `⌘/` | Focus with `/` |
| `⌘P` | Quick project switcher |
| `⌘E` | Quick agent switcher |
| `⌘⇧T` | Tool menu |
| `Esc` | Exit mode/close |
| `↑` | Edit last message |"""
        }

    async def _handle_tools_list(self, **kwargs) -> Dict[str, Any]:
        """
        Handle /tools command - list available tools for the current agent.
        BUG-014 Fix: Added tools listing command.
        """
        try:
            from models import Agent, SandboxedTool, SandboxedToolCommand, AgentSandboxedTool

            agent_id = kwargs.get("agent_id")
            tenant_id = kwargs.get("tenant_id")

            self.logger.info(f"Handling /tools command for agent_id={agent_id}, tenant_id={tenant_id}")

            if not agent_id:
                return {
                    "status": "error",
                    "message": "❌ No agent selected. Please select an agent first."
                }

            # Get agent
            agent = self.db.query(Agent).filter(
                Agent.id == agent_id,
                Agent.tenant_id == tenant_id
            ).first()

            if not agent:
                self.logger.error(f"Agent not found: id={agent_id}, tenant_id={tenant_id}")
                return {
                    "status": "error",
                    "message": f"❌ Agent not found (ID: {agent_id})"
                }

            lines = ["🔧 **Available Tools:**\n"]

            # Check for enabled skills (new Skills system)
            from models import AgentSkill
            agent_skills = self.db.query(AgentSkill).filter(
                AgentSkill.agent_id == agent_id,
                AgentSkill.is_enabled == True
            ).all()

            if agent_skills:
                lines.append("**Enabled Skills:**")
                skill_icons = {
                    "web_search": ("🔍", "Search the web"),
                    "weather": ("🌤️", "Get weather information"),
                    "web_scraping": ("📄", "Scrape web pages"),
                    "calendar": ("📅", "Manage calendar events"),
                    "flight_search": ("✈️", "Search for flights"),
                    "audio_transcript": ("🎙️", "Audio transcription"),
                }
                for skill in agent_skills:
                    icon, desc = skill_icons.get(skill.skill_type, ("⚙️", f"{skill.skill_type} skill"))
                    lines.append(f"• {icon} **{skill.skill_type}** - {desc}")
                lines.append("")

            # Sandboxed tools assigned to this agent
            agent_tools = self.db.query(AgentSandboxedTool).filter(
                AgentSandboxedTool.agent_id == agent_id,
                AgentSandboxedTool.is_enabled == True
            ).all()

            if agent_tools:
                lines.append("**Sandboxed Tools:**")
                for at in agent_tools:
                    sandboxed_tool = self.db.query(SandboxedTool).filter(
                        SandboxedTool.id == at.sandboxed_tool_id,
                        SandboxedTool.is_enabled == True
                    ).first()

                    if sandboxed_tool:
                        # Get commands for this tool
                        commands = self.db.query(SandboxedToolCommand).filter(
                            SandboxedToolCommand.tool_id == sandboxed_tool.id
                        ).all()

                        cmd_list = ", ".join([cmd.command_name for cmd in commands]) if commands else "No commands"
                        lines.append(f"• ⚡ **{sandboxed_tool.name}** ({sandboxed_tool.tool_type})")
                        lines.append(f"  Commands: {cmd_list}")
                lines.append("")
            else:
                lines.append("*No sandboxed tools assigned*\n")

            lines.append("💡 *Tip: Use `/tool <tool_name> [command] [args]` to execute a tool*")
            lines.append("Example: `/tool nmap localhost` or `/tool nmap quick_scan 192.168.1.1`")

            return {
                "status": "success",
                "action": "tools_list",
                "message": "\n".join(lines)
            }
        except Exception as e:
            self.logger.error(f"Error in _handle_tools_list: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"❌ Failed to list tools: {str(e)}"
            }

    async def _handle_inject(self, **kwargs) -> Dict[str, Any]:
        """
        Handle /inject command for selective tool output retrieval.

        Usage:
        - /inject                  - Inject latest tool output
        - /inject 3                - Inject execution #3
        - /inject nmap             - Inject latest nmap output
        - /inject nmap 2           - Inject nmap execution #2
        - /inject list             - List available executions
        - /inject clear            - Clear all injected tool outputs
        """
        from agent.memory.tool_output_buffer import get_tool_output_buffer

        args = kwargs.get("args", "")
        groups = kwargs.get("groups", ())
        agent_id = kwargs.get("agent_id")
        sender_key = kwargs.get("sender_key")

        # Parse args: could be empty, a number, a tool name, or "list"
        # Args come from captured groups (pattern: ^/inject\s*(.*)?$) OR from trailing text
        if not args and groups and groups[0]:
            args = groups[0]  # Use captured group from regex pattern
        args_parts = args.strip().split() if args else []

        buffer = get_tool_output_buffer()

        # Handle /inject list
        if args_parts and args_parts[0].lower() == "list":
            refs = buffer.list_available_executions(agent_id, sender_key)
            if not refs:
                return {
                    "status": "success",
                    "action": "inject_list",
                    "message": "📋 **No tool executions available.**\n\nRun a tool first, then use `/inject` to retrieve its output."
                }

            return {
                "status": "success",
                "action": "inject_list",
                "message": "📋 **Available Tool Executions:**\n\n" + "\n".join(f"  {ref}" for ref in refs) + "\n\n💡 Use `/inject [id]` to inject a specific execution."
            }

        # Handle /inject clear
        if args_parts and args_parts[0].lower() == "clear":
            count = buffer.clear_executions(agent_id, sender_key)
            if count == 0:
                return {
                    "status": "success",
                    "action": "inject_clear",
                    "message": "📋 **No tool executions to clear.**\n\nThe injection buffer is already empty."
                }

            return {
                "status": "success",
                "action": "inject_clear",
                "message": f"🧹 **Cleared {count} injected tool output{'s' if count != 1 else ''}.**\n\nThe injection buffer has been emptied."
            }

        # Determine what to inject
        execution_id = None
        tool_name = None

        for part in args_parts:
            if part.isdigit():
                execution_id = int(part)
            elif part.startswith("#") and part[1:].isdigit():
                execution_id = int(part[1:])
            else:
                tool_name = part.lower()

        # Get the execution
        if execution_id:
            execution = buffer.get_execution_by_id(agent_id, sender_key, execution_id)
            if not execution:
                refs = buffer.list_available_executions(agent_id, sender_key)
                available = "\n".join(f"  {ref}" for ref in refs) if refs else "  No executions available"
                return {
                    "status": "error",
                    "action": "inject_error",
                    "message": f"❌ **Execution #{execution_id} not found.**\n\n**Available:**\n{available}"
                }
        else:
            execution = buffer.get_latest_execution(agent_id, sender_key, tool_name)
            if not execution:
                if tool_name:
                    return {
                        "status": "error",
                        "action": "inject_error",
                        "message": f"❌ **No {tool_name} executions found.**\n\nRun `/{tool_name}` first or use `/inject list` to see available executions."
                    }
                return {
                    "status": "error",
                    "action": "inject_error",
                    "message": "❌ **No tool executions available.**\n\nRun a tool first, then use `/inject` to retrieve its output."
                }

        # Format and return the injection
        full_output = execution.to_full_context()

        # Mark this execution for pending injection so the NEXT message includes it in AI context
        # This is critical: /inject shows the output to the user, but the AI context
        # is built when processing the NEXT message. By marking it pending, the next
        # call to get_context_for_injection() will include this execution's full output.
        buffer.mark_pending_injection(agent_id, sender_key, execution.execution_id)

        return {
            "status": "success",
            "action": "inject_output",
            "execution_id": execution.execution_id,
            "tool_name": execution.tool_name,
            "command_name": execution.command_name,
            "output": full_output,
            "message": f"💉 **Injected Execution #{execution.execution_id}**\n\n{full_output}"
        }

    async def _handle_flows_run(self, **kwargs) -> Dict[str, Any]:
        """
        Handle /flows run <flow_name_or_id> command.

        Execute a workflow by name or ID.
        Requires AutomationSkill to be enabled for the agent.

        Examples:
        - /flows run 5
        - /flows run weekly-report
        """
        from services.flow_command_service import FlowCommandService
        from models import AgentSkill

        groups = kwargs.get("groups", ())
        flow_identifier = groups[0] if groups else ""
        tenant_id = kwargs.get("tenant_id")
        agent_id = kwargs.get("agent_id")
        sender_key = kwargs.get("sender_key")

        if not flow_identifier:
            return {
                "status": "error",
                "message": (
                    "❌ **Usage:** `/flows run <flow_name_or_id>`\n\n"
                    "**Examples:**\n"
                    "• `/flows run 5` - Run flow with ID 5\n"
                    "• `/flows run weekly-report` - Run flow by name\n\n"
                    "Use `/flows list` to see available flows."
                )
            }

        # Check if automation skill is enabled
        automation_skill = self.db.query(AgentSkill).filter(
            AgentSkill.agent_id == agent_id,
            AgentSkill.skill_type == "automation",
            AgentSkill.is_enabled == True
        ).first()

        if not automation_skill:
            return {
                "status": "error",
                "message": (
                    "❌ **Automation skill not enabled**\n\n"
                    "The Automation skill is required to use `/flows` commands.\n"
                    "Enable it in the agent settings to run workflows."
                )
            }

        # Execute flow via service
        service = FlowCommandService(self.db)
        result = await service.execute_run(
            tenant_id=tenant_id,
            agent_id=agent_id,
            flow_identifier=flow_identifier,
            sender_key=sender_key
        )

        return result

    async def _handle_flows_list(self, **kwargs) -> Dict[str, Any]:
        """
        Handle /flows list command.

        List all available workflows for the tenant.
        Requires AutomationSkill to be enabled for the agent.

        Example:
        - /flows list
        """
        from services.flow_command_service import FlowCommandService
        from models import AgentSkill

        tenant_id = kwargs.get("tenant_id")
        agent_id = kwargs.get("agent_id")

        # Check if automation skill is enabled
        automation_skill = self.db.query(AgentSkill).filter(
            AgentSkill.agent_id == agent_id,
            AgentSkill.skill_type == "automation",
            AgentSkill.is_enabled == True
        ).first()

        if not automation_skill:
            return {
                "status": "error",
                "message": (
                    "❌ **Automation skill not enabled**\n\n"
                    "The Automation skill is required to use `/flows` commands.\n"
                    "Enable it in the agent settings to manage workflows."
                )
            }

        # List flows via service
        service = FlowCommandService(self.db)
        result = await service.execute_list(
            tenant_id=tenant_id,
            agent_id=agent_id
        )

        return result

    async def _handle_tool_command(
        self,
        cmd: Dict,
        groups: tuple,
        args: str,
        tenant_id: str,
        agent_id: int,
        sender_key: str
    ) -> Dict[str, Any]:
        """
        Handle tool-related commands.

        Supports:
        - /tool <tool_name> <args> - Generic tool execution
        - /weather <location> - Direct weather tool
        - /search <query> - Direct search tool
        - /schedule <event> - Direct schedule tool

        Pattern for /tool: ^/tool\\s+(\\w+)\\s*(.*)$
        groups[0] = tool_name, groups[1] = arguments
        """
        command_name = cmd.get("command_name", "").lower()

        # Determine tool name and arguments based on command
        if command_name in ("tool", "ferramenta", "t", "f"):
            # Generic /tool <name> <args> command
            tool_name = groups[0].lower() if groups else ""
            tool_args = groups[1].strip() if len(groups) > 1 else ""
        else:
            # Direct tool command like /weather, /search
            tool_name = command_name
            tool_args = groups[0].strip() if groups else args

        if not tool_name:
            return {
                "status": "error",
                "message": "❌ Please specify a tool name. Usage: /tool <tool_name> [arguments]"
            }

        self.logger.info(f"Executing tool command: {tool_name} with args: {tool_args}")

        try:
            # Handle built-in tools
            if tool_name in ("weather", "clima", "w"):
                return await self._execute_weather_tool(tool_args, tenant_id)

            elif tool_name in ("search", "buscar", "s"):
                return await self._execute_search_tool(tool_args, tenant_id)

            elif tool_name in ("schedule", "agenda", "agendar"):
                return await self._execute_schedule_tool(tool_args, agent_id, sender_key, tenant_id)

            elif tool_name in ("flights", "voos", "flight"):
                return await self._execute_flights_tool(tool_args, agent_id, sender_key)

            else:
                # Try to execute as custom tool
                return await self._execute_sandboxed_tool(tool_name, tool_args, tenant_id, agent_id)

        except Exception as e:
            self.logger.error(f"Tool execution failed: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"❌ Tool execution failed: {str(e)}"
            }

    async def _execute_weather_tool(self, location: str, tenant_id: str) -> Dict[str, Any]:
        """Execute the weather tool."""
        if not location:
            return {
                "status": "error",
                "message": "❌ Please specify a location. Usage: /weather <city>\nExample: /weather New York"
            }

        try:
            from agent.tools.weather_tool import WeatherTool

            weather_tool = WeatherTool(db=self.db)

            # Check if forecast is requested
            is_forecast = any(word in location.lower() for word in ['forecast', 'próximos', 'next', 'previsão', 'week'])

            if is_forecast:
                # Remove forecast keywords from location
                clean_location = location
                for word in ['forecast', 'próximos dias', 'next days', 'previsão', 'week', 'semana']:
                    clean_location = clean_location.replace(word, '').strip()
                weather_data = weather_tool.get_forecast(clean_location or location, days=3)
                result = weather_tool.format_forecast_data(weather_data)
            else:
                weather_data = weather_tool.get_current_weather(location)
                result = weather_tool.format_weather_data(weather_data)

            return {
                "status": "success",
                "action": "tool_executed",
                "tool_name": "weather",
                "message": f"🌤️ **Weather for {location}**\n\n{result}"
            }
        except Exception as e:
            self.logger.error(f"Weather tool error: {e}")
            return {
                "status": "error",
                "message": f"❌ Failed to get weather: {str(e)}"
            }

    async def _execute_search_tool(self, query: str, tenant_id: str) -> Dict[str, Any]:
        """Execute the search tool."""
        if not query:
            return {
                "status": "error",
                "message": "❌ Please specify a search query. Usage: /search <query>\nExample: /search latest AI news"
            }

        try:
            from agent.tools.search_tool import SearchTool

            search_tool = SearchTool(db=self.db)
            search_data = search_tool.search(query, count=5)
            result = search_tool.format_search_results(search_data)

            return {
                "status": "success",
                "action": "tool_executed",
                "tool_name": "search",
                "message": f"🔍 **Search Results for: {query}**\n\n{result}"
            }
        except Exception as e:
            self.logger.error(f"Search tool error: {e}")
            return {
                "status": "error",
                "message": f"❌ Failed to search: {str(e)}"
            }

    async def _execute_schedule_tool(
        self,
        event_desc: str,
        agent_id: int,
        sender_key: str,
        tenant_id: str
    ) -> Dict[str, Any]:
        """Execute the schedule/reminder tool."""
        if not event_desc:
            return {
                "status": "error",
                "message": "❌ Please describe what to schedule. Usage: /schedule <event description>\nExample: /schedule meeting tomorrow at 3pm"
            }

        # For now, return a helpful message about scheduling
        # Full implementation would parse the event and create a reminder
        return {
            "status": "success",
            "action": "schedule_request",
            "message": f"📅 **Schedule Request**\n\nTo schedule \"{event_desc}\", please provide more details:\n• Date/Time\n• Duration\n• Any reminders needed\n\nOr use the full scheduling command:\n`/reminder set \"title\" in 1h`"
        }

    async def _execute_flights_tool(
        self,
        args: str,
        agent_id: int,
        sender_key: str
    ) -> Dict[str, Any]:
        """Execute the flights search tool via skill system."""
        if not args:
            return {
                "status": "error",
                "message": "❌ Please specify flight details. Usage: /flights <origin> to <destination> on <date>\nExample: /flights NYC to LAX on 2025-02-15"
            }

        # Flight search is handled by the skill system
        # Return guidance for using the full message flow
        return {
            "status": "success",
            "action": "flights_request",
            "message": f"✈️ **Flight Search**\n\nSearching for: {args}\n\nFor best results, send a complete message like:\n\"Find flights from New York to Los Angeles on February 15\"\n\nThe agent will use the FlightSearchSkill to find options."
        }

    def _parse_tool_arguments(
        self,
        args: List[str],
        cmd_params: List,
        tool_name: str,
        command_name: str
    ) -> Dict[str, str]:
        """
        Parse tool arguments with smart flag detection and named parameter support.

        Phase 16.1: Fix for nmap tool execution bug (2026-01-08)

        This parser addresses the issue where command-line flags (e.g., -sV, -A)
        were incorrectly mapped to tool parameters, causing tools like nmap to fail.

        Supported formats:
        1. Named parameters: target=localhost output_file=scan.txt
        2. Positional arguments: localhost scan.txt
        3. Mixed with flags (ignored): -sV localhost (flags are filtered out)

        Args:
            args: List of argument strings
            cmd_params: List of CustomToolParameter objects
            tool_name: Tool name (for logging)
            command_name: Command name (for logging)

        Returns:
            Dictionary mapping parameter names to values

        Examples:
            Input: ["-sV", "localhost"]
            Output: {"target": "localhost"}  (flag ignored)

            Input: ["target=localhost", "output_file=scan.txt"]
            Output: {"target": "localhost", "output_file": "scan.txt"}
        """
        parameters = {}

        # Check if using named parameter syntax (param=value)
        has_named_params = any('=' in arg and not arg.startswith('-') for arg in args)

        if has_named_params:
            # Parse named parameters: param=value
            for arg in args:
                if '=' in arg and not arg.startswith('-'):
                    key, value = arg.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    parameters[key] = value
                    self.logger.info(f"[TOOL PARSER] Named param: {key}={value}")
        else:
            # Positional parsing with smart flag detection
            flags = []
            positional_args = []

            for arg in args:
                # Flags start with - or -- and are not negative numbers
                if arg.startswith('-') and not (arg.startswith('-') and len(arg) > 1 and arg[1:].replace('.', '', 1).isdigit()):
                    flags.append(arg)
                else:
                    positional_args.append(arg)

            # Map positional arguments (non-flags) to parameters in order
            for i, param in enumerate(cmd_params):
                if i < len(positional_args):
                    parameters[param.parameter_name] = positional_args[i]
                    self.logger.info(f"[TOOL PARSER] Positional param[{i}]: {param.parameter_name}={positional_args[i]}")

            # Warn if flags were detected and ignored
            if flags:
                self.logger.warning(
                    f"[TOOL PARSER] Command-line flags detected in /{tool_name} {command_name}: {' '.join(flags)}. "
                    f"These flags are not mapped to parameters and were ignored. "
                    f"To use flags, add them to the command template or use named syntax: param=value"
                )

        return parameters

    async def _execute_sandboxed_tool(
        self,
        tool_name: str,
        tool_args: str,
        tenant_id: str,
        agent_id: int
    ) -> Dict[str, Any]:
        """Execute a sandboxed tool by name."""
        from models import SandboxedTool, SandboxedToolCommand, AgentSkill

        # First check if this is an enabled skill/tool for the agent
        # Note: AgentSkill uses skill_type (e.g., "audio_transcript") not skill_name
        skill = self.db.query(AgentSkill).filter(
            AgentSkill.agent_id == agent_id,
            AgentSkill.skill_type.ilike(f"%{tool_name}%"),
            AgentSkill.is_enabled == True
        ).first()

        # Look for sandboxed tool
        tool = self.db.query(SandboxedTool).filter(
            SandboxedTool.tenant_id == tenant_id,
            SandboxedTool.name.ilike(f"%{tool_name}%"),
            SandboxedTool.is_enabled == True
        ).first()

        if not tool:
            # List available tools
            available_tools = self.db.query(SandboxedTool).filter(
                SandboxedTool.tenant_id == tenant_id,
                SandboxedTool.is_enabled == True
            ).all()

            tool_list = "\n".join([f"• {t.name}" for t in available_tools]) if available_tools else "No sandboxed tools available"

            return {
                "status": "error",
                "message": f"❌ Tool '{tool_name}' not found.\n\n**Available tools:**\n{tool_list}\n\n**Built-in tools:**\n• weather\n• search\n• schedule\n• flights"
            }

        # Parse arguments intelligently
        # tool_args can be:
        # 1. "localhost" -> {"command": first_command, "target": "localhost"}
        # 2. "quick_scan localhost" -> {"command": "quick_scan", "target": "localhost"}
        # 3. "service_scan localhost 7" -> {"command": "service_scan", "target": "localhost", "intensity": "7"}

        from models import SandboxedToolParameter
        from agent.tools.sandboxed_tool_service import SandboxedToolService

        # Get all commands for this tool
        all_commands = self.db.query(SandboxedToolCommand).filter(
            SandboxedToolCommand.tool_id == tool.id
        ).all()

        if not all_commands:
            return {
                "status": "error",
                "message": f"❌ Tool '{tool.name}' has no commands configured."
            }

        # Parse the arguments
        args_parts = tool_args.strip().split() if tool_args else []

        # Try to determine which command to use
        command = None
        command_offset = 0

        if args_parts:
            # Check if first argument matches a command name
            first_arg = args_parts[0]
            matching_cmd = next((cmd for cmd in all_commands if cmd.command_name.lower() == first_arg.lower()), None)

            if matching_cmd:
                command = matching_cmd
                command_offset = 1  # Skip the command name from args
            else:
                # Use first/default command
                command = all_commands[0]
                command_offset = 0
        else:
            # No args, use first command
            command = all_commands[0]

        # Get parameters for this command
        cmd_params = self.db.query(SandboxedToolParameter).filter(
            SandboxedToolParameter.command_id == command.id
        ).order_by(SandboxedToolParameter.id).all()

        # Parse arguments with smart flag detection (Phase 16.1: Fix for nmap bug)
        remaining_args = args_parts[command_offset:]
        parameters = self._parse_tool_arguments(remaining_args, cmd_params, tool.name, command.command_name)

        self.logger.info(f"Parsed tool command: {tool.name}.{command.command_name} with params: {parameters}")

        try:
            sandboxed_service = SandboxedToolService(self.db, tenant_id=tenant_id)
            execution = await sandboxed_service.execute_command(
                tool_id=tool.id,
                command_id=command.id,
                parameters=parameters
            )

            if execution.status == "completed":
                return {
                    "status": "success",
                    "action": "tool_executed",
                    "tool_name": tool.name,
                    "message": f"🔧 **{tool.name}**\n\n{execution.output or 'Command executed successfully.'}"
                }
            elif execution.status == "running":
                return {
                    "status": "success",
                    "action": "tool_running",
                    "tool_name": tool.name,
                    "message": f"🔧 **{tool.name}** is running in the background.\n\n{execution.output or 'You will be notified when complete.'}"
                }
            else:
                return {
                    "status": "error",
                    "message": f"❌ Tool execution failed: {execution.error or 'Unknown error'}"
                }

        except Exception as e:
            self.logger.error(f"Custom tool execution error: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"❌ Failed to execute tool '{tool.name}': {str(e)}"
            }

    # =========================================================================
    # Scheduler Command Handlers
    # =========================================================================

    async def _handle_scheduler_info(self, **kwargs) -> Dict[str, Any]:
        """Handle /scheduler info command."""
        from services.scheduler_command_service import SchedulerCommandService

        service = SchedulerCommandService(self.db)
        return await service.execute_info(
            tenant_id=kwargs.get("tenant_id"),
            agent_id=kwargs.get("agent_id")
        )

    async def _handle_scheduler_list(self, **kwargs) -> Dict[str, Any]:
        """Handle /scheduler list [filter] command."""
        from services.scheduler_command_service import SchedulerCommandService

        groups = kwargs.get("groups", ())
        date_filter = groups[0] if groups and groups[0] else "week"

        service = SchedulerCommandService(self.db)
        return await service.execute_list(
            tenant_id=kwargs.get("tenant_id"),
            agent_id=kwargs.get("agent_id"),
            date_filter=date_filter
        )

    async def _handle_scheduler_create(self, **kwargs) -> Dict[str, Any]:
        """Handle /scheduler create <description> command."""
        from services.scheduler_command_service import SchedulerCommandService

        groups = kwargs.get("groups", ())
        input_text = groups[0] if groups else ""

        service = SchedulerCommandService(self.db)
        return await service.execute_create(
            tenant_id=kwargs.get("tenant_id"),
            agent_id=kwargs.get("agent_id"),
            input_text=input_text,
            sender_key=kwargs.get("sender_key")
        )

    async def _handle_scheduler_update(self, **kwargs) -> Dict[str, Any]:
        """Handle /scheduler update <event> new_name <name> new_description <desc> command."""
        from services.scheduler_command_service import SchedulerCommandService

        groups = kwargs.get("groups", ())
        event_identifier = groups[0] if groups and len(groups) > 0 else ""
        new_name = groups[1] if groups and len(groups) > 1 and groups[1] else None
        new_description = groups[2] if groups and len(groups) > 2 and groups[2] else None

        # Clean up quoted strings
        if new_name:
            new_name = new_name.strip('"\'')
        if new_description:
            new_description = new_description.strip('"\'')

        service = SchedulerCommandService(self.db)
        return await service.execute_update(
            tenant_id=kwargs.get("tenant_id"),
            agent_id=kwargs.get("agent_id"),
            event_identifier=event_identifier.strip('"\''),
            new_name=new_name,
            new_description=new_description
        )

    async def _handle_scheduler_delete(self, **kwargs) -> Dict[str, Any]:
        """Handle /scheduler delete <event_id_or_name> command."""
        from services.scheduler_command_service import SchedulerCommandService

        groups = kwargs.get("groups", ())
        event_identifier = groups[0] if groups else ""

        service = SchedulerCommandService(self.db)
        return await service.execute_delete(
            tenant_id=kwargs.get("tenant_id"),
            agent_id=kwargs.get("agent_id"),
            event_identifier=event_identifier.strip('"\'')
        )

    # =========================================================================
    # Thread Control Handlers
    # =========================================================================

    async def _handle_thread_end(self, **kwargs) -> Dict[str, Any]:
        """Handle /thread end command to end active conversation thread."""
        from models import ConversationThread

        sender_key = kwargs.get("sender_key", "")

        # Normalize sender key
        normalized_sender = sender_key.split('@')[0].lstrip('+')

        # Build possible recipient formats
        possible_recipients = [
            sender_key,
            normalized_sender,
            f"+{normalized_sender}",
            f"{normalized_sender}@s.whatsapp.net",
            f"{normalized_sender}@lid"
        ]

        # Find active thread
        thread = self.db.query(ConversationThread).filter(
            ConversationThread.recipient.in_(possible_recipients),
            ConversationThread.status == 'active'
        ).first()

        if not thread:
            return {
                "status": "success",
                "action": "thread_end",
                "message": "ℹ️ No active conversation thread found."
            }

        # End the thread
        thread.status = 'completed'
        thread.completed_at = datetime.utcnow()
        thread.goal_summary = 'Manually ended by user via /thread end command'
        self.db.commit()

        return {
            "status": "success",
            "action": "thread_end",
            "message": f"✅ Ended conversation thread #{thread.id}\n\nObjective: {thread.objective}\nTurns: {thread.current_turn}/{thread.max_turns}"
        }

    async def _handle_thread_list(self, **kwargs) -> Dict[str, Any]:
        """Handle /thread list command to show active threads."""
        from models import ConversationThread

        sender_key = kwargs.get("sender_key", "")

        # Normalize sender key
        normalized_sender = sender_key.split('@')[0].lstrip('+')

        # Build possible recipient formats
        possible_recipients = [
            sender_key,
            normalized_sender,
            f"+{normalized_sender}",
            f"{normalized_sender}@s.whatsapp.net",
            f"{normalized_sender}@lid"
        ]

        # Find all active threads for this user
        threads = self.db.query(ConversationThread).filter(
            ConversationThread.recipient.in_(possible_recipients),
            ConversationThread.status == 'active'
        ).order_by(ConversationThread.started_at.desc()).all()

        if not threads:
            return {
                "status": "success",
                "action": "thread_list",
                "message": "ℹ️ No active conversation threads."
            }

        # Format thread list
        lines = ["📋 **Active Conversation Threads:**\n"]
        for thread in threads:
            time_active = datetime.utcnow() - thread.started_at
            minutes_active = int(time_active.total_seconds() / 60)

            lines.append(f"**Thread #{thread.id}**")
            lines.append(f"  Objective: {thread.objective}")
            lines.append(f"  Progress: {thread.current_turn}/{thread.max_turns} turns")
            lines.append(f"  Active for: {minutes_active} minutes")
            lines.append("")

        lines.append("💡 Use `/thread end` to end the current thread.")

        return {
            "status": "success",
            "action": "thread_list",
            "message": "\n".join(lines)
        }

    async def _handle_thread_status(self, **kwargs) -> Dict[str, Any]:
        """Handle /thread status command to show current thread details."""
        from models import ConversationThread

        sender_key = kwargs.get("sender_key", "")

        # Normalize sender key
        normalized_sender = sender_key.split('@')[0].lstrip('+')

        # Build possible recipient formats
        possible_recipients = [
            sender_key,
            normalized_sender,
            f"+{normalized_sender}",
            f"{normalized_sender}@s.whatsapp.net",
            f"{normalized_sender}@lid"
        ]

        # Find active thread
        thread = self.db.query(ConversationThread).filter(
            ConversationThread.recipient.in_(possible_recipients),
            ConversationThread.status == 'active'
        ).order_by(ConversationThread.last_activity_at.desc()).first()

        if not thread:
            return {
                "status": "success",
                "action": "thread_status",
                "message": "ℹ️ No active conversation thread."
            }

        # Calculate time metrics
        time_active = datetime.utcnow() - thread.started_at
        minutes_active = int(time_active.total_seconds() / 60)

        time_since_last = datetime.utcnow() - thread.last_activity_at
        minutes_since_last = int(time_since_last.total_seconds() / 60)

        # Format status
        lines = [
            f"💬 **Thread #{thread.id} Status**\n",
            f"**Objective:** {thread.objective}",
            f"**Progress:** {thread.current_turn}/{thread.max_turns} turns",
            f"**Started:** {minutes_active} minutes ago",
            f"**Last Activity:** {minutes_since_last} minutes ago",
            f"**Goal Achieved:** {'✅ Yes' if thread.goal_achieved else '❌ Not yet'}",
            "",
            "💡 Use `/thread end` to end this thread."
        ]

        return {
            "status": "success",
            "action": "thread_status",
            "message": "\n".join(lines)
        }

    # =========================================================================
    # Shell Command Handler (Phase 18.3)
    # =========================================================================

    async def _handle_shell(self, **kwargs) -> Dict[str, Any]:
        """
        Handle /shell command for remote command execution.

        Usage:
        - /shell ls -la                    - Execute on default target
        - /shell myserver:df -h            - Execute on specific host
        - /shell @all:uptime               - Execute on all beacons

        Pattern: ^/shell\\s+(?:([\\w\\-@]+):)?(.+)$
        groups[0] = target (optional), groups[1] = command
        """
        from services.shell_command_service import ShellCommandService
        from models import AgentSkill
        from rbac_middleware import check_permission
        from models_rbac import User

        groups = kwargs.get("groups", ())
        tenant_id = kwargs.get("tenant_id")
        agent_id = kwargs.get("agent_id")
        sender_key = kwargs.get("sender_key")
        user_id = kwargs.get("user_id")

        # MED-010 FIX: Permission check - User must have shell.execute permission
        # This ensures users without proper shell permissions cannot execute commands
        # via slash commands, even if the agent has shell skill enabled
        if user_id:
            user = self.db.query(User).filter(User.id == user_id).first()
            if user and not check_permission(user, "shell.execute", self.db):
                self.logger.warning(
                    f"Permission denied: user {user.email} attempted /shell without shell.execute permission"
                )
                return {
                    "status": "error",
                    "action": "permission_denied",
                    "message": (
                        "🔒 **Permission Denied**\n\n"
                        "You need the `shell.execute` permission to run shell commands.\n\n"
                        "Contact your administrator to request access."
                    )
                }

        # Parse groups - pattern captures (target, command)
        target = groups[0] if groups and groups[0] else "default"
        command = groups[1].strip() if groups and len(groups) > 1 and groups[1] else ""

        if not command:
            return {
                "status": "error",
                "action": "shell_error",
                "message": (
                    "❌ **Usage:** `/shell [target:]<command>`\n\n"
                    "**Examples:**\n"
                    "• `/shell ls -la` - Execute on default beacon\n"
                    "• `/shell myserver:df -h` - Execute on specific host\n"
                    "• `/shell @all:uptime` - Execute on all beacons\n\n"
                    "**Targets:**\n"
                    "• `default` - First available beacon\n"
                    "• `hostname` - Specific beacon by hostname\n"
                    "• `@all` - All beacons (broadcast)"
                )
            }

        # Check if shell skill is enabled for this agent
        shell_skill = self.db.query(AgentSkill).filter(
            AgentSkill.agent_id == agent_id,
            AgentSkill.skill_type == "shell",
            AgentSkill.is_enabled == True
        ).first()

        if not shell_skill:
            return {
                "status": "error",
                "action": "shell_error",
                "message": (
                    "❌ **Shell skill not enabled**\n\n"
                    "The Shell skill is required to use `/shell` commands.\n"
                    "Enable it in the agent settings to execute remote commands."
                )
            }

        # Get skill config for execution mode
        skill_config = shell_skill.config or {}
        wait_for_result = skill_config.get("wait_for_result", False)  # Slash command defaults to fire-and-forget
        default_timeout = skill_config.get("default_timeout", 60)

        self.logger.info(f"Executing shell command: target={target}, command={command}, wait={wait_for_result}")

        try:
            # Execute via ShellCommandService using async version
            # FIX (2026-01-30): Use async version to avoid blocking the event loop
            # and allow beacon checkins to be processed during the wait
            service = ShellCommandService(self.db)
            result = await service.execute_command_async(
                script=command,
                target=target,
                tenant_id=tenant_id,
                initiated_by=f"user:{sender_key}",
                agent_id=agent_id,
                timeout_seconds=default_timeout,
                wait_for_result=wait_for_result
            )

            if result.success:
                if wait_for_result:
                    # Show output if we waited
                    output = result.stdout or "(no output)"
                    if len(output) > 1500:
                        output = output[:1500] + "\n... (truncated)"

                    return {
                        "status": "success",
                        "action": "shell_executed",
                        "command_id": result.command_id,
                        "exit_code": result.exit_code,
                        "message": f"🐚 **Shell Command Completed**\n\n**Target:** {target}\n**Command:** `{command}`\n**Exit Code:** {result.exit_code}\n\n```\n{output}\n```"
                    }
                else:
                    # Fire and forget
                    return {
                        "status": "success",
                        "action": "shell_queued",
                        "command_id": result.command_id,
                        "message": f"🐚 **Command Queued**\n\n**ID:** `{result.command_id}`\n**Target:** {target}\n**Command:** `{command}`\n\n💡 The command will execute when the beacon checks in. Use `/inject` to retrieve output later."
                    }
            else:
                error_msg = result.error_message or "Unknown error"
                if result.timed_out:
                    return {
                        "status": "error",
                        "action": "shell_timeout",
                        "command_id": result.command_id,
                        "message": f"⏱️ **Command Timed Out**\n\n**ID:** `{result.command_id}`\n**Target:** {target}\n\nThe beacon may still be processing the command. Check results later via Shell Command Center."
                    }
                return {
                    "status": "error",
                    "action": "shell_error",
                    "message": f"❌ **Shell Command Failed**\n\n**Target:** {target}\n**Error:** {error_msg}"
                }

        except Exception as e:
            self.logger.error(f"Shell command execution error: {e}", exc_info=True)
            return {
                "status": "error",
                "action": "shell_error",
                "message": f"❌ **Shell execution failed:** {str(e)}"
            }

    # =========================================================================
    # Email Command Handlers
    # =========================================================================

    async def _handle_email_inbox(self, **kwargs) -> Dict[str, Any]:
        """
        Handle /email inbox [count] command.

        List recent emails from inbox (programmatic, zero AI tokens).
        """
        from services.email_command_service import EmailCommandService

        groups = kwargs.get("groups", ())
        count = int(groups[0]) if groups and groups[0] else 10

        service = EmailCommandService(self.db)
        return await service.execute_inbox(
            tenant_id=kwargs.get("tenant_id"),
            agent_id=kwargs.get("agent_id"),
            count=count
        )

    async def _handle_email_search(self, **kwargs) -> Dict[str, Any]:
        """
        Handle /email search "query" command.

        Search emails with Gmail query syntax (programmatic, zero AI tokens).
        """
        from services.email_command_service import EmailCommandService

        groups = kwargs.get("groups", ())
        query = groups[0] if groups else ""

        service = EmailCommandService(self.db)
        return await service.execute_search(
            tenant_id=kwargs.get("tenant_id"),
            agent_id=kwargs.get("agent_id"),
            query=query
        )

    async def _handle_email_unread(self, **kwargs) -> Dict[str, Any]:
        """
        Handle /email unread command.

        Show unread emails (programmatic, zero AI tokens).
        """
        from services.email_command_service import EmailCommandService

        service = EmailCommandService(self.db)
        return await service.execute_unread(
            tenant_id=kwargs.get("tenant_id"),
            agent_id=kwargs.get("agent_id")
        )

    async def _handle_email_info(self, **kwargs) -> Dict[str, Any]:
        """
        Handle /email info command.

        Show Gmail configuration and connection status (programmatic, zero AI tokens).
        """
        from services.email_command_service import EmailCommandService

        service = EmailCommandService(self.db)
        return await service.execute_info(
            tenant_id=kwargs.get("tenant_id"),
            agent_id=kwargs.get("agent_id")
        )

    async def _handle_email_list(self, **kwargs) -> Dict[str, Any]:
        """
        Handle /email list [filter] command.

        List emails with optional filter (programmatic, zero AI tokens).
        Filters: unread, today, <number>
        """
        from services.email_command_service import EmailCommandService

        groups = kwargs.get("groups", ())
        filter_type = groups[0] if groups and groups[0] else None

        service = EmailCommandService(self.db)
        return await service.execute_list(
            tenant_id=kwargs.get("tenant_id"),
            agent_id=kwargs.get("agent_id"),
            filter_type=filter_type
        )

    async def _handle_email_read(self, **kwargs) -> Dict[str, Any]:
        """
        Handle /email read <identifier> command.

        Read full email content by ID or list index (programmatic, zero AI tokens).
        """
        from services.email_command_service import EmailCommandService

        groups = kwargs.get("groups", ())
        identifier = groups[0] if groups else ""

        service = EmailCommandService(self.db)
        return await service.execute_read(
            tenant_id=kwargs.get("tenant_id"),
            agent_id=kwargs.get("agent_id"),
            identifier=identifier
        )

    # =========================================================================
    # Weather Command Handlers
    # =========================================================================

    async def _handle_weather(self, **kwargs) -> Dict[str, Any]:
        """
        Handle /weather <location> command.

        Get current weather (programmatic, zero AI tokens).
        """
        from services.weather_command_service import WeatherCommandService

        groups = kwargs.get("groups", ())
        location = groups[0] if groups else ""

        service = WeatherCommandService(self.db)
        return await service.execute_current(
            tenant_id=kwargs.get("tenant_id"),
            agent_id=kwargs.get("agent_id"),
            location=location
        )

    async def _handle_weather_forecast(self, **kwargs) -> Dict[str, Any]:
        """
        Handle /weather forecast <location> [days] command.

        Get weather forecast (programmatic, zero AI tokens).
        """
        from services.weather_command_service import WeatherCommandService

        groups = kwargs.get("groups", ())
        location = groups[0] if groups else ""
        days = int(groups[1]) if len(groups) > 1 and groups[1] else 3

        service = WeatherCommandService(self.db)
        return await service.execute_forecast(
            tenant_id=kwargs.get("tenant_id"),
            agent_id=kwargs.get("agent_id"),
            location=location,
            days=days
        )

    # =========================================================================
    # Search Command Handlers
    # =========================================================================

    async def _handle_search(self, **kwargs) -> Dict[str, Any]:
        """
        Handle /search "query" command.

        Search the web (programmatic, zero AI tokens).
        """
        from services.search_command_service import SearchCommandService

        groups = kwargs.get("groups", ())
        query = groups[0] if groups else ""

        service = SearchCommandService(self.db)
        return await service.execute_search(
            tenant_id=kwargs.get("tenant_id"),
            agent_id=kwargs.get("agent_id"),
            query=query
        )

    # =========================================================================
    # Cache Management
    # =========================================================================

    def invalidate_cache(self, tenant_id: str = None):
        """Invalidate pattern cache for a tenant or all tenants."""
        if tenant_id:
            self._pattern_cache.pop(tenant_id, None)
        else:
            self._pattern_cache.clear()
