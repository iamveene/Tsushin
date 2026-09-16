"""Agent configuration enums / constants — single source of truth."""
from typing import Final, Tuple

MEMORY_ISOLATION_MODES: Final[Tuple[str, ...]] = ("isolated", "shared", "channel_isolated")
DEFAULT_MEMORY_ISOLATION_MODE: Final[str] = "isolated"

# Default IANA timezone used when an agent has no explicit timezone set.
# The platform's primary locale is Brazil (UTC-3). This exists so the agent's
# injected "current time" and relative-reminder parsing ("in 15 minutes") are
# computed in a real local zone instead of the container's UTC — the root cause
# of reminders landing 3 hours late.
DEFAULT_AGENT_TIMEZONE: Final[str] = "America/Sao_Paulo"
