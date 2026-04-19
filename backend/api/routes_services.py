"""
Hub Local Services Management Routes

Provides endpoints for managing local service containers (Kokoro TTS, etc.)
via the Docker API. Requires the Docker socket to be mounted in the backend container.

Permissions:
- Start/Stop: org.settings.write
- Status: org.settings.read

DEPRECATION NOTE (v0.6.0-patch.5):
The /api/services/kokoro/* endpoints target the single stack-level `kokoro-tts`
compose container (named `{TSN_STACK_NAME}-kokoro-tts`). They are preserved for
backward compatibility, but per-tenant Kokoro containers now have their own
auto-provisioning API at `/api/tts-instances/*`. New integrations should use the
TTS Instance routes instead of these endpoints.
"""

import os

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import logging

from db import get_db
from models_rbac import User
from auth_dependencies import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/services", tags=["Local Services"])


def _kokoro_compose_container_name() -> str:
    """Exact container name for the stack-level Kokoro TTS container.

    Matches the naming convention used by docker-compose for the `kokoro-tts`
    service under the configured TSN_STACK_NAME.
    """
    stack_name = (os.getenv("TSN_STACK_NAME") or "tsushin").strip() or "tsushin"
    return f"{stack_name}-kokoro-tts"


def _kokoro_name_filter() -> dict:
    """Docker name filter anchored to exact-match via ^$ regex.

    Peer review A-B1: the previous loose {"name": "kokoro"} filter would match
    ANY container whose name contained 'kokoro', including per-tenant
    auto-provisioned TTS instances (`tsushin-tts-kokoro-*`). Pinning to the
    regex-anchored exact name prevents these legacy endpoints from hijacking a
    tenant container.
    """
    return {"name": f"^{_kokoro_compose_container_name()}$"}


# ==================== Kokoro TTS Container Management ====================

@router.post("/kokoro/start")
async def start_kokoro(
    _user: User = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    """Start the stack-level Kokoro TTS Docker container.

    DEPRECATED: Use POST /api/tts-instances/{id}/container/start for per-tenant
    Kokoro instances. This endpoint only affects the single shared compose-level
    container named `{TSN_STACK_NAME}-kokoro-tts`.
    """
    import docker
    try:
        client = docker.from_env()
        containers = client.containers.list(all=True, filters=_kokoro_name_filter())
        if not containers:
            return {
                "success": False,
                "message": "Kokoro TTS container not found. Start with: docker compose --profile tts up -d",
            }

        container = containers[0]
        if container.status == "running":
            return {"success": True, "message": "Kokoro TTS is already running"}

        container.start()
        return {"success": True, "message": "Kokoro TTS started successfully"}
    except Exception as e:
        logger.exception("Failed to start Kokoro TTS container")
        return {"success": False, "message": f"Failed to start Kokoro: {str(e)}"}


@router.post("/kokoro/stop")
async def stop_kokoro(
    _user: User = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    """Stop the stack-level Kokoro TTS Docker container.

    DEPRECATED: Use POST /api/tts-instances/{id}/container/stop for per-tenant
    Kokoro instances. This endpoint only affects the single shared compose-level
    container named `{TSN_STACK_NAME}-kokoro-tts`.
    """
    import docker
    try:
        client = docker.from_env()
        containers = client.containers.list(filters=_kokoro_name_filter())
        if not containers:
            return {"success": False, "message": "Kokoro TTS is not running"}

        containers[0].stop()
        return {"success": True, "message": "Kokoro TTS stopped"}
    except Exception as e:
        logger.exception("Failed to stop Kokoro TTS container")
        return {"success": False, "message": f"Failed to stop Kokoro: {str(e)}"}


@router.get("/kokoro/status")
async def kokoro_status(
    _user: User = Depends(require_permission("org.settings.read")),
):
    """Get the stack-level Kokoro TTS container status.

    DEPRECATED: Use GET /api/tts-instances/{id}/container/status for per-tenant
    Kokoro instances. This endpoint only affects the single shared compose-level
    container named `{TSN_STACK_NAME}-kokoro-tts`.
    """
    import docker
    try:
        client = docker.from_env()
        containers = client.containers.list(all=True, filters=_kokoro_name_filter())
        if not containers:
            return {"status": "not_installed", "message": "Container not found"}

        c = containers[0]
        return {
            "status": c.status,  # running, exited, created
            "name": c.name,
            "image": c.image.tags[0] if c.image.tags else "unknown",
        }
    except Exception as e:
        logger.exception("Failed to get Kokoro TTS container status")
        return {"status": "error", "message": str(e)}
