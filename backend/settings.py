"""
Tsushin Backend Settings
Environment variable management with backward compatibility for legacy names.
"""

import os
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def get_env(new_var: str, old_var: Optional[str] = None, default: Optional[str] = None) -> str:
    """
    Get environment variable with backward compatibility.

    Tries new variable name first (TSN_*), falls back to old name if provided,
    then returns default if neither is set.

    Args:
        new_var: New TSN_* prefixed variable name
        old_var: Legacy variable name (for backward compatibility)
        default: Default value if neither variable is set

    Returns:
        Environment variable value or default
    """
    # Try new variable first
    value = os.getenv(new_var)
    if value is not None:
        return value

    # Fall back to old variable if provided
    if old_var is not None:
        value = os.getenv(old_var)
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

# Database Paths
INTERNAL_DB_PATH = get_env("TSN_INTERNAL_DB_PATH", "INTERNAL_DB_PATH", "./data/agent.db")
MCP_MESSAGES_DB_PATH = get_env("TSN_MCP_MESSAGES_DB_PATH", "MCP_MESSAGES_DB_PATH")

# Data Storage Paths (Phase 4.1 & 6.1)
WORKSPACE_DIR = get_env("TSN_WORKSPACE_DIR", None, "./data/workspace")
CHROMA_DIR = get_env("TSN_CHROMA_DIR", None, "./data/chroma")
BACKUPS_DIR = get_env("TSN_BACKUPS_DIR", None, "./data/backups")

# Logging
LOG_FILE = get_env("TSN_LOG_FILE", "LOG_FILE", "logs/tsushin.log")
LOG_LEVEL = get_env("TSN_LOG_LEVEL", "LOG_LEVEL", "INFO")

# MCP Watcher
POLL_INTERVAL_MS = int(get_env("TSN_POLL_INTERVAL_MS", "POLL_INTERVAL_MS", "3000"))
WHATSAPP_CONVERSATION_DELAY_SECONDS = float(
    get_env("TSN_WHATSAPP_CONVERSATION_DELAY_SECONDS", "WHATSAPP_CONVERSATION_DELAY_SECONDS", "5")
)

# OAuth Token Refresh Worker
OAUTH_REFRESH_POLL_MINUTES = int(
    get_env("TSN_OAUTH_REFRESH_POLL_MINUTES", "OAUTH_REFRESH_POLL_MINUTES", "30")
)
OAUTH_REFRESH_THRESHOLD_HOURS = int(
    get_env("TSN_OAUTH_REFRESH_THRESHOLD_HOURS", "OAUTH_REFRESH_THRESHOLD_HOURS", "24")
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
SERVICE_VERSION = "0.5.0"


def get_log_config() -> dict:
    """
    Get logging configuration with TSN-specific fields.

    Returns structured logging config for JSON formatting.
    """
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "tsushin": {
                "format": "%(asctime)s - [%(name)s] - %(levelname)s - %(message)s",
            },
            "json": {
                # Future: JSON formatter with tsn.run_id, agent.id, etc.
                "format": "%(asctime)s - [%(name)s] - %(levelname)s - %(message)s",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "tsushin",
            },
            "file": {
                "class": "logging.FileHandler",
                "filename": LOG_FILE,
                "formatter": "tsushin",
                "encoding": "utf-8",
            }
        },
        "root": {
            "level": LOG_LEVEL,
            "handlers": ["console", "file"]
        }
    }


# Validation
# Phase 9: MCP_MESSAGES_DB_PATH is now optional - Phase 8 multi-watcher architecture
# manages MCP instances dynamically via WhatsAppMCPInstance table
if not MCP_MESSAGES_DB_PATH:
    import logging
    logging.warning(
        "MCP_MESSAGES_DB_PATH not set. Using Phase 8 multi-watcher architecture. "
        "Legacy single-watcher mode is disabled."
    )


# Create log directory if it doesn't exist
log_dir = Path(LOG_FILE).parent
log_dir.mkdir(parents=True, exist_ok=True)
