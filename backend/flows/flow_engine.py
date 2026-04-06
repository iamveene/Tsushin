"""
Phase 6.7: Multi-Step Flows - Flow Execution Engine
Phase 8.0: Unified Flow Architecture - Enhanced with step-based execution and conversation threading

Core execution engine that orchestrates flow runs with proper error handling,
timeouts, retries, and integration with existing Tsushin modules.

Key changes in Phase 8.0:
- Removed Trigger requirement (triggers are now flow-level metadata)
- Added retry logic for steps
- Added ConversationThread support for multi-turn conversations
- Support for new step types: notification, message, tool, conversation
- Support for execution methods: immediate, scheduled, recurring
"""

import json
import logging
import asyncio
import hashlib
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from models import (
    FlowDefinition, FlowNode, FlowRun, FlowNodeRun,
    ConversationThread, Agent, ScheduledEvent
)
from mcp_sender import MCPSender
from flows.template_parser import TemplateParser

logger = logging.getLogger(__name__)

# Default timeout per step (seconds)
DEFAULT_STEP_TIMEOUT = 300


class FlowValidationError(Exception):
    """Raised when flow structure is invalid."""
    pass


class FlowStepHandler:
    """Base class for all step type handlers."""

    def __init__(self, db: Session, mcp_sender: MCPSender, token_tracker=None):
        self.db = db
        self.mcp_sender = mcp_sender
        self.token_tracker = token_tracker  # Phase 7.2: Token usage tracking

    def _resolve_mcp_url(self, recipient: str, flow_run: FlowRun = None, step: FlowNode = None) -> str:
        """
        Resolve MCP API URL for sending messages.

        Uses tenant_id from flow_run or agent_id from step to find the correct
        MCP instance (matching AgentRouter._resolve_mcp_api_url logic).

        Args:
            recipient: Phone number (used for logging)
            flow_run: Current FlowRun for tenant context
            step: Current FlowNode for agent_id override

        Returns:
            MCP API URL (e.g., http://mcp-agent-tenant_123:8080/api)
        """
        url, _ = self._resolve_mcp_url_and_secret(recipient, flow_run, step)
        return url

    def _resolve_mcp_url_and_secret(self, recipient: str, flow_run: FlowRun = None, step: FlowNode = None) -> tuple:
        """
        Resolve MCP API URL and secret for sending messages.

        Phase Security-1: Returns both URL and api_secret for authentication.

        Args:
            recipient: Phone number (used for logging)
            flow_run: Current FlowRun for tenant context
            step: Current FlowNode for agent_id override

        Returns:
            Tuple of (MCP API URL, api_secret or None)
        """
        from models import WhatsAppMCPInstance

        try:
            tenant_id = None

            # 1. Try to get tenant_id from flow_run
            if flow_run and flow_run.tenant_id:
                tenant_id = flow_run.tenant_id
                logger.debug(f"Using tenant_id from flow_run: {tenant_id}")

            # 2. If step has agent_id, resolve tenant from agent
            elif step and step.agent_id:
                agent = self.db.query(Agent).filter(Agent.id == step.agent_id).first()
                if agent and agent.tenant_id:
                    tenant_id = agent.tenant_id
                    logger.debug(f"Resolved tenant_id from step.agent_id: {tenant_id}")

            # 3. Try to get default_agent_id from flow definition
            elif flow_run:
                flow = self.db.query(FlowDefinition).filter(
                    FlowDefinition.id == flow_run.flow_definition_id
                ).first()
                if flow and flow.default_agent_id:
                    agent = self.db.query(Agent).filter(Agent.id == flow.default_agent_id).first()
                    if agent and agent.tenant_id:
                        tenant_id = agent.tenant_id
                        logger.debug(f"Resolved tenant_id from flow.default_agent_id: {tenant_id}")

            # Query MCP instance with tenant filter (if available)
            if tenant_id:
                instance = self.db.query(WhatsAppMCPInstance).filter(
                    WhatsAppMCPInstance.tenant_id == tenant_id,
                    WhatsAppMCPInstance.instance_type == "agent",
                    WhatsAppMCPInstance.status.in_(["running", "starting"])
                ).first()

                if instance and instance.mcp_api_url:
                    logger.info(f"Resolved MCP URL for tenant {tenant_id}: {instance.mcp_api_url}")
                    return (instance.mcp_api_url, instance.api_secret)
                else:
                    logger.warning(f"No active MCP instance for tenant {tenant_id}")

            # Fallback: find any agent instance (backward compatibility)
            instance = self.db.query(WhatsAppMCPInstance).filter(
                WhatsAppMCPInstance.status.in_(["running", "starting"]),
                WhatsAppMCPInstance.instance_type == "agent"
            ).first()

            if instance and instance.mcp_api_url:
                logger.info(f"Resolved MCP URL (fallback): {instance.mcp_api_url}")
                return (instance.mcp_api_url, instance.api_secret)
            else:
                logger.warning(f"No active MCP instance found, using default URL")
                return ("http://127.0.0.1:8080/api", None)

        except Exception as e:
            logger.error(f"Error resolving MCP URL for {recipient}: {e}", exc_info=True)
            return ("http://127.0.0.1:8080/api", None)

    def _check_mcp_connection(self, mcp_api_url: str) -> bool:
        """
        Check if MCP instance is connected before sending.

        Prevents message queue replay by verifying WhatsApp device is authenticated.
        If device is unlinked, messages should NOT be sent to avoid queue buildup.

        Args:
            mcp_api_url: MCP API URL to check

        Returns:
            True if connected and ready to send, False otherwise
        """
        import httpx

        try:
            # If no URL provided, assume default is available (backward compatibility)
            if not mcp_api_url or mcp_api_url == "http://127.0.0.1:8080/api":
                # For default URL, skip check (assume always available for backward compat)
                return True

            # Call health endpoint to check connection status
            health_url = f"{mcp_api_url}/health"
            response = httpx.get(health_url, timeout=5.0)

            if response.status_code == 200:
                health_data = response.json()
                connected = health_data.get("connected", False)
                authenticated = health_data.get("authenticated", False)

                if not connected or not authenticated:
                    logger.warning(
                        f"MCP instance at {mcp_api_url} is NOT ready "
                        f"(connected={connected}, authenticated={authenticated}). "
                        f"Skipping message send to prevent queue buildup."
                    )
                    return False

                # Connected and authenticated
                return True
            else:
                logger.warning(
                    f"MCP health check failed at {mcp_api_url}: HTTP {response.status_code}. "
                    f"Skipping message send."
                )
                return False

        except Exception as e:
            logger.error(
                f"Failed to check MCP connection at {mcp_api_url}: {e}. "
                f"Skipping message send to be safe."
            )
            return False

    async def execute(
        self,
        step: FlowNode,
        input_data: Dict[str, Any],
        flow_run: FlowRun,
        step_run: FlowNodeRun
    ) -> Dict[str, Any]:
        """
        Execute the step logic.

        Args:
            step: FlowNode (step) to execute
            input_data: Input data from previous step or trigger context
            flow_run: Current FlowRun for context
            step_run: Current FlowNodeRun for tracking

        Returns:
            Dict with execution results
        """
        raise NotImplementedError("Subclasses must implement execute()")

    def _replace_variables(self, template: str, data: Dict[str, Any]) -> str:
        """
        Replace {{variable}} placeholders with values from data.

        Phase 13.1: Enhanced with TemplateParser for step output injection.
        Supports:
        - Step references: {{step_1.output}}, {{step_name.result}}
        - Previous step: {{previous_step.summary}}
        - JSON paths: {{step_1.raw_output.ports[0]}}
        - Helpers: {{truncate step_1.output 100}}
        - Conditionals: {{#if step_1.success}}OK{{/if}}
        """
        parser = TemplateParser(data)
        return parser.render(template)

    def _resolve_contact_to_phone(self, identifier: str, tenant_id: Optional[str] = None) -> Optional[str]:
        """
        Resolve a contact identifier (friendly name, @mention) to phone number or group JID.

        Args:
            identifier: Contact identifier (e.g., "@Alice", "Alice", "+5500000000001", "120363...@g.us")
            tenant_id: V060-CHN-006 follow-up — scope contact lookups to this tenant
                so a flow step for Tenant A can't resolve "@Alice" to Tenant B's
                contact. Callers should derive this from flow_run.tenant_id.

        Returns:
            Phone number or group JID if found, None otherwise
        """
        from agent.contact_service import ContactService

        if not identifier:
            return None

        # If it's a WhatsApp group JID (ends with @g.us), use it directly
        if identifier.endswith('@g.us'):
            logger.info(f"Using group JID directly: {identifier}")
            return identifier

        # If it's already a phone number (contains only digits and + symbol), return it
        if identifier.replace("+", "").replace(" ", "").replace("-", "").isdigit():
            return identifier.replace(" ", "").replace("-", "")

        # Try to resolve as contact identifier (tenant-scoped — V060-CHN-006)
        try:
            contact_service = ContactService(self.db, tenant_id=tenant_id)
            contact = contact_service.resolve_identifier(identifier)

            if contact:
                # Check if contact has a group JID in whatsapp_id
                if contact.whatsapp_id and contact.whatsapp_id.endswith('@g.us'):
                    logger.info(f"Resolved contact '{identifier}' to group JID: {contact.whatsapp_id}")
                    return contact.whatsapp_id

                # Check if phone_number is actually a group JID
                if contact.phone_number and contact.phone_number.endswith('@g.us'):
                    logger.info(f"Resolved contact '{identifier}' to group JID: {contact.phone_number}")
                    return contact.phone_number

                # Return regular phone number
                if contact.phone_number:
                    logger.info(f"Resolved contact '{identifier}' to phone: {contact.phone_number}")
                    return contact.phone_number

                # Try whatsapp_id as fallback for individual chats
                if contact.whatsapp_id:
                    logger.info(f"Resolved contact '{identifier}' to whatsapp_id: {contact.whatsapp_id}")
                    return contact.whatsapp_id

            logger.warning(f"Could not resolve contact '{identifier}' to phone number or group JID")
            return None
        except Exception as e:
            logger.error(f"Error resolving contact '{identifier}': {e}")
            return None

    def _resolve_tenant_id(self, flow_run: FlowRun, step: FlowNode) -> Optional[str]:
        """Resolve tenant_id from flow context."""
        if flow_run and hasattr(flow_run, 'tenant_id') and flow_run.tenant_id:
            return flow_run.tenant_id
        # Try via agent
        agent_id = step.agent_id if step else None
        if not agent_id and flow_run:
            flow = self.db.query(FlowDefinition).filter(
                FlowDefinition.id == flow_run.flow_definition_id
            ).first()
            if flow:
                agent_id = flow.default_agent_id
        if agent_id:
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            if agent:
                return agent.tenant_id
        return None

    def _resolve_telegram_sender(self, tenant_id: str):
        """Resolve TelegramSender for a tenant."""
        from models import TelegramBotInstance
        from services.telegram_bot_service import TelegramBotService
        from telegram_integration.sender import TelegramSender

        try:
            bot_instance = self.db.query(TelegramBotInstance).filter(
                TelegramBotInstance.tenant_id == tenant_id,
                TelegramBotInstance.status == "active"
            ).first()

            if not bot_instance:
                logger.warning(f"No active Telegram bot for tenant {tenant_id}")
                return None

            telegram_service = TelegramBotService(self.db)
            token = telegram_service._decrypt_token(
                bot_instance.bot_token_encrypted,
                bot_instance.tenant_id
            )
            return TelegramSender(token)
        except Exception as e:
            logger.error(f"Failed to resolve Telegram sender: {e}")
            return None


class NotificationStepHandler(FlowStepHandler):
    """Handles Notification steps - sends one-way notifications."""

    async def execute(
        self,
        step: FlowNode,
        input_data: Dict[str, Any],
        flow_run: FlowRun,
        step_run: FlowNodeRun
    ) -> Dict[str, Any]:
        """Send notification message without expecting reply."""
        config = json.loads(step.config_json) if isinstance(step.config_json, str) else step.config_json

        # Channel guard: WhatsApp and Telegram supported
        channel = config.get("channel", "whatsapp")
        if channel not in ("whatsapp", "telegram"):
            logger.warning(f"Notification step uses unsupported channel '{channel}', skipping")
            return {
                "status": "skipped",
                "channel": channel,
                "error": f"Channel '{channel}' is not yet supported for flow notifications",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        # Handle both "recipient" (singular) and "recipients" (array) formats
        recipient = config.get("recipient", "")
        if not recipient:
            recipients_list = config.get("recipients", [])
            if recipients_list and len(recipients_list) > 0:
                recipient = recipients_list[0]  # Take first recipient for single notification

        message_template = config.get("message_template", config.get("content", ""))

        # Add current timestamp to context for template rendering
        enriched_data = {
            **input_data,
            "current_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "current_date": datetime.utcnow().strftime("%Y-%m-%d"),
        }

        # Variable replacement
        recipient = self._replace_variables(recipient, enriched_data)
        message = self._replace_variables(message_template, enriched_data)

        if channel == "whatsapp":
            # Resolve contact identifier (e.g., "@alice") to phone number — tenant-scoped (V060-CHN-006)
            resolved_recipient = self._resolve_contact_to_phone(
                recipient, tenant_id=(flow_run.tenant_id if flow_run else None)
            )
            if not resolved_recipient:
                logger.error(f"Could not resolve recipient '{recipient}' to a phone number")
                return {
                    "recipient": recipient,
                    "status": "failed",
                    "error": f"Could not resolve recipient '{recipient}' to a phone number"
                }

            logger.info(f"Sending notification to {recipient} (resolved: {resolved_recipient})")

            try:
                # Resolve MCP URL and secret using tenant context from flow_run and step
                mcp_url, api_secret = self._resolve_mcp_url_and_secret(resolved_recipient, flow_run=flow_run, step=step)

                # Check MCP health before sending
                if not self._check_mcp_connection(mcp_url):
                    logger.error(f"MCP not ready at {mcp_url}, cannot send notification")
                    return {
                        "recipient": recipient,
                        "resolved_recipient": resolved_recipient,
                        "message_sent": message,
                        "mcp_url": mcp_url,
                        "success": False,
                        "status": "failed",
                        "error": "MCP instance not connected or authenticated",
                        "channel": "whatsapp",
                        "timestamp": datetime.utcnow().isoformat() + "Z"
                    }

                # Phase Security-1: Pass api_secret for authentication
                success = await self.mcp_sender.send_message(resolved_recipient, message, api_url=mcp_url, api_secret=api_secret)

                return {
                    "recipient": recipient,
                    "resolved_recipient": resolved_recipient,
                    "message_sent": message,
                    "mcp_url": mcp_url,
                    "success": success,
                    "status": "completed" if success else "failed",
                    "channel": "whatsapp",
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
            except Exception as e:
                logger.error(f"Failed to send notification: {e}")
                return {
                    "recipient": recipient,
                    "resolved_recipient": resolved_recipient if 'resolved_recipient' in locals() else None,
                    "status": "failed",
                    "error": str(e)
                }

        elif channel == "telegram":
            # Telegram notification: resolve sender and send via Telegram Bot API
            tenant_id = self._resolve_tenant_id(flow_run, step)
            if not tenant_id:
                return {
                    "status": "failed",
                    "channel": "telegram",
                    "error": "Could not resolve tenant_id for Telegram notification",
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }

            telegram_sender = self._resolve_telegram_sender(tenant_id)
            if not telegram_sender:
                return {
                    "status": "failed",
                    "channel": "telegram",
                    "error": "No active Telegram bot configured for this tenant",
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }

            # Recipient should be a Telegram chat_id (numeric string)
            try:
                chat_id = int(recipient)
            except (ValueError, TypeError):
                return {
                    "status": "failed",
                    "channel": "telegram",
                    "error": f"Invalid Telegram chat_id: {recipient}",
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }

            try:
                success = await telegram_sender.send_message(chat_id=chat_id, message=message)
                return {
                    "recipient": recipient,
                    "message_sent": message,
                    "success": success,
                    "status": "completed" if success else "failed",
                    "channel": "telegram",
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }
            except Exception as e:
                logger.error(f"Failed to send Telegram notification: {e}")
                return {
                    "recipient": recipient,
                    "status": "failed",
                    "channel": "telegram",
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }


class MessageStepHandler(FlowStepHandler):
    """Handles Message steps - sends messages (may support attachments in future)."""

    async def execute(
        self,
        step: FlowNode,
        input_data: Dict[str, Any],
        flow_run: FlowRun,
        step_run: FlowNodeRun
    ) -> Dict[str, Any]:
        """Send message to recipients."""
        config = json.loads(step.config_json) if isinstance(step.config_json, str) else step.config_json

        # Channel guard: WhatsApp and Telegram supported
        channel = config.get("channel", "whatsapp")
        if channel not in ("whatsapp", "telegram"):
            logger.warning(f"Message step uses unsupported channel '{channel}', skipping")
            return {
                "status": "skipped",
                "channel": channel,
                "error": f"Channel '{channel}' is not yet supported for flow messages",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        recipients = config.get("recipients", [])
        if isinstance(recipients, str):
            recipients = [recipients]
        recipient = config.get("recipient")
        if recipient and recipient not in recipients:
            recipients.append(recipient)

        message_template = config.get("message_template", config.get("content", ""))

        # Variable replacement
        message = self._replace_variables(message_template, input_data)
        recipients = [self._replace_variables(r, input_data) for r in recipients]

        if not message.strip():
            logger.warning("Rendered message is empty, skipping send")
            return {
                "recipients": recipients,
                "resolved_recipients": [],
                "message_sent": message,
                "sent_count": 0,
                "total_recipients": len(recipients),
                "status": "failed",
                "error": "Rendered message is empty",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        if channel == "whatsapp":
            # Resolve contact identifiers to phone numbers — tenant-scoped (V060-CHN-006)
            _flow_tenant = flow_run.tenant_id if flow_run else None
            resolved_recipients = []
            for recipient in recipients:
                resolved = self._resolve_contact_to_phone(recipient, tenant_id=_flow_tenant)
                if resolved:
                    resolved_recipients.append(resolved)
                else:
                    logger.warning(f"Could not resolve recipient '{recipient}', skipping")

            if not resolved_recipients:
                logger.error("No valid recipients after resolution")
                return {
                    "recipients": recipients,
                    "resolved_recipients": [],
                    "message_sent": message,
                    "sent_count": 0,
                    "total_recipients": len(recipients),
                    "status": "failed",
                    "error": "No valid recipients could be resolved",
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }

            logger.info(f"Sending message to {len(resolved_recipients)} resolved recipient(s)")

            # Resolve MCP URL and secret once using tenant context (same for all recipients)
            mcp_url, api_secret = self._resolve_mcp_url_and_secret(resolved_recipients[0], flow_run=flow_run, step=step)

            # Check MCP health before sending
            if not self._check_mcp_connection(mcp_url):
                logger.error(f"MCP not ready at {mcp_url}, cannot send messages")
                return {
                    "recipients": recipients,
                    "resolved_recipients": resolved_recipients,
                    "message_sent": message,
                    "mcp_url": mcp_url,
                    "sent_count": 0,
                    "total_recipients": len(recipients),
                    "status": "failed",
                    "error": "MCP instance not connected or authenticated",
                    "channel": "whatsapp",
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }

            sent_count = 0
            for recipient in resolved_recipients:
                try:
                    # Phase Security-1: Pass api_secret for authentication
                    success = await self.mcp_sender.send_message(recipient, message, api_url=mcp_url, api_secret=api_secret)
                    if success:
                        sent_count += 1
                except Exception as e:
                    logger.error(f"Failed to send message to {recipient}: {e}")

            return {
                "recipients": recipients,
                "resolved_recipients": resolved_recipients,
                "message_sent": message,
                "mcp_url": mcp_url,
                "sent_count": sent_count,
                "total_recipients": len(recipients),
                "status": "completed" if sent_count > 0 else "failed",
                "channel": "whatsapp",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        elif channel == "telegram":
            # Telegram message: resolve sender and send via Telegram Bot API
            tenant_id = self._resolve_tenant_id(flow_run, step)
            if not tenant_id:
                return {
                    "status": "failed",
                    "channel": "telegram",
                    "error": "Could not resolve tenant_id for Telegram message",
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }

            telegram_sender = self._resolve_telegram_sender(tenant_id)
            if not telegram_sender:
                return {
                    "status": "failed",
                    "channel": "telegram",
                    "error": "No active Telegram bot configured for this tenant",
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }

            sent_count = 0
            for recipient in recipients:
                # Each recipient should be a Telegram chat_id (numeric string)
                try:
                    chat_id = int(recipient)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid Telegram chat_id: {recipient}, skipping")
                    continue

                try:
                    success = await telegram_sender.send_message(chat_id=chat_id, message=message)
                    if success:
                        sent_count += 1
                except Exception as e:
                    logger.error(f"Failed to send Telegram message to {recipient}: {e}")

            return {
                "recipients": recipients,
                "message_sent": message,
                "sent_count": sent_count,
                "total_recipients": len(recipients),
                "status": "completed" if sent_count > 0 else "failed",
                "channel": "telegram",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }


class ToolStepHandler(FlowStepHandler):
    """Handles Tool steps - executes built-in or custom tools."""

    def __init__(self, db: Session, mcp_sender: MCPSender, token_tracker=None):
        super().__init__(db, mcp_sender, token_tracker)

    async def execute(
        self,
        step: FlowNode,
        input_data: Dict[str, Any],
        flow_run: FlowRun,
        step_run: FlowNodeRun
    ) -> Dict[str, Any]:
        """Execute tool via Core tool execution pathway."""
        config = json.loads(step.config_json) if isinstance(step.config_json, str) else step.config_json

        # Handle None config gracefully
        if not config:
            config = {}

        tool_type = config.get("tool_type", "built_in")
        tool_name = config.get("tool_name") or config.get("tool_id") or ""
        parameters = config.get("parameters", config.get("tool_parameters", {})) or {}
        timeout = step.timeout_seconds or DEFAULT_STEP_TIMEOUT

        # Phase 13.1: Resolve template variables in parameters
        # This allows tool parameters to reference previous step outputs
        resolved_params = {}
        for key, value in parameters.items():
            if isinstance(value, str):
                resolved_params[key] = self._replace_variables(value, input_data)
            else:
                resolved_params[key] = value

        # Merge input_data into parameters (ensure both are dicts)
        input_data = input_data or {}
        merged_params = {**resolved_params, **input_data}

        logger.info(f"Executing {tool_type} tool: {tool_name} (tool_id from config: {config.get('tool_id')})")

        # Validate tool_id for sandboxed tools (also accepts "custom_tool" for backward compatibility)
        if (tool_type == "sandboxed_tool" or tool_type == "sandboxed" or tool_type == "custom_tool" or tool_type == "custom") and not tool_name:
            raise ValueError(f"Missing tool_id/tool_name for sandboxed tool. Config: {config}")

        if tool_type == "sandboxed_tool" or tool_type == "sandboxed" or tool_type == "custom_tool" or tool_type == "custom":
            try:
                # Pass tenant_id from flow_run for container execution
                tenant_id = flow_run.tenant_id if flow_run else None
                result = await asyncio.wait_for(
                    self._execute_sandboxed_tool(tool_name, merged_params, tenant_id),
                    timeout=timeout
                )
                return result
            except asyncio.TimeoutError:
                raise Exception(f"Tool execution timed out after {timeout}s")
        else:
            result = await self._execute_builtin_tool(tool_name, merged_params)
            return result

    async def _execute_sandboxed_tool(self, tool_id: str, parameters: Dict[str, Any], tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Execute sandboxed tool through SandboxedToolService."""
        from models import SandboxedToolCommand
        from agent.tools.sandboxed_tool_service import SandboxedToolService

        try:
            if not tool_id:
                raise ValueError("tool_id is required but was empty or None")

            tool_id_int = int(tool_id)

            # Find the first command for this tool
            command = self.db.query(SandboxedToolCommand).filter_by(tool_id=tool_id_int).first()
            if not command:
                raise ValueError(f"No command found for tool {tool_id}")

            # Create service with tenant_id for container execution
            sandboxed_tool_service = SandboxedToolService(self.db, tenant_id=tenant_id)

            # Execute the command
            execution = await sandboxed_tool_service.execute_command(
                tool_id=tool_id_int,
                command_id=command.id,
                parameters=parameters
            )

            return {
                "tool_used": f"sandboxed_tool_{tool_id}",
                "tool_type": "custom",
                "summary": f"Command executed: {execution.rendered_command[:100]}..." if execution.rendered_command else "Tool executed",
                "raw_output": execution.output,
                "error": execution.error,
                "exit_code": 0 if execution.status == "completed" else 1,
                "status": execution.status,
                "execution_time_ms": execution.execution_time_ms or 0
            }
        except Exception as e:
            logger.error(f"Custom tool execution failed: {e}")
            return {
                "tool_used": f"sandboxed_tool_{tool_id}",
                "tool_type": "custom",
                "status": "failed",
                "error": str(e)
            }

    async def _execute_builtin_tool(self, tool_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute built-in tool (google_search, web_scraping)."""
        try:
            if tool_id == "google_search":
                from agent.tools.search_tool import SearchTool
                tool = SearchTool(db=self.db)
                query = parameters.get("query", parameters.get("q", ""))
                result = tool.search(query)

                if result.get("error"):
                    return {
                        "tool_used": "google_search",
                        "tool_type": "built_in",
                        "query": query,
                        "status": "failed",
                        "error": result.get("error"),
                        "search_results": "",
                        "search_summary": "Search failed"
                    }

                results_text = result.get("summary", "")
                if not results_text and result.get("results"):
                    formatted_results = []
                    for idx, item in enumerate(result.get("results", [])[:5], 1):
                        title = item.get("title", "")
                        desc = item.get("description", "")
                        formatted_results.append(f"{idx}. {title}\n{desc}")
                    results_text = "\n\n".join(formatted_results)

                return {
                    "tool_used": "google_search",
                    "tool_type": "built_in",
                    "query": query,
                    "search_results": results_text,
                    "search_summary": result.get("summary", "Search completed"),
                    "results_count": len(result.get("results", [])),
                    "raw_output": result,
                    "status": "completed"
                }

            elif tool_id == "web_scraping":
                # Deprecated: web_scraping replaced by browser_automation skill
                return {
                    "tool_used": "web_scraping",
                    "tool_type": "built_in",
                    "status": "deprecated",
                    "error": "web_scraping is deprecated. Update this flow to use browser_automation with action=extract."
                }

            else:
                raise Exception(f"Unknown built-in tool: {tool_id}")

        except Exception as e:
            logger.error(f"Built-in tool execution failed: {e}")
            return {
                "tool_used": tool_id,
                "tool_type": "built_in",
                "status": "failed",
                "error": str(e)
            }


class SlashCommandStepHandler(FlowStepHandler):
    """Handles Slash Command steps - executes slash commands and returns their output."""

    async def execute(
        self,
        step: FlowNode,
        input_data: Dict[str, Any],
        flow_run: FlowRun,
        step_run: FlowNodeRun
    ) -> Dict[str, Any]:
        """Execute a slash command and return its output for subsequent steps."""
        config = json.loads(step.config_json) if isinstance(step.config_json, str) else step.config_json

        # Handle None config gracefully
        if not config:
            config = {}

        command = config.get("command", "")
        agent_id = config.get("agent_id") or step.agent_id

        # Get tenant_id from flow_run or agent
        tenant_id = flow_run.tenant_id if flow_run else None
        if not tenant_id and agent_id:
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            if agent:
                tenant_id = agent.tenant_id

        if not tenant_id:
            tenant_id = "_system"

        # Resolve template variables in command
        command = self._replace_variables(command, input_data)

        logger.info(f"Executing slash command: {command}")

        try:
            from services.slash_command_service import SlashCommandService

            slash_service = SlashCommandService(self.db)

            # Execute the command
            result = await slash_service.execute_command(
                message=command,
                tenant_id=tenant_id,
                agent_id=agent_id or 1,  # Fallback to agent 1
                sender_key=f"flow_{flow_run.id}_step_{step.id}",
                channel="flow"
            )

            # Extract the output message
            output_message = result.get("message", "")
            status = result.get("status", "unknown")
            action = result.get("action", "")

            # Return structured output for template injection
            return {
                "command": command,
                "status": status,
                "action": action,
                "message": output_message,
                "output": output_message,  # Alias for easier template access
                "raw_result": result,
                "executed_at": datetime.utcnow().isoformat() + "Z"
            }

        except Exception as e:
            logger.error(f"Slash command execution failed: {e}", exc_info=True)
            return {
                "command": command,
                "status": "failed",
                "error": str(e),
                "message": f"Error executing command: {str(e)}",
                "output": ""
            }


class SkillStepHandler(FlowStepHandler):
    """
    Phase 16: Handles Skill steps - executes agentic skills (flight_search, etc.).

    Allows flows to call skills like FlightSearchSkill with a natural language prompt
    and receive structured output that can be injected into subsequent steps.

    Config schema:
    {
        "skill_type": "flight_search",  # Skill type from SkillManager registry
        "prompt": "busque voos de VIX para CGH",  # Natural language prompt
        "skill_config": {  # Optional: Override skill configuration
            "provider": "google_flights",
            "settings": {"default_currency": "BRL"}
        }
    }
    """

    async def execute(
        self,
        step: FlowNode,
        input_data: Dict[str, Any],
        flow_run: FlowRun,
        step_run: FlowNodeRun
    ) -> Dict[str, Any]:
        """
        Execute an agentic skill and return its output for subsequent steps.

        Args:
            step: FlowNode with skill configuration
            input_data: Input data from previous steps (for template resolution)
            flow_run: Current FlowRun for context
            step_run: Current FlowNodeRun for tracking

        Returns:
            Dict with skill output for template injection:
            {
                "skill_type": "flight_search",
                "prompt": "busque voos...",
                "success": True,
                "output": "Flight search results...",
                "metadata": {...},
                "status": "completed"
            }
        """
        from agent.skills.skill_manager import get_skill_manager
        from agent.skills.base import InboundMessage

        config = json.loads(step.config_json) if isinstance(step.config_json, str) else step.config_json

        # Handle None config gracefully
        if not config:
            config = {}

        skill_type = config.get("skill_type", "")
        prompt_template = config.get("prompt", "")
        skill_config_override = config.get("skill_config", {})

        # Get agent_id from step, config, or flow's default
        agent_id = step.agent_id or config.get("agent_id")
        if not agent_id and flow_run:
            flow = self.db.query(FlowDefinition).filter(
                FlowDefinition.id == flow_run.flow_definition_id
            ).first()
            if flow:
                agent_id = flow.default_agent_id

        # Fallback to agent 1 if still no agent
        if not agent_id:
            agent_id = 1

        # Resolve template variables in prompt
        prompt = self._replace_variables(prompt_template, input_data)

        logger.info(f"Executing skill '{skill_type}' with prompt: {prompt[:100]}...")

        try:
            # Get skill manager and validate skill exists
            skill_manager = get_skill_manager()

            if skill_type not in skill_manager.registry:
                raise ValueError(f"Skill type '{skill_type}' is not registered. Available: {list(skill_manager.registry.keys())}")

            skill_class = skill_manager.registry[skill_type]

            # Create skill instance
            # Some skills need special initialization (knowledge_sharing)
            if skill_type == "knowledge_sharing":
                skill_instance = skill_class(self.db, agent_id)
            else:
                skill_instance = skill_class()

            # Set database session for API key loading
            if hasattr(skill_instance, 'set_db_session'):
                skill_instance.set_db_session(self.db)

            # Set agent_id for skill context
            skill_instance._agent_id = agent_id

            # Create an InboundMessage with the prompt
            # This simulates a user message that the skill will process
            inbound_message = InboundMessage(
                id=f"flow_{flow_run.id}_step_{step.id}",
                sender=f"flow_step_{step.id}",
                sender_key=f"flow_{flow_run.id}",
                body=prompt,
                chat_id=f"flow_{flow_run.id}",
                chat_name=f"Flow: {flow_run.id}",
                is_group=False,
                timestamp=datetime.utcnow(),
                media_type=None,
                media_url=None,
                media_path=None,
                channel="flow"  # Skills-as-Tools: flow step execution
            )

            # Get skill config from agent settings, with overrides
            agent_skill_config = await skill_manager.get_skill_config(self.db, agent_id, skill_type)
            final_config = {
                **(agent_skill_config or skill_class.get_default_config()),
                **skill_config_override,
                "agent_id": agent_id
            }

            # Inject config for can_handle
            skill_instance._config = final_config

            # Phase 4 Skills-as-Tools: Determine execution mode
            # Tool mode requires explicit tool_arguments in step config.
            # If only a prompt is provided, use legacy mode (AI parameter extraction).
            use_tool_mode = config.get("use_tool_mode")  # None means auto-detect
            tool_arguments = config.get("tool_arguments", {})

            # Check if skill supports tool mode
            has_execute_tool = hasattr(skill_instance, 'execute_tool')
            is_tool_enabled = has_execute_tool and skill_instance.is_tool_enabled(final_config)

            # Auto-detect mode: use tool mode only if tool_arguments are explicitly provided
            if use_tool_mode is None:
                # Default behavior: use tool mode if tool_arguments exist, legacy otherwise
                use_tool_mode = bool(tool_arguments) and is_tool_enabled
                logger.info(f"SkillStepHandler: Auto-detected mode for '{skill_type}': "
                           f"{'tool' if use_tool_mode else 'legacy'} "
                           f"(tool_arguments={'yes' if tool_arguments else 'no'})")

            if use_tool_mode and has_execute_tool and is_tool_enabled:
                logger.info(f"SkillStepHandler: Using execute_tool() for skill '{skill_type}'")
                # Execute skill via tool mode
                result = await skill_instance.execute_tool(tool_arguments, inbound_message, final_config)
            else:
                # Legacy mode: Execute the skill via process()
                if use_tool_mode and has_execute_tool and not is_tool_enabled:
                    logger.info(f"SkillStepHandler: Tool mode preferred but not enabled for '{skill_type}', using process()")
                elif use_tool_mode and not has_execute_tool:
                    logger.info(f"SkillStepHandler: Skill '{skill_type}' doesn't support tool mode, using process()")
                else:
                    logger.info(f"SkillStepHandler: Using legacy mode for skill '{skill_type}' (prompt-based parameter extraction)")
                result = await skill_instance.process(inbound_message, final_config)

            # Determine actual execution mode used
            actual_execution_mode = "tool" if (use_tool_mode and has_execute_tool and is_tool_enabled) else "legacy"

            # Return structured output for template injection
            return {
                "skill_type": skill_type,
                "skill_name": skill_class.skill_name,
                "prompt": prompt,
                "success": result.success,
                "output": result.output,
                "processed_content": result.processed_content,
                "metadata": result.metadata,
                "status": "completed" if result.success else "failed",
                "agent_id": agent_id,
                "executed_at": datetime.utcnow().isoformat() + "Z",
                "execution_mode": actual_execution_mode
            }

        except Exception as e:
            logger.error(f"Skill execution failed: {e}", exc_info=True)
            return {
                "skill_type": skill_type,
                "prompt": prompt,
                "success": False,
                "output": f"Error executing skill: {str(e)}",
                "processed_content": None,
                "metadata": {"error": str(e)},
                "status": "failed",
                "agent_id": agent_id if 'agent_id' in dir() else None,
                "executed_at": datetime.utcnow().isoformat() + "Z"
            }


class ConversationStepHandler(FlowStepHandler):
    """
    Handles Conversation steps - starts/continues multi-turn conversations.

    Phase 8.0: Uses ConversationThread for state persistence instead of ScheduledEvent.
    Enhancement 2026-01-07: Added contact reference resolution for auto-discovery.
    """

    def _resolve_recipient(self, recipient: str) -> str:
        """
        Resolve @ContactName or phone to best WhatsApp identifier.

        Priority:
        1. If @ContactName → lookup contact
        2. If contact has whatsapp_id (known) → use it
        3. Else use phone number → will auto-discover on reply
        4. If plain number/ID → use as-is

        Args:
            recipient: Contact reference (@Name), phone number, or WhatsApp ID

        Returns:
            Resolved recipient identifier
        """
        # Handle @ContactName references
        if recipient.startswith('@'):
            from models import Contact
            contact_name = recipient[1:]  # Remove @ prefix

            try:
                contact = self.db.query(Contact).filter(
                    Contact.friendly_name == contact_name
                ).first()

                if contact:
                    # Prefer known WhatsApp ID, fallback to phone
                    if contact.whatsapp_id:
                        logger.info(
                            f"✅ RESOLVED: @{contact_name} → WhatsApp ID {contact.whatsapp_id} (cached)"
                        )
                        # Return WhatsApp ID in proper format
                        return f"{contact.whatsapp_id}@lid"
                    elif contact.phone_number:
                        logger.info(
                            f"✅ RESOLVED: @{contact_name} → phone {contact.phone_number} "
                            "(will auto-discover WhatsApp ID on reply)"
                        )
                        return contact.phone_number
                    else:
                        logger.warning(
                            f"⚠️ Contact {contact_name} has no phone or WhatsApp ID! "
                            "Using as-is."
                        )
                        return recipient
                else:
                    logger.warning(
                        f"⚠️ Contact @{contact_name} not found, using recipient as-is"
                    )
                    return recipient
            except Exception as e:
                logger.error(f"Error resolving contact reference @{contact_name}: {e}")
                return recipient

        # Plain phone number or ID - use as-is
        return recipient

    async def execute(
        self,
        step: FlowNode,
        input_data: Dict[str, Any],
        flow_run: FlowRun,
        step_run: FlowNodeRun
    ) -> Dict[str, Any]:
        """Start conversation and optionally create ConversationThread."""
        config = json.loads(step.config_json) if isinstance(step.config_json, str) else step.config_json

        # Channel guard: WhatsApp and Telegram supported
        channel = config.get("channel", "whatsapp")
        if channel not in ("whatsapp", "telegram"):
            logger.warning(f"Conversation step uses unsupported channel '{channel}', skipping")
            return {
                "status": "skipped",
                "channel": channel,
                "error": f"Channel '{channel}' is not yet supported for flow conversations",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        # Get agent_id from step, config, or flow's default
        agent_id = step.agent_id or config.get("agent_id")
        if not agent_id and flow_run.flow:
            agent_id = flow_run.flow.default_agent_id

        recipient = config.get("recipient", "")
        objective = step.conversation_objective or config.get("objective", "")
        initial_prompt = config.get("initial_prompt", config.get("initial_prompt_template", ""))
        # Bug Fix 2026-01-07: Also check for "initial_message" key (used by UI)
        initial_message_from_config = config.get("initial_message", "")
        allow_multi_turn = step.allow_multi_turn
        max_turns = step.max_turns or config.get("max_turns", 20)
        persona_id = step.persona_id or config.get("persona_id")

        # Phase 17: Blocking conversation mode
        wait_for_completion = config.get("wait_for_completion", False)
        poll_interval = config.get("poll_interval_seconds", 10)
        max_wait_time = config.get("max_wait_seconds", 600)  # 10 min default

        # BUG-FLOWS-002 FIX: Cap max_wait_time to not exceed step timeout
        # This prevents conversation steps from waiting longer than the step timeout allows
        step_timeout = step.timeout_seconds if step and step.timeout_seconds else DEFAULT_STEP_TIMEOUT
        if max_wait_time > step_timeout - 30:  # Leave 30s buffer for processing
            logger.warning(
                f"max_wait_seconds ({max_wait_time}s) exceeds step timeout ({step_timeout}s), "
                f"capping to {step_timeout - 30}s"
            )
            max_wait_time = max(60, step_timeout - 30)  # At least 60s, leave 30s buffer

        # Enhancement 2026-01-07: Resolve contact references (@ContactName) to WhatsApp IDs
        # This allows users to use friendly names instead of cryptic WhatsApp Business IDs
        recipient = self._resolve_recipient(recipient)

        # Variable replacement
        recipient = self._replace_variables(recipient, input_data)
        objective = self._replace_variables(objective, input_data)
        initial_prompt = self._replace_variables(initial_prompt, input_data)
        initial_message_from_config = self._replace_variables(initial_message_from_config, input_data)

        logger.info(f"Starting conversation with agent {agent_id} for {recipient}")

        # Generate and send initial message
        # Priority: initial_message (UI key) > initial_prompt > objective
        # Bug Fix 2026-01-07: Never send the objective as the message!
        initial_message = initial_message_from_config or initial_prompt or "Oi"

        try:
            # Resolve MCP URL and secret - use tenant context from flow_run and step
            mcp_url, api_secret = self._resolve_mcp_url_and_secret(recipient, flow_run=flow_run, step=step)

            # Check MCP health before proceeding
            if not self._check_mcp_connection(mcp_url):
                logger.error(f"MCP not ready at {mcp_url}, cannot start conversation")
                return {
                    "agent_id": agent_id,
                    "recipient": recipient,
                    "objective": objective,
                    "mcp_url": mcp_url,
                    "status": "failed",
                    "error": "MCP instance not connected or authenticated"
                }

            # If this is a multi-turn conversation, create a ConversationThread
            thread = None
            if allow_multi_turn:
                thread = ConversationThread(
                    flow_step_run_id=step_run.id,
                    status='active',
                    current_turn=1,
                    max_turns=max_turns,
                    recipient=recipient,
                    agent_id=agent_id,
                    persona_id=persona_id,
                    objective=objective,
                    conversation_history=[{
                        "role": "agent",
                        "content": initial_message,
                        "timestamp": datetime.utcnow().isoformat() + "Z"
                    }],
                    context_data=input_data,
                    started_at=datetime.utcnow(),
                    last_activity_at=datetime.utcnow(),
                    timeout_at=datetime.utcnow() + timedelta(hours=24)
                )
                self.db.add(thread)
                self.db.commit()
                self.db.refresh(thread)

                logger.info(f"Created conversation thread {thread.id} for multi-turn conversation")

            # Send initial message (Phase Security-1: with authentication)
            success = await self.mcp_sender.send_message(recipient, initial_message, api_url=mcp_url, api_secret=api_secret)

            # Phase 17: If wait_for_completion is enabled, poll until conversation finishes
            if allow_multi_turn and wait_for_completion:
                logger.info(f"Waiting for conversation thread {thread.id} to complete (max {max_wait_time}s)...")

                start_wait_time = datetime.utcnow()
                elapsed = 0

                while elapsed < max_wait_time:
                    # Refresh thread from DB
                    self.db.refresh(thread)

                    # Check if conversation is complete
                    if thread.status in ['completed', 'goal_achieved', 'timeout']:
                        logger.info(
                            f"Conversation thread {thread.id} finished with status '{thread.status}' "
                            f"after {elapsed}s ({thread.current_turn} turns)"
                        )

                        # Build conversation transcript for next steps
                        transcript = ""
                        for msg in thread.conversation_history:
                            role = "Agent" if msg["role"] == "agent" else "User"
                            transcript += f"{role}: {msg['content']}\n"

                        return {
                            "thread_id": thread.id,
                            "agent_id": agent_id,
                            "recipient": recipient,
                            "objective": objective,
                            "initial_message": initial_message,
                            "mcp_url": mcp_url,
                            "allow_multi_turn": True,
                            "max_turns": max_turns,
                            "conversation_status": thread.status,
                            "current_turn": thread.current_turn,
                            "goal_achieved": thread.goal_achieved,
                            "goal_summary": thread.goal_summary,
                            "conversation_history": thread.conversation_history,
                            "transcript": transcript,
                            "wait_time_seconds": elapsed,
                            "status": "completed",
                            "message": f"Conversation completed with status '{thread.status}'"
                        }

                    # Wait before next poll
                    await asyncio.sleep(poll_interval)
                    elapsed = int((datetime.utcnow() - start_wait_time).total_seconds())

                    # Log progress periodically
                    if elapsed % 60 == 0 and elapsed > 0:
                        logger.info(
                            f"Still waiting for thread {thread.id}... "
                            f"({elapsed}s elapsed, status={thread.status}, turns={thread.current_turn})"
                        )

                # Timeout reached
                logger.warning(
                    f"Conversation thread {thread.id} did not complete within {max_wait_time}s "
                    f"(status={thread.status}, turns={thread.current_turn})"
                )

                # Build partial transcript
                transcript = ""
                for msg in thread.conversation_history:
                    role = "Agent" if msg["role"] == "agent" else "User"
                    transcript += f"{role}: {msg['content']}\n"

                return {
                    "thread_id": thread.id,
                    "agent_id": agent_id,
                    "recipient": recipient,
                    "objective": objective,
                    "conversation_status": thread.status,
                    "current_turn": thread.current_turn,
                    "goal_achieved": thread.goal_achieved,
                    "conversation_history": thread.conversation_history,
                    "transcript": transcript,
                    "wait_time_seconds": max_wait_time,
                    "status": "timeout",
                    "error": f"Conversation did not complete within {max_wait_time}s",
                    "message": "Conversation timed out while waiting for completion"
                }

            # Original non-blocking behavior
            if allow_multi_turn:
                return {
                    "thread_id": thread.id,
                    "agent_id": agent_id,
                    "recipient": recipient,
                    "objective": objective,
                    "initial_message": initial_message,
                    "mcp_url": mcp_url,
                    "allow_multi_turn": True,
                    "max_turns": max_turns,
                    "conversation_status": "started",
                    "status": "completed" if success else "failed",
                    "message": "Conversation thread created and initial message sent"
                }
            else:
                return {
                    "agent_id": agent_id,
                    "recipient": recipient,
                    "objective": objective,
                    "message_sent": initial_message,
                    "mcp_url": mcp_url,
                    "allow_multi_turn": False,
                    "status": "completed" if success else "failed",
                    "message": "Single-turn message sent"
                }

        except Exception as e:
            logger.error(f"Failed to start conversation: {e}")
            return {
                "agent_id": agent_id,
                "recipient": recipient,
                "status": "failed",
                "error": str(e)
            }


class SummarizationStepHandler(FlowStepHandler):
    """
    Phase 17: Agentic Summarization Step Handler

    Generates AI-powered summaries of:
    1. Conversation transcripts (via thread_id from conversation steps)
    2. Raw text output (via source_step from tool/skill steps)

    Config schema:
    {
        "source_step": "step_1",      # Step name/position to get content from
        "thread_id": 123,              # Or explicit thread_id (for conversation steps)
        "summary_prompt": "...",       # Custom summarization instructions
        "output_format": "brief|detailed|structured|minimal",  # Output style
        "prompt_mode": "append|replace",  # How to use summary_prompt
        "model": "gemini-2.5-flash"    # Optional: AI model to use
    }

    Resolution priority:
    1. Explicit thread_id in config
    2. thread_id from source_step output (conversation steps)
    3. raw_output from source_step output (tool/skill steps)
    4. previous_step fallback (if no source_step specified)

    Output formats:
    - "brief": Concise 2-3 sentence summary (default)
    - "detailed": Comprehensive summary with key points and outcomes
    - "structured": Sections for Objective, Key Points, Outcome, Next Steps
    - "minimal": Extract only essential data points, no analysis

    Prompt modes:
    - "append": Add summary_prompt to default template (default)
    - "replace": Use summary_prompt as the full prompt (for complete control)

    Legacy: summary_prompt starting with "OVERRIDE:" also triggers replace mode.
    """

    async def execute(
        self,
        step: FlowNode,
        input_data: Dict[str, Any],
        flow_run: FlowRun,
        step_run: FlowNodeRun
    ) -> Dict[str, Any]:
        """Generate AI summary of conversation transcript or raw text output."""
        config = json.loads(step.config_json) if isinstance(step.config_json, str) else step.config_json

        # Get thread_id from previous step or explicit config
        thread_id = config.get("thread_id")
        source_step = config.get("source_step")
        source_text = None  # Raw text from source step (for tool/skill outputs)

        if not thread_id and source_step:
            # Use proper nested dict access (source_step is a context key like "step_1")
            source_data = input_data.get(source_step, {})
            if isinstance(source_data, dict):
                thread_id = source_data.get("thread_id")

            # Fallback: check root-level thread_id (backward compat)
            if not thread_id:
                thread_id = input_data.get("thread_id")

            # If still no thread_id, try to get raw text from source step
            if not thread_id and isinstance(source_data, dict):
                source_text = (
                    source_data.get("raw_output")
                    or source_data.get("summary")
                    or source_data.get("search_results")
                    or source_data.get("error")
                )

        # If no source_step and no thread_id, try previous_step as fallback
        if not thread_id and not source_text:
            prev = input_data.get("previous_step", {})
            if isinstance(prev, dict):
                thread_id = prev.get("thread_id")
                if not thread_id:
                    source_text = (
                        prev.get("raw_output")
                        or prev.get("summary")
                        or prev.get("search_results")
                        or prev.get("error")
                    )

        if not thread_id and not source_text:
            return {
                "status": "failed",
                "error": "No thread_id or source text found. Specify 'thread_id', 'source_step' (with raw_output), or provide text to summarize.",
                "summary": ""
            }

        # === Path B: Raw text summarization (for tool/skill outputs) ===
        if not thread_id and source_text:
            return await self._summarize_raw_text(source_text, config, source_step)

        # === Path A: Thread-based summarization (for conversation steps) ===
        try:
            # Fetch conversation thread
            thread = self.db.query(ConversationThread).filter(
                ConversationThread.id == thread_id
            ).first()

            if not thread:
                return {
                    "status": "failed",
                    "error": f"Conversation thread {thread_id} not found",
                    "summary": ""
                }

            # Optional wait: ensure conversation completes before summarizing
            wait_for_completion = config.get("wait_for_completion", True)
            poll_interval = config.get("poll_interval_seconds", 5)
            max_wait_time = config.get("max_wait_seconds", 600)
            allowed_completion_statuses = {"completed", "goal_achieved"}
            terminal_statuses = allowed_completion_statuses | {"timeout"}

            if wait_for_completion and thread.status == "active":
                logger.info(
                    f"Waiting for conversation thread {thread_id} to complete "
                    f"(max {max_wait_time}s, poll {poll_interval}s)..."
                )
                start_wait_time = datetime.utcnow()
                elapsed = 0

                while elapsed < max_wait_time:
                    await asyncio.sleep(poll_interval)
                    self.db.refresh(thread)
                    if thread.status in terminal_statuses:
                        break
                    elapsed = int((datetime.utcnow() - start_wait_time).total_seconds())

                if thread.status not in terminal_statuses:
                    logger.warning(
                        f"Conversation thread {thread_id} did not reach a terminal status "
                        f"within {max_wait_time}s (status={thread.status})"
                    )

            if wait_for_completion and thread.status not in allowed_completion_statuses:
                return {
                    "status": "failed",
                    "error": f"Conversation thread not completed (status={thread.status})",
                    "summary": "",
                    "thread_id": thread_id,
                    "conversation_status": thread.status
                }

            # Build transcript from conversation history
            transcript = ""
            for msg in thread.conversation_history:
                role = "Agent" if msg["role"] == "agent" else "User"
                timestamp = msg.get("timestamp", "")
                content = msg.get("content", "")
                transcript += f"[{timestamp}] {role}: {content}\n"

            if not transcript:
                return {
                    "status": "failed",
                    "error": "Conversation transcript is empty",
                    "summary": "",
                    "thread_id": thread_id
                }

            # Get summarization parameters
            output_format = config.get("output_format", "brief")
            custom_prompt = config.get("summary_prompt", "")
            prompt_mode = config.get("prompt_mode", "append")

            # Get model from config, or from thread's agent, or fallback
            model = config.get("model")
            model_provider = config.get("model_provider")

            # If model or model_provider missing, try to get from agent config
            if (not model or not model_provider) and thread.agent_id:
                agent = self.db.query(Agent).filter(Agent.id == thread.agent_id).first()
                if agent:
                    if not model and agent.model_name:
                        model = agent.model_name
                    if not model_provider and agent.model_provider:
                        model_provider = agent.model_provider
                    logger.info(f"Using agent {agent.id}'s model config: {model_provider}/{model}")

            # Fallback if still not set
            if not model:
                model = "gemini-2.5-flash"
            if not model_provider:
                # Infer provider from model name
                if model.startswith("gpt-") or model.startswith("o1") or model.startswith("o3"):
                    model_provider = "openai"
                elif model.startswith("claude"):
                    model_provider = "anthropic"
                else:
                    model_provider = "gemini"  # Default
                logger.warning(f"Model provider not configured, inferred '{model_provider}' for model '{model}'")

            # Build summarization prompt based on prompt_mode
            # Legacy support: "OVERRIDE:" prefix triggers replace mode
            if prompt_mode == "replace" or custom_prompt.startswith("OVERRIDE:"):
                # Custom prompt fully replaces the base prompt
                prompt_text = custom_prompt[9:].strip() if custom_prompt.startswith("OVERRIDE:") else custom_prompt
                base_prompt = f"""{prompt_text}

Conversation Transcript:
{transcript}"""
            else:
                # Default: use format instructions with optional custom additions
                format_instructions = {
                    "brief": "Provide a concise 2-3 sentence summary.",
                    "detailed": "Provide a comprehensive summary with key points and outcomes.",
                    "structured": "Provide a structured summary with sections: Objective, Key Points, Outcome, Next Steps.",
                    "minimal": "Extract ONLY the essential data points (status, dates, numbers, outcomes). No analysis, no narrative. Maximum 3-5 lines."
                }

                format_instruction = format_instructions.get(output_format, format_instructions["brief"])

                # Minimal format has a different base structure
                if output_format == "minimal":
                    base_prompt = f"""{format_instruction}

Conversation Transcript:
{transcript}

{custom_prompt}"""
                else:
                    base_prompt = f"""Analyze the following customer service conversation transcript and provide a summary.

{format_instruction}

Focus on:
- The customer's objective/request
- Key information exchanged
- Resolution or outcome
- Any tracking numbers, codes, or important details

Conversation Transcript:
{transcript}

{custom_prompt}

Summary:"""

            # Use AIClient to generate summary (supports all providers)
            # Phase 7.2: Token tracking integrated via handler's token_tracker
            from agent.ai_client import AIClient

            ai_client = AIClient(
                provider=model_provider,
                model_name=model,
                db=self.db,
                token_tracker=self.token_tracker
            )

            logger.info(f"Generating summary for thread {thread_id} using {model_provider}/{model}...")

            # Generate summary using AIClient
            response = await ai_client.generate(
                system_prompt="You are a helpful assistant that summarizes conversations.",
                user_message=base_prompt,
                operation_type="conversation_summarization"
            )

            if response.get('error'):
                return {
                    "status": "failed",
                    "error": f"AI generation error: {response['error']}",
                    "summary": "",
                    "thread_id": thread_id
                }

            summary = response.get('answer', '').strip()

            logger.info(f"Generated summary ({len(summary)} chars) for thread {thread_id}")

            return {
                "status": "completed",
                "summary": summary,
                "transcript": transcript,
                "thread_id": thread_id,
                "conversation_status": thread.status,
                "goal_achieved": thread.goal_achieved,
                "goal_summary": thread.goal_summary,
                "turns": thread.current_turn,
                "model_used": f"{model_provider}/{model}",
                "output_format": output_format
            }

        except Exception as e:
            logger.error(f"Summarization failed: {e}", exc_info=True)
            return {
                "status": "failed",
                "error": str(e),
                "summary": "",
                "thread_id": thread_id
            }

    async def _summarize_raw_text(
        self,
        source_text: str,
        config: Dict[str, Any],
        source_step: Optional[str] = None
    ) -> Dict[str, Any]:
        """Summarize raw text output from tool/skill steps using AI."""
        try:
            # Convert structured data to string
            if isinstance(source_text, (dict, list)):
                transcript = json.dumps(source_text, ensure_ascii=False, indent=2)
            else:
                transcript = str(source_text)

            if not transcript.strip():
                return {
                    "status": "failed",
                    "error": "Source text is empty",
                    "summary": "",
                    "source_step": source_step
                }

            output_format = config.get("output_format", "brief")
            custom_prompt = config.get("summary_prompt", "")
            prompt_mode = config.get("prompt_mode", "append")

            model = config.get("model")
            model_provider = config.get("model_provider")

            if not model:
                model = "gemini-2.5-flash"
            if not model_provider:
                if model.startswith("gpt-") or model.startswith("o1") or model.startswith("o3"):
                    model_provider = "openai"
                elif model.startswith("claude"):
                    model_provider = "anthropic"
                else:
                    model_provider = "gemini"
                logger.warning(f"Model provider not configured, inferred '{model_provider}' for model '{model}'")

            # Build prompt
            if prompt_mode == "replace" or (custom_prompt and custom_prompt.startswith("OVERRIDE:")):
                prompt_text = custom_prompt[9:].strip() if custom_prompt.startswith("OVERRIDE:") else custom_prompt
                base_prompt = f"""{prompt_text}

Text to summarize:
{transcript}"""
            else:
                format_instructions = {
                    "brief": "Provide a concise 2-3 sentence summary.",
                    "detailed": "Provide a comprehensive summary with key points and outcomes.",
                    "structured": "Provide a structured summary with sections: Objective, Key Points, Outcome, Next Steps.",
                    "minimal": "Extract ONLY the essential data points (status, dates, numbers, outcomes). No analysis, no narrative. Maximum 3-5 lines."
                }
                format_instruction = format_instructions.get(output_format, format_instructions["brief"])

                if output_format == "minimal":
                    base_prompt = f"""{format_instruction}

Text to summarize:
{transcript}

{custom_prompt}"""
                else:
                    base_prompt = f"""Analyze the following text output and provide a summary.

{format_instruction}

Focus on:
- Key findings and results
- Important data points, numbers, or identifiers
- Status and outcome
- Any errors or warnings

Text to summarize:
{transcript}

{custom_prompt}

Summary:"""

            from agent.ai_client import AIClient

            ai_client = AIClient(
                provider=model_provider,
                model_name=model,
                db=self.db,
                token_tracker=self.token_tracker
            )

            source_label = source_step or "previous_step"
            logger.info(f"Generating summary for raw text from '{source_label}' using {model_provider}/{model}...")

            response = await ai_client.generate(
                system_prompt="You are a helpful assistant that summarizes text output and technical results.",
                user_message=base_prompt,
                operation_type="text_summarization"
            )

            if response.get('error'):
                return {
                    "status": "failed",
                    "error": f"AI generation error: {response['error']}",
                    "summary": "",
                    "source_step": source_label
                }

            summary = response.get('answer', '').strip()
            logger.info(f"Generated summary ({len(summary)} chars) from raw text of '{source_label}'")

            return {
                "status": "completed",
                "summary": summary,
                "transcript": transcript,
                "source_step": source_label,
                "source_type": "raw_text",
                "model_used": f"{model_provider}/{model}",
                "output_format": output_format
            }

        except Exception as e:
            logger.error(f"Raw text summarization failed: {e}", exc_info=True)
            return {
                "status": "failed",
                "error": str(e),
                "summary": "",
                "source_step": source_step
            }


class GateStepHandler(FlowStepHandler):
    """
    Conditional Gate Step Handler — flow control node.

    Evaluates conditions against previous step outputs and either passes
    (status="completed") or blocks (status="failed") the flow.

    Two modes:
    - "programmatic": Zero LLM cost. Evaluates gate_conditions using operators.
    - "agentic": Sends source data + prompt to LLM for pass/fail decision.

    Config schema:
    {
        "gate_mode": "programmatic",           # or "agentic"
        "gate_conditions": [                   # programmatic mode
            {"field": "inbox.count", "operator": ">=", "value": 5, "type": "number"},
            {"field": "inbox.raw_output", "operator": "matches", "value": "urgent|critical", "type": "regex"}
        ],
        "gate_logic": "all",                   # "all" (AND) or "any" (OR)
        "gate_prompt": "...",                   # agentic mode prompt
        "gate_source_step": "inbox",           # step output to evaluate
        "gate_on_fail": "skip",                # "skip", "notify"
        "gate_fail_notification": {            # optional notification on fail
            "channel": "whatsapp",
            "recipient": "+5527...",
            "message_template": "Gate blocked: {{gate.reason}}"
        }
    }

    Supported operators (programmatic mode):
    - Numeric: ==, !=, >, >=, <, <=
    - String: contains, not_contains, starts_with, ends_with
    - Regex: matches
    - Existence: is_empty, is_not_empty
    - Collection: count_gte, count_lte
    - Boolean: == true/false
    """

    async def execute(self, step, input_data, flow_run, step_run):
        config = json.loads(step.config_json) if isinstance(step.config_json, str) else (step.config_json or {})
        gate_mode = config.get("gate_mode", "programmatic")
        gate_source_step = config.get("gate_source_step")
        gate_on_fail = config.get("gate_on_fail", "skip")

        logger.info(f"Gate step executing in '{gate_mode}' mode (source={gate_source_step})")

        # Resolve source data from step context
        source_data = self._resolve_source_data(gate_source_step, input_data)

        try:
            if gate_mode == "agentic":
                passed, reasoning, conditions_detail = await self._evaluate_agentic(
                    config, source_data, input_data, flow_run, step
                )
            else:
                passed, reasoning, conditions_detail = self._evaluate_programmatic(
                    config, source_data, input_data
                )
        except Exception as e:
            logger.error(f"Gate evaluation failed with exception: {e}", exc_info=True)
            # Fail-closed: exceptions block the flow
            passed = False
            reasoning = f"Gate evaluation error: {str(e)}"
            conditions_detail = []

        result = {
            "gate_result": "pass" if passed else "fail",
            "gate_mode": gate_mode,
            "conditions_evaluated": conditions_detail,
            "reasoning": reasoning,
        }

        if passed:
            logger.info(f"Gate PASSED: {reasoning}")
            result["status"] = "completed"
            return result

        # Gate failed
        logger.info(f"Gate FAILED: {reasoning}")

        # Handle gate_on_fail actions
        if gate_on_fail == "notify":
            fail_notif = config.get("gate_fail_notification")
            if fail_notif:
                try:
                    await self._send_gate_notification(fail_notif, result, input_data, flow_run, step)
                    result["fail_action_taken"] = "notify"
                except Exception as e:
                    logger.warning(f"Gate fail notification failed: {e}")
                    result["fail_action_taken"] = "notify_failed"
        else:
            result["fail_action_taken"] = "skip"

        result["status"] = "failed"
        return result

    def _resolve_source_data(self, gate_source_step, input_data):
        """Resolve the source step's output data from context."""
        if not gate_source_step:
            # Default to previous_step
            return input_data.get("previous_step", {})

        # Try exact key first (step name or alias)
        if gate_source_step in input_data:
            return input_data[gate_source_step]

        # Try step_N format
        if gate_source_step.startswith("step_"):
            return input_data.get(gate_source_step, {})

        # Try previous_step as fallback
        return input_data.get("previous_step", {})

    def _resolve_field_path(self, path, data):
        """Navigate a dot-separated field path through nested dicts/lists.

        Examples:
            "count" -> data["count"]
            "raw_output.items" -> data["raw_output"]["items"]
            "items[0].subject" -> data["items"][0]["subject"]
        """
        if not path or data is None:
            return None

        parts = []
        for segment in path.split("."):
            # Handle array indexing: "items[0]" -> "items", 0
            if "[" in segment and segment.endswith("]"):
                key, idx_str = segment.rstrip("]").split("[", 1)
                if key:
                    parts.append(key)
                try:
                    parts.append(int(idx_str))
                except ValueError:
                    parts.append(idx_str)
            else:
                parts.append(segment)

        current = data
        for part in parts:
            if current is None:
                return None
            if isinstance(part, int):
                if isinstance(current, (list, tuple)) and 0 <= part < len(current):
                    current = current[part]
                else:
                    return None
            elif isinstance(current, dict):
                current = current.get(part)
            else:
                # Try attribute access as fallback
                current = getattr(current, str(part), None)
        return current

    def _evaluate_programmatic(self, config, source_data, input_data):
        """Evaluate programmatic gate conditions. Zero LLM cost.

        Returns (passed: bool, reasoning: str, conditions_detail: list)
        """
        conditions = config.get("gate_conditions", [])
        logic = config.get("gate_logic", "all")

        if not conditions:
            # No conditions = auto-pass
            return True, "No conditions defined — gate passes by default", []

        results = []
        for cond in conditions:
            field_path = cond.get("field", "")
            operator = cond.get("operator", "is_not_empty")
            expected = cond.get("value")
            value_type = cond.get("type", "string")

            # Resolve the field value — try source data first, then full context
            actual = self._resolve_field_path(field_path, source_data)
            if actual is None:
                actual = self._resolve_field_path(field_path, input_data)

            passed = self._evaluate_condition(actual, operator, expected, value_type)
            results.append({
                "field": field_path,
                "operator": operator,
                "expected": expected,
                "actual": self._safe_serialize(actual),
                "passed": passed,
            })

        if logic == "any":
            overall = any(r["passed"] for r in results)
            mode_label = "ANY"
        else:
            overall = all(r["passed"] for r in results)
            mode_label = "ALL"

        passed_count = sum(1 for r in results if r["passed"])
        total = len(results)
        reasoning = f"{mode_label} logic: {passed_count}/{total} conditions passed"

        return overall, reasoning, results

    def _evaluate_condition(self, actual, operator, expected, value_type):
        """Evaluate a single condition. Returns bool."""
        try:
            # Existence checks (work on any type)
            if operator == "is_empty":
                if actual is None:
                    return True
                if isinstance(actual, (str, list, dict, tuple)):
                    return len(actual) == 0
                return actual == 0 or actual == ""
            if operator == "is_not_empty":
                if actual is None:
                    return False
                if isinstance(actual, (str, list, dict, tuple)):
                    return len(actual) > 0
                return actual != 0 and actual != ""

            # Count operations (on collections)
            if operator == "count_gte":
                return self._safe_len(actual) >= int(expected)
            if operator == "count_lte":
                return self._safe_len(actual) <= int(expected)

            # Regex matching
            if operator == "matches":
                return bool(re.search(str(expected), str(actual or ""), re.IGNORECASE))

            # String operations
            if operator == "contains":
                return str(expected).lower() in str(actual or "").lower()
            if operator == "not_contains":
                return str(expected).lower() not in str(actual or "").lower()
            if operator == "starts_with":
                return str(actual or "").lower().startswith(str(expected).lower())
            if operator == "ends_with":
                return str(actual or "").lower().endswith(str(expected).lower())

            # Numeric comparisons
            if value_type == "number" or operator in (">", ">=", "<", "<="):
                a = float(actual) if actual is not None else 0
                e = float(expected) if expected is not None else 0
                if operator == "==":
                    return a == e
                if operator == "!=":
                    return a != e
                if operator == ">":
                    return a > e
                if operator == ">=":
                    return a >= e
                if operator == "<":
                    return a < e
                if operator == "<=":
                    return a <= e

            # Boolean comparisons
            if value_type == "boolean":
                a = self._to_bool(actual)
                e = self._to_bool(expected)
                if operator == "==":
                    return a == e
                if operator == "!=":
                    return a != e

            # Default string equality
            if operator == "==":
                return str(actual or "") == str(expected or "")
            if operator == "!=":
                return str(actual or "") != str(expected or "")

            logger.warning(f"Unknown gate operator: {operator}")
            return False

        except (TypeError, ValueError) as e:
            logger.debug(f"Condition evaluation type error: {e}")
            return False

    async def _evaluate_agentic(self, config, source_data, input_data, flow_run, step):
        """Evaluate gate condition using LLM. Returns (passed, reasoning, detail)."""
        gate_prompt = config.get("gate_prompt", "")
        if not gate_prompt:
            return False, "No gate_prompt defined for agentic mode", []

        # Resolve template variables in prompt
        resolved_prompt = self._replace_variables(gate_prompt, input_data)

        # Serialize source data (truncate to control token usage)
        source_str = self._safe_serialize(source_data, max_length=4000)

        system_prompt = (
            "You are a gate evaluator for an automated workflow. "
            "Your job is to evaluate whether the data below satisfies the given condition. "
            "Reply with EXACTLY one line starting with 'PASS:' or 'FAIL:' followed by a brief reason.\n\n"
            "Example responses:\n"
            "PASS: The data contains 5 unread financial emails matching the criteria.\n"
            "FAIL: No emails related to financial topics were found in the data."
        )

        user_message = (
            f"## Data to evaluate:\n{source_str}\n\n"
            f"## Condition to check:\n{resolved_prompt}\n\n"
            "Respond with PASS: or FAIL: followed by your reasoning."
        )

        # Resolve agent/model — same pattern as SummarizationStepHandler
        agent_id = step.agent_id or (flow_run.flow.default_agent_id if flow_run.flow else None)

        # Resolve model from agent config
        model = None
        model_provider = None
        if agent_id:
            from models import Agent
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            if agent:
                model = agent.model_name
                model_provider = agent.model_provider

        if not model:
            model = "gemini-2.5-flash"
        if not model_provider:
            if model.startswith("gpt-") or model.startswith("o1") or model.startswith("o3"):
                model_provider = "openai"
            elif model.startswith("claude"):
                model_provider = "anthropic"
            else:
                model_provider = "gemini"

        # Resolve tenant_id for API key lookup
        tenant_id = getattr(flow_run, 'tenant_id', None)

        try:
            from agent.ai_client import AIClient
            ai_client = AIClient(
                provider=model_provider,
                model_name=model,
                db=self.db,
                token_tracker=self.token_tracker,
                tenant_id=tenant_id,
            )
            response = await ai_client.generate(
                system_prompt=system_prompt,
                user_message=user_message,
                operation_type="gate_evaluation",
            )
            if response.get("error"):
                raise RuntimeError(response["error"])
            response_text = response.get("answer", "")
        except Exception as e:
            logger.error(f"Agentic gate LLM call failed: {e}")
            # Fail-closed: LLM failures block the flow
            return False, f"LLM evaluation failed: {str(e)}", []

        # Parse PASS/FAIL from response
        response_text = (response_text or "").strip()
        response_upper = response_text.upper()

        if response_upper.startswith("PASS"):
            passed = True
            reasoning = response_text[5:].strip(": ") if len(response_text) > 4 else "LLM approved"
        elif response_upper.startswith("FAIL"):
            passed = False
            reasoning = response_text[5:].strip(": ") if len(response_text) > 4 else "LLM rejected"
        elif "PASS" in response_upper:
            passed = True
            reasoning = response_text
        elif "FAIL" in response_upper:
            passed = False
            reasoning = response_text
        else:
            # Unparseable — fail-closed
            passed = False
            reasoning = f"Unparseable LLM response (fail-closed): {response_text[:200]}"

        detail = [{
            "type": "agentic",
            "prompt": resolved_prompt[:200],
            "llm_response": response_text[:500],
            "passed": passed,
        }]

        return passed, reasoning, detail

    async def _send_gate_notification(self, notif_config, gate_result, input_data, flow_run, step):
        """Send a notification when gate fails (gate_on_fail='notify')."""
        channel = notif_config.get("channel", "whatsapp")
        recipient = notif_config.get("recipient")
        message_template = notif_config.get("message_template", "Gate blocked flow execution.")

        if not recipient:
            logger.warning("Gate fail notification has no recipient — skipping")
            return

        # Build gate context for template resolution
        gate_context = {**input_data, "gate": gate_result}
        message = self._replace_variables(message_template, gate_context)

        # Resolve recipient
        resolved = self._resolve_contact_to_phone(recipient, getattr(flow_run, 'tenant_id', None))
        if not resolved:
            resolved = recipient

        # Send via MCP (same pattern as NotificationStepHandler)
        mcp_url, mcp_secret = self._resolve_mcp_url_and_secret(resolved, flow_run, step)
        if mcp_url:
            try:
                await self.mcp_sender.send_message(resolved, message, api_url=mcp_url, api_secret=mcp_secret)
                logger.info(f"Gate fail notification sent to {resolved}")
            except Exception as e:
                logger.warning(f"Gate fail notification send error: {e}")

    @staticmethod
    def _safe_len(value):
        """Safely get length of a value."""
        if value is None:
            return 0
        if isinstance(value, (str, list, dict, tuple)):
            return len(value)
        return 0

    @staticmethod
    def _to_bool(value):
        """Convert a value to boolean."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes")
        return bool(value)

    @staticmethod
    def _safe_serialize(data, max_length=2000):
        """Safely serialize data to string with truncation."""
        if data is None:
            return "null"
        try:
            serialized = json.dumps(data, default=str, indent=2)
        except (TypeError, ValueError):
            serialized = str(data)
        if len(serialized) > max_length:
            return serialized[:max_length] + f"\n... (truncated, {len(serialized)} total chars)"
        return serialized


# Legacy handler for backward compatibility
class TriggerNodeHandler(FlowStepHandler):
    """
    Handles legacy Trigger nodes.

    Note: In Phase 8.0, triggers are flow-level metadata.
    This handler is kept for backward compatibility with existing flows.
    """

    async def execute(
        self,
        step: FlowNode,
        input_data: Dict[str, Any],
        flow_run: FlowRun,
        step_run: FlowNodeRun
    ) -> Dict[str, Any]:
        """Trigger nodes pass through context (legacy support)."""
        config = json.loads(step.config_json) if isinstance(step.config_json, str) else step.config_json
        trigger_context = json.loads(flow_run.trigger_context_json) if flow_run.trigger_context_json else {}

        logger.info(f"Trigger node executed (legacy) for flow {flow_run.flow_definition_id}")

        return {
            "agent_id": config.get("agent_id"),
            "recipients": config.get("recipients", []),
            "objective": config.get("objective", ""),
            "trigger_context": trigger_context,
            "context_fields": config.get("context_fields", {}),
            "status": "completed"
        }


class SubflowStepHandler(FlowStepHandler):
    """Handles Subflow steps - invokes another FlowDefinition."""

    def __init__(self, db: Session, mcp_sender: MCPSender, flow_engine, token_tracker=None):
        super().__init__(db, mcp_sender, token_tracker)
        self.flow_engine = flow_engine

    async def execute(
        self,
        step: FlowNode,
        input_data: Dict[str, Any],
        flow_run: FlowRun,
        step_run: FlowNodeRun
    ) -> Dict[str, Any]:
        """Recursively call FlowEngine to execute child flow."""
        config = json.loads(step.config_json) if isinstance(step.config_json, str) else step.config_json

        target_flow_id = config.get("target_flow_definition_id", config.get("subflow_id"))
        input_mapping = config.get("input_mapping", {})
        context_passthrough = config.get("context_passthrough", True)

        # Build child flow trigger context
        child_context = {}
        if context_passthrough:
            child_context = {**input_data}

        for target_key, source_value in input_mapping.items():
            if isinstance(source_value, str) and source_value.startswith("{{") and source_value.endswith("}}"):
                source_key = source_value[2:-2]
                child_context[target_key] = input_data.get(source_key)
            else:
                child_context[target_key] = source_value

        # SEC: Validate target flow belongs to same tenant (BUG-LOG-002)
        target_flow = self.db.query(FlowDefinition).filter(
            FlowDefinition.id == target_flow_id,
            FlowDefinition.tenant_id == flow_run.tenant_id
        ).first()
        if not target_flow:
            raise FlowValidationError(
                f"Subflow {target_flow_id} not found or belongs to different tenant"
            )

        logger.info(f"Starting subflow {target_flow_id}")

        child_run = await self.flow_engine.run_flow(
            flow_definition_id=target_flow_id,
            trigger_context=child_context,
            initiator="subflow",
            parent_run_id=flow_run.id,
            tenant_id=flow_run.tenant_id
        )

        return {
            "child_flow_run_id": child_run.id,
            "child_flow_definition_id": target_flow_id,
            "child_status": child_run.status,
            "child_final_report": json.loads(child_run.final_report_json) if child_run.final_report_json else None,
            "status": "completed" if child_run.status == "completed" else "failed"
        }


class BrowserAutomationStepHandler(FlowStepHandler):
    """
    Phase 14.5: Handles Browser Automation steps - executes browser actions via skill.

    Allows flows to control web browsers, navigate pages, take screenshots,
    extract content, and fill forms as part of automated workflows.

    Config schema:
    {
        "prompt": "take a screenshot of google.com",  # Natural language prompt
        "url": "https://example.com",                 # Direct URL (alternative to prompt)
        "mode": "container",                          # "container" or "host"
        "provider_type": "playwright",                # Browser provider
        "timeout_seconds": 30                         # Action timeout
    }
    """

    async def execute(
        self,
        step: FlowNode,
        input_data: Dict[str, Any],
        flow_run: FlowRun,
        step_run: FlowNodeRun
    ) -> Dict[str, Any]:
        """
        Execute browser automation actions and return results for subsequent steps.

        Args:
            step: FlowNode with browser automation configuration
            input_data: Input data from previous steps (for template resolution)
            flow_run: Current FlowRun for context
            step_run: Current FlowNodeRun for tracking

        Returns:
            Dict with browser automation output for template injection:
            {
                "status": "completed",
                "output": "Navigated to: Example Domain...",
                "screenshot_paths": ["/tmp/screenshot.png"],
                "actions_executed": 2,
                "provider": "playwright",
                "mode": "container"
            }
        """
        from agent.skills.browser_automation_skill import BrowserAutomationSkill
        from agent.skills.base import InboundMessage

        config = json.loads(step.config_json) if isinstance(step.config_json, str) else step.config_json

        # Handle None config gracefully
        if not config:
            config = {}

        # Resolve template variables in prompt and URL
        prompt_template = config.get("prompt", "")
        url = config.get("url", "")

        prompt = self._replace_variables(prompt_template, input_data)
        url = self._replace_variables(url, input_data)

        # Get tenant_id from flow_run
        tenant_id = flow_run.tenant_id if flow_run else None

        # Build the command (prefer prompt, fallback to URL navigation)
        command = prompt if prompt else f"navigate to {url}" if url else ""

        if not command:
            return {
                "status": "failed",
                "output": "No prompt or URL specified for browser automation",
                "error": "Missing configuration: either 'prompt' or 'url' required",
                "screenshot_paths": [],
                "actions_executed": 0
            }

        logger.info(f"Executing browser automation: {command[:100]}...")

        try:
            # Create skill instance with db and token_tracker
            skill = BrowserAutomationSkill(db=self.db, token_tracker=self.token_tracker)

            # Create synthetic message for skill processing
            message = InboundMessage(
                id=f"flow_{flow_run.id}_step_{step.id}",
                sender=f"flow_step_{step.id}",
                sender_key=f"flow_{flow_run.id}",
                body=command,
                chat_id=f"flow_{flow_run.id}",
                chat_name=f"Flow: {flow_run.id}",
                is_group=False,
                timestamp=datetime.utcnow(),
                channel="flow"  # Skills-as-Tools: browser automation step
            )

            # Build skill config from step config
            skill_config = {
                "mode": config.get("mode", "container"),
                "provider_type": config.get("provider_type", "playwright"),
                "timeout_seconds": config.get("timeout_seconds", 30),
                "allowed_user_keys": config.get("allowed_user_keys", []),
                "keywords": ["browser", "navigate", "screenshot", "click", "fill", "extract"],
                "use_ai_fallback": True
            }

            # Phase 4 Skills-as-Tools: Check if step config requests tool mode execution
            use_tool_mode = config.get("use_tool_mode", False)
            tool_action = config.get("tool_action")  # e.g., "navigate", "screenshot", etc.
            tool_arguments = config.get("tool_arguments", {})

            if use_tool_mode and tool_action and skill.is_tool_enabled(skill_config):
                # Execute via tool mode with explicit action and arguments
                arguments = {
                    "action": tool_action,
                    **tool_arguments,
                    "mode": config.get("mode", "container")
                }
                # Add URL to arguments if specified
                if url and tool_action == "navigate":
                    arguments["url"] = url
                logger.info(f"BrowserAutomationStepHandler: Using execute_tool() with action='{tool_action}'")
                result = await skill.execute_tool(arguments, message, skill_config)
                execution_mode = "tool"
            else:
                # Legacy mode: Execute the skill via natural language processing
                result = await skill.process(message, skill_config)
                execution_mode = "legacy"

            return {
                "status": "completed" if result.success else "failed",
                "output": result.output,
                "screenshot_paths": result.media_paths or result.metadata.get("screenshot_paths", []),
                "actions_executed": result.metadata.get("actions_executed", 1 if result.success else 0),
                "actions_succeeded": result.metadata.get("actions_succeeded", 1 if result.success else 0),
                "provider": result.metadata.get("provider"),
                "mode": result.metadata.get("mode"),
                "error": result.metadata.get("error") if not result.success else None,
                "executed_at": datetime.utcnow().isoformat() + "Z",
                "execution_mode": execution_mode
            }

        except Exception as e:
            logger.error(f"Browser automation step failed: {e}", exc_info=True)
            return {
                "status": "failed",
                "output": f"Browser automation error: {str(e)}",
                "error": str(e),
                "screenshot_paths": [],
                "actions_executed": 0,
                "executed_at": datetime.utcnow().isoformat() + "Z"
            }


class FlowEngine:
    """
    Main execution engine for Unified Flows.

    Responsibilities:
    - Load and validate FlowDefinition
    - Execute steps in linear order with retry support
    - Handle timeouts, errors, retries
    - Generate final report
    - Support ConversationThread for multi-turn conversations
    - Track token usage and costs (Phase 7.2)
    """

    def __init__(self, db: Session, token_tracker=None):
        self.db = db
        self.mcp_sender = MCPSender()

        # Phase 7.2: Initialize TokenTracker for usage analytics
        if token_tracker:
            self.token_tracker = token_tracker
        else:
            from analytics.token_tracker import TokenTracker
            self.token_tracker = TokenTracker(db)

        # Initialize step handlers (both new and legacy types)
        # Phase 7.2: Pass token_tracker to handlers that use LLM
        self.handlers = {
            # New step types (Phase 8.0)
            "notification": NotificationStepHandler(db, self.mcp_sender, self.token_tracker),
            "message": MessageStepHandler(db, self.mcp_sender, self.token_tracker),
            "tool": ToolStepHandler(db, self.mcp_sender, self.token_tracker),
            "conversation": ConversationStepHandler(db, self.mcp_sender, self.token_tracker),
            "slash_command": SlashCommandStepHandler(db, self.mcp_sender, self.token_tracker),
            "skill": SkillStepHandler(db, self.mcp_sender, self.token_tracker),  # Phase 16: Agentic skill execution
            "custom_skill": SkillStepHandler(db, self.mcp_sender, self.token_tracker),  # Phase 22: Custom skill alias
            "summarization": SummarizationStepHandler(db, self.mcp_sender, self.token_tracker),  # Phase 17: Agentic summarization
            "gate": GateStepHandler(db, self.mcp_sender, self.token_tracker),  # Conditional gate node
            "browser_automation": BrowserAutomationStepHandler(db, self.mcp_sender, self.token_tracker),  # Phase 14.5: Browser automation
            # Legacy types (backward compatibility)
            "Trigger": TriggerNodeHandler(db, self.mcp_sender, self.token_tracker),
            "Message": MessageStepHandler(db, self.mcp_sender, self.token_tracker),
            "Tool": ToolStepHandler(db, self.mcp_sender, self.token_tracker),
            "Conversation": ConversationStepHandler(db, self.mcp_sender, self.token_tracker),
            "SlashCommand": SlashCommandStepHandler(db, self.mcp_sender, self.token_tracker),
            "Subflow": SubflowStepHandler(db, self.mcp_sender, self, self.token_tracker),
            "Summarization": SummarizationStepHandler(db, self.mcp_sender, self.token_tracker),  # Phase 17: Legacy casing
            "Gate": GateStepHandler(db, self.mcp_sender, self.token_tracker),  # Gate: Legacy casing
            "BrowserAutomation": BrowserAutomationStepHandler(db, self.mcp_sender, self.token_tracker)  # Phase 14.5: Legacy casing
        }

        # BUG-LOG-007: Clean up any globally stale runs at engine init
        try:
            self._cleanup_stale_runs()
        except Exception as e:
            logger.warning(f"Stale run cleanup at init failed (non-fatal): {e}")

    def _cleanup_stale_runs(self, flow_definition_id: Optional[int] = None) -> int:
        """
        BUG-LOG-007: Recover flow runs stuck in "running" state.

        Runs that have been in "running" state for longer than a reasonable timeout
        are marked as "failed" with a recovery message.  This prevents stale runs
        from accumulating after process crashes or unhandled exceptions.

        Args:
            flow_definition_id: If provided, only clean up runs for this flow.
                                If None, clean up all stale runs globally.

        Returns:
            Number of stale runs recovered.
        """
        # Use 2x the default step timeout as the stale cutoff (minimum 1 hour)
        stale_cutoff = datetime.utcnow() - timedelta(seconds=max(DEFAULT_STEP_TIMEOUT * 2, 3600))

        query = self.db.query(FlowRun).filter(
            FlowRun.status == "running",
            FlowRun.started_at < stale_cutoff,
        )
        if flow_definition_id is not None:
            query = query.filter(FlowRun.flow_definition_id == flow_definition_id)

        stale_runs = query.all()
        for stale in stale_runs:
            stale.status = "failed"
            stale.error_text = "Recovered: flow was stuck in running state (process crash or timeout)"
            stale.completed_at = datetime.utcnow()

        if stale_runs:
            self.db.commit()
            logger.info(f"BUG-LOG-007: Recovered {len(stale_runs)} stale flow runs"
                        f"{f' for flow {flow_definition_id}' if flow_definition_id else ' (global)'}")

        return len(stale_runs)

    def _build_step_context(
        self,
        flow_run: FlowRun,
        completed_step_runs: List[FlowNodeRun],
        trigger_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Build comprehensive step context for template resolution.

        Phase 13.1: Step Output Injection

        Creates a context dictionary with step outputs accessible by:
        - step_N: Step by position (1-based), e.g., step_1, step_2
        - step_name: Step by name (if named), e.g., network_scan, notify_user
        - previous_step: Most recent completed step output
        - flow: Flow-level context (id, trigger_context)

        Args:
            flow_run: Current FlowRun
            completed_step_runs: List of completed FlowNodeRun records
            trigger_context: Initial trigger context/parameters

        Returns:
            Context dictionary for template resolution
        """
        context = {
            "flow": {
                "id": flow_run.id,
                "flow_definition_id": flow_run.flow_definition_id,
                "trigger_context": trigger_context or {},
                "status": flow_run.status,
                "initiator": flow_run.initiator,
            },
            "previous_step": None,
            "steps": {}
        }

        # Also merge trigger_context at root level for backward compatibility
        if trigger_context:
            context.update(trigger_context)

        for step_run in completed_step_runs:
            # Get the step definition
            step = self.db.query(FlowNode).filter(FlowNode.id == step_run.flow_node_id).first()
            if not step:
                continue

            position = step.position
            name = step.name
            step_type = step.type

            # Parse step config to get output_alias
            config = {}
            if step.config_json:
                try:
                    config = json.loads(step.config_json) if isinstance(step.config_json, str) else step.config_json
                except json.JSONDecodeError:
                    config = {}
            output_alias = config.get("output_alias")

            # Parse output JSON
            output = {}
            if step_run.output_json:
                try:
                    output = json.loads(step_run.output_json)
                except json.JSONDecodeError:
                    output = {"raw": step_run.output_json}

            # Build step data with all output fields merged
            step_data = {
                "position": position,
                "name": name,
                "type": step_type,
                "status": step_run.status,
                "error": step_run.error_text,
                "execution_time_ms": step_run.execution_time_ms,
                "retry_count": step_run.retry_count,
                **output  # Merge all output fields (raw_output, summary, tool_used, etc.)
            }

            # Add by position (1-based): step_1, step_2, etc.
            if position > 0:
                context[f"step_{position}"] = step_data
                context["steps"][position] = step_data

            # Add by name if available: network_scan, notify_user, etc.
            if name:
                # Normalize name for context key (replace spaces, etc.)
                context_key = name.replace(" ", "_").replace("-", "_").lower()
                context[context_key] = step_data
                # Also add original name if different
                if context_key != name:
                    context[name] = step_data

            # Phase 13.1: Add by output_alias if configured
            # Example: output_alias="scan_results" allows {{scan_results.status}}
            if output_alias:
                alias_key = output_alias.replace(" ", "_").replace("-", "_").lower()
                context[alias_key] = step_data
                if alias_key != output_alias:
                    context[output_alias] = step_data

            # Update previous_step to most recent
            context["previous_step"] = step_data

            # Also merge output fields at root level for backward compatibility
            context.update(output)

        return context

    def validate_flow_structure(self, flow_id: int, strict: bool = False) -> None:
        """
        Validate flow structure before execution.

        Args:
            flow_id: Flow ID to validate
            strict: If True, enforce legacy Trigger requirement (backward compat)

        Raises:
            FlowValidationError: If flow structure is invalid
        """
        steps = self.db.query(FlowNode).filter(
            FlowNode.flow_definition_id == flow_id
        ).order_by(FlowNode.position).all()

        if not steps:
            raise FlowValidationError("Flow has no steps")

        # Legacy strict mode requires Trigger as first node
        if strict:
            if steps[0].type != "Trigger" or steps[0].position != 1:
                raise FlowValidationError("First node must be a Trigger at position 1 (legacy mode)")

            trigger_count = sum(1 for s in steps if s.type == "Trigger")
            if trigger_count > 1:
                raise FlowValidationError("Flow can only have one Trigger node")

        # Check positions are valid (either sequential starting from 1, or just positive)
        positions = [s.position for s in steps]
        if len(positions) != len(set(positions)):
            raise FlowValidationError("Duplicate step positions found")

        if min(positions) < 1:
            raise FlowValidationError("Step positions must be >= 1")

        # Check for Subflow depth
        for step in steps:
            if step.type in ("Subflow", "subflow"):
                config = json.loads(step.config_json) if isinstance(step.config_json, str) else step.config_json
                target_flow_id = config.get("target_flow_definition_id", config.get("subflow_id"))
                if target_flow_id:
                    target_subflows = self.db.query(FlowNode).filter(
                        FlowNode.flow_definition_id == target_flow_id,
                        FlowNode.type.in_(["Subflow", "subflow"])
                    ).count()
                    if target_subflows > 0:
                        raise FlowValidationError("Subflow depth limited to 1")

    def generate_idempotency_key(self, flow_run_id: int, step_id: int, retry: int = 0) -> str:
        """Generate idempotency key for step run."""
        key_str = f"flow_run_{flow_run_id}_step_{step_id}_retry_{retry}"
        return hashlib.sha256(key_str.encode()).hexdigest()

    async def execute_step(
        self,
        flow_run: FlowRun,
        step: FlowNode,
        input_data: Dict[str, Any]
    ) -> FlowNodeRun:
        """
        Execute a single step with timeout, retry, and error handling.

        Args:
            flow_run: Current FlowRun
            step: FlowNode (step) to execute
            input_data: Input data from previous step

        Returns:
            FlowNodeRun with execution results
        """
        timeout = step.timeout_seconds or DEFAULT_STEP_TIMEOUT
        max_retries = step.max_retries or 0
        retry_delay = step.retry_delay_seconds or 1
        retry_count = 0

        while True:
            idempotency_key = self.generate_idempotency_key(flow_run.id, step.id, retry_count)

            # BUG-LOG-010: Use SELECT FOR UPDATE to prevent TOCTOU race
            existing = self.db.query(FlowNodeRun).filter(
                FlowNodeRun.idempotency_key == idempotency_key
            ).with_for_update(skip_locked=True).first()

            if existing and existing.status == "completed":
                logger.info(f"Step {step.id} already executed (idempotency key: {idempotency_key})")
                return existing

            # Create or update FlowNodeRun record
            step_run = FlowNodeRun(
                flow_run_id=flow_run.id,
                flow_node_id=step.id,
                status="running",
                started_at=datetime.utcnow(),
                input_json=json.dumps(input_data),
                idempotency_key=idempotency_key,
                retry_count=retry_count
            )
            try:
                self.db.add(step_run)
                self.db.commit()
                self.db.refresh(step_run)
            except IntegrityError:
                self.db.rollback()
                existing = self.db.query(FlowNodeRun).filter(
                    FlowNodeRun.idempotency_key == idempotency_key
                ).first()
                if existing:
                    logger.info(f"BUG-LOG-010: Concurrent insert detected for step {step.id}, returning existing record")
                    return existing
                raise

            try:
                # Get handler for step type (case-insensitive)
                handler = self.handlers.get(step.type) or self.handlers.get(step.type.lower())
                if not handler:
                    raise Exception(f"No handler for step type: {step.type}")

                # BUG-LOG-011: Execute with timeout AND periodic cancellation checks.
                # Instead of a simple wait_for, run the handler as a task and poll
                # for cancellation every few seconds so cancel_run can interrupt
                # a long-running step without waiting for the full timeout.
                start_time = datetime.utcnow()
                handler_task = asyncio.ensure_future(
                    handler.execute(step, input_data, flow_run, step_run)
                )
                cancel_poll_interval = 5  # seconds between cancellation checks
                elapsed = 0.0
                while not handler_task.done():
                    wait_time = min(cancel_poll_interval, timeout - elapsed)
                    if wait_time <= 0:
                        handler_task.cancel()
                        raise asyncio.TimeoutError()
                    try:
                        await asyncio.wait_for(asyncio.shield(handler_task), timeout=wait_time)
                    except asyncio.TimeoutError:
                        elapsed += wait_time
                        if handler_task.done():
                            break
                        # Check for external cancellation
                        self.db.refresh(flow_run)
                        if flow_run.status in ("cancelled", "failed"):
                            logger.info(f"BUG-LOG-011: Step {step.id} interrupted — flow run {flow_run.id} was {flow_run.status}")
                            handler_task.cancel()
                            try:
                                await handler_task
                            except (asyncio.CancelledError, Exception):
                                pass
                            step_run.status = "cancelled"
                            step_run.completed_at = datetime.utcnow()
                            step_run.error_text = f"Step cancelled: flow run was {flow_run.status}"
                            step_run.execution_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                            self.db.commit()
                            return step_run

                # Retrieve the result (may re-raise exceptions from the handler)
                output = handler_task.result()
                end_time = datetime.utcnow()

                # Update step_run with results
                step_run.completed_at = end_time
                step_run.output_json = json.dumps(output)
                step_run.execution_time_ms = int((end_time - start_time).total_seconds() * 1000)
                step_run.tool_used = output.get("tool_used")

                # Check if the handler reported internal failure via output status
                if isinstance(output, dict) and output.get("status") == "failed":
                    step_run.status = "failed"
                    step_run.error_text = output.get("error", "Step handler reported failure")
                    logger.warning(f"Step {step.id} ({step.type}) reported failure: {step_run.error_text}")
                else:
                    step_run.status = "completed"
                    logger.info(f"Step {step.id} ({step.type}) completed in {step_run.execution_time_ms}ms")

                if "token_usage" in output:
                    step_run.token_usage_json = json.dumps(output["token_usage"])

                self.db.commit()
                self.db.refresh(step_run)

                return step_run

            except asyncio.TimeoutError:
                step_run.status = "failed"
                step_run.completed_at = datetime.utcnow()
                step_run.error_text = f"Step execution timed out after {timeout}s"
                self.db.commit()

                if step.retry_on_failure and retry_count < max_retries:
                    retry_count += 1
                    logger.warning(f"Step {step.id} timed out, retrying ({retry_count}/{max_retries})")
                    await asyncio.sleep(retry_delay * (2 ** (retry_count - 1)))  # Exponential backoff
                    continue

                logger.error(f"Step {step.id} timed out")
                return step_run

            except Exception as e:
                step_run.status = "failed"
                step_run.completed_at = datetime.utcnow()
                step_run.error_text = str(e)
                self.db.commit()

                if step.retry_on_failure and retry_count < max_retries:
                    retry_count += 1
                    logger.warning(f"Step {step.id} failed: {e}, retrying ({retry_count}/{max_retries})")
                    await asyncio.sleep(retry_delay * (2 ** (retry_count - 1)))
                    continue

                logger.error(f"Step {step.id} failed: {e}")
                return step_run

    def generate_final_report(self, flow_run: FlowRun) -> Dict[str, Any]:
        """Generate final report aggregating all step runs."""
        step_runs = self.db.query(FlowNodeRun).filter(
            FlowNodeRun.flow_run_id == flow_run.id
        ).all()

        report = {
            "flow_run_id": flow_run.id,
            "flow_definition_id": flow_run.flow_definition_id,
            "status": flow_run.status,
            "started_at": flow_run.started_at.isoformat() if flow_run.started_at else None,
            "completed_at": flow_run.completed_at.isoformat() if flow_run.completed_at else None,
            "duration_ms": int((flow_run.completed_at - flow_run.started_at).total_seconds() * 1000) if flow_run.completed_at and flow_run.started_at else None,
            "steps_executed": len(step_runs),
            "steps_successful": sum(1 for sr in step_runs if sr.status == "completed"),
            "steps_failed": sum(1 for sr in step_runs if sr.status == "failed"),
            "total_execution_time_ms": sum(sr.execution_time_ms or 0 for sr in step_runs),
            "total_tokens": self._aggregate_tokens(step_runs),
            "tools_used": [sr.tool_used for sr in step_runs if sr.tool_used],
            "step_results": []
        }

        for step_run in step_runs:
            step = self.db.query(FlowNode).filter(FlowNode.id == step_run.flow_node_id).first()
            report["step_results"].append({
                "step_id": step_run.flow_node_id,
                "step_name": step.name if step else None,
                "step_type": step.type if step else "unknown",
                "position": step.position if step else 0,
                "status": step_run.status,
                "retry_count": step_run.retry_count,
                "execution_time_ms": step_run.execution_time_ms,
                "output_summary": self._summarize_output(step_run.output_json),
                "error": step_run.error_text
            })

        return report

    def _aggregate_tokens(self, step_runs: List[FlowNodeRun]) -> Dict[str, Any]:
        """
        Aggregate token usage and costs across all steps.

        Phase 7.2: Added estimated_cost aggregation for billing visibility.
        """
        total = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated_cost": 0.0  # Phase 7.2: Aggregate cost in USD
        }

        for step_run in step_runs:
            if step_run.token_usage_json:
                try:
                    usage = json.loads(step_run.token_usage_json)
                    total["prompt_tokens"] += usage.get("prompt_tokens", usage.get("prompt", 0))
                    total["completion_tokens"] += usage.get("completion_tokens", usage.get("completion", 0))
                    total["total_tokens"] += usage.get("total_tokens", usage.get("total", 0))
                    total["estimated_cost"] += usage.get("estimated_cost", 0.0)
                except:
                    pass

        return total

    def _summarize_output(self, output_json: Optional[str]) -> Optional[str]:
        """Create a brief summary of step output."""
        if not output_json:
            return None

        try:
            output = json.loads(output_json)
            if "summary" in output:
                return output["summary"]
            elif "message" in output:
                return output["message"]
            elif "status" in output:
                return f"Status: {output['status']}"
            else:
                return "Output available"
        except:
            return None

    async def run_flow(
        self,
        flow_definition_id: int,
        trigger_context: Optional[Dict[str, Any]] = None,
        initiator: str = "api",
        trigger_type: str = "immediate",
        triggered_by: Optional[str] = None,
        parent_run_id: Optional[int] = None,
        tenant_id: Optional[str] = None
    ) -> FlowRun:
        """
        Main execution entry point.

        Args:
            flow_definition_id: ID of FlowDefinition to execute
            trigger_context: Initial trigger data / input variables
            initiator: Who/what started this run ('api', 'agent', 'system', 'subflow', 'scheduler')
            trigger_type: Execution method ('immediate', 'scheduled', 'recurring', 'manual')
            triggered_by: User/system identifier
            parent_run_id: If this is a subflow, ID of parent FlowRun

        Returns:
            Completed FlowRun
        """
        logger.info(f"Starting flow run for definition {flow_definition_id}")

        # Load flow definition (with tenant filter when provided — BUG-LOG-002)
        query = self.db.query(FlowDefinition).filter(FlowDefinition.id == flow_definition_id)
        if tenant_id:
            query = query.filter(FlowDefinition.tenant_id == tenant_id)
        flow = query.first()
        if not flow:
            raise FlowValidationError(f"Flow definition {flow_definition_id} not found")

        # BUG-LOG-007: Clean up stale flow runs stuck in "running"
        # Scoped to this flow's definition to avoid cross-tenant collateral (2D-2)
        self._cleanup_stale_runs(flow_definition_id=flow_definition_id)

        # Get tenant from flow
        tenant_id = flow.tenant_id

        # Validate flow structure (non-strict mode for new flows)
        try:
            self.validate_flow_structure(flow_definition_id, strict=False)
        except FlowValidationError as e:
            logger.error(f"Flow validation failed: {e}")
            flow_run = FlowRun(
                flow_definition_id=flow_definition_id,
                tenant_id=tenant_id,
                status="failed",
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                initiator=initiator,
                trigger_type=trigger_type,
                triggered_by=triggered_by,
                total_steps=0,
                completed_steps=0,
                failed_steps=0,
                trigger_context_json=json.dumps(trigger_context) if trigger_context else None,
                error_text=f"Validation failed: {str(e)}"
            )
            self.db.add(flow_run)
            self.db.commit()
            return flow_run

        # Load steps
        steps = self.db.query(FlowNode).filter(
            FlowNode.flow_definition_id == flow_definition_id
        ).order_by(FlowNode.position).all()

        # Create FlowRun
        flow_run = FlowRun(
            flow_definition_id=flow_definition_id,
            tenant_id=tenant_id,
            status="running",
            started_at=datetime.utcnow(),
            initiator=initiator,
            trigger_type=trigger_type,
            triggered_by=triggered_by,
            total_steps=len(steps),
            completed_steps=0,
            failed_steps=0,
            trigger_context_json=json.dumps(trigger_context) if trigger_context else None
        )
        self.db.add(flow_run)
        self.db.commit()
        self.db.refresh(flow_run)

        try:
            # Execute steps sequentially
            # Phase 13.1: Track completed step runs for context building
            completed_step_runs: List[FlowNodeRun] = []

            for step in steps:
                # BUG-LOG-011: Check for cancellation between steps
                self.db.refresh(flow_run)
                if flow_run.status in ("cancelled", "failed"):
                    logger.info(f"Flow run {flow_run.id} was {flow_run.status} externally, stopping execution")
                    break

                logger.info(f"Executing step {step.position}: {step.type} ({step.name or 'unnamed'})")

                # Phase 13.1: Build comprehensive step context with all previous step outputs
                # This enables templates like {{step_1.raw_output}} or {{network_scan.result}}
                step_context = self._build_step_context(
                    flow_run=flow_run,
                    completed_step_runs=completed_step_runs,
                    trigger_context=trigger_context
                )

                logger.debug(f"Step context keys: {list(step_context.keys())}")

                step_run = await self.execute_step(flow_run, step, step_context)

                # Track completed step run for context building
                completed_step_runs.append(step_run)

                # BUG-LOG-011: Handle cancelled steps (from in-flight cancellation)
                if step_run.status == "cancelled":
                    logger.info(f"Step {step.position} was cancelled, stopping flow")
                    # flow_run.status was already set to "cancelled" by the API
                    break
                elif step_run.status == "failed":
                    # Check on_failure action
                    if step.on_failure == "continue":
                        logger.warning(f"Step {step.position} failed but continuing (on_failure=continue)")
                        flow_run.failed_steps += 1
                    elif step.on_failure == "skip":
                        logger.warning(f"Step {step.position} failed, skipping remaining steps")
                        break
                    else:
                        # Default: stop execution on failure
                        logger.error(f"Step {step.position} failed, stopping flow")
                        flow_run.status = "failed"
                        flow_run.failed_steps += 1
                        flow_run.error_text = f"Step {step.position} ({step.type}) failed: {step_run.error_text}"
                        break
                else:
                    flow_run.completed_steps += 1

            # Mark as completed if not already failed/cancelled
            if flow_run.status not in ("failed", "cancelled"):
                if flow_run.failed_steps > 0:
                    flow_run.status = "completed_with_errors"
                else:
                    flow_run.status = "completed"

            flow_run.completed_at = datetime.utcnow()

            # Update flow definition execution tracking
            flow.last_executed_at = datetime.utcnow()
            flow.execution_count = (flow.execution_count or 0) + 1

            # Generate final report
            final_report = self.generate_final_report(flow_run)
            flow_run.final_report_json = json.dumps(final_report)

            self.db.commit()
            self.db.refresh(flow_run)

            logger.info(f"Flow run {flow_run.id} completed with status: {flow_run.status}")
            return flow_run

        except Exception as e:
            logger.error(f"Flow execution failed: {e}")
            flow_run.status = "failed"
            flow_run.completed_at = datetime.utcnow()
            flow_run.error_text = str(e)
            self.db.commit()
            self.db.refresh(flow_run)
            return flow_run


# Backward compatibility aliases
FlowNodeHandler = FlowStepHandler
