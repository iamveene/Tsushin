"""
v0.6.0 Item 5: Sliding-window rate limiter for vector store operations.

Thread-safe singleton with in-memory counters. Resets on process restart,
which is acceptable for rate limiting (not a security boundary).
"""

import time
import threading
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# Default security config values
DEFAULT_MAX_READS_PER_MINUTE = 30
DEFAULT_MAX_WRITES_PER_MINUTE = 100
DEFAULT_MAX_BATCH_SIZE = 500


class VectorStoreRateLimiter:
    """In-memory sliding-window rate limiter for vector store operations."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._read_windows: Dict[str, List[float]] = {}
                    cls._instance._write_windows: Dict[str, List[float]] = {}
                    cls._instance._window_lock = threading.Lock()
        return cls._instance

    def _cleanup_window(self, window: List[float], window_seconds: int = 60) -> List[float]:
        """Remove entries older than window_seconds."""
        cutoff = time.time() - window_seconds
        return [t for t in window if t > cutoff]

    def check_read(self, instance_id: int, agent_id: int, max_per_minute: int = DEFAULT_MAX_READS_PER_MINUTE) -> bool:
        """Check if a read operation is within rate limits. Returns True if allowed."""
        key = f"read:{instance_id}:{agent_id}"
        return self._check(key, max_per_minute, self._read_windows)

    def check_write(self, instance_id: int, tenant_id: str, max_per_minute: int = DEFAULT_MAX_WRITES_PER_MINUTE) -> bool:
        """Check if a write operation is within rate limits. Returns True if allowed."""
        key = f"write:{instance_id}:{tenant_id}"
        return self._check(key, max_per_minute, self._write_windows)

    def check_batch_size(self, count: int, max_batch: int = DEFAULT_MAX_BATCH_SIZE) -> bool:
        """Check if batch size is within limits. Returns True if allowed."""
        return count <= max_batch

    def _check(self, key: str, max_per_minute: int, windows: Dict[str, List[float]]) -> bool:
        """Core rate check with sliding window."""
        with self._window_lock:
            now = time.time()
            if key not in windows:
                windows[key] = []
            windows[key] = self._cleanup_window(windows[key])
            if len(windows[key]) >= max_per_minute:
                logger.warning(f"Rate limit exceeded: {key} ({len(windows[key])}/{max_per_minute})")
                return False
            windows[key].append(now)
            return True

    def reset(self):
        """Reset all windows (for testing)."""
        with self._window_lock:
            self._read_windows.clear()
            self._write_windows.clear()
