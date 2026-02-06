"""
Tsushin Shell Beacon - WebSocket Client (Phase 18.4)

WebSocket-based beacon client that:
1. Connects to the Tsushin backend via WebSocket
2. Authenticates using API key
3. Receives commands in real-time
4. Sends heartbeats and results

Provides lower latency than HTTP polling mode.
"""

import sys
import time
import signal
import logging
import json
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger("tsushin.beacon.websocket")

# Try to import websockets library
try:
    import websockets
    from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    logger.warning("websockets library not installed. Run: pip install websockets")


class WebSocketBeaconClient:
    """
    WebSocket-based beacon client.

    Provides real-time command delivery with automatic reconnection
    and exponential backoff.
    """

    def __init__(
        self,
        server_url: str,
        api_key: str,
        integration_id: Optional[int] = None,
        heartbeat_interval: int = 15,
        reconnect_delay: int = 5,
        max_reconnect_delay: int = 300,
        executor=None
    ):
        """
        Initialize the WebSocket beacon client.

        Args:
            server_url: WebSocket server URL (e.g., ws://localhost:8000/ws/beacon/1)
            api_key: API key for authentication
            integration_id: Integration ID (optional, extracted from server response)
            heartbeat_interval: Seconds between heartbeat messages
            reconnect_delay: Initial reconnect delay in seconds
            max_reconnect_delay: Maximum reconnect delay (for exponential backoff)
            executor: CommandExecutor instance for running commands
        """
        if not WEBSOCKETS_AVAILABLE:
            raise ImportError("websockets library required for WebSocket mode")

        self.server_url = server_url
        self.api_key = api_key
        self.integration_id = integration_id
        self.heartbeat_interval = heartbeat_interval
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self.executor = executor

        self._running = False
        self._shutdown_requested = False
        self._websocket: Optional[Any] = None
        self._current_reconnect_delay = reconnect_delay

        # Stats
        self._commands_executed = 0
        self._connected_at: Optional[datetime] = None
        self._last_heartbeat: Optional[datetime] = None

    async def connect(self) -> bool:
        """
        Establish WebSocket connection and authenticate.

        Returns:
            True if connected and authenticated successfully
        """
        try:
            logger.info(f"Connecting to {self.server_url}...")

            self._websocket = await websockets.connect(
                self.server_url,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5
            )

            logger.info("WebSocket connected, authenticating...")

            # Send authentication message
            await self._websocket.send(json.dumps({
                "type": "auth",
                "api_key": self.api_key
            }))

            # Wait for auth response
            response = await asyncio.wait_for(
                self._websocket.recv(),
                timeout=10
            )

            auth_response = json.loads(response)

            if auth_response.get("type") == "auth_success":
                self.integration_id = auth_response.get("integration_id")
                poll_interval = auth_response.get("poll_interval", 5)

                logger.info(
                    f"Authenticated successfully: integration_id={self.integration_id}, "
                    f"poll_interval={poll_interval}s"
                )

                self._connected_at = datetime.utcnow()
                self._current_reconnect_delay = self.reconnect_delay

                # Send initial OS info
                await self._send_os_info()

                return True

            else:
                reason = auth_response.get("reason", "Unknown")
                logger.error(f"Authentication failed: {reason}")
                await self._close()
                return False

        except asyncio.TimeoutError:
            logger.error("Authentication timeout")
            await self._close()
            return False

        except Exception as e:
            logger.error(f"Connection error: {e}")
            await self._close()
            return False

    async def _close(self):
        """Close the WebSocket connection."""
        if self._websocket:
            try:
                await self._websocket.close()
            except Exception:
                pass
            self._websocket = None

    async def _send_os_info(self):
        """Send OS information to server."""
        try:
            from .executor import get_os_info
            os_info = get_os_info()

            await self._websocket.send(json.dumps({
                "type": "os_info",
                "hostname": os_info.get("hostname", "unknown"),
                "os_info": os_info
            }))

            logger.debug("Sent OS info to server")

        except Exception as e:
            logger.warning(f"Failed to send OS info: {e}")

    async def _send_heartbeat(self):
        """Send heartbeat message."""
        if not self._websocket:
            return

        try:
            await self._websocket.send(json.dumps({
                "type": "heartbeat"
            }))
            self._last_heartbeat = datetime.utcnow()
            logger.debug("Heartbeat sent")

        except Exception as e:
            logger.warning(f"Failed to send heartbeat: {e}")

    async def _send_result(self, command_id: str, result: Dict[str, Any]):
        """
        Send command result to server.

        Args:
            command_id: UUID of the command
            result: Execution result dictionary
        """
        if not self._websocket:
            logger.warning(f"Cannot send result for {command_id}: not connected")
            return

        try:
            await self._websocket.send(json.dumps({
                "type": "command_result",
                "command_id": command_id,
                "exit_code": result.get("exit_code", 1),
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
                "execution_time_ms": result.get("execution_time_ms", 0),
                "final_working_dir": result.get("final_working_dir", ""),
                "full_result_json": result.get("full_result_json", []),
                "error_message": result.get("error_message")
            }))

            logger.debug(f"Sent result for command {command_id}")

        except Exception as e:
            logger.error(f"Failed to send result for {command_id}: {e}")

    async def _handle_command(self, command_data: Dict[str, Any]):
        """
        Handle an incoming command.

        Args:
            command_data: Command data from server
        """
        command_id = command_data.get("id")
        commands = command_data.get("commands", [])
        timeout = command_data.get("timeout", 300)

        if not command_id or not commands:
            logger.warning("Received invalid command data")
            return

        logger.info(f"Executing command {command_id}: {len(commands)} command(s)")

        # Execute commands
        if self.executor:
            result = self.executor.run_stacked(
                commands=commands,
                timeout_per_command=timeout,
                stop_on_error=True
            )

            self._commands_executed += 1

            # Log result
            if result.final_exit_code == 0:
                logger.info(f"Command {command_id} completed successfully ({result.total_execution_time_ms}ms)")
            else:
                logger.warning(f"Command {command_id} failed with exit code {result.final_exit_code}")

            # Send result
            await self._send_result(command_id, result.to_dict())
        else:
            logger.error("No executor configured, cannot run command")
            await self._send_result(command_id, {
                "exit_code": 1,
                "stderr": "Executor not configured",
                "error_message": "Executor not configured"
            })

    async def _message_loop(self):
        """Main message receiving loop."""
        while self._running and self._websocket:
            try:
                # Wait for message with timeout (for heartbeat)
                try:
                    raw_message = await asyncio.wait_for(
                        self._websocket.recv(),
                        timeout=self.heartbeat_interval
                    )

                    message = json.loads(raw_message)
                    msg_type = message.get("type")

                    if msg_type == "command":
                        # Handle command asynchronously
                        asyncio.create_task(self._handle_command(message))

                    elif msg_type == "ack":
                        logger.debug(f"Received ack for command {message.get('command_id')}")

                    else:
                        logger.debug(f"Received message type: {msg_type}")

                except asyncio.TimeoutError:
                    # Send heartbeat on timeout
                    await self._send_heartbeat()

            except ConnectionClosedError as e:
                logger.warning(f"Connection closed: {e}")
                break

            except ConnectionClosedOK:
                logger.info("Connection closed cleanly")
                break

            except Exception as e:
                logger.error(f"Error in message loop: {e}")
                break

    async def run(self):
        """
        Main run loop with automatic reconnection.

        Runs until shutdown is requested.
        """
        self._running = True

        logger.info("Starting WebSocket beacon...")

        while self._running and not self._shutdown_requested:
            try:
                # Connect
                if await self.connect():
                    # Run message loop
                    await self._message_loop()

                # Connection lost or failed
                if self._shutdown_requested:
                    break

                # Reconnect with backoff
                logger.info(f"Reconnecting in {self._current_reconnect_delay}s...")
                await asyncio.sleep(self._current_reconnect_delay)

                # Exponential backoff
                self._current_reconnect_delay = min(
                    self._current_reconnect_delay * 2,
                    self.max_reconnect_delay
                )

            except Exception as e:
                logger.error(f"Unexpected error in run loop: {e}")
                await asyncio.sleep(self._current_reconnect_delay)

        await self._close()
        self._running = False

        self._log_stats()
        logger.info("WebSocket beacon stopped")

    async def stop(self):
        """Request graceful shutdown."""
        logger.info("Shutdown requested...")
        self._shutdown_requested = True
        await self._close()

    def _log_stats(self):
        """Log session statistics."""
        if self._connected_at:
            uptime = datetime.utcnow() - self._connected_at
            logger.info(f"Session stats: uptime={uptime}, commands_executed={self._commands_executed}")


async def run_websocket_beacon(
    server_url: str,
    api_key: str,
    integration_id: int,
    executor,
    heartbeat_interval: int = 15
):
    """
    Run the WebSocket beacon client.

    Args:
        server_url: Base server URL (e.g., ws://localhost:8000)
        api_key: API key for authentication
        integration_id: Integration ID
        executor: CommandExecutor instance
        heartbeat_interval: Heartbeat interval in seconds
    """
    # Build WebSocket URL
    ws_url = f"{server_url}/ws/beacon/{integration_id}"

    client = WebSocketBeaconClient(
        server_url=ws_url,
        api_key=api_key,
        integration_id=integration_id,
        heartbeat_interval=heartbeat_interval,
        executor=executor
    )

    # Setup signal handlers
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(client.stop())
        )

    await client.run()
