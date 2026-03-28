"""
Secret Provider Abstraction Layer
Phase: GKE Readiness

Provides a pluggable interface for secret/credential retrieval.
Supports environment variables (default, local dev) and
GCP Secret Manager for GKE deployment.

Usage:
    from services.secret_provider import get_secret_provider
    provider = get_secret_provider()
    value = provider.get_secret("TSN_APP_HOST")
    values = provider.get_secrets(["TSN_APP_HOST", "TSN_APP_PORT"])
"""

import os
import time
import logging
import threading
import concurrent.futures
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Thread-safe TTL cache for GCP Secret Manager
# ---------------------------------------------------------------------------

@dataclass
class _CacheEntry:
    value: Optional[str]
    expires_at: float  # time.monotonic()


class _SecretCache:
    """Thread-safe TTL cache for secret values."""

    def __init__(self, ttl: int):
        self._ttl = ttl
        self._store: Dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Tuple[bool, Optional[str]]:
        """Return (hit, value). Thread-safe."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return False, None
            if time.monotonic() > entry.expires_at:
                del self._store[key]
                return False, None
            return True, entry.value

    def set(self, key: str, value: Optional[str]) -> None:
        """Cache a value with TTL. Thread-safe."""
        with self._lock:
            self._store[key] = _CacheEntry(
                value=value,
                expires_at=time.monotonic() + self._ttl,
            )

    def invalidate(self, key: str) -> None:
        """Remove a single key from the cache."""
        with self._lock:
            self._store.pop(key, None)

    def invalidate_all(self) -> None:
        """Clear the entire cache."""
        with self._lock:
            self._store.clear()


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class SecretProvider(ABC):
    """
    Abstract base class for secret/credential providers.

    All secret retrieval goes through this interface, allowing the
    application to read from environment variables (local) or
    GCP Secret Manager (GKE) without changing application code.
    """

    @abstractmethod
    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Retrieve a single secret by key.

        Args:
            key: Secret key / environment variable name
            default: Default value if secret is not found

        Returns:
            Secret value, or default if not found
        """
        ...

    @abstractmethod
    def get_secrets(self, keys: List[str]) -> Dict[str, Optional[str]]:
        """
        Retrieve multiple secrets at once.

        Args:
            keys: List of secret keys

        Returns:
            Dict mapping each key to its value (None if not found)
        """
        ...


# ---------------------------------------------------------------------------
# Environment Variable Provider — reads from os.environ (current behavior)
# ---------------------------------------------------------------------------

class EnvSecretProvider(SecretProvider):
    """
    Secret provider that reads from environment variables.

    This is the default provider and preserves the exact current behavior
    of os.getenv() calls throughout settings.py and the rest of the app.
    """

    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return os.getenv(key, default)

    def get_secrets(self, keys: List[str]) -> Dict[str, Optional[str]]:
        return {key: os.getenv(key) for key in keys}


# ---------------------------------------------------------------------------
# GCP Secret Manager Provider — production GKE deployment
# ---------------------------------------------------------------------------

class GCPSecretProvider(SecretProvider):
    """
    Secret provider backed by GCP Secret Manager.

    Fetches secrets from GCP Secret Manager with a thread-safe TTL cache
    and falls back to environment variables when a secret is unavailable
    in GCP.  Sensitive keys are warmed into the cache at startup.

    Bootstrap env vars (read directly from os.environ):
        TSN_GCP_PROJECT_ID       — required, hard fail if missing
        TSN_GCP_SECRET_PREFIX    — default "tsushin"
        TSN_GCP_SECRET_VERSION   — default "latest"
        TSN_GCP_SECRET_CACHE_TTL — default 300 (seconds)

    Authentication uses Application Default Credentials (Workload Identity
    on GKE, ``gcloud auth application-default login`` locally).
    """

    SENSITIVE_KEYS = [
        "JWT_SECRET_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY", "GROQ_API_KEY", "GROK_API_KEY",
        "ELEVENLABS_API_KEY", "BRAVE_API", "BRAVE_SEARCH_API_KEY",
        "OPENWEATHER_API_KEY", "AMADEUS_API_KEY", "AMADEUS_API_SECRET",
        "ASANA_ENCRYPTION_KEY", "GOOGLE_SSO_CLIENT_SECRET",
        "DATABASE_URL",
    ]

    def __init__(self):
        # Bootstrap vars — read directly from os.environ (not from provider)
        self._project_id = os.environ["TSN_GCP_PROJECT_ID"]  # hard fail if missing
        self._prefix = os.environ.get("TSN_GCP_SECRET_PREFIX", "tsushin")
        self._version = os.environ.get("TSN_GCP_SECRET_VERSION", "latest")
        ttl = int(os.environ.get("TSN_GCP_SECRET_CACHE_TTL", "300"))
        self._cache = _SecretCache(ttl)

        # Lazy import — only loaded when GCP mode is active
        from google.cloud import secretmanager
        self._client = secretmanager.SecretManagerServiceClient()

        logger.info(
            "GCPSecretProvider: project=%s prefix=%s ttl=%ds",
            self._project_id, self._prefix, ttl,
        )

        # Warm up cache with sensitive keys in parallel
        self._warm_up()

    # -- internal helpers ----------------------------------------------------

    def _secret_name(self, key: str) -> str:
        """Map env var name to GCP Secret Manager resource path."""
        secret_id = f"{self._prefix}_{key.lower()}"
        return f"projects/{self._project_id}/secrets/{secret_id}/versions/{self._version}"

    def _fetch_from_gcp(self, key: str) -> Optional[str]:
        """Fetch a single secret from GCP.  Falls back to env var on error."""
        try:
            response = self._client.access_secret_version(
                name=self._secret_name(key),
            )
            return response.payload.data.decode("utf-8")
        except Exception as e:
            logger.warning("GCP secret fetch failed for %s: %s", key, e)
            return os.environ.get(key)

    def _warm_up(self) -> None:
        """Pre-fetch all sensitive keys in parallel at startup."""
        max_workers = min(10, len(self.SENSITIVE_KEYS))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_key = {
                executor.submit(self._fetch_from_gcp, k): k
                for k in self.SENSITIVE_KEYS
            }
            for future in concurrent.futures.as_completed(future_to_key):
                key = future_to_key[future]
                try:
                    value = future.result()
                except Exception as e:
                    logger.warning("Warm-up failed for %s: %s", key, e)
                    value = None
                # Only cache if we got a real value; leave uncached on failure
                # so get_secret() retries GCP on first access.
                if value is not None:
                    self._cache.set(key, value)
        logger.info("GCPSecretProvider: warmed %d secrets", len(self.SENSITIVE_KEYS))

    # -- public interface ----------------------------------------------------

    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        # 1. Cache hit → return
        hit, value = self._cache.get(key)
        if hit:
            return value if value is not None else default

        # 2. Cache miss → fetch from GCP (includes env-var fallback)
        value = self._fetch_from_gcp(key)
        self._cache.set(key, value)

        # 3. Return value or default
        return value if value is not None else default

    def get_secrets(self, keys: List[str]) -> Dict[str, Optional[str]]:
        results: Dict[str, Optional[str]] = {}
        missing_keys: List[str] = []

        # Check cache first
        for key in keys:
            hit, value = self._cache.get(key)
            if hit:
                results[key] = value
            else:
                missing_keys.append(key)

        # Fetch missing keys in parallel
        if missing_keys:
            max_workers = min(10, len(missing_keys))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_key = {
                    executor.submit(self._fetch_from_gcp, k): k
                    for k in missing_keys
                }
                for future in concurrent.futures.as_completed(future_to_key):
                    key = future_to_key[future]
                    try:
                        value = future.result()
                    except Exception as e:
                        logger.warning("get_secrets failed for %s: %s", key, e)
                        value = os.environ.get(key)
                    self._cache.set(key, value)
                    results[key] = value

        return results


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_provider_instance: Optional[SecretProvider] = None
_provider_lock = threading.Lock()


def get_secret_provider() -> SecretProvider:
    """
    Factory: return the configured secret provider singleton.

    Reads TSN_SECRET_BACKEND env var (directly from os.environ, since
    the provider itself may not be initialized yet):
        - "env" (default) -> EnvSecretProvider
        - "gcp"           -> GCPSecretProvider

    Returns:
        SecretProvider instance
    """
    global _provider_instance
    if _provider_instance is not None:
        return _provider_instance

    with _provider_lock:
        if _provider_instance is not None:
            return _provider_instance

        # Read backend choice directly from os.environ (bootstrap — can't use
        # the provider to read its own config)
        backend = os.environ.get("TSN_SECRET_BACKEND", "env").lower().strip()

        if backend == "env":
            _provider_instance = EnvSecretProvider()
        elif backend == "gcp":
            _provider_instance = GCPSecretProvider()
        else:
            raise ValueError(
                f"Unknown secret backend: '{backend}'. "
                f"Set TSN_SECRET_BACKEND to 'env' or 'gcp'."
            )

        logger.info(f"Secret provider initialized: {backend}")
    return _provider_instance
