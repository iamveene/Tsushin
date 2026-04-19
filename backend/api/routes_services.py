"""
Hub Local Services Management Routes

Historically provided endpoints for managing the stack-level `kokoro-tts`
compose container. As of v0.7.0 the legacy compose service and the
`KOKORO_SERVICE_URL` env fallback have been removed — Kokoro now runs as
per-tenant auto-provisioned instances managed via `/api/tts-instances/*`.

The three endpoints below are preserved ONLY to return HTTP 410 Gone with a
helpful pointer to the replacement API, so old clients get a clear migration
message instead of a 404.

Replacement: `/api/tts-instances` + `/api/tts-instances/{id}/container/*`.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
import logging

from models_rbac import User
from auth_dependencies import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/services", tags=["Local Services"])


_GONE_BODY = {
    "error": "gone",
    "message": (
        "The global Kokoro TTS service has been replaced by per-tenant "
        "auto-provisioned instances. Configure one at Hub → Kokoro TTS → "
        "Setup with Wizard."
    ),
    "replacement": "/api/tts-instances",
}

_GONE_HEADERS = {"Link": "</api/tts-instances>; rel=\"successor-version\""}


def _gone_response() -> JSONResponse:
    return JSONResponse(status_code=410, content=_GONE_BODY, headers=_GONE_HEADERS)


# ==================== Kokoro TTS Container Management (DEPRECATED) ====================

@router.post("/kokoro/start")
async def start_kokoro(
    _user: User = Depends(require_permission("org.settings.write")),
):
    """REMOVED in v0.7.0 — returns 410 Gone.

    Use POST /api/tts-instances/{id}/container/start for per-tenant Kokoro
    instances. The stack-level compose `kokoro-tts` service no longer exists.
    """
    return _gone_response()


@router.post("/kokoro/stop")
async def stop_kokoro(
    _user: User = Depends(require_permission("org.settings.write")),
):
    """REMOVED in v0.7.0 — returns 410 Gone.

    Use POST /api/tts-instances/{id}/container/stop for per-tenant Kokoro
    instances. The stack-level compose `kokoro-tts` service no longer exists.
    """
    return _gone_response()


@router.get("/kokoro/status")
async def kokoro_status(
    _user: User = Depends(require_permission("org.settings.read")),
):
    """REMOVED in v0.7.0 — returns 410 Gone.

    Use GET /api/tts-instances/{id}/container/status for per-tenant Kokoro
    instances. The stack-level compose `kokoro-tts` service no longer exists.
    """
    return _gone_response()
