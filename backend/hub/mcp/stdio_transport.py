"""Stdio MCP transport -- runs MCP server binaries inside tenant toolbox containers."""
import asyncio
import json
import logging
import shutil
import time
from typing import Any, Optional, List, Dict
from hub.mcp.transport_base import MCPTransport

logger = logging.getLogger(__name__)

ALLOWED_MCP_STDIO_BINARIES = ["uvx", "npx", "node"]


class StdioTransport(MCPTransport):
    """
    Stdio-based MCP transport that delegates to ToolboxContainerService.

    Binary must be in ALLOWED_MCP_STDIO_BINARIES.
    Process runs as UID 1000 (toolbox user) inside the tenant container.
    """

    def __init__(self, server_config):
        super().__init__(server_config)
        self._process = None
        self._last_activity = time.time()
        self._idle_watchdog_task = None
        self._tenant_id = None

    async def connect(self) -> Any:
        """Start MCP server process inside tenant container."""
        binary = self.server_config.stdio_binary
        args = self.server_config.stdio_args or []

        # Security: Validate binary
        if not binary:
            raise ValueError("No binary specified for stdio transport")

        if binary not in ALLOWED_MCP_STDIO_BINARIES:
            raise ValueError(
                f"Binary '{binary}' not in allowed list: {ALLOWED_MCP_STDIO_BINARIES}"
            )

        # Security: Path traversal rejection
        if '/' in binary or '..' in binary or '\\' in binary:
            raise ValueError(f"Binary name contains path characters: '{binary}'")

        # Security: Validate args don't contain injection
        for arg in args:
            if any(c in str(arg) for c in [';', '|', '&', '`', '$', '(', ')']):
                raise ValueError(f"Argument contains shell metacharacters: '{arg}'")

        # Verify the binary can be resolved on the host (basic sanity check).
        # For container-based stdio the real resolution happens inside the
        # toolbox container, but we can at least verify the binary name is
        # known locally or reject obviously invalid paths early.
        if not shutil.which(binary):
            # The binary might only exist inside the container, so we do a
            # best-effort check via the toolbox container when available.
            try:
                from services.toolbox_container_service import ToolboxContainerService
                svc = ToolboxContainerService()
                result = await svc.execute_command(
                    tenant_id=self.server_config.tenant_id,
                    command=f"which {binary}",
                    timeout=10,
                )
                exit_code = result.get("exit_code", -1)
                if exit_code != 0:
                    raise ValueError(
                        f"Binary '{binary}' not found in toolbox container "
                        f"(exit_code={exit_code})"
                    )
            except ImportError:
                # ToolboxContainerService unavailable — fall through
                logger.warning(
                    f"Cannot verify binary '{binary}' — "
                    "ToolboxContainerService not available"
                )
            except ValueError:
                raise  # Re-raise our own ValueError
            except Exception as e:
                raise ValueError(
                    f"Failed to verify binary '{binary}' in container: {e}"
                )

        # Validate stdio_args reference a real MCP server package when the
        # binary is a package runner (npx/uvx).  If the first arg looks like
        # a clearly-invalid path (e.g. absolute path to a non-existent file),
        # reject early instead of silently succeeding with no tools.
        if args and binary in ("npx", "node"):
            first_arg = str(args[0])
            if first_arg.startswith("/") and not first_arg.startswith("@"):
                # Absolute path — check existence inside container
                try:
                    from services.toolbox_container_service import ToolboxContainerService
                    svc = ToolboxContainerService()
                    result = await svc.execute_command(
                        tenant_id=self.server_config.tenant_id,
                        command=f"test -e {_shell_escape(first_arg)}",
                        timeout=10,
                    )
                    if result.get("exit_code", -1) != 0:
                        raise ValueError(
                            f"Stdio server path '{first_arg}' does not exist "
                            "in toolbox container"
                        )
                except ImportError:
                    pass
                except ValueError:
                    raise
                except Exception as e:
                    raise ValueError(
                        f"Failed to verify server path '{first_arg}': {e}"
                    )

        self._connected = True
        self._last_activity = time.time()
        self._tenant_id = self.server_config.tenant_id

        # Start idle watchdog
        idle_timeout = self.server_config.idle_timeout_seconds or 300
        self._idle_watchdog_task = asyncio.create_task(
            self._idle_watchdog(idle_timeout)
        )

        logger.info(
            f"Stdio transport connected: {binary} {' '.join(str(a) for a in args)}"
        )
        return self

    async def disconnect(self) -> None:
        """Stop the MCP server process."""
        if self._idle_watchdog_task:
            self._idle_watchdog_task.cancel()
            try:
                await self._idle_watchdog_task
            except asyncio.CancelledError:
                pass
            self._idle_watchdog_task = None
        self._connected = False
        self._session = None
        logger.info(
            f"Stdio transport disconnected for {self.server_config.server_name}"
        )

    async def ping(self) -> bool:
        return self._connected

    async def list_tools(self) -> list:
        """Execute tools/list via container exec.

        For stdio transport, tools are discovered by sending a JSON-RPC
        ``tools/list`` request to the process's stdin.  If the process
        cannot be reached, an empty list is returned so the caller can
        detect that no tools were verified.
        """
        if not self._connected:
            return []

        binary = self.server_config.stdio_binary
        args = self.server_config.stdio_args or []

        tool_list_input = json.dumps({
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": 1,
        })

        try:
            from services.toolbox_container_service import ToolboxContainerService
            svc = ToolboxContainerService()

            cmd_parts = [binary] + [str(a) for a in args]
            cmd = f"printf '%s' {_shell_escape(tool_list_input)} | {' '.join(cmd_parts)}"

            result = await svc.execute_command(
                tenant_id=self.server_config.tenant_id,
                command=cmd,
                timeout=self.server_config.timeout_seconds or 30,
            )

            exit_code = result.get("exit_code", -1)
            stdout = result.get("stdout", "")

            if exit_code != 0:
                logger.warning(
                    f"Stdio list_tools failed (exit={exit_code}) for "
                    f"{self.server_config.server_name}"
                )
                return []

            parsed = json.loads(stdout)
            tools = parsed.get("result", {}).get("tools", [])
            return tools

        except Exception as e:
            logger.warning(f"Stdio list_tools error for {self.server_config.server_name}: {e}")
            return []

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Execute tool via container command."""
        self._last_activity = time.time()

        binary = self.server_config.stdio_binary
        args = self.server_config.stdio_args or []

        # Build command with resource limits
        cmd_parts = [
            "ulimit -v 1048576 -t 60;",  # 1GB vmem, 60s CPU
            binary,
        ] + [str(a) for a in args]

        # Pass tool call as JSON-RPC to stdin
        tool_input = json.dumps({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
            "id": 1,
        })

        # Execute in tenant container
        from services.toolbox_container_service import ToolboxContainerService

        container_service = ToolboxContainerService()

        try:
            # Use printf to safely pipe JSON without shell interpretation issues
            cmd = f"printf '%s' {_shell_escape(tool_input)} | {' '.join(cmd_parts)}"
            result = await container_service.execute_command(
                tenant_id=self.server_config.tenant_id,
                command=cmd,
                timeout=self.server_config.timeout_seconds or 30,
            )

            exit_code = result.get("exit_code", -1)
            stdout = result.get("stdout", "")
            stderr = result.get("stderr", "")

            if exit_code != 0:
                return {"error": stderr or f"Process exited with code {exit_code}"}

            # Parse MCP response
            try:
                parsed = json.loads(stdout)
                return parsed.get("result", parsed)
            except json.JSONDecodeError:
                return {"output": stdout}
        except Exception as e:
            logger.error(f"Stdio tool execution failed: {e}")
            return {"error": str(e)}

    async def _idle_watchdog(self, timeout_seconds: int):
        """Kill process after idle timeout."""
        try:
            while True:
                await asyncio.sleep(60)  # Check every minute
                if time.time() - self._last_activity > timeout_seconds:
                    logger.info(
                        f"Stdio transport idle timeout ({timeout_seconds}s) "
                        f"for {self.server_config.server_name}"
                    )
                    await self.disconnect()
                    break
        except asyncio.CancelledError:
            pass


def _shell_escape(value: str) -> str:
    """Escape a string for safe shell usage via single-quoting."""
    import shlex
    return shlex.quote(value)
