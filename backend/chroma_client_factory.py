"""Process-wide ChromaDB PersistentClient factory.

ChromaDB enforces a process-level singleton per filesystem path. If two call
sites open ``PersistentClient(path=...)`` with different ``Settings`` objects,
the second open raises::

    ValueError: An instance of Chroma already exists for <path> with different settings.

This module is the single canonical entry point for opening a Chroma client.
All callers use ``get_chroma_client(path)`` which returns a cached client per
path with a single shared ``Settings`` instance, eliminating the conflict
(BUG-695).
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict

import chromadb
from chromadb.config import Settings


logger = logging.getLogger(__name__)


# Single shared Settings instance for every Chroma client in the process.
# allow_reset=True is the union of what individual call sites previously
# requested; anonymized_telemetry=False matches the prior most-restrictive
# setting. Adding any new field here is a breaking change for already-cached
# clients in the same process and must be coordinated with a process restart.
_SHARED_SETTINGS: Settings = Settings(
    anonymized_telemetry=False,
    allow_reset=True,
)


_clients: Dict[str, chromadb.api.client.Client] = {}
_lock = threading.Lock()


def get_chroma_client(path: str) -> chromadb.api.client.Client:
    """Return the cached PersistentClient for ``path``, creating it once.

    Thread-safe. Idempotent: every call for the same path returns the same
    client object, with the same ``Settings`` instance. Different paths get
    different clients (Chroma's singleton guard is per-path, not global).

    Args:
        path: Filesystem path passed to ``chromadb.PersistentClient(path=...)``.

    Returns:
        The shared ``chromadb.api.client.Client`` for that path.

    Raises:
        ValueError / RuntimeError if Chroma itself rejects the open (e.g.,
        permissions, corrupt index) — pass the exception through unchanged.
    """
    cached = _clients.get(path)
    if cached is not None:
        return cached
    with _lock:
        cached = _clients.get(path)
        if cached is not None:
            return cached
        logger.info("Initializing ChromaDB PersistentClient for path=%s", path)
        client = chromadb.PersistentClient(path=path, settings=_SHARED_SETTINGS)
        _clients[path] = client
        return client


def reset_cache() -> None:
    """Clear the cache. Intended for tests only."""
    with _lock:
        _clients.clear()


def cached_paths() -> list[str]:
    """Return the list of paths currently held in the cache (test/debug aid)."""
    with _lock:
        return list(_clients.keys())


__all__ = ["get_chroma_client", "reset_cache", "cached_paths"]
