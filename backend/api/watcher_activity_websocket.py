"""
Watcher Activity WebSocket Endpoint (Phase 8)

Real-time activity updates for Graph View visualization.

Protocol:
    Client → Server:
        {"type": "auth", "token": "jwt_token_here"}
        {"type": "ping"}

    Server → Client:
        {"type": "authenticated", "tenant_id": "..."}
        {"type": "error", "message": "..."}
        {"type": "pong"}
        {"type": "agent_processing", "agent_id": 1, "status": "start"|"end", "timestamp": "..."}
        {"type": "skill_used", "agent_id": 1, "skill_type": "web_search", "skill_name": "...", "timestamp": "..."}
        {"type": "kb_used", "agent_id": 1, "doc_count": 3, "chunk_count": 12, "timestamp": "..."}
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from auth_utils import decode_access_token
from services.watcher_activity_service import WatcherActivityService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Watcher WebSocket"])

# Authentication timeout (seconds)
AUTH_TIMEOUT = 10


@dataclass
class AuthResult:
    """Result of WebSocket authentication."""
    user_id: int
    tenant_id: str


async def authenticate_watcher_client(
    websocket: WebSocket,
    timeout: float = AUTH_TIMEOUT
) -> Optional[AuthResult]:
    """
    Wait for authentication message and validate JWT token.

    Protocol:
        Client sends: {"type": "auth", "token": "jwt_token"}
        Server responds: {"type": "authenticated", ...} or {"type": "error", ...}

    Args:
        websocket: WebSocket connection
        timeout: Max time to wait for auth message

    Returns:
        AuthResult if authenticated, None otherwise
    """
    try:
        # Wait for auth message with timeout
        raw_message = await asyncio.wait_for(
            websocket.receive_text(),
            timeout=timeout
        )

        message = json.loads(raw_message)

        if message.get("type") != "auth":
            await websocket.send_json({
                "type": "error",
                "message": "Expected auth message as first message"
            })
            return None

        token = message.get("token")
        if not token:
            await websocket.send_json({
                "type": "error",
                "message": "Missing token"
            })
            return None

        # Validate JWT token
        payload = decode_access_token(token)
        if not payload:
            logger.warning("Watcher activity auth failed: invalid token")
            await websocket.send_json({
                "type": "error",
                "message": "Invalid or expired token"
            })
            return None

        # Extract user_id from token's "sub" claim (standard JWT claim)
        user_id = payload.get("sub") or payload.get("user_id")
        if not user_id:
            await websocket.send_json({
                "type": "error",
                "message": "Invalid token payload"
            })
            return None

        # Convert to int if string
        user_id = int(user_id) if isinstance(user_id, str) else user_id

        # Extract tenant_id from token
        tenant_id = payload.get("tenant_id")
        if not tenant_id:
            # Fallback to "default" for backward compatibility with older tokens
            tenant_id = "default"
            logger.warning(f"Watcher activity: no tenant_id in token, using default")

        return AuthResult(user_id=user_id, tenant_id=tenant_id)

    except asyncio.TimeoutError:
        logger.warning("Watcher activity auth timeout - no auth message received")
        await websocket.send_json({
            "type": "error",
            "message": "Authentication timeout"
        })
        return None

    except Exception as e:
        logger.error(f"Watcher activity auth error: {e}")
        await websocket.send_json({
            "type": "error",
            "message": "Authentication failed"
        })
        return None


@router.websocket("/ws/watcher/activity")
async def watcher_activity_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for real-time Graph View activity updates.

    Provides tenant-scoped activity events:
    - agent_processing: When an agent starts/stops processing a message
    - skill_used: When an agent uses a skill
    - kb_used: When an agent retrieves from knowledge base

    Connection flow:
    1. Client connects
    2. Client sends: {"type": "auth", "token": "jwt_token"}
    3. Server validates token and responds with authenticated or error
    4. Server pushes activity events to client as they occur
    5. Client can send ping messages, server responds with pong
    """
    await websocket.accept()

    tenant_id = None
    user_id = None
    activity_service = WatcherActivityService.get_instance()

    try:
        # Authenticate user
        auth_result = await authenticate_watcher_client(websocket)
        if not auth_result:
            await websocket.close()
            return

        tenant_id = auth_result.tenant_id
        user_id = auth_result.user_id

        # Register connection with activity service
        await activity_service.register_connection(tenant_id, websocket)

        # Send success response
        await websocket.send_json({
            "type": "authenticated",
            "tenant_id": tenant_id,
            "user_id": user_id
        })

        logger.info(f"Watcher activity WebSocket connected: tenant={tenant_id}, user={user_id}")

        # Keep connection alive, handle pings
        while True:
            try:
                data = await websocket.receive_json()

                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.warning(f"Error receiving from watcher client: {e}")
                break

    except WebSocketDisconnect:
        logger.debug(f"Watcher activity WebSocket disconnected: tenant={tenant_id}")

    except Exception as e:
        logger.error(f"Watcher activity WebSocket error: {e}")

    finally:
        # Unregister connection
        if tenant_id:
            activity_service.unregister_connection(tenant_id, websocket)

        logger.info(f"Watcher activity WebSocket cleaned up: tenant={tenant_id}")
