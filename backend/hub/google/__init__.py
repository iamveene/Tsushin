"""
Google Hub Integration

Provides OAuth and service integrations for:
- Gmail (read-only email access)
- Google Calendar (event management)

Features:
- Multi-account support per tenant
- Per-tenant OAuth credentials (BYOT)
- Per-workspace token encryption
"""

from .oauth_handler import GoogleOAuthHandler, get_google_oauth_handler
from .gmail_service import GmailService
from .calendar_service import CalendarService

__all__ = [
    "GoogleOAuthHandler",
    "get_google_oauth_handler",
    "GmailService",
    "CalendarService",
]
