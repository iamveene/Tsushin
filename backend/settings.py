"""
Tsushin Backend Settings
Environment variable management with backward compatibility for legacy names.

Secret retrieval is routed through the SecretProvider abstraction so the
application can transparently switch between environment variables (default)
and external secret stores (e.g. GCP Secret Manager) via TSN_SECRET_BACKEND.
"""

import os
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables (must happen before provider init so .env
# values are visible to os.environ)
load_dotenv()

from services.secret_provider import get_secret_provider

# Initialize the secret provider singleton.  For the default EnvSecretProvider
# this is a no-op wrapper around os.getenv; for GCP it would fetch from
# Secret Manager.
_secret_provider = get_secret_provider()


def get_env(new_var: str, old_var: Optional[str] = None, default: Optional[str] = None) -> str:
    """
    Get environment variable with backward compatibility.

    Tries new variable name first (TSN_*), falls back to old name if provided,
    then returns default if neither is set.

    Retrieval is routed through the configured SecretProvider so that the same
    code works whether secrets live in .env files or an external vault.

    Args:
        new_var: New TSN_* prefixed variable name
        old_var: Legacy variable name (for backward compatibility)
        default: Default value if neither variable is set

    Returns:
        Environment variable value or default
    """
    # Try new variable first
    value = _secret_provider.get_secret(new_var)
    if value is not None:
        return value

    # Fall back to old variable if provided
    if old_var is not None:
        value = _secret_provider.get_secret(old_var)
        if value is not None:
            return value

    # Return default
    return default if default is not None else ""


# Application Configuration
APP_HOST = get_env("TSN_APP_HOST", "APP_HOST", "127.0.0.1")
APP_PORT = int(get_env("TSN_APP_PORT", "APP_PORT", "8081"))

# URL Configuration (for OAuth callbacks, redirects, etc.)
# These should be set in production to the actual URLs
BACKEND_URL = get_env("TSN_BACKEND_URL", "BACKEND_URL", f"http://{APP_HOST}:{APP_PORT}")
FRONTEND_URL = get_env("TSN_FRONTEND_URL", "FRONTEND_URL", "http://localhost:3030")

# Public Ingress Resolver (v0.6.1) — developer escape hatch. When set, the
# resolver uses this URL when no tenant override is configured and no
# platform tunnel is running. Also flips the tenant-override validator into
# dev mode so http:// overrides are accepted. MUST NOT be set in production.
DEV_PUBLIC_BASE_URL: Optional[str] = (
    get_env("TSN_DEV_PUBLIC_BASE_URL", "TSUSHIN_DEV_PUBLIC_BASE_URL", "") or None
)

# Google OAuth Configuration (for Gmail/Calendar integrations)
GOOGLE_OAUTH_REDIRECT_URI = get_env(
    "TSN_GOOGLE_OAUTH_REDIRECT_URI",
    "GOOGLE_OAUTH_REDIRECT_URI",
    f"{BACKEND_URL}/api/hub/google/oauth/callback"
)

# Google SSO Configuration (for user authentication)
GOOGLE_SSO_CLIENT_ID = get_env("TSN_GOOGLE_SSO_CLIENT_ID", "GOOGLE_SSO_CLIENT_ID", "")
GOOGLE_SSO_CLIENT_SECRET = get_env("TSN_GOOGLE_SSO_CLIENT_SECRET", "GOOGLE_SSO_CLIENT_SECRET", "")
GOOGLE_SSO_REDIRECT_URI = get_env(
    "TSN_GOOGLE_SSO_REDIRECT_URI",
    "GOOGLE_SSO_REDIRECT_URI",
    f"{BACKEND_URL}/api/auth/google/callback"
)

# Database
INTERNAL_DB_PATH = get_env("TSN_INTERNAL_DB_PATH", "INTERNAL_DB_PATH", "./data/agent.db")
DATABASE_URL = get_env("DATABASE_URL", None, f"sqlite:///{INTERNAL_DB_PATH}")
MCP_MESSAGES_DB_PATH = get_env("TSN_MCP_MESSAGES_DB_PATH", "MCP_MESSAGES_DB_PATH")
DB_IDLE_IN_TRANSACTION_TIMEOUT_MS = int(
    get_env("TSN_DB_IDLE_IN_TRANSACTION_TIMEOUT_MS", None, "15000")
)

# Data Storage Paths (Phase 4.1 & 6.1)
WORKSPACE_DIR = get_env("TSN_WORKSPACE_DIR", None, "./data/workspace")
CHROMA_DIR = get_env("TSN_CHROMA_DIR", None, "./data/chroma")
BACKUPS_DIR = get_env("TSN_BACKUPS_DIR", None, "./data/backups")

# Logging
LOG_FILE = get_env("TSN_LOG_FILE", "LOG_FILE", "logs/tsushin.log")
LOG_LEVEL = get_env("TSN_LOG_LEVEL", "LOG_LEVEL", "INFO")
LOG_FORMAT = get_env("TSN_LOG_FORMAT", None, "text")  # text | json

# MCP Watcher
POLL_INTERVAL_MS = int(get_env("TSN_POLL_INTERVAL_MS", "POLL_INTERVAL_MS", "1000"))
WHATSAPP_CONVERSATION_DELAY_SECONDS = float(
    get_env("TSN_WHATSAPP_CONVERSATION_DELAY_SECONDS", "WHATSAPP_CONVERSATION_DELAY_SECONDS", "1")
)
WATCHER_MAX_CATCHUP_SECONDS = int(
    get_env("TSN_WATCHER_MAX_CATCHUP_SECONDS", "WATCHER_MAX_CATCHUP_SECONDS", "300")
)

# OAuth Token Refresh Worker
OAUTH_REFRESH_POLL_MINUTES = int(
    get_env("TSN_OAUTH_REFRESH_POLL_MINUTES", "OAUTH_REFRESH_POLL_MINUTES", "30")
)
OAUTH_REFRESH_THRESHOLD_HOURS = int(
    get_env("TSN_OAUTH_REFRESH_THRESHOLD_HOURS", "OAUTH_REFRESH_THRESHOLD_HOURS", "24")
)
OAUTH_REFRESH_MAX_RETRIES = int(
    get_env("TSN_OAUTH_REFRESH_MAX_RETRIES", None, "3")
)
OAUTH_REFRESH_RETRY_DELAY = int(
    get_env("TSN_OAUTH_REFRESH_RETRY_DELAY", None, "5")  # seconds, base for exponential backoff
)

# Stale Flow Cleanup Service (Phase 19 - BUG-FLOWS-002)
STALE_FLOW_THRESHOLD_SECONDS = int(
    get_env("TSN_STALE_FLOW_THRESHOLD_SECONDS", None, "7200")  # 2 hours
)
STALE_FLOW_CHECK_INTERVAL_SECONDS = int(
    get_env("TSN_STALE_FLOW_CHECK_INTERVAL_SECONDS", None, "300")  # 5 minutes
)
STALE_CONVERSATION_THRESHOLD_SECONDS = int(
    get_env("TSN_STALE_CONVERSATION_THRESHOLD_SECONDS", None, "3600")  # 1 hour
)

# Service Identification (Phase 3)
SERVICE_NAME = "tsn-core"
SERVICE_VERSION = "0.7.0"

# Observability — Prometheus
METRICS_ENABLED = get_env("TSN_METRICS_ENABLED", None, "true").lower() in ("true", "1", "yes")

# GCP Secret Manager (when TSN_SECRET_BACKEND=gcp)
GCP_PROJECT_ID = os.environ.get("TSN_GCP_PROJECT_ID", "")
GCP_SECRET_PREFIX = os.environ.get("TSN_GCP_SECRET_PREFIX", "tsushin")
GCP_SECRET_CACHE_TTL = int(os.environ.get("TSN_GCP_SECRET_CACHE_TTL", "300"))

# Kubernetes Runtime (Phase GKE — only used when TSN_CONTAINER_RUNTIME=kubernetes)
K8S_NAMESPACE = get_env("TSN_K8S_NAMESPACE", None, "tsushin")
K8S_IMAGE_PULL_POLICY = get_env("TSN_K8S_IMAGE_PULL_POLICY", None, "IfNotPresent")


def get_log_config() -> dict:
    """
    Get logging configuration with TSN-specific fields.

    When TSN_LOG_FORMAT=json, uses JsonFormatter for structured output.
    Default (text) preserves the existing human-readable format.
    """
    use_json = LOG_FORMAT.lower() == "json"
    formatter_name = "json" if use_json else "tsushin"

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "tsushin": {
                "format": "%(asctime)s - [%(name)s] - %(levelname)s - %(message)s",
            },
            "json": {
                "()": "services.logging_service.JsonFormatter",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": formatter_name,
            },
            "file": {
                "class": "logging.FileHandler",
                "filename": LOG_FILE,
                "formatter": formatter_name,
                "encoding": "utf-8",
            }
        },
        "root": {
            "level": LOG_LEVEL,
            "handlers": ["console", "file"]
        }
    }
    return config


# Validation
# Phase 9: MCP_MESSAGES_DB_PATH is now optional - Phase 8 multi-watcher architecture
# manages MCP instances dynamically via WhatsAppMCPInstance table
if not MCP_MESSAGES_DB_PATH:
    import logging
    logging.warning(
        "MCP_MESSAGES_DB_PATH not set. Using Phase 8 multi-watcher architecture. "
        "Legacy single-watcher mode is disabled."
    )


# Item 38: Channel Health Monitor
CHANNEL_HEALTH_CHECK_INTERVAL = int(get_env("TSN_CHANNEL_HEALTH_CHECK_INTERVAL", None, "30"))
CHANNEL_CB_FAILURE_THRESHOLD = int(get_env("TSN_CHANNEL_CB_FAILURE_THRESHOLD", None, "3"))
CHANNEL_CB_RECOVERY_TIMEOUT = int(get_env("TSN_CHANNEL_CB_RECOVERY_TIMEOUT", None, "60"))
CHANNEL_HEALTH_ENABLED = get_env("TSN_CHANNEL_HEALTH_ENABLED", None, "true").lower() in ("true", "1", "yes")


# Create log directory if it doesn't exist
log_dir = Path(LOG_FILE).parent
log_dir.mkdir(parents=True, exist_ok=True)
