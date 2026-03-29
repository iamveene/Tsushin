"""
Hub Local Services Management Routes

Provides endpoints for managing local service containers (Kokoro TTS, etc.)
via the Docker API. Requires the Docker socket to be mounted in the backend container.

Permissions:
- Start/Stop: org.settings.write
- Status: org.settings.read
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import logging

from db import get_db
from models_rbac import User
from auth_dependencies import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/services", tags=["Local Services"])


# ==================== Kokoro TTS Container Management ====================

@router.post("/kokoro/start")
async def start_kokoro(
    _user: User = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    """Start the Kokoro TTS Docker container."""
    import docker
    try:
        client = docker.from_env()
        containers = client.containers.list(all=True, filters={"name": "kokoro"})
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
    """Stop the Kokoro TTS Docker container."""
    import docker
    try:
        client = docker.from_env()
        containers = client.containers.list(filters={"name": "kokoro"})
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
    """Get Kokoro TTS container status."""
    import docker
    try:
        client = docker.from_env()
        containers = client.containers.list(all=True, filters={"name": "kokoro"})
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
