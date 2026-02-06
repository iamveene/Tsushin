"""
Shell Skill WebSocket Endpoints (Phase 18.4)
Real-time C2 Communication for Beacon Agents

Provides WebSocket endpoints for:
- Beacon connections (/ws/beacon/{integration_id})
- UI status updates (/ws/shell/status)

Protocol:
    Beacon → Server:
        {"type": "auth", "api_key": "shb_xxxxx"}
        {"type": "heartbeat"}
        {"type": "command_result", "command_id": "uuid", "result": {...}}

    Server → Beacon:
        {"type": "auth_success", "integration_id": 123, "poll_interval": 5}
        {"type": "auth_failed", "reason": "..."}
        {"type": "command", "id": "uuid", "commands": [...], "timeout": 60}
"""

import logging
import hashlib
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.orm import Session

from models import ShellIntegration, ShellCommand
from websocket_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Shell WebSocket"])

# Global engine reference (set by main app.py)
_engine = None

# Authentication timeout (seconds)
AUTH_TIMEOUT = 10


def set_engine(engine):
    """Set the global engine reference"""
    global _engine
    _engine = engine


def get_db():
    """Dependency to get database session"""
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_api_key(api_key: str) -> str:
    """Hash an API key for comparison."""
    return hashlib.sha256(api_key.encode()).hexdigest()


async def authenticate_beacon(
    websocket: WebSocket,
    db: Session,
    timeout: float = AUTH_TIMEOUT
) -> Optional[ShellIntegration]:
    """
    Wait for authentication message and validate API key.

    Protocol:
        Beacon sends: {"type": "auth", "api_key": "shb_xxxxx"}
        Server responds: {"type": "auth_success", ...} or {"type": "auth_failed", ...}

    Args:
        websocket: WebSocket connection
        db: Database session
        timeout: Max time to wait for auth message

    Returns:
        ShellIntegration if authenticated, None otherwise
    """
    try:
        # Wait for auth message with timeout
        raw_message = await asyncio.wait_for(
            websocket.receive_text(),
            timeout=timeout
        )

        import json
        message = json.loads(raw_message)

        if message.get("type") != "auth":
            await websocket.send_json({
                "type": "auth_failed",
                "reason": "Expected auth message as first message"
            })
            return None

        api_key = message.get("api_key")
        if not api_key:
            await websocket.send_json({
                "type": "auth_failed",
                "reason": "Missing api_key"
            })
            return None

        # Validate API key
        hashed = hash_api_key(api_key)
        integration = db.query(ShellIntegration).filter(
            ShellIntegration.api_key_hash == hashed,
            ShellIntegration.is_active == True
        ).first()

        if not integration:
            logger.warning(f"Beacon auth failed: invalid API key")
            await websocket.send_json({
                "type": "auth_failed",
                "reason": "Invalid API key"
            })
            return None

        # Update integration with connection info
        integration.last_checkin = datetime.utcnow()
        integration.health_status = "healthy"
        db.commit()

        # Send success response
        await websocket.send_json({
            "type": "auth_success",
            "integration_id": integration.id,
            "poll_interval": integration.poll_interval,
            "mode": "websocket"
        })

        logger.info(f"Beacon {integration.id} authenticated via WebSocket")
        return integration

    except asyncio.TimeoutError:
        logger.warning("Beacon auth timeout - no auth message received")
        await websocket.send_json({
            "type": "auth_failed",
            "reason": "Authentication timeout"
        })
        return None

    except Exception as e:
        logger.error(f"Beacon auth error: {e}")
        try:
            await websocket.send_json({
                "type": "auth_failed",
                "reason": f"Authentication error: {str(e)}"
            })
        except Exception:
            pass
        return None


async def send_pending_commands(
    integration_id: int,
    websocket: WebSocket,
    db: Session
) -> int:
    """
    Send any pending commands to the beacon.

    Called after authentication to push queued commands.

    Args:
        integration_id: ShellIntegration ID
        websocket: WebSocket connection
        db: Database session

    Returns:
        Number of commands sent
    """
    pending = db.query(ShellCommand).filter(
        ShellCommand.shell_id == integration_id,
        ShellCommand.status == "queued"
    ).order_by(ShellCommand.queued_at).all()

    count = 0
    for cmd in pending:
        try:
            await websocket.send_json({
                "type": "command",
                "id": cmd.id,
                "commands": cmd.commands,
                "timeout": cmd.timeout_seconds
            })

            # Update status
            cmd.status = "sent"
            cmd.sent_at = datetime.utcnow()
            count += 1

            logger.debug(f"Sent pending command {cmd.id} to beacon {integration_id}")

        except Exception as e:
            logger.error(f"Error sending pending command {cmd.id}: {e}")
            break

    if count > 0:
        db.commit()

    return count


async def handle_beacon_message(
    message: Dict[str, Any],
    integration: ShellIntegration,
    db: Session
):
    """
    Handle a message from the beacon.

    Message types:
        - heartbeat: Update last_checkin
        - command_result: Store execution result

    Args:
        message: Parsed message from beacon
        integration: ShellIntegration record
        db: Database session
    """
    msg_type = message.get("type")

    if msg_type == "heartbeat":
        # Update heartbeat in manager
        manager.update_beacon_heartbeat(integration.id)

        # Update DB last_checkin
        integration.last_checkin = datetime.utcnow()
        db.commit()

        logger.debug(f"Beacon {integration.id} heartbeat")

    elif msg_type == "command_result":
        await handle_command_result(message, integration, db)

    elif msg_type == "os_info":
        # Update OS info
        integration.os_info = message.get("os_info")
        integration.hostname = message.get("hostname", integration.hostname)
        db.commit()
        logger.debug(f"Beacon {integration.id} OS info updated")

    else:
        logger.warning(f"Unknown message type from beacon {integration.id}: {msg_type}")


async def handle_command_result(
    message: Dict[str, Any],
    integration: ShellIntegration,
    db: Session
):
    """
    Handle command result from beacon.

    Expected message format:
        {
            "type": "command_result",
            "command_id": "uuid",
            "exit_code": 0,
            "stdout": "...",
            "stderr": "...",
            "execution_time_ms": 1234,
            "final_working_dir": "/tmp",
            "full_result_json": [...]
        }
    """
    command_id = message.get("command_id")
    if not command_id:
        logger.warning(f"Command result missing command_id from beacon {integration.id}")
        return

    # Find the command
    command = db.query(ShellCommand).filter(
        ShellCommand.id == command_id,
        ShellCommand.shell_id == integration.id
    ).first()

    if not command:
        logger.warning(f"Command {command_id} not found for beacon {integration.id}")
        return

    # Update command with results
    exit_code = message.get("exit_code", 1)
    command.status = "completed" if exit_code == 0 else "failed"
    command.completed_at = datetime.utcnow()
    command.exit_code = exit_code
    command.stdout = message.get("stdout")
    command.stderr = message.get("stderr")
    command.execution_time_ms = message.get("execution_time_ms")
    command.final_working_dir = message.get("final_working_dir")
    command.full_result_json = message.get("full_result_json")
    command.error_message = message.get("error_message")

    db.commit()

    logger.info(f"Command {command_id} completed with exit code {exit_code}")

    # Notify UI clients
    await manager.notify_command_update(
        tenant_id=command.tenant_id,
        command_id=command_id,
        status=command.status,
        result={
            "exit_code": exit_code,
            "stdout": command.stdout[:500] if command.stdout else None,  # Truncate for notification
            "stderr": command.stderr[:500] if command.stderr else None,
            "execution_time_ms": command.execution_time_ms
        }
    )


@router.websocket("/ws/beacon/{integration_id}")
async def beacon_websocket(
    websocket: WebSocket,
    integration_id: int
):
    """
    WebSocket endpoint for beacon connections.

    Protocol:
        1. Client connects
        2. Server accepts connection
        3. Client sends auth message: {"type": "auth", "api_key": "..."}
        4. Server validates and responds
        5. Server sends any pending commands
        6. Main loop: receive messages, handle heartbeats/results

    Note: integration_id in URL is informational only - actual auth is via API key
    """
    # Accept the connection first
    await websocket.accept()

    # Get DB session
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()

    integration = None

    try:
        # Authenticate
        integration = await authenticate_beacon(websocket, db)

        if not integration:
            await websocket.close(code=4001, reason="Authentication failed")
            return

        # Verify integration_id matches (optional security check)
        if integration.id != integration_id:
            logger.warning(
                f"Integration ID mismatch: URL={integration_id}, auth={integration.id}"
            )
            # We'll use the authenticated integration, not the URL

        # Register connection
        await manager.connect_beacon(
            integration_id=integration.id,
            websocket=websocket,
            tenant_id=integration.tenant_id,
            hostname=integration.hostname
        )

        # Send any pending commands
        pending_count = await send_pending_commands(integration.id, websocket, db)
        if pending_count > 0:
            logger.info(f"Sent {pending_count} pending commands to beacon {integration.id}")

        # Main message loop
        while True:
            try:
                raw_message = await websocket.receive_text()

                import json
                message = json.loads(raw_message)

                await handle_beacon_message(message, integration, db)

            except WebSocketDisconnect:
                logger.info(f"Beacon {integration.id} disconnected")
                break

            except Exception as e:
                logger.error(f"Error handling beacon message: {e}")
                # Don't break on message errors - continue listening

    except Exception as e:
        logger.error(f"Beacon WebSocket error: {e}")

    finally:
        # Clean up
        if integration:
            await manager.disconnect_beacon(integration.id)

            # Update DB status
            try:
                integration.health_status = "offline"
                db.commit()
            except Exception:
                pass

        db.close()


@router.websocket("/ws/shell/status")
async def shell_status_websocket(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """
    WebSocket endpoint for UI clients to receive shell status updates.

    Events sent to clients:
        - beacon_online: When a beacon connects
        - beacon_offline: When a beacon disconnects
        - command_update: When a command status changes

    MED-005 FIX: Proper JWT authentication required.
    Supports both secure first-message auth (preferred) and legacy query param auth.
    """
    import json
    from auth_utils import decode_access_token

    # Accept connection first (before auth) - required for WebSocket protocol
    await websocket.accept()

    user_id = None
    tenant_id = None

    # MED-005 FIX: Validate JWT token and extract user/tenant
    if token:
        # Legacy mode: token in query params (for backward compatibility)
        logger.warning("Shell status WebSocket using legacy query param auth - please update client")
    else:
        # Secure mode: wait for auth message with token
        logger.debug("Waiting for auth message...")
        try:
            # Wait for first message (should be auth)
            auth_data = await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT)
            auth_message = json.loads(auth_data)

            if auth_message.get("type") != "auth":
                logger.error(f"Shell status WebSocket rejected: First message must be auth, got: {auth_message.get('type')}")
                await websocket.close(code=4001, reason="First message must be auth type")
                return

            token = auth_message.get("token")
            if not token:
                logger.error("Shell status WebSocket rejected: Auth message missing token")
                await websocket.close(code=4001, reason="Missing token in auth message")
                return

            logger.debug("Received auth token via secure first-message method")

        except asyncio.TimeoutError:
            logger.error("Shell status WebSocket rejected: Auth timeout")
            await websocket.close(code=4001, reason="Authentication timeout")
            return
        except json.JSONDecodeError:
            logger.error("Shell status WebSocket rejected: Invalid JSON in auth message")
            await websocket.close(code=4001, reason="Invalid auth message format")
            return

    # Verify JWT token
    if not token:
        logger.error("Shell status WebSocket rejected: Missing authentication token")
        await websocket.close(code=4001, reason="Missing authentication token")
        return

    try:
        payload = decode_access_token(token)
        if not payload:
            logger.error("Shell status WebSocket auth error: token decode failed")
            await websocket.close(code=4003, reason="Invalid or expired token")
            return

        # Extract user_id from token's "sub" claim (standard JWT claim)
        user_id = payload.get("sub") or payload.get("user_id")
        if not user_id:
            logger.error(f"Shell status WebSocket auth error: no user_id in payload")
            await websocket.close(code=4002, reason="Invalid token payload")
            return

        # Convert to int if string
        user_id = int(user_id) if isinstance(user_id, str) else user_id

        # Extract tenant_id from token
        tenant_id = payload.get("tenant_id")
        if not tenant_id:
            # Fallback to "default" for backward compatibility with older tokens
            tenant_id = "default"
            logger.warning(f"Shell status WebSocket: no tenant_id in token, using default")

        logger.info(f"Shell status WebSocket auth successful for user {user_id}, tenant {tenant_id}")

    except Exception as auth_error:
        logger.error(f"Shell status WebSocket auth error: {auth_error}")
        await websocket.close(code=4003, reason="Authentication failed")
        return

    # Send auth success confirmation
    await websocket.send_json({
        "type": "auth_success",
        "user_id": user_id,
        "tenant_id": tenant_id,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    })

    # Register for tenant updates
    manager.register_tenant_connection(tenant_id, user_id, websocket)

    try:
        # Send initial beacon status
        online_beacons = manager.get_online_beacons(tenant_id)
        await websocket.send_json({
            "type": "initial_status",
            "online_beacons": online_beacons,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })

        # Keep connection alive - just receive pings
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break

    except Exception as e:
        logger.error(f"Shell status WebSocket error: {e}")

    finally:
        manager.unregister_tenant_connection(tenant_id, user_id, websocket)


# ============================================================================
# REST API Helper for pushing commands via WebSocket
# ============================================================================

async def push_command_to_beacon(
    integration_id: int,
    command: ShellCommand
) -> bool:
    """
    Push a command to a connected beacon via WebSocket.

    Called by shell_command_service when queuing commands.

    Args:
        integration_id: Target beacon
        command: ShellCommand to push

    Returns:
        True if command was pushed, False if beacon not connected
    """
    if not manager.is_beacon_online(integration_id):
        return False

    success = await manager.send_to_beacon(integration_id, {
        "type": "command",
        "id": command.id,
        "commands": command.commands,
        "timeout": command.timeout_seconds
    })

    return success
