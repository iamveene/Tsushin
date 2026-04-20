"""Agent configuration enums / constants — single source of truth."""
from typing import Final, Tuple

MEMORY_ISOLATION_MODES: Final[Tuple[str, ...]] = ("isolated", "shared", "channel_isolated")
DEFAULT_MEMORY_ISOLATION_MODE: Final[str] = "isolated"
