"""WebSocket Connection Manager for Real-Time Updates (Phase 6.11.2, Phase 14.9, Phase 18.4)"""
from fastapi import WebSocket, WebSocketDisconnect
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging
import json
import asyncio

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections for real-time updates.

    Phase 18.4: Extended for Shell Beacon C2 connections.
    Supports:
    - User connections (UI clients)
    - Beacon connections (Shell Skill remote hosts)
    - Tenant-scoped broadcasting
    """

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        # Phase 14.9: User-specific connections for targeted messaging
        self.user_connections: Dict[int, List[WebSocket]] = {}

        # Phase 18.4: Beacon C2 connections
        # Maps integration_id -> WebSocket for instant command push
        self.beacon_connections: Dict[int, WebSocket] = {}
        # Tracks last heartbeat per beacon for health monitoring
        self.beacon_last_heartbeat: Dict[int, datetime] = {}
        # Beacon metadata (tenant_id, hostname, etc.)
        self.beacon_metadata: Dict[int, Dict[str, Any]] = {}

        # Tenant-scoped connections for UI updates
        # Maps tenant_id -> list of (user_id, websocket)
        self.tenant_connections: Dict[str, List[tuple]] = {}

        self.logger = logging.getLogger(__name__)

    async def connect(self, websocket: WebSocket, user_id: Optional[int] = None):
        """
        Accept new WebSocket connection.

        Args:
            websocket: WebSocket connection
            user_id: Optional user ID for targeted messaging (Phase 14.9)
        """
        await websocket.accept()
        self.active_connections.append(websocket)

        # Phase 14.9: Track user-specific connections
        if user_id is not None:
            if user_id not in self.user_connections:
                self.user_connections[user_id] = []
            self.user_connections[user_id].append(websocket)
            self.logger.info(f"New WebSocket connection for user {user_id}. Total: {len(self.active_connections)}")
        else:
            self.logger.info(f"New WebSocket connection. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket, user_id: Optional[int] = None):
        """
        Remove WebSocket connection.

        Args:
            websocket: WebSocket connection
            user_id: Optional user ID (Phase 14.9)
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

        # Phase 14.9: Remove from user-specific connections
        if user_id is not None and user_id in self.user_connections:
            if websocket in self.user_connections[user_id]:
                self.user_connections[user_id].remove(websocket)
            # Clean up empty user connection lists
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]

        self.logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast message to all connected clients"""
        if not self.active_connections:
            return  # No clients connected

        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
                self.logger.debug(f"Broadcast sent: {message.get('type')}")
            except Exception as e:
                self.logger.error(f"Error broadcasting to client: {e}")
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)

    async def send_to_client(self, websocket: WebSocket, message: Dict[str, Any]):
        """Send message to specific client"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            self.logger.error(f"Error sending to client: {e}")
            self.disconnect(websocket)

    async def send_to_user(self, user_id: int, message: Dict[str, Any]):
        """
        Send message to all connections for a specific user (Phase 14.9).

        Args:
            user_id: Target user ID
            message: Message to send
        """
        if user_id not in self.user_connections:
            self.logger.debug(f"No active connections for user {user_id}")
            return

        disconnected = []
        for websocket in self.user_connections[user_id]:
            try:
                await websocket.send_json(message)
                self.logger.debug(f"Sent message to user {user_id}: {message.get('type')}")
            except Exception as e:
                self.logger.error(f"Error sending to user {user_id}: {e}")
                disconnected.append(websocket)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn, user_id)

    def get_user_connections(self, user_id: int) -> List[WebSocket]:
        """
        Get all active connections for a user (Phase 14.9).

        Args:
            user_id: User ID

        Returns:
            List of active WebSocket connections for the user
        """
        return self.user_connections.get(user_id, [])

    def get_connection_count(self) -> int:
        """Get number of active connections"""
        return len(self.active_connections)

    # ==========================================================================
    # Phase 18.4: Beacon C2 Connection Methods
    # ==========================================================================

    async def connect_beacon(
        self,
        integration_id: int,
        websocket: WebSocket,
        tenant_id: str,
        hostname: str
    ):
        """
        Register a beacon WebSocket connection.

        Args:
            integration_id: Shell integration ID
            websocket: WebSocket connection from beacon
            tenant_id: Tenant ID the beacon belongs to
            hostname: Hostname of the beacon machine
        """
        self.beacon_connections[integration_id] = websocket
        self.beacon_last_heartbeat[integration_id] = datetime.utcnow()
        self.beacon_metadata[integration_id] = {
            "tenant_id": tenant_id,
            "hostname": hostname,
            "connected_at": datetime.utcnow().isoformat() + "Z"
        }
        self.logger.info(
            f"Beacon connected: integration_id={integration_id}, "
            f"hostname={hostname}, tenant={tenant_id}"
        )

    def disconnect_beacon(self, integration_id: int):
        """
        Remove a beacon connection.

        Args:
            integration_id: Shell integration ID
        """
        if integration_id in self.beacon_connections:
            del self.beacon_connections[integration_id]
        if integration_id in self.beacon_last_heartbeat:
            del self.beacon_last_heartbeat[integration_id]
        if integration_id in self.beacon_metadata:
            del self.beacon_metadata[integration_id]
        self.logger.info(f"Beacon disconnected: integration_id={integration_id}")

    async def send_to_beacon(self, integration_id: int, message: Dict[str, Any]) -> bool:
        """
        Send a message to a specific beacon.

        Args:
            integration_id: Target shell integration ID
            message: Message to send (will be JSON serialized)

        Returns:
            True if sent successfully, False otherwise
        """
        if integration_id not in self.beacon_connections:
            self.logger.warning(f"Beacon {integration_id} not connected")
            return False

        try:
            websocket = self.beacon_connections[integration_id]
            await websocket.send_json(message)
            self.logger.debug(f"Sent to beacon {integration_id}: {message.get('type')}")
            return True
        except Exception as e:
            self.logger.error(f"Error sending to beacon {integration_id}: {e}")
            self.disconnect_beacon(integration_id)
            return False

    def is_beacon_online(self, integration_id: int) -> bool:
        """
        Check if a beacon is currently connected.

        Args:
            integration_id: Shell integration ID

        Returns:
            True if beacon is connected, False otherwise
        """
        return integration_id in self.beacon_connections

    def update_beacon_heartbeat(self, integration_id: int):
        """
        Update the last heartbeat timestamp for a beacon.

        Args:
            integration_id: Shell integration ID
        """
        if integration_id in self.beacon_connections:
            self.beacon_last_heartbeat[integration_id] = datetime.utcnow()
            self.logger.debug(f"Heartbeat updated for beacon {integration_id}")

    async def notify_command_update(
        self,
        tenant_id: str,
        command_id: int,
        status: str,
        result: Optional[str] = None
    ):
        """
        Notify all tenant UI connections about a command status update.

        Args:
            tenant_id: Tenant ID to notify
            command_id: Command that was updated
            status: New status (queued, sent, running, completed, failed, timeout)
            result: Optional command result/output
        """
        if tenant_id not in self.tenant_connections:
            return

        message = {
            "type": "command_update",
            "command_id": command_id,
            "status": status,
            "result": result,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

        disconnected = []
        for user_id, websocket in self.tenant_connections[tenant_id]:
            try:
                await websocket.send_json(message)
            except Exception as e:
                self.logger.error(f"Error notifying tenant {tenant_id} user {user_id}: {e}")
                disconnected.append((user_id, websocket))

        # Clean up disconnected
        for item in disconnected:
            self.tenant_connections[tenant_id].remove(item)

    def get_online_beacons(self, tenant_id: Optional[str] = None) -> List[int]:
        """
        Get list of online beacon integration IDs.

        Args:
            tenant_id: Optional filter by tenant

        Returns:
            List of integration IDs that are currently connected
        """
        if tenant_id is None:
            return list(self.beacon_connections.keys())

        return [
            iid for iid, meta in self.beacon_metadata.items()
            if meta.get("tenant_id") == tenant_id and iid in self.beacon_connections
        ]

    async def register_tenant_connection(
        self,
        tenant_id: str,
        user_id: int,
        websocket: WebSocket
    ):
        """
        Register a UI WebSocket connection for tenant-scoped updates.

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            websocket: WebSocket connection
        """
        if tenant_id not in self.tenant_connections:
            self.tenant_connections[tenant_id] = []
        self.tenant_connections[tenant_id].append((user_id, websocket))
        self.logger.info(f"Tenant connection registered: tenant={tenant_id}, user={user_id}")

    def unregister_tenant_connection(
        self,
        tenant_id: str,
        user_id: int,
        websocket: WebSocket
    ):
        """
        Remove a UI WebSocket connection.

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            websocket: WebSocket connection
        """
        if tenant_id in self.tenant_connections:
            try:
                self.tenant_connections[tenant_id].remove((user_id, websocket))
                if not self.tenant_connections[tenant_id]:
                    del self.tenant_connections[tenant_id]
                self.logger.info(f"Tenant connection unregistered: tenant={tenant_id}, user={user_id}")
            except ValueError:
                pass  # Already removed

    def get_beacon_stats(self) -> Dict[str, Any]:
        """
        Get statistics about beacon connections.

        Returns:
            Dict with beacon connection statistics
        """
        now = datetime.utcnow()
        stale_threshold = now - timedelta(minutes=5)

        stale_beacons = [
            iid for iid, last_hb in self.beacon_last_heartbeat.items()
            if last_hb < stale_threshold
        ]

        return {
            "total_beacons": len(self.beacon_connections),
            "online_beacons": list(self.beacon_connections.keys()),
            "stale_beacons": stale_beacons,
            "tenant_connections": {
                tid: len(conns) for tid, conns in self.tenant_connections.items()
            }
        }


# Global connection manager instance
manager = ConnectionManager()
