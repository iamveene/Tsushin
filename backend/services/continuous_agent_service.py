"""Continuous-agent backend helpers for v0.7.0 Track A2.

This module intentionally keeps writes narrow: route handlers expose read-only
control-plane APIs in this track, while trigger adapters in later tracks can
reuse these helpers to create wake events/runs and enforce daily budgets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import time
from typing import Any, Optional

from sqlalchemy.orm import Session

from middleware.rate_limiter import SlidingWindowRateLimiter
from models import BudgetPolicy, ContinuousAgent, ContinuousRun, WakeEvent


class BudgetKind(str, Enum):
    RUN = "run"
    AGENTIC_RUN = "agentic_run"
    TOKEN = "token"
    TOOL_INVOCATION = "tool_invocation"


class BudgetDecision(str, Enum):
    ALLOW = "allow"
    PAUSE = "pause"
    DEGRADE_TO_HYBRID = "degrade_to_hybrid"
    NOTIFY_ONLY = "notify_only"


@dataclass(frozen=True)
class BudgetCheckResult:
    allowed: bool
    decision: BudgetDecision
    budget_kind: BudgetKind
    limit: Optional[int]
    remaining: Optional[int]


class ContinuousBudgetLimiter:
    """Daily budget hook keyed by tenant, continuous agent, and budget kind."""

    WINDOW_SECONDS = 24 * 60 * 60

    def __init__(self, limiter: Optional[SlidingWindowRateLimiter] = None):
        self._limiter = limiter or SlidingWindowRateLimiter()

    def check(
        self,
        *,
        tenant_id: str,
        continuous_agent_id: int,
        policy: BudgetPolicy,
        budget_kind: BudgetKind,
        amount: int = 1,
    ) -> BudgetCheckResult:
        limit = self._limit_for(policy, budget_kind)
        if limit is None or limit <= 0:
            return BudgetCheckResult(True, BudgetDecision.ALLOW, budget_kind, limit, None)

        key = f"continuous:{tenant_id}:{continuous_agent_id}"
        allowed = True
        for _ in range(max(1, amount)):
            if not self._limiter.allow(
                key,
                limit,
                self.WINDOW_SECONDS,
                budget_kind=budget_kind.value,
            ):
                allowed = False
                break

        remaining = self._limiter.remaining(
            key,
            limit,
            self.WINDOW_SECONDS,
            budget_kind=budget_kind.value,
        )
        if allowed:
            return BudgetCheckResult(True, BudgetDecision.ALLOW, budget_kind, limit, remaining)

        action = (policy.on_exhaustion or "pause").strip().lower()
        if action == BudgetDecision.DEGRADE_TO_HYBRID.value:
            decision = BudgetDecision.DEGRADE_TO_HYBRID
        elif action == BudgetDecision.NOTIFY_ONLY.value:
            decision = BudgetDecision.NOTIFY_ONLY
        else:
            decision = BudgetDecision.PAUSE
        return BudgetCheckResult(False, decision, budget_kind, limit, remaining)

    @staticmethod
    def _limit_for(policy: BudgetPolicy, budget_kind: BudgetKind) -> Optional[int]:
        if budget_kind == BudgetKind.RUN:
            return policy.max_runs_per_day
        if budget_kind == BudgetKind.AGENTIC_RUN:
            return policy.max_agentic_runs_per_day
        if budget_kind == BudgetKind.TOKEN:
            return policy.max_tokens_per_day
        if budget_kind == BudgetKind.TOOL_INVOCATION:
            return policy.max_tool_invocations_per_day
        return None


budget_limiter = ContinuousBudgetLimiter()


def create_wake_event(
    db: Session,
    *,
    tenant_id: str,
    channel_type: str,
    channel_instance_id: int,
    event_type: str,
    dedupe_key: str,
    occurred_at: Optional[datetime] = None,
    continuous_agent_id: Optional[int] = None,
    continuous_subscription_id: Optional[int] = None,
    importance: str = "normal",
    payload_ref: Optional[str] = None,
    commit: bool = True,
) -> WakeEvent:
    """Create a wake event without inline payload storage.

    payload_ref is expected to point at a redacted local payload file under
    backend/data/wake_events/ or a future blob key. A2 intentionally does not
    expose a payload fetch endpoint.
    """
    event = WakeEvent(
        tenant_id=tenant_id,
        continuous_agent_id=continuous_agent_id,
        continuous_subscription_id=continuous_subscription_id,
        channel_type=channel_type,
        channel_instance_id=channel_instance_id,
        event_type=event_type,
        occurred_at=occurred_at or datetime.utcnow(),
        dedupe_key=dedupe_key,
        importance=importance,
        payload_ref=payload_ref,
        status="pending",
    )
    db.add(event)
    if commit:
        db.commit()
        db.refresh(event)
    return event


def create_continuous_run(
    db: Session,
    *,
    tenant_id: str,
    continuous_agent_id: int,
    wake_event_ids: Optional[list[int]] = None,
    execution_mode: Optional[str] = None,
    status: str = "queued",
    agentic_scratchpad: Optional[Any] = None,
    commit: bool = True,
) -> ContinuousRun:
    agent = db.query(ContinuousAgent).filter(
        ContinuousAgent.id == continuous_agent_id,
        ContinuousAgent.tenant_id == tenant_id,
    ).first()
    if agent is None:
        raise ValueError("continuous_agent not found for tenant")

    run = ContinuousRun(
        tenant_id=tenant_id,
        continuous_agent_id=continuous_agent_id,
        wake_event_ids=wake_event_ids or [],
        execution_mode=execution_mode or agent.execution_mode,
        status=status,
        agentic_scratchpad=agentic_scratchpad,
        run_type="continuous",
    )
    db.add(run)
    if commit:
        db.commit()
        db.refresh(run)
        try:
            from services.watcher_activity_service import emit_continuous_run_async

            emit_continuous_run_async(
                tenant_id=tenant_id,
                continuous_run_id=run.id,
                continuous_agent_id=continuous_agent_id,
                status=run.status,
                wake_event_ids=run.wake_event_ids or [],
            )
        except Exception:
            pass
    return run


def count_runs_today(db: Session, *, tenant_id: str, continuous_agent_id: int) -> int:
    since = datetime.utcnow() - timedelta(days=1)
    return db.query(ContinuousRun).filter(
        ContinuousRun.tenant_id == tenant_id,
        ContinuousRun.continuous_agent_id == continuous_agent_id,
        ContinuousRun.created_at >= since,
    ).count()


async def analyze_continuous_action_approval(
    db: Session,
    *,
    tenant_id: str,
    action_text: str,
    agent_id: Optional[int] = None,
    sender_key: Optional[str] = None,
):
    """Run the bounded Sentinel approval detection for continuous contexts."""
    from services.sentinel_service import SentinelService

    sentinel = SentinelService(db, tenant_id)
    start_time = time.time()
    input_hash = hashlib.sha256(action_text.encode("utf-8")).hexdigest()
    return await sentinel._analyze_single(
        input_content=action_text,
        input_hash=input_hash,
        analysis_type="continuous_agent",
        detection_type="continuous_agent_action_approval",
        config=sentinel.get_effective_config(agent_id),
        sender_key=sender_key,
        message_id=None,
        agent_id=agent_id,
        start_time=start_time,
    )


def continuous_context_from_config(config: dict[str, Any] | None) -> Optional[dict[str, Any]]:
    """Return normalized continuous context only when explicitly present."""
    if not config:
        return None
    raw = config.get("continuous_agent_context") or {}
    if not raw and config.get("run_type") == "continuous":
        raw = config
    if not raw:
        return None
    tenant_id = raw.get("tenant_id") or config.get("tenant_id")
    if not tenant_id:
        return None
    return {
        "tenant_id": tenant_id,
        "agent_id": raw.get("agent_id") or config.get("agent_id"),
        "sender_key": raw.get("sender_key") or config.get("sender_key"),
        "mode": raw.get("mode") or config.get("execution_mode"),
    }
