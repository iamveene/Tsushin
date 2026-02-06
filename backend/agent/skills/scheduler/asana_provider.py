"""
Asana Provider

Scheduler provider implementation for Asana Tasks.
Converts between the unified SchedulerEvent model and Asana task format.

Uses Asana tasks with due dates as "events" for scheduling purposes.
Good for task-based scheduling workflows.

Features:
- Create tasks with due dates
- List tasks within a date range
- Update task details and due dates
- Complete/close tasks
- Project and section assignment
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import logging
import os
import json

from sqlalchemy.orm import Session

from .base import (
    SchedulerProviderBase,
    SchedulerEvent,
    SchedulerProviderType,
    SchedulerEventStatus,
    SchedulerProviderError,
    ProviderAuthenticationError,
    ProviderAPIError,
)

logger = logging.getLogger(__name__)


class AsanaProvider(SchedulerProviderBase):
    """
    Asana task-based scheduler provider.

    Uses Asana tasks with due dates as scheduled "events".
    Great for task-oriented workflows where scheduling means
    assigning deadlines to work items.

    Features:
        - Task creation with due dates
        - Task listing and filtering
        - Task completion status
        - Project/section organization

    Limitations (compared to Calendar):
        - No event end times (tasks have single due date)
        - No attendee/guest support
        - No location field
        - Limited recurrence support

    Example:
        provider = AsanaProvider(
            db=db_session,
            tenant_id="tenant_123",
            integration_id=3  # AsanaIntegration ID
        )

        # Create a task
        event = await provider.create_event(
            title="Review PR #42",
            start=datetime(2025, 1, 15, 17, 0),  # Due date/time
            description="Review and approve pull request"
        )
    """

    provider_type = SchedulerProviderType.ASANA
    provider_name = "Asana Tasks"
    provider_description = "Asana tasks with due dates"

    # Feature flags - Asana has limited event-like features
    supports_end_time = False  # Tasks have due date, not duration
    supports_location = False
    supports_attendees = False  # Asana has assignees, not attendees
    supports_recurrence = False  # Limited recurrence support
    supports_reminders = False  # Handled by Asana itself
    supports_availability = False

    def __init__(
        self,
        db: Session,
        tenant_id: Optional[str] = None,
        integration_id: Optional[int] = None,
        **kwargs
    ):
        """
        Initialize Asana provider.

        Args:
            db: Database session
            tenant_id: Tenant ID for multi-tenant isolation
            integration_id: AsanaIntegration ID (required)
        """
        super().__init__(db, tenant_id)

        if not integration_id:
            raise ValueError("AsanaProvider requires integration_id")

        self.integration_id = integration_id
        self._service = None

    def _get_service(self):
        """Lazy-load AsanaService."""
        if self._service is None:
            from hub.asana.asana_service import AsanaService
            from models import AsanaIntegration
            import os

            # Get integration details
            integration = self.db.query(AsanaIntegration).filter(
                AsanaIntegration.id == self.integration_id
            ).first()

            if not integration:
                raise ValueError(f"Asana integration {self.integration_id} not found")

            # Get OAuth config
            from services.encryption_key_service import get_asana_encryption_key
            encryption_key = get_asana_encryption_key(db)
            redirect_uri = os.getenv("ASANA_REDIRECT_URI", "http://localhost:8081/api/hub/asana/oauth/callback")

            self._service = AsanaService(
                db=self.db,
                integration_id=self.integration_id,
                encryption_key=encryption_key,
                redirect_uri=redirect_uri
            )

        return self._service

    def _asana_task_to_scheduler_event(self, task: Dict) -> SchedulerEvent:
        """
        Convert Asana task to SchedulerEvent.

        Args:
            task: Task dict from Asana API

        Returns:
            SchedulerEvent with mapped fields
        """
        # Parse due date
        due_on = task.get("due_on")  # Date only: "2025-01-15"
        due_at = task.get("due_at")  # DateTime: "2025-01-15T17:00:00.000Z"

        if due_at:
            # Parse datetime
            if due_at.endswith("Z"):
                due_at = due_at[:-1]
            start = datetime.fromisoformat(due_at.replace(".000", ""))
        elif due_on:
            # Parse date only (midnight)
            start = datetime.strptime(due_on, "%Y-%m-%d")
        else:
            start = datetime.utcnow()

        # Map completion status
        completed = task.get("completed", False)
        if completed:
            status = SchedulerEventStatus.COMPLETED
        else:
            status = SchedulerEventStatus.SCHEDULED

        # Get assignee info
        assignee = task.get("assignee")
        assignee_name = assignee.get("name") if assignee else None

        # Get project info
        projects = task.get("projects", [])
        project_names = [p.get("name") for p in projects if p.get("name")]

        return SchedulerEvent(
            id=f"asana_{task['gid']}",
            provider=self.provider_type.value,
            title=task.get("name", "Untitled Task"),
            start=start,
            end=None,  # Asana tasks don't have end times
            description=task.get("notes"),
            status=status,
            raw_data=task,
            metadata={
                "gid": task.get("gid"),
                "assignee": assignee_name,
                "projects": project_names,
                "permalink_url": task.get("permalink_url"),
                "completed_at": task.get("completed_at"),
            }
        )

    async def create_event(
        self,
        title: str,
        start: datetime,
        end: Optional[datetime] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        reminder_minutes: Optional[int] = None,
        recurrence: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        project_gid: Optional[str] = None,
        assignee_gid: Optional[str] = None,
        **kwargs
    ) -> SchedulerEvent:
        """
        Create an Asana task as a scheduled event.

        Args:
            title: Task name
            start: Due date/time
            end: Ignored (Asana doesn't support end times)
            description: Task notes
            location: Ignored
            reminder_minutes: Ignored (Asana has own reminders)
            recurrence: Ignored
            attendees: Ignored (use assignee_gid instead)
            project_gid: Optional Asana project to add task to
            assignee_gid: Optional Asana user GID to assign to

        Returns:
            SchedulerEvent representing the created task
        """
        self._log_info(f"Creating Asana task: {title}")

        try:
            service = self._get_service()

            # Build create task arguments
            # Use the MCP tool directly for task creation
            tool_args = {
                "name": title,
            }

            # Format due date
            if start:
                # Asana accepts ISO format with timezone
                tool_args["due_at"] = start.isoformat() + "Z"

            if description:
                tool_args["notes"] = description

            if project_gid:
                tool_args["project"] = project_gid
            elif hasattr(service.integration, 'default_project_gid') and service.integration.default_project_gid:
                tool_args["project"] = service.integration.default_project_gid

            if assignee_gid:
                tool_args["assignee"] = assignee_gid
            elif hasattr(service.integration, 'default_assignee_gid') and service.integration.default_assignee_gid:
                tool_args["assignee"] = service.integration.default_assignee_gid

            # Execute task creation via MCP
            result = await service.execute_tool("asana_create_task", tool_args)

            # Parse result
            if isinstance(result, str):
                result = json.loads(result)

            task_data = result.get("data", result)

            event = self._asana_task_to_scheduler_event(task_data)
            self._log_info(f"Created task: {event.id}")

            return event

        except Exception as e:
            self._log_error(f"Failed to create task: {e}", exc_info=True)
            raise ProviderAPIError(
                self.provider_type.value,
                f"Failed to create Asana task: {e}"
            )

    async def list_events(
        self,
        start: datetime,
        end: datetime,
        query: Optional[str] = None,
        max_results: int = 50,
        project_gid: Optional[str] = None,
        assignee_gid: Optional[str] = None,
        **kwargs
    ) -> List[SchedulerEvent]:
        """
        List Asana tasks within a date range.

        Args:
            start: Start of date range (filter by due_on >= start)
            end: End of date range (filter by due_on <= end)
            query: Optional search text
            max_results: Maximum tasks to return
            project_gid: Filter by project
            assignee_gid: Filter by assignee

        Returns:
            List of SchedulerEvent objects
        """
        self._log_info(f"Listing tasks from {start} to {end}")

        try:
            service = self._get_service()

            # Build search arguments
            tool_args = {
                "workspace": service.integration.workspace_gid,
            }

            # Date range filter
            tool_args["due_on.after"] = start.strftime("%Y-%m-%d")
            tool_args["due_on.before"] = end.strftime("%Y-%m-%d")

            if project_gid:
                tool_args["project"] = project_gid

            if assignee_gid:
                tool_args["assignee"] = assignee_gid
            elif hasattr(service.integration, 'default_assignee_gid') and service.integration.default_assignee_gid:
                # Default to integration's assignee if set
                tool_args["assignee"] = service.integration.default_assignee_gid

            # Limit results
            tool_args["limit"] = min(max_results, 100)

            # Search tasks
            result = await service.execute_tool("asana_search_tasks", tool_args)

            # Parse result
            if isinstance(result, str):
                result = json.loads(result)

            tasks = result.get("data", [])

            # Convert to SchedulerEvents
            events = [
                self._asana_task_to_scheduler_event(task)
                for task in tasks
            ]

            # Filter by query if provided
            if query:
                query_lower = query.lower()
                events = [
                    e for e in events
                    if query_lower in e.title.lower() or
                    (e.description and query_lower in e.description.lower())
                ]

            self._log_info(f"Found {len(events)} tasks")
            return events[:max_results]

        except Exception as e:
            self._log_error(f"Failed to list tasks: {e}", exc_info=True)
            raise ProviderAPIError(
                self.provider_type.value,
                f"Failed to list Asana tasks: {e}"
            )

    async def get_event(self, event_id: str) -> Optional[SchedulerEvent]:
        """
        Get a specific task by ID.

        Args:
            event_id: Event ID (format: "asana_xxx" or just task GID)

        Returns:
            SchedulerEvent if found, None otherwise
        """
        # Extract Asana task GID
        if event_id.startswith("asana_"):
            task_gid = event_id[6:]
        else:
            task_gid = event_id

        try:
            service = self._get_service()

            result = await service.execute_tool("asana_get_task", {"task_id": task_gid})

            # Parse result
            if isinstance(result, str):
                result = json.loads(result)

            task_data = result.get("data", result)

            if task_data and task_data.get("gid"):
                return self._asana_task_to_scheduler_event(task_data)
            return None

        except Exception as e:
            self._log_error(f"Failed to get task {event_id}: {e}", exc_info=True)
            return None

    async def update_event(
        self,
        event_id: str,
        title: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        status: Optional[SchedulerEventStatus] = None,
        **kwargs
    ) -> SchedulerEvent:
        """
        Update an Asana task.

        Args:
            event_id: Task ID to update
            title: New task name
            start: New due date
            end: Ignored
            description: New notes
            location: Ignored
            status: If COMPLETED, mark task complete

        Returns:
            Updated SchedulerEvent
        """
        # Extract Asana task GID
        if event_id.startswith("asana_"):
            task_gid = event_id[6:]
        else:
            task_gid = event_id

        self._log_info(f"Updating task {task_gid}")

        try:
            service = self._get_service()

            # Build update arguments
            tool_args = {"task_id": task_gid}

            if title is not None:
                tool_args["name"] = title

            if start is not None:
                tool_args["due_at"] = start.isoformat() + "Z"

            if description is not None:
                tool_args["notes"] = description

            if status == SchedulerEventStatus.COMPLETED:
                tool_args["completed"] = True
            elif status == SchedulerEventStatus.SCHEDULED:
                tool_args["completed"] = False

            # Execute update
            result = await service.execute_tool("asana_update_task", tool_args)

            # Parse result
            if isinstance(result, str):
                result = json.loads(result)

            task_data = result.get("data", result)

            return self._asana_task_to_scheduler_event(task_data)

        except Exception as e:
            self._log_error(f"Failed to update task: {e}", exc_info=True)
            raise ProviderAPIError(
                self.provider_type.value,
                f"Failed to update Asana task: {e}"
            )

    async def delete_event(self, event_id: str) -> bool:
        """
        Delete an Asana task.

        Note: Asana doesn't support task deletion via API.
        This marks the task as completed instead.

        Args:
            event_id: Task ID to delete/complete

        Returns:
            True if marked complete successfully
        """
        # Extract Asana task GID
        if event_id.startswith("asana_"):
            task_gid = event_id[6:]
        else:
            task_gid = event_id

        self._log_info(f"Completing task {task_gid} (Asana doesn't support deletion)")

        try:
            service = self._get_service()

            # Mark as completed instead of deleting
            await service.execute_tool(
                "asana_update_task",
                {"task_id": task_gid, "completed": True}
            )

            return True

        except Exception as e:
            self._log_error(f"Failed to complete task: {e}", exc_info=True)
            return False

    async def check_health(self) -> Dict[str, Any]:
        """
        Check Asana provider health.

        Returns:
            Health status dict
        """
        try:
            service = self._get_service()
            health = await service.check_health()

            return {
                "status": health["status"],
                "provider": self.provider_type.value,
                "provider_name": self.provider_name,
                "last_check": health["last_check"],
                "details": health.get("details", {}),
                "errors": health.get("errors", [])
            }
        except Exception as e:
            return {
                "status": "unavailable",
                "provider": self.provider_type.value,
                "provider_name": self.provider_name,
                "last_check": datetime.utcnow().isoformat() + "Z",
                "errors": [str(e)]
            }
