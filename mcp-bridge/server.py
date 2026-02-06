#!/usr/bin/env python3
"""
MCP HTTP Bridge Server

Phase 8: Browser Automation - Host-side bridge for MCP tool execution.

This server runs on the host machine and provides an HTTP interface
for the Docker-based Tsushin backend to execute MCP browser tools.

Communication Flow:
    Tsushin Backend (Docker) --HTTP--> This Bridge --MCP/stdio--> Browser MCP Server

Usage:
    python server.py

Environment Variables:
    MCP_BRIDGE_PORT: HTTP port (default: 8765)
    MCP_BRIDGE_API_KEY: Optional API key for authentication
    MCP_BRIDGE_ALLOWED_TOOLS: Comma-separated whitelist of allowed MCP tools

Security:
    - API key authentication (optional)
    - Tool whitelist (only browser tools allowed)
    - Rate limiting per session
    - Request logging for audit

Requirements:
    pip install aiohttp

Note: This server should only run on trusted local machines.
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from aiohttp import web

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("mcp-bridge")


# Default configuration
DEFAULT_PORT = 8765
DEFAULT_ALLOWED_TOOLS = [
    # Playwright MCP tools
    "browser_navigate",
    "browser_click",
    "browser_type",
    "browser_snapshot",
    "browser_take_screenshot",
    "browser_evaluate",
    "browser_close",
    "browser_resize",
    "browser_fill_form",
    "browser_press_key",
    "browser_select_option",
    "browser_wait_for",
    # Claude in Chrome tools
    "navigate",
    "computer",
    "read_page",
    "find",
    "form_input",
    "javascript_tool",
    "get_page_text",
    "tabs_context_mcp",
    "tabs_create_mcp",
]

# Rate limiting settings
MAX_REQUESTS_PER_MINUTE = 60
RATE_LIMIT_WINDOW_SECONDS = 60


class RateLimiter:
    """Simple in-memory rate limiter per session."""

    def __init__(self, max_requests: int = MAX_REQUESTS_PER_MINUTE, window_seconds: int = RATE_LIMIT_WINDOW_SECONDS):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, List[float]] = {}

    def is_allowed(self, session_id: str) -> bool:
        """Check if request is allowed for session."""
        now = time.time()
        cutoff = now - self.window_seconds

        # Get request timestamps for session
        timestamps = self._requests.get(session_id, [])

        # Remove old timestamps
        timestamps = [t for t in timestamps if t > cutoff]

        # Check limit
        if len(timestamps) >= self.max_requests:
            self._requests[session_id] = timestamps
            return False

        # Add current timestamp
        timestamps.append(now)
        self._requests[session_id] = timestamps
        return True

    def get_remaining(self, session_id: str) -> int:
        """Get remaining requests for session."""
        now = time.time()
        cutoff = now - self.window_seconds
        timestamps = self._requests.get(session_id, [])
        timestamps = [t for t in timestamps if t > cutoff]
        return max(0, self.max_requests - len(timestamps))


class MCPBridgeServer:
    """
    HTTP bridge server for MCP tool execution.

    Listens for HTTP requests from Docker containers and proxies
    them to MCP servers via stdio.
    """

    def __init__(
        self,
        port: int = DEFAULT_PORT,
        api_key: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None,
    ):
        self.port = port
        self.api_key = api_key
        self.allowed_tools = set(allowed_tools or DEFAULT_ALLOWED_TOOLS)
        self.rate_limiter = RateLimiter()

        # Session tracking
        self._sessions: Dict[str, Dict[str, Any]] = {}

        # MCP client connections (to be implemented based on MCP SDK)
        self._mcp_clients: Dict[str, Any] = {}

        # Request logging
        self._request_log: List[Dict[str, Any]] = []

        logger.info(f"MCP Bridge initialized (port={port}, tools={len(self.allowed_tools)})")

    async def _validate_auth(self, request: web.Request) -> bool:
        """Validate API key authentication."""
        if not self.api_key:
            return True  # No auth required

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            return token == self.api_key

        return False

    async def _validate_tool(self, tool_name: str) -> bool:
        """Validate tool is in whitelist."""
        return tool_name in self.allowed_tools

    def _log_request(
        self,
        session_id: str,
        tool: str,
        params: Dict,
        success: bool,
        duration_ms: int,
        error: Optional[str] = None,
    ):
        """Log request for audit trail."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": session_id,
            "tool": tool,
            "params_hash": hashlib.sha256(
                json.dumps(params, sort_keys=True).encode()
            ).hexdigest()[:16],
            "success": success,
            "duration_ms": duration_ms,
            "error": error,
        }
        self._request_log.append(log_entry)

        # Keep only last 1000 entries
        if len(self._request_log) > 1000:
            self._request_log = self._request_log[-1000:]

        logger.info(
            f"MCP call: tool={tool} session={session_id} "
            f"success={success} duration={duration_ms}ms"
        )

    async def handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "active_sessions": len(self._sessions),
            "tools_available": len(self.allowed_tools),
        })

    async def handle_mcp_call(self, request: web.Request) -> web.Response:
        """
        Handle MCP tool call request.

        Request body:
            {
                "tool": "browser_navigate",
                "params": {"url": "https://example.com"},
                "session_id": "abc123",
                "mcp_backend": "playwright"
            }

        Response:
            {
                "success": true,
                "result": {"url": "https://example.com", "title": "Example"},
                "duration_ms": 150
            }
        """
        start_time = time.time()

        # Validate auth
        if not await self._validate_auth(request):
            return web.json_response(
                {"success": False, "error": "Unauthorized"},
                status=401
            )

        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response(
                {"success": False, "error": "Invalid JSON"},
                status=400
            )

        tool = data.get("tool", "")
        params = data.get("params", {})
        session_id = data.get("session_id", "unknown")
        mcp_backend = data.get("mcp_backend", "playwright")

        # Validate tool
        if not await self._validate_tool(tool):
            return web.json_response(
                {"success": False, "error": f"Tool not allowed: {tool}"},
                status=403
            )

        # Rate limiting
        if not self.rate_limiter.is_allowed(session_id):
            remaining = self.rate_limiter.get_remaining(session_id)
            return web.json_response(
                {
                    "success": False,
                    "error": "Rate limit exceeded",
                    "remaining": remaining,
                },
                status=429
            )

        try:
            # Execute MCP tool
            # Note: In a full implementation, this would connect to the actual MCP server
            # For now, we return a mock response indicating the bridge is working
            result = await self._execute_mcp_tool(tool, params, mcp_backend)

            duration_ms = int((time.time() - start_time) * 1000)

            self._log_request(session_id, tool, params, True, duration_ms)

            return web.json_response({
                "success": True,
                "result": result,
                "duration_ms": duration_ms,
            })

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)

            self._log_request(session_id, tool, params, False, duration_ms, error_msg)

            return web.json_response(
                {"success": False, "error": error_msg},
                status=500
            )

    async def _execute_mcp_tool(
        self,
        tool: str,
        params: Dict[str, Any],
        mcp_backend: str,
    ) -> Dict[str, Any]:
        """
        Execute MCP tool via stdio.

        This is a placeholder implementation. In production, this would:
        1. Spawn or connect to the appropriate MCP server process
        2. Send the tool call via JSON-RPC over stdio
        3. Return the response

        For testing purposes, this returns mock responses.
        """
        logger.info(f"Executing MCP tool: {tool} (backend={mcp_backend})")

        # Mock implementation for testing
        # In production, this would actually call the MCP server
        if tool == "browser_navigate":
            url = params.get("url", "")
            return {
                "url": url,
                "title": f"Page at {url}",
                "status": 200,
            }
        elif tool == "browser_snapshot":
            return {
                "content": "Mock page content for testing",
                "url": "https://example.com",
                "title": "Example Domain",
            }
        elif tool == "browser_take_screenshot":
            # In production, would save actual screenshot
            filename = params.get("filename", "/tmp/screenshot.png")
            return {
                "path": filename,
                "success": True,
            }
        elif tool == "browser_click":
            return {"clicked": True, "selector": params.get("ref", "")}
        elif tool == "browser_type":
            return {"typed": True, "text": params.get("text", "")}
        elif tool == "browser_evaluate":
            return {"result": "mock_script_result"}
        else:
            # Generic mock response
            return {"tool": tool, "status": "executed", "params_received": list(params.keys())}

    async def handle_session_end(self, request: web.Request) -> web.Response:
        """Handle session end notification."""
        if not await self._validate_auth(request):
            return web.json_response(
                {"success": False, "error": "Unauthorized"},
                status=401
            )

        try:
            data = await request.json()
            session_id = data.get("session_id", "")

            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info(f"Session ended: {session_id}")

            return web.json_response({"success": True})

        except Exception as e:
            return web.json_response(
                {"success": False, "error": str(e)},
                status=500
            )

    async def handle_logs(self, request: web.Request) -> web.Response:
        """Return recent request logs (for debugging)."""
        if not await self._validate_auth(request):
            return web.json_response(
                {"success": False, "error": "Unauthorized"},
                status=401
            )

        limit = int(request.query.get("limit", "100"))
        logs = self._request_log[-limit:]

        return web.json_response({
            "success": True,
            "logs": logs,
            "total": len(self._request_log),
        })

    def create_app(self) -> web.Application:
        """Create aiohttp application with routes."""
        app = web.Application()

        app.router.add_get("/health", self.handle_health)
        app.router.add_post("/mcp/call", self.handle_mcp_call)
        app.router.add_post("/mcp/session/end", self.handle_session_end)
        app.router.add_get("/logs", self.handle_logs)

        return app

    async def start(self):
        """Start the HTTP server."""
        app = self.create_app()
        runner = web.AppRunner(app)
        await runner.setup()

        site = web.TCPSite(runner, "0.0.0.0", self.port)
        await site.start()

        logger.info(f"MCP Bridge server started on http://0.0.0.0:{self.port}")
        logger.info(f"Health check: http://localhost:{self.port}/health")

        # Keep running
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            logger.info("Server shutdown requested")
        finally:
            await runner.cleanup()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="MCP HTTP Bridge Server")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_BRIDGE_PORT", DEFAULT_PORT)),
        help=f"HTTP port (default: {DEFAULT_PORT})"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.getenv("MCP_BRIDGE_API_KEY", ""),
        help="API key for authentication (optional)"
    )
    args = parser.parse_args()

    # Create server
    server = MCPBridgeServer(
        port=args.port,
        api_key=args.api_key or None,
    )

    # Handle shutdown signals
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def handle_signal(sig):
        logger.info(f"Received signal {sig}, shutting down...")
        loop.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))

    try:
        loop.run_until_complete(server.start())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        loop.close()
        logger.info("Server stopped")


if __name__ == "__main__":
    main()
