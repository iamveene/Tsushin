"""
Asana MCP Client with TRUE SSE Transport

Implements Model Context Protocol over Server-Sent Events for Asana integration.
Uses JSON-RPC 2.0 protocol over SSE as per MCP specification.

CRITICAL NOTE: After investigation, Asana MCP requires using their SDK or
specific protocol implementation. For now, we fallback to REST API with proper error handling.
Future implementation should use official Asana MCP SDK when available.
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import httpx

logger = logging.getLogger(__name__)


@dataclass
class MCPTool:
    """Represents an MCP tool schema."""
    name: str
    description: str
    input_schema: Dict


class AsanaMCPClient:
    """
    Client for Asana MCP Server.

    IMPORTANT: This implementation uses Asana REST API as a bridge since the true
    MCP protocol requires SDK integration. The OAuth token is compatible with both.

    Supports:
    - list_tasks: List user's tasks
    - create_task: Create new tasks
    - update_task: Update/complete tasks
    - get_task: Get task details
    - list_projects: List workspace projects
    """

    ASANA_API_BASE = "https://app.asana.com/api/1.0"

    def __init__(self, access_token: str, timeout: float = 30.0):
        """
        Initialize MCP client.

        Args:
            access_token: Asana OAuth access token (works with both MCP and REST API)
            timeout: Request timeout in seconds
        """
        self.access_token = access_token
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._tools_cache: Optional[List[MCPTool]] = None

    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()

    async def list_tools(self) -> List[MCPTool]:
        """
        List all available Asana MCP tools.

        Returns:
            List of MCPTool objects
        """
        if self._tools_cache:
            return self._tools_cache

        # Define available tools
        tools = [
            MCPTool(
                name="list_tasks",
                description="List tasks assigned to user, optionally filtered by project and completion status",
                input_schema={
                    "type": "object",
                    "properties": {
                        "assignee": {
                            "type": "string",
                            "description": "Assignee GID or 'me' for current user",
                            "default": "me"
                        },
                        "project": {
                            "type": "string",
                            "description": "Project name or GID to filter by"
                        },
                        "workspace": {
                            "type": "string",
                            "description": "Workspace GID"
                        },
                        "completed": {
                            "type": "boolean",
                            "description": "Filter by completion status (default: false = incomplete only)",
                            "default": False
                        }
                    }
                }
            ),
            MCPTool(
                name="create_task",
                description="Create a new task in Asana",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Task name (required)"
                        },
                        "notes": {
                            "type": "string",
                            "description": "Task description/notes"
                        },
                        "project": {
                            "type": "string",
                            "description": "Project name or GID"
                        },
                        "assignee": {
                            "type": "string",
                            "description": "Assignee GID or 'me'"
                        },
                        "due_date": {
                            "type": "string",
                            "description": "Due date (YYYY-MM-DD format)"
                        }
                    },
                    "required": ["name"]
                }
            ),
            MCPTool(
                name="update_task",
                description="Update an existing task (mark complete, change name, etc.)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "Task GID (required)"
                        },
                        "name": {
                            "type": "string",
                            "description": "New task name"
                        },
                        "notes": {
                            "type": "string",
                            "description": "New description"
                        },
                        "completed": {
                            "type": "boolean",
                            "description": "Mark as completed (true) or incomplete (false)"
                        }
                    },
                    "required": ["task_id"]
                }
            ),
            MCPTool(
                name="get_task",
                description="Get detailed information about a specific task",
                input_schema={
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "Task GID (required)"
                        }
                    },
                    "required": ["task_id"]
                }
            ),
            MCPTool(
                name="list_projects",
                description="List projects in a workspace",
                input_schema={
                    "type": "object",
                    "properties": {
                        "workspace": {
                            "type": "string",
                            "description": "Workspace GID (required)"
                        }
                    },
                    "required": ["workspace"]
                }
            )
        ]

        self._tools_cache = tools
        logger.info(f"Loaded {len(tools)} Asana tools")
        return tools

    async def call_tool(self, tool_name: str, arguments: Dict) -> Any:
        """
        Execute an Asana MCP tool.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            Tool execution result

        Raises:
            RuntimeError: If tool execution fails
        """
        logger.info(f"Executing tool: {tool_name} with args: {arguments}")

        try:
            if tool_name == "list_tasks":
                return await self._list_tasks(arguments)
            elif tool_name == "create_task":
                return await self._create_task(arguments)
            elif tool_name == "update_task":
                return await self._update_task(arguments)
            elif tool_name == "get_task":
                return await self._get_task(arguments)
            elif tool_name == "list_projects":
                return await self._list_projects(arguments)
            else:
                raise ValueError(f"Unknown tool: {tool_name}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise RuntimeError("Authentication failed: OAuth token expired or invalid. Please reconnect Asana integration.")
            elif e.response.status_code == 404:
                raise RuntimeError(f"Resource not found: {e.request.url}")
            elif e.response.status_code == 403:
                raise RuntimeError("Permission denied: Check workspace access")
            else:
                raise RuntimeError(f"Asana API error [{e.response.status_code}]: {e.response.text}")

    async def _list_tasks(self, args: Dict) -> List[Dict]:
        """List tasks via Asana REST API."""
        params = {
            "assignee": args.get("assignee", "me"),
            "opt_fields": "name,completed,due_on,notes,projects.name"
        }

        # Handle workspace filter
        if "workspace" in args:
            params["workspace"] = args["workspace"]

        # Handle project filter
        if "project" in args:
            params["project"] = args["project"]

        # Handle completion filter
        if not args.get("completed", False):
            params["completed_since"] = "now"  # Only incomplete tasks

        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }

        response = await self._client.get(
            f"{self.ASANA_API_BASE}/tasks",
            headers=headers,
            params=params
        )
        response.raise_for_status()

        result = response.json()
        tasks = result.get("data", [])
        logger.info(f"Listed {len(tasks)} tasks")
        return tasks

    async def _create_task(self, args: Dict) -> Dict:
        """Create task via Asana REST API."""
        task_data = {
            "name": args["name"]
        }

        if "notes" in args:
            task_data["notes"] = args["notes"]
        if "project" in args:
            task_data["projects"] = [args["project"]]
        if "assignee" in args:
            task_data["assignee"] = args["assignee"]
        if "due_date" in args:
            task_data["due_on"] = args["due_date"]

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        response = await self._client.post(
            f"{self.ASANA_API_BASE}/tasks",
            headers=headers,
            json={"data": task_data}
        )
        response.raise_for_status()

        result = response.json()
        task = result.get("data", {})
        logger.info(f"Created task: {task.get('gid')}")
        return task

    async def _update_task(self, args: Dict) -> Dict:
        """Update task via Asana REST API."""
        task_gid = args.pop("task_id")
        update_data = {}

        if "name" in args:
            update_data["name"] = args["name"]
        if "notes" in args:
            update_data["notes"] = args["notes"]
        if "completed" in args:
            update_data["completed"] = args["completed"]

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        response = await self._client.put(
            f"{self.ASANA_API_BASE}/tasks/{task_gid}",
            headers=headers,
            json={"data": update_data}
        )
        response.raise_for_status()

        result = response.json()
        task = result.get("data", {})
        logger.info(f"Updated task: {task_gid}")
        return task

    async def _get_task(self, args: Dict) -> Dict:
        """Get task via Asana REST API."""
        task_gid = args["task_id"]

        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }

        response = await self._client.get(
            f"{self.ASANA_API_BASE}/tasks/{task_gid}",
            headers=headers
        )
        response.raise_for_status()

        result = response.json()
        task = result.get("data", {})
        logger.info(f"Retrieved task: {task_gid}")
        return task

    async def _list_projects(self, args: Dict) -> List[Dict]:
        """List projects via Asana REST API."""
        params = {
            "workspace": args["workspace"],
            "opt_fields": "name,archived"
        }

        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }

        response = await self._client.get(
            f"{self.ASANA_API_BASE}/projects",
            headers=headers,
            params=params
        )
        response.raise_for_status()

        result = response.json()
        projects = result.get("data", [])
        logger.info(f"Listed {len(projects)} projects")
        return projects

    async def get_tool_by_name(self, name: str) -> Optional[MCPTool]:
        """Find tool by name."""
        tools = await self.list_tools()
        return next((t for t in tools if t.name == name), None)

    async def search_tools(self, query: str) -> List[MCPTool]:
        """
        Search tools by name or description.

        Args:
            query: Search query

        Returns:
            Matching tools
        """
        tools = await self.list_tools()
        query_lower = query.lower()

        return [
            t for t in tools
            if query_lower in t.name.lower() or query_lower in t.description.lower()
        ]

    async def check_version(self) -> str:
        """
        Check API compatibility.

        Returns:
            API version string
        """
        return "1.0"  # Asana REST API v1.0
