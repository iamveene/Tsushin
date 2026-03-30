"""
Circuit Breaker Pattern - Item 38
Implements the circuit breaker state machine for channel health monitoring.
States: CLOSED (healthy) -> OPEN (failing) -> HALF_OPEN (testing recovery)
"""

import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 3
    recovery_timeout_seconds: int = 60
    half_open_max_failures: int = 1
    success_threshold: int = 1


@dataclass
class CircuitBreaker:
    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)

    def record_success(self) -> Optional[Tuple[CircuitBreakerState, CircuitBreakerState]]:
        """Record successful probe. Returns (old, new) if transition occurred."""
        old = self.state
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitBreakerState.CLOSED
                self._reset_counters()
                return (old, self.state)
        elif self.state == CircuitBreakerState.CLOSED:
            self.failure_count = 0  # Reset on success
        return None if old == self.state else (old, self.state)

    def record_failure(self, reason: str = "") -> Optional[Tuple[CircuitBreakerState, CircuitBreakerState]]:
        """Record failed probe. Returns (old, new) if transition occurred."""
        old = self.state
        self.last_failure_at = datetime.utcnow()

        if self.state == CircuitBreakerState.CLOSED:
            self.failure_count += 1
            if self.failure_count >= self.config.failure_threshold:
                self.state = CircuitBreakerState.OPEN
                self.opened_at = datetime.utcnow()
                return (old, self.state)
        elif self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.OPEN
            self.opened_at = datetime.utcnow()
            self.success_count = 0
            return (old, self.state)
        return None if old == self.state else (old, self.state)

    def should_probe(self) -> bool:
        """Whether a health probe should be attempted."""
        if self.state == CircuitBreakerState.CLOSED:
            return True
        if self.state == CircuitBreakerState.HALF_OPEN:
            return True
        # OPEN: only probe after recovery timeout
        if self.state == CircuitBreakerState.OPEN and self.opened_at:
            elapsed = (datetime.utcnow() - self.opened_at).total_seconds()
            if elapsed >= self.config.recovery_timeout_seconds:
                self.state = CircuitBreakerState.HALF_OPEN
                self.success_count = 0
                return True
        return False

    def _reset_counters(self):
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_at = None
        self.opened_at = None

    def to_dict(self) -> dict:
        return {
            'state': self.state.value,
            'failure_count': self.failure_count,
            'success_count': self.success_count,
            'last_failure_at': self.last_failure_at.isoformat() if self.last_failure_at else None,
            'opened_at': self.opened_at.isoformat() if self.opened_at else None,
        }

    @classmethod
    def from_db(cls, state_str: str, failure_count: int, opened_at: Optional[datetime],
                config: Optional[CircuitBreakerConfig] = None) -> 'CircuitBreaker':
        try:
            state = CircuitBreakerState(state_str)
        except ValueError:
            state = CircuitBreakerState.CLOSED
        return cls(
            state=state,
            failure_count=failure_count or 0,
            opened_at=opened_at,
            config=config or CircuitBreakerConfig(),
        )
