"""
Channel Health Monitor API Routes - Item 38
Provides REST API endpoints for channel health monitoring and circuit breaker management.
Supports WhatsApp, Telegram, Slack, and Discord channels.
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from models_rbac import User
from auth_dependencies import get_current_user_required, get_tenant_context, TenantContext, require_permission

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/channel-health",
    tags=["Channel Health"],
    redirect_slashes=False,
)

# Valid channel types
VALID_CHANNEL_TYPES = {"whatsapp", "telegram", "slack", "discord"}


# ============================================================================
# Pydantic Schemas
# ============================================================================

class CircuitBreakerResponse(BaseModel):
    state: str
    failure_count: int
    success_count: int = 0
    last_failure_at: Optional[str] = None
    opened_at: Optional[str] = None


class ChannelHealthResponse(BaseModel):
    channel_type: str
    instance_id: int
    instance_name: Optional[str] = None
    status: Optional[str] = None
    circuit_breaker: CircuitBreakerResponse


class ChannelHealthListResponse(BaseModel):
    instances: List[ChannelHealthResponse]
    total: int


class ChannelHealthEventResponse(BaseModel):
    id: int
    channel_type: str
    instance_id: int
    event_type: str
    old_state: str
    new_state: str
    reason: Optional[str] = None
    health_status: Optional[str] = None
    latency_ms: Optional[float] = None
    created_at: str

    class Config:
        from_attributes = True


class ChannelHealthEventsListResponse(BaseModel):
    events: List[ChannelHealthEventResponse]
    total: int


class ProbeResultResponse(BaseModel):
    channel_type: str
    instance_id: int
    circuit_breaker: CircuitBreakerResponse
    probed: bool = True
    error: Optional[str] = None


class ResetResultResponse(BaseModel):
    channel_type: str
    instance_id: int
    circuit_breaker: CircuitBreakerResponse
    reset: bool = True


class AlertConfigResponse(BaseModel):
    enabled: bool = False
    webhook_url: Optional[str] = None
    email_recipients: Optional[List[str]] = None
    cooldown_seconds: int = 300


class AlertConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    webhook_url: Optional[str] = None
    email_recipients: Optional[List[str]] = None
    cooldown_seconds: Optional[int] = None


class ChannelHealthSummaryResponse(BaseModel):
    total_instances: int
    healthy: int
    unhealthy: int
    circuit_open: int
    circuit_closed: int
    circuit_half_open: int
    by_channel: Dict[str, Dict[str, int]]


# ============================================================================
# Service accessor
# ============================================================================

def _get_health_service(request: Request = None):
    """Get the ChannelHealthService from app.state. Returns None if not initialized."""
    if request and hasattr(request.app.state, 'channel_health_service'):
        return request.app.state.channel_health_service
    return None


def _validate_channel_type(channel_type: str):
    """Validate channel_type path parameter."""
    if channel_type not in VALID_CHANNEL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid channel type '{channel_type}'. Must be one of: {', '.join(sorted(VALID_CHANNEL_TYPES))}"
        )


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/", response_model=ChannelHealthListResponse)
async def list_channel_health(
    request: Request,
    current_user: User = Depends(get_current_user_required),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """List health status for all channel instances of the current tenant."""
    svc = _get_health_service(request)
    if svc is None:
        raise HTTPException(status_code=503, detail="Channel Health Service not available")

    instances = svc.get_all_health(ctx.tenant_id, ctx.db)
    items = []
    for inst in instances:
        cb_data = inst.get("circuit_breaker", {})
        items.append(ChannelHealthResponse(
            channel_type=inst["channel_type"],
            instance_id=inst["instance_id"],
            instance_name=inst.get("instance_name"),
            status=inst.get("status"),
            circuit_breaker=CircuitBreakerResponse(**cb_data),
        ))

    return ChannelHealthListResponse(instances=items, total=len(items))


@router.get("/summary", response_model=ChannelHealthSummaryResponse)
async def get_health_summary(
    request: Request,
    current_user: User = Depends(get_current_user_required),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get aggregate health summary counts for the current tenant."""
    svc = _get_health_service(request)
    if svc is None:
        raise HTTPException(status_code=503, detail="Channel Health Service not available")

    instances = svc.get_all_health(ctx.tenant_id, ctx.db)

    total = len(instances)
    healthy = 0
    unhealthy = 0
    circuit_open = 0
    circuit_closed = 0
    circuit_half_open = 0
    by_channel: Dict[str, Dict[str, int]] = {}

    for inst in instances:
        ch = inst["channel_type"]
        if ch not in by_channel:
            by_channel[ch] = {"total": 0, "healthy": 0, "unhealthy": 0}
        by_channel[ch]["total"] += 1

        cb_state = inst.get("circuit_breaker", {}).get("state", "closed")

        if cb_state == "closed":
            circuit_closed += 1
            healthy += 1
            by_channel[ch]["healthy"] += 1
        elif cb_state == "open":
            circuit_open += 1
            unhealthy += 1
            by_channel[ch]["unhealthy"] += 1
        elif cb_state == "half_open":
            circuit_half_open += 1
            by_channel[ch]["healthy"] += 1  # Testing recovery, count as transitional

    return ChannelHealthSummaryResponse(
        total_instances=total,
        healthy=healthy,
        unhealthy=unhealthy,
        circuit_open=circuit_open,
        circuit_closed=circuit_closed,
        circuit_half_open=circuit_half_open,
        by_channel=by_channel,
    )


@router.get("/alerts/config", response_model=AlertConfigResponse)
async def get_alert_config(
    current_user: User = Depends(get_current_user_required),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get tenant alert configuration."""
    try:
        from models import ChannelAlertConfig
        config = ctx.db.query(ChannelAlertConfig).filter(
            ChannelAlertConfig.tenant_id == ctx.tenant_id,
        ).first()
        if config:
            return AlertConfigResponse(
                enabled=config.is_enabled,
                webhook_url=config.webhook_url,
                email_recipients=config.email_recipients,
                cooldown_seconds=config.cooldown_seconds or 300,
            )
    except ImportError:
        logger.debug("ChannelAlertConfig model not yet available")
    except Exception as e:
        logger.warning(f"Error loading alert config: {e}")

    # Return defaults
    return AlertConfigResponse()


@router.put("/alerts/config", response_model=AlertConfigResponse)
async def update_alert_config(
    data: AlertConfigUpdate,
    current_user: User = Depends(get_current_user_required),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Update tenant alert configuration."""
    try:
        from models import ChannelAlertConfig
        config = ctx.db.query(ChannelAlertConfig).filter(
            ChannelAlertConfig.tenant_id == ctx.tenant_id,
        ).first()

        if not config:
            config = ChannelAlertConfig(tenant_id=ctx.tenant_id)
            ctx.db.add(config)

        if data.enabled is not None:
            config.is_enabled = data.enabled
        if data.webhook_url is not None:
            # V060-HLT-005 FIX: Prevent SSRF — block file://, cloud metadata IPs,
            # localhost, private ranges, and non-http(s) schemes from webhook URLs.
            if data.webhook_url.strip():
                from utils.ssrf_validator import validate_url, SSRFValidationError
                try:
                    validate_url(data.webhook_url.strip())
                except SSRFValidationError as e:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid webhook URL: {e}",
                    )
                config.webhook_url = data.webhook_url.strip()
            else:
                config.webhook_url = None
        if data.email_recipients is not None:
            config.email_recipients = data.email_recipients
        if data.cooldown_seconds is not None:
            config.cooldown_seconds = data.cooldown_seconds

        ctx.db.commit()

        return AlertConfigResponse(
            enabled=config.is_enabled,
            webhook_url=config.webhook_url,
            email_recipients=config.email_recipients,
            cooldown_seconds=config.cooldown_seconds or 300,
        )
    except ImportError:
        raise HTTPException(status_code=503, detail="ChannelAlertConfig model not yet available")
    except HTTPException:
        # V060-HLT-005: preserve validation errors (e.g., 400 SSRF) instead of
        # downgrading them to 500 via the generic handler below.
        try:
            ctx.db.rollback()
        except Exception:
            pass
        raise
    except Exception as e:
        logger.error(f"Error updating alert config: {e}")
        try:
            ctx.db.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Failed to update alert configuration")


@router.get("/{channel_type}/{instance_id}", response_model=ChannelHealthResponse)
async def get_instance_health(
    channel_type: str,
    instance_id: int,
    request: Request,
    current_user: User = Depends(get_current_user_required),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get health status for a specific channel instance."""
    _validate_channel_type(channel_type)

    svc = _get_health_service(request)
    if svc is None:
        raise HTTPException(status_code=503, detail="Channel Health Service not available")

    # Verify tenant ownership by checking the instance in DB
    instance_name = _verify_instance_ownership(channel_type, instance_id, ctx.tenant_id, ctx.db)

    health = svc.get_instance_health(channel_type, instance_id)
    if health is None:
        # Return default (no probes yet)
        from services.circuit_breaker import CircuitBreaker
        health = {
            "channel_type": channel_type,
            "instance_id": instance_id,
            "circuit_breaker": CircuitBreaker().to_dict(),
        }

    cb_data = health.get("circuit_breaker", {})
    return ChannelHealthResponse(
        channel_type=channel_type,
        instance_id=instance_id,
        instance_name=instance_name,
        circuit_breaker=CircuitBreakerResponse(**cb_data),
    )


@router.get("/{channel_type}/{instance_id}/history", response_model=ChannelHealthEventsListResponse)
async def get_instance_history(
    channel_type: str,
    instance_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user_required),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get paginated health event history for a specific channel instance."""
    _validate_channel_type(channel_type)

    # Verify tenant ownership
    _verify_instance_ownership(channel_type, instance_id, ctx.tenant_id, ctx.db)

    events = []
    total = 0

    try:
        from models import ChannelHealthEvent
        query = ctx.db.query(ChannelHealthEvent).filter(
            ChannelHealthEvent.tenant_id == ctx.tenant_id,
            ChannelHealthEvent.channel_type == channel_type,
            ChannelHealthEvent.instance_id == instance_id,
        ).order_by(ChannelHealthEvent.created_at.desc())

        total = query.count()
        rows = query.offset(offset).limit(limit).all()

        for row in rows:
            events.append(ChannelHealthEventResponse(
                id=row.id,
                channel_type=row.channel_type,
                instance_id=row.instance_id,
                event_type=row.event_type,
                old_state=row.old_state,
                new_state=row.new_state,
                reason=row.reason,
                health_status=row.health_status,
                latency_ms=row.latency_ms,
                created_at=row.created_at.isoformat() if row.created_at else "",
            ))
    except ImportError:
        logger.debug("ChannelHealthEvent model not yet available")
    except Exception as e:
        logger.warning(f"Error querying health events: {e}")

    return ChannelHealthEventsListResponse(events=events, total=total)


@router.post("/{channel_type}/{instance_id}/probe", response_model=ProbeResultResponse)
async def manual_probe(
    channel_type: str,
    instance_id: int,
    request: Request,
    current_user: User = Depends(get_current_user_required),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Manually trigger a health probe for a specific channel instance."""
    _validate_channel_type(channel_type)

    svc = _get_health_service(request)
    if svc is None:
        raise HTTPException(status_code=503, detail="Channel Health Service not available")

    # Verify tenant ownership
    _verify_instance_ownership(channel_type, instance_id, ctx.tenant_id, ctx.db)

    result = await svc.manual_probe(channel_type, instance_id, ctx.tenant_id)

    if "error" in result and result["error"]:
        raise HTTPException(status_code=404, detail=result["error"])

    cb_data = result.get("circuit_breaker", {})
    return ProbeResultResponse(
        channel_type=result["channel_type"],
        instance_id=result["instance_id"],
        circuit_breaker=CircuitBreakerResponse(**cb_data),
        probed=result.get("probed", True),
    )


@router.post("/{channel_type}/{instance_id}/reset", response_model=ResetResultResponse)
async def reset_circuit_breaker(
    channel_type: str,
    instance_id: int,
    request: Request,
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Reset circuit breaker to CLOSED state (admin override)."""
    _validate_channel_type(channel_type)

    svc = _get_health_service(request)
    if svc is None:
        raise HTTPException(status_code=503, detail="Channel Health Service not available")

    # Verify tenant ownership
    _verify_instance_ownership(channel_type, instance_id, ctx.tenant_id, ctx.db)

    result = svc.reset_circuit_breaker(channel_type, instance_id)

    cb_data = result.get("circuit_breaker", {})
    return ResetResultResponse(
        channel_type=result["channel_type"],
        instance_id=result["instance_id"],
        circuit_breaker=CircuitBreakerResponse(**cb_data),
        reset=result.get("reset", True),
    )


# ============================================================================
# Helpers
# ============================================================================

def _verify_instance_ownership(
    channel_type: str, instance_id: int, tenant_id: str, db: Session
) -> Optional[str]:
    """
    Verify that the instance belongs to the given tenant.
    Returns instance display name if found, raises 404 if not.
    """
    from models import WhatsAppMCPInstance, TelegramBotInstance

    if channel_type == "whatsapp":
        inst = db.query(WhatsAppMCPInstance).filter(
            WhatsAppMCPInstance.id == instance_id,
            WhatsAppMCPInstance.tenant_id == tenant_id,
        ).first()
        if not inst:
            raise HTTPException(status_code=404, detail="WhatsApp instance not found")
        return inst.phone_number

    elif channel_type == "telegram":
        inst = db.query(TelegramBotInstance).filter(
            TelegramBotInstance.id == instance_id,
            TelegramBotInstance.tenant_id == tenant_id,
        ).first()
        if not inst:
            raise HTTPException(status_code=404, detail="Telegram instance not found")
        return inst.bot_username

    elif channel_type == "slack":
        try:
            from models import SlackIntegration
            inst = db.query(SlackIntegration).filter(
                SlackIntegration.id == instance_id,
                SlackIntegration.tenant_id == tenant_id,
            ).first()
            if not inst:
                raise HTTPException(status_code=404, detail="Slack instance not found")
            return inst.workspace_name or inst.workspace_id
        except ImportError:
            raise HTTPException(status_code=404, detail="Slack integration not available")

    elif channel_type == "discord":
        try:
            from models import DiscordIntegration
            inst = db.query(DiscordIntegration).filter(
                DiscordIntegration.id == instance_id,
                DiscordIntegration.tenant_id == tenant_id,
            ).first()
            if not inst:
                raise HTTPException(status_code=404, detail="Discord instance not found")
            return inst.application_id
        except ImportError:
            raise HTTPException(status_code=404, detail="Discord integration not available")

    return None
