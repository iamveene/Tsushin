"""
Flow Command Service

Service for executing flow-related slash commands.
Used by slash command handlers and the AutomationSkill.

Provides:
- List flows for a tenant
- Execute flows by ID or name
- Query flow execution status
"""

import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from models import FlowDefinition, FlowRun

logger = logging.getLogger(__name__)


class FlowCommandService:
    """
    Service for flow command execution.

    Handles flow listing and execution operations for slash commands
    and the AutomationSkill.
    """

    def __init__(self, db: Session):
        """
        Initialize the flow command service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self.logger = logging.getLogger(__name__)

    async def execute_list(
        self,
        tenant_id: str,
        agent_id: int
    ) -> Dict[str, Any]:
        """
        List all flows for the tenant.

        Returns formatted list with:
        - Flow ID
        - Flow name
        - Flow type (workflow/notification/conversation/task)
        - Description
        - Status (active/inactive)
        - Execution method (immediate/scheduled/recurring)

        Args:
            tenant_id: Tenant ID for filtering flows
            agent_id: Agent ID (for future per-agent filtering)

        Returns:
            Dict with status, message, and data:
            {
                "status": "success",
                "message": "Formatted flow list",
                "data": {
                    "flows": [
                        {
                            "id": 1,
                            "name": "Weekly Report",
                            "type": "workflow",
                            "description": "...",
                            "is_active": True,
                            "execution_method": "scheduled"
                        }
                    ]
                }
            }
        """
        try:
            # Query flows for tenant
            flows = self.db.query(FlowDefinition).filter(
                FlowDefinition.tenant_id == tenant_id
            ).order_by(FlowDefinition.created_at.desc()).all()

            if not flows:
                return {
                    "status": "success",
                    "message": "📋 No flows found. Create your first automation workflow!",
                    "data": {"flows": [], "count": 0}
                }

            # Format flow data
            flow_list = []
            for flow in flows:
                flow_list.append({
                    "id": flow.id,
                    "name": flow.name,
                    "type": flow.flow_type,
                    "description": flow.description or "No description",
                    "is_active": flow.is_active,
                    "execution_method": flow.execution_method or "immediate",
                    "execution_count": flow.execution_count or 0
                })

            # Create readable message
            message_lines = [f"📋 **Available Flows** ({len(flow_list)} total)\n"]

            # Group by type for better organization
            by_type = {}
            for f in flow_list:
                flow_type = f['type']
                if flow_type not in by_type:
                    by_type[flow_type] = []
                by_type[flow_type].append(f)

            # Format by type
            type_emojis = {
                'workflow': '⚙️',
                'notification': '🔔',
                'conversation': '💬',
                'task': '✅'
            }

            for flow_type, flows_of_type in by_type.items():
                emoji = type_emojis.get(flow_type, '📄')
                message_lines.append(f"\n**{emoji} {flow_type.title()} Flows**")

                for f in flows_of_type:
                    status = "✅" if f["is_active"] else "⏸️"
                    exec_info = ""
                    if f["execution_method"] == "scheduled":
                        exec_info = " 📅 Scheduled"
                    elif f["execution_method"] == "recurring":
                        exec_info = " 🔄 Recurring"

                    message_lines.append(
                        f"{status} **{f['name']}** (ID: {f['id']}){exec_info}\n"
                        f"   {f['description']}"
                    )
                    if f["execution_count"] > 0:
                        message_lines.append(f"   ▸ Executed {f['execution_count']} times")
                    message_lines.append("")  # Empty line for spacing

            # Add usage tip
            message_lines.append("\n💡 **Tip:** Use `/flows run <id>` to execute a flow")

            return {
                "status": "success",
                "message": "\n".join(message_lines),
                "data": {
                    "flows": flow_list,
                    "count": len(flow_list),
                    "by_type": by_type
                }
            }

        except Exception as e:
            self.logger.error(f"Error listing flows: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"❌ Error listing flows: {str(e)}",
                "data": {"flows": [], "count": 0}
            }

    async def execute_run(
        self,
        tenant_id: str,
        agent_id: int,
        flow_identifier: str,
        sender_key: str
    ) -> Dict[str, Any]:
        """
        Execute a flow by name or ID.

        Flow identifier can be:
        - Integer ID: "5", "123"
        - Flow name (exact match): "Weekly Report"
        - Flow name (partial match): "report", "weekly"

        Args:
            tenant_id: Tenant ID for security filtering
            agent_id: Agent ID initiating the flow
            flow_identifier: Flow ID or name
            sender_key: User/sender identifier

        Returns:
            Dict with execution status:
            {
                "status": "success",
                "action": "flow_started",
                "message": "Flow execution started...",
                "data": {
                    "flow_id": 1,
                    "flow_name": "...",
                    "run_id": 123,
                    "status": "running"
                }
            }
        """
        try:
            # Find flow by ID or name
            flow = self._find_flow(tenant_id, flow_identifier)

            if not flow:
                # Provide helpful error with suggestions
                suggestions = self._suggest_flows(tenant_id, flow_identifier)
                suggestion_text = ""
                if suggestions:
                    suggestion_text = "\n\n**Did you mean?**\n"
                    for s in suggestions[:3]:
                        suggestion_text += f"- {s['name']} (ID: {s['id']})\n"

                return {
                    "status": "error",
                    "message": f"❌ Flow not found: '{flow_identifier}'{suggestion_text}",
                    "data": {}
                }

            # Check if flow is active
            if not flow.is_active:
                return {
                    "status": "error",
                    "message": (
                        f"❌ Flow '{flow.name}' is inactive.\n"
                        f"Activate it in the UI before running."
                    ),
                    "data": {
                        "flow_id": flow.id,
                        "flow_name": flow.name,
                        "is_active": False
                    }
                }

            # Execute flow using FlowEngine
            from flows.flow_engine import FlowEngine
            engine = FlowEngine(self.db)

            self.logger.info(
                f"Executing flow {flow.id} ('{flow.name}') "
                f"for tenant {tenant_id}, agent {agent_id}, sender {sender_key}"
            )

            flow_run = await engine.run_flow(
                flow_definition_id=flow.id,
                trigger_context={
                    "triggered_by_command": True,
                    "sender_key": sender_key,
                    "agent_id": agent_id,
                    "trigger_source": "slash_command"
                },
                initiator="command",
                trigger_type="immediate",
                triggered_by=sender_key
            )

            self.logger.info(
                f"Flow execution started: run_id={flow_run.id}, status={flow_run.status}"
            )

            # Format success message
            status_emoji = {
                "running": "🚀",
                "completed": "✅",
                "failed": "❌",
                "pending": "⏳"
            }.get(flow_run.status, "▶️")

            message = (
                f"{status_emoji} **Flow Execution Started**\n\n"
                f"**Flow:** {flow.name}\n"
                f"**Type:** {flow.flow_type}\n"
                f"**Run ID:** {flow_run.id}\n"
                f"**Status:** {flow_run.status}\n"
                f"**Steps:** {flow_run.total_steps} total"
            )

            if flow_run.status == "completed":
                message += f"\n\n✅ Flow completed successfully!"
            elif flow_run.status == "failed":
                message += f"\n\n❌ Flow execution failed"
                if flow_run.error_text:
                    message += f": {flow_run.error_text}"

            return {
                "status": "success",
                "action": "flow_started",
                "message": message,
                "data": {
                    "flow_id": flow.id,
                    "flow_name": flow.name,
                    "flow_type": flow.flow_type,
                    "run_id": flow_run.id,
                    "run_status": flow_run.status,
                    "total_steps": flow_run.total_steps,
                    "completed_steps": flow_run.completed_steps
                }
            }

        except Exception as e:
            self.logger.error(f"Flow execution failed: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"❌ Flow execution failed: {str(e)}",
                "data": {"error": str(e)}
            }

    def _find_flow(self, tenant_id: str, identifier: str) -> Optional[FlowDefinition]:
        """
        Find a flow by ID or name.

        Args:
            tenant_id: Tenant ID for filtering
            identifier: Flow ID (int) or name (string)

        Returns:
            FlowDefinition or None
        """
        # Try to parse as integer ID
        try:
            flow_id = int(identifier)
            flow = self.db.query(FlowDefinition).filter(
                FlowDefinition.id == flow_id,
                FlowDefinition.tenant_id == tenant_id
            ).first()
            if flow:
                return flow
        except ValueError:
            pass  # Not an integer, try by name

        # Try exact name match (case-insensitive)
        flow = self.db.query(FlowDefinition).filter(
            FlowDefinition.name.ilike(identifier),
            FlowDefinition.tenant_id == tenant_id
        ).first()
        if flow:
            return flow

        # Try partial name match (case-insensitive)
        flow = self.db.query(FlowDefinition).filter(
            FlowDefinition.name.ilike(f"%{identifier}%"),
            FlowDefinition.tenant_id == tenant_id
        ).first()
        if flow:
            return flow

        return None

    def _suggest_flows(self, tenant_id: str, identifier: str, limit: int = 3) -> list:
        """
        Suggest similar flows when exact match not found.

        Uses simple text similarity for suggestions.

        Args:
            tenant_id: Tenant ID
            identifier: Search string
            limit: Max suggestions to return

        Returns:
            List of flow dicts with id and name
        """
        try:
            # Get all active flows for tenant
            flows = self.db.query(FlowDefinition).filter(
                FlowDefinition.tenant_id == tenant_id,
                FlowDefinition.is_active == True
            ).limit(limit * 2).all()  # Get more than needed for filtering

            if not flows:
                return []

            # Simple relevance scoring
            identifier_lower = identifier.lower()
            scored_flows = []

            for flow in flows:
                name_lower = flow.name.lower()
                desc_lower = (flow.description or "").lower()

                score = 0
                # Exact word match in name
                if identifier_lower in name_lower:
                    score += 10
                # Word in description
                if identifier_lower in desc_lower:
                    score += 3
                # Partial word match
                for word in identifier_lower.split():
                    if word in name_lower:
                        score += 5
                    if word in desc_lower:
                        score += 1

                if score > 0:
                    scored_flows.append({
                        "id": flow.id,
                        "name": flow.name,
                        "score": score
                    })

            # Sort by score and return top matches
            scored_flows.sort(key=lambda x: x['score'], reverse=True)
            return scored_flows[:limit]

        except Exception as e:
            self.logger.error(f"Error suggesting flows: {e}", exc_info=True)
            return []

    async def execute_status(
        self,
        tenant_id: str,
        agent_id: int,
        run_id: int
    ) -> Dict[str, Any]:
        """
        Get flow execution status.

        Future enhancement for checking flow run progress.

        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            run_id: Flow run ID

        Returns:
            Dict with run status information
        """
        try:
            # Query flow run
            flow_run = self.db.query(FlowRun).filter(
                FlowRun.id == run_id,
                FlowRun.tenant_id == tenant_id
            ).first()

            if not flow_run:
                return {
                    "status": "error",
                    "message": f"❌ Flow run not found: {run_id}",
                    "data": {}
                }

            # Get flow definition
            flow = self.db.query(FlowDefinition).filter(
                FlowDefinition.id == flow_run.flow_definition_id
            ).first()

            # Format status message
            status_emoji = {
                "running": "⏳",
                "completed": "✅",
                "failed": "❌",
                "pending": "⏸️",
                "cancelled": "🚫"
            }.get(flow_run.status, "❓")

            message = (
                f"{status_emoji} **Flow Run Status**\n\n"
                f"**Run ID:** {flow_run.id}\n"
                f"**Flow:** {flow.name if flow else 'Unknown'}\n"
                f"**Status:** {flow_run.status}\n"
                f"**Progress:** {flow_run.completed_steps}/{flow_run.total_steps} steps\n"
            )

            if flow_run.started_at:
                message += f"**Started:** {flow_run.started_at.strftime('%Y-%m-%d %H:%M:%S')}\n"

            if flow_run.completed_at:
                message += f"**Completed:** {flow_run.completed_at.strftime('%Y-%m-%d %H:%M:%S')}\n"

                # Calculate duration
                if flow_run.started_at:
                    duration = flow_run.completed_at - flow_run.started_at
                    message += f"**Duration:** {duration.total_seconds():.1f}s\n"

            if flow_run.error_text:
                message += f"\n**Error:** {flow_run.error_text}"

            return {
                "status": "success",
                "message": message,
                "data": {
                    "run_id": flow_run.id,
                    "flow_id": flow_run.flow_definition_id,
                    "flow_name": flow.name if flow else None,
                    "run_status": flow_run.status,
                    "total_steps": flow_run.total_steps,
                    "completed_steps": flow_run.completed_steps,
                    "failed_steps": flow_run.failed_steps,
                    "started_at": flow_run.started_at.isoformat() if flow_run.started_at else None,
                    "completed_at": flow_run.completed_at.isoformat() if flow_run.completed_at else None
                }
            }

        except Exception as e:
            self.logger.error(f"Error getting flow status: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"❌ Error getting status: {str(e)}",
                "data": {}
            }
