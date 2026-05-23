"""Browser Automation Recorder — REST + WebSocket endpoints.

REST (authn via Bearer/cookie, authz via flows.write):
    POST   /api/recorder/sessions                    — spawn Chromium, return id + ws_url
    POST   /api/recorder/sessions/{id}/compile       — return preview config_json
    POST   /api/recorder/sessions/{id}/agent         — (v1.1) start Browser-Use loop
    POST   /api/recorder/sessions/{id}/agent/pause   — (v1.1) pause/resume agent
    DELETE /api/recorder/sessions/{id}               — teardown

WebSocket (authn via httpOnly cookie, fallback first-message token):
    /ws/recorder/{session_id}                        — frames out, input in

See `backend/browser_recorder/cdp_relay.py` for the wire protocol.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth_dependencies import (
    TenantContext,
    get_current_user_required,
    get_tenant_context,
    require_permission,
)
from auth_utils import decode_access_token
from browser_recorder import RecordingDriver, get_registry
from browser_recorder.cdp_relay import relay
from models_rbac import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recorder", tags=["recorder"])
ws_router = APIRouter(tags=["Recorder WebSocket"])


# ---------------------------------------------------------------------------
# Engine binding (parallel to other routers; not used yet but keeps the
# convention so a future audit table can hang off the same hook)
# ---------------------------------------------------------------------------

_engine = None


def set_engine(engine) -> None:
    global _engine
    _engine = engine


def _get_db() -> Session:
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    initial_url: Optional[str] = Field(default=None, max_length=2048)
    viewport_width: Optional[int] = Field(default=None, ge=320, le=3840)
    viewport_height: Optional[int] = Field(default=None, ge=240, le=2160)


class CreateSessionResponse(BaseModel):
    session_id: str
    ws_url: str  # relative path; client builds full wss:// from window.location


class CompileResponse(BaseModel):
    config_json: dict
    event_count: int


class StartAgentRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    planner_model: Optional[str] = None
    step_model: Optional[str] = None


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/sessions",
    response_model=CreateSessionResponse,
    status_code=201,
    dependencies=[Depends(require_permission("flows.write"))],
)
async def create_session(
    body: CreateSessionRequest,
    ctx: TenantContext = Depends(get_tenant_context),
) -> CreateSessionResponse:
    """Spawn a Chromium recording session for the current tenant."""
    registry = get_registry()

    viewport = None
    if body.viewport_width and body.viewport_height:
        viewport = {"width": body.viewport_width, "height": body.viewport_height}

    try:
        session = await registry.create(
            tenant_id=ctx.tenant_id or "default",
            user_id=int(ctx.user.id),
            initial_url=body.initial_url,
            viewport=viewport,
        )
    except RuntimeError as e:
        # Concurrency cap exceeded — surface a 409 so the client renders
        # a "discard an existing recording" hint instead of a generic error.
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.exception("Recorder session create failed")
        raise HTTPException(status_code=500, detail=f"Failed to spawn recorder: {e}")

    return CreateSessionResponse(
        session_id=session.session_id,
        ws_url=f"/ws/recorder/{session.session_id}",
    )


@router.post(
    "/sessions/{session_id}/compile",
    response_model=CompileResponse,
    dependencies=[Depends(require_permission("flows.write"))],
)
async def compile_session(
    session_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
) -> CompileResponse:
    """Return a preview of the FlowNode.config_json for the recorded session.

    **Phase 1 stub**: returns the raw event list inside a `_recorder_events`
    field plus a skeletal config_json. Phase 2 swaps in the real compiler
    from `browser_recorder.event_compiler`.
    """
    registry = get_registry()
    session = await registry.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Recording session not found")
    if not ctx.can_access_resource(session.tenant_id):
        raise HTTPException(status_code=404, detail="Recording session not found")

    # Phase 2 will replace this with `from browser_recorder.event_compiler import compile`
    # and feed `session.events`. The output shape below matches what
    # `BrowserAutomationStepHandler` reads — `use_tool_mode`, `mode`, `selectors`,
    # `browser_secret_references`, etc. — so the frontend can wire the Save
    # path now and we only swap the compiler implementation later.
    try:
        from browser_recorder.event_compiler import compile_events  # Phase 2
        config_json = compile_events(session.events)
    except ImportError:
        # Phase 1 fallback — preserves the event stream so we can verify
        # the loop end-to-end before the compiler exists.
        config_json = {
            "use_tool_mode": True,
            "mode": "container",
            "provider_type": "playwright",
            "selectors": [],
            "browser_secret_references": [],
            "timeout_seconds": 60,
            "session_persistence": False,
            "_recorder_events": [
                {"kind": e.kind, "payload": e.payload, "ts": e.ts}
                for e in session.events
            ],
        }

    return CompileResponse(
        config_json=config_json,
        event_count=len(session.events),
    )


@router.get(
    "/sessions/{session_id}/debug",
    dependencies=[Depends(require_permission("flows.write"))],
)
async def debug_session(
    session_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
) -> dict:
    """Introspect a live recording session.

    Returns the raw event stream + agent task state. Intended for
    debugging agentic recordings — gives the UI (and humans) a way to
    surface why an agent stalled without spelunking server logs.
    """
    registry = get_registry()
    session = await registry.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Recording session not found")
    if not ctx.can_access_resource(session.tenant_id):
        raise HTTPException(status_code=404, detail="Recording session not found")
    agent_done = session.agent_task.done() if session.agent_task else None
    agent_exception = None
    if session.agent_task and session.agent_task.done():
        try:
            exc = session.agent_task.exception()
            if exc is not None:
                agent_exception = f"{type(exc).__name__}: {str(exc)[:500]}"
        except (asyncio.CancelledError, Exception):
            pass
    return {
        "session_id": session.session_id,
        "tenant_id": session.tenant_id,
        "current_driver": session.current_driver.value if session.current_driver else None,
        "agent_paused": session.agent_paused,
        "agent_task_done": agent_done,
        "agent_exception": agent_exception,
        "event_count": len(session.events),
        "events": [
            {"kind": e.kind, "payload": e.payload, "ts": e.ts}
            for e in session.events
        ],
    }


@router.delete(
    "/sessions/{session_id}",
    status_code=204,
    dependencies=[Depends(require_permission("flows.write"))],
)
async def delete_session(
    session_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
) -> None:
    registry = get_registry()
    session = await registry.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Recording session not found")
    if not ctx.can_access_resource(session.tenant_id):
        raise HTTPException(status_code=404, detail="Recording session not found")
    await registry.teardown(session_id)


# ---- Phase 6 stubs ---------------------------------------------------------


@router.post(
    "/sessions/{session_id}/agent",
    status_code=202,
    dependencies=[Depends(require_permission("flows.write"))],
)
async def start_agent(
    session_id: str,
    body: StartAgentRequest,
    ctx: TenantContext = Depends(get_tenant_context),
) -> dict:
    """Start a Browser-Use driver against the existing recording session.

    Resolves the Anthropic API key via the tenant's default
    ProviderInstance (same path AIClient uses); returns 501 if browser-use
    isn't installed, 503 if the tenant has no Anthropic key configured.
    """
    registry = get_registry()
    session = await registry.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Recording session not found")
    if not ctx.can_access_resource(session.tenant_id):
        raise HTTPException(status_code=404, detail="Recording session not found")
    try:
        from browser_recorder.agentic_driver import start_agent_loop  # Phase 6
    except ImportError:
        raise HTTPException(status_code=501, detail="Agentic mode not yet enabled")
    try:
        await start_agent_loop(
            session=session,
            prompt=body.prompt,
            tenant_id=session.tenant_id,
            db=ctx.db,
            planner_model=body.planner_model,
            step_model=body.step_model,
        )
    except RuntimeError as e:
        # Tenant missing the Anthropic provider instance / key — surface
        # a specific 503 so the UI can render a "configure Anthropic
        # provider first" hint instead of a generic 500.
        raise HTTPException(status_code=503, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Agentic recorder start failed for session %s", session_id)
        raise HTTPException(
            status_code=500,
            detail=f"Agent start failed: {type(e).__name__}: {str(e)[:300]}",
        )
    return {"status": "started", "driver": RecordingDriver.AGENT.value}


@router.post(
    "/sessions/{session_id}/agent/pause",
    dependencies=[Depends(require_permission("flows.write"))],
)
async def pause_agent(
    session_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
) -> dict:
    registry = get_registry()
    session = await registry.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Recording session not found")
    if not ctx.can_access_resource(session.tenant_id):
        raise HTTPException(status_code=404, detail="Recording session not found")

    session.agent_paused = not session.agent_paused
    # Call Browser-Use's native pause/resume if the agent handle is around.
    # The flag is the source of truth — the native call is a best-effort
    # nudge so the agent yields between steps even if our cooperative
    # on_step_start check missed.
    handle = getattr(session, "agent_handle", None)
    if handle is not None:
        try:
            if session.agent_paused and hasattr(handle, "pause"):
                handle.pause()
            elif (not session.agent_paused) and hasattr(handle, "resume"):
                handle.resume()
        except Exception:
            logger.debug("Native pause/resume call failed for %s", session_id, exc_info=True)
    return {"paused": session.agent_paused}


# ---------------------------------------------------------------------------
# WebSocket endpoint — cookie auth, mirrors watcher_activity_websocket.py
# ---------------------------------------------------------------------------


AUTH_TIMEOUT = 10


async def _authenticate_ws(websocket: WebSocket) -> Optional[dict]:
    """Resolve user/tenant from httpOnly cookie or first-message JWT.

    Mirrors the watcher_activity pattern. Returns a dict with `user_id` and
    `tenant_id` on success; sends an error frame and returns None on failure.
    """
    token = websocket.cookies.get("tsushin_session")

    if not token:
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT)
            msg = json.loads(raw)
        except (asyncio.TimeoutError, json.JSONDecodeError):
            await websocket.send_json({"type": "error", "message": "Authentication required"})
            return None
        if msg.get("type") != "auth":
            await websocket.send_json({"type": "error", "message": "First message must be auth"})
            return None
        token = msg.get("token")

    if not token:
        await websocket.send_json({"type": "error", "message": "Missing token"})
        return None

    payload = decode_access_token(token)
    if not payload:
        await websocket.send_json({"type": "error", "message": "Invalid or expired token"})
        return None

    user_id = payload.get("sub") or payload.get("user_id")
    tenant_id = payload.get("tenant_id")
    if not user_id or not tenant_id:
        await websocket.send_json({"type": "error", "message": "Token missing required claims"})
        return None
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        await websocket.send_json({"type": "error", "message": "Invalid user_id claim"})
        return None

    # Fail-closed user-state check, matching shell_websocket.py. A revoked
    # user with a still-valid JWT must not get a recorder session.
    if _engine is not None:
        from sqlalchemy.orm import sessionmaker
        SessionLocal = sessionmaker(bind=_engine)
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user or not user.is_active or user.deleted_at is not None:
                await websocket.send_json({"type": "error", "message": "Account disabled"})
                return None
            is_global = bool(getattr(user, "is_global_admin", False))
            if (
                not is_global
                and user.tenant_id
                and user.tenant_id != tenant_id
            ):
                await websocket.send_json({"type": "error", "message": "Tenant mismatch"})
                return None
        finally:
            try:
                db.close()
            except Exception:
                pass

    return {"user_id": user_id, "tenant_id": tenant_id}


@ws_router.websocket("/ws/recorder/{session_id}")
async def recorder_websocket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()

    auth = await _authenticate_ws(websocket)
    if not auth:
        await websocket.close(code=4001, reason="Authentication failed")
        return

    registry = get_registry()
    session = await registry.get(session_id)
    if not session:
        await websocket.send_json({"type": "error", "message": "Recording session not found"})
        await websocket.close(code=4404, reason="Session not found")
        return

    # Tenant guard — a valid JWT for tenant A must not reach tenant B's session
    if session.tenant_id != auth["tenant_id"]:
        logger.warning(
            "Recorder WS tenant mismatch: session=%s session_tenant=%s jwt_tenant=%s",
            session_id, session.tenant_id, auth["tenant_id"],
        )
        await websocket.send_json({"type": "error", "message": "Tenant mismatch"})
        await websocket.close(code=4003, reason="Tenant mismatch")
        return

    try:
        await relay(session, websocket)
    except WebSocketDisconnect:
        logger.info("Recorder WS closed cleanly (session=%s)", session_id)
    except Exception:
        logger.exception("Recorder WS relay error (session=%s)", session_id)
        try:
            await websocket.close(code=1011, reason="relay error")
        except Exception:
            pass
