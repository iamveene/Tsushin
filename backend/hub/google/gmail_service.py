"""
Gmail Service

Provides Gmail API integration through HubIntegrationBase.
Supports read-only email access for agents.

Features:
- List emails with filtering
- Get specific email content
- Search emails with Gmail query syntax
- List labels

Note: This implementation is read-only. Write operations (send, draft)
are not supported in this version for security.

Required Gmail API Scopes:
- https://www.googleapis.com/auth/gmail.readonly
"""

import base64
import os
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy.orm import Session

from hub.base import (
    HubIntegrationBase,
    IntegrationHealthStatus,
    TokenExpiredError,
    RateLimitError,
)
from hub.security import TokenEncryption
from models import GmailIntegration, OAuthToken, HubIntegration

logger = logging.getLogger(__name__)


class GmailService(HubIntegrationBase):
    """
    Gmail API service.

    Provides read-only email access for agents.
    Each GmailService instance is tied to a specific GmailIntegration.

    Example:
        service = GmailService(db, integration_id)

        # List recent emails
        emails = await service.list_messages(max_results=10)

        # Search emails
        emails = await service.search_messages(query="from:boss@company.com")

        # Get full email content
        email = await service.get_message(message_id)
    """

    # Gmail API base URL
    BASE_URL = "https://gmail.googleapis.com/gmail/v1"

    def __init__(
        self,
        db: Session,
        integration_id: int,
        encryption_key: Optional[str] = None
    ):
        """
        Initialize Gmail service.

        Args:
            db: Database session
            integration_id: GmailIntegration ID
            encryption_key: Token encryption key (defaults to env var)
        """
        super().__init__(db, integration_id)

        if not encryption_key:
            from services.encryption_key_service import get_google_encryption_key
            encryption_key = get_google_encryption_key(db)

        self._encryption_key = encryption_key
        if not self._encryption_key:
            raise ValueError("GOOGLE_ENCRYPTION_KEY not configured in database or environment")

        self._token_encryption = TokenEncryption(self._encryption_key.encode())
        self._integration: Optional[GmailIntegration] = None
        self._metrics = {
            "requests_total": 0,
            "requests_failed": 0,
            "requests_duration_seconds": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
        }

    def _get_integration(self) -> GmailIntegration:
        """Get the Gmail integration."""
        if self._integration is None:
            self._integration = self.db.query(GmailIntegration).filter(
                GmailIntegration.id == self.integration_id
            ).first()

            if not self._integration:
                raise ValueError(f"Gmail integration {self.integration_id} not found")

        return self._integration

    async def _get_access_token(self) -> str:
        """
        Get valid access token, refreshing if needed.

        Returns:
            Valid access token

        Raises:
            TokenExpiredError: If token cannot be refreshed
        """
        integration = self._get_integration()

        # Get token from database
        token = self.db.query(OAuthToken).filter(
            OAuthToken.integration_id == self.integration_id
        ).order_by(OAuthToken.created_at.desc()).first()

        if not token:
            raise TokenExpiredError(f"No token found for integration {self.integration_id}")

        # Check if expired
        now = datetime.utcnow()
        buffer = timedelta(minutes=5)

        if token.expires_at < now + buffer:
            # Need to refresh
            self._log_info("Token expired, refreshing...")
            success = await self.refresh_tokens()
            if not success:
                raise TokenExpiredError("Token refresh failed")

            # Reload token
            token = self.db.query(OAuthToken).filter(
                OAuthToken.integration_id == self.integration_id
            ).order_by(OAuthToken.created_at.desc()).first()

        # Decrypt and return
        return self._token_encryption.decrypt(
            token.access_token_encrypted,
            integration.email_address
        )

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None
    ) -> Dict:
        """
        Make authenticated request to Gmail API.

        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint (relative to BASE_URL)
            params: Query parameters
            json_data: JSON body data

        Returns:
            API response as dict

        Raises:
            TokenExpiredError: If authentication fails
            RateLimitError: If rate limited
        """
        import time
        start_time = time.time()
        self._metrics["requests_total"] += 1

        try:
            access_token = await self._get_access_token()

            url = f"{self.BASE_URL}{endpoint}"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(
                    method,
                    url,
                    params=params,
                    json=json_data,
                    headers=headers
                )

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    self._metrics["requests_failed"] += 1
                    raise RateLimitError(
                        "Gmail API rate limit exceeded",
                        retry_after=retry_after
                    )

                # Handle auth errors
                if response.status_code == 401:
                    self._metrics["requests_failed"] += 1
                    raise TokenExpiredError("Gmail authentication failed")

                response.raise_for_status()

                return response.json()

        except (TokenExpiredError, RateLimitError):
            raise
        except Exception as e:
            self._metrics["requests_failed"] += 1
            self._log_error(f"API request failed: {e}", exc_info=True)
            raise
        finally:
            duration = time.time() - start_time
            self._metrics["requests_duration_seconds"] += duration

    # ========================================
    # Gmail Messages API
    # ========================================

    async def list_messages(
        self,
        max_results: int = 20,
        label_ids: Optional[List[str]] = None,
        include_spam_trash: bool = False
    ) -> List[Dict]:
        """
        List messages in the mailbox.

        Args:
            max_results: Maximum messages to return
            label_ids: Filter by labels (e.g., ["INBOX", "UNREAD"])
            include_spam_trash: Include spam and trash folders

        Returns:
            List of message metadata dicts
        """
        params = {
            "maxResults": max_results,
            "includeSpamTrash": str(include_spam_trash).lower(),
        }

        if label_ids:
            params["labelIds"] = ",".join(label_ids)

        self._log_info(f"Listing messages (max: {max_results})")

        response = await self._make_request(
            "GET",
            "/users/me/messages",
            params=params
        )

        messages = response.get("messages", [])
        self._log_info(f"Found {len(messages)} messages")

        return messages

    async def search_messages(
        self,
        query: str,
        max_results: int = 20,
        include_spam_trash: bool = False
    ) -> List[Dict]:
        """
        Search messages with Gmail query syntax.

        Args:
            query: Gmail search query (e.g., "from:boss@company.com subject:urgent")
            max_results: Maximum messages to return
            include_spam_trash: Include spam and trash

        Returns:
            List of message metadata dicts

        Query Examples:
            - "from:email@example.com" - From specific sender
            - "subject:meeting" - Subject contains "meeting"
            - "is:unread" - Unread messages
            - "after:2025/01/01" - After specific date
            - "has:attachment" - Has attachments
        """
        params = {
            "q": query,
            "maxResults": max_results,
            "includeSpamTrash": str(include_spam_trash).lower(),
        }

        self._log_info(f"Searching messages: {query}")

        response = await self._make_request(
            "GET",
            "/users/me/messages",
            params=params
        )

        messages = response.get("messages", [])
        self._log_info(f"Found {len(messages)} messages for query")

        return messages

    async def get_message(
        self,
        message_id: str,
        format: str = "full"
    ) -> Dict:
        """
        Get a specific message by ID.

        Args:
            message_id: Gmail message ID
            format: "minimal", "metadata", "full", or "raw"

        Returns:
            Message dict with headers, body, etc.
        """
        params = {"format": format}

        self._log_info(f"Getting message {message_id}")

        return await self._make_request(
            "GET",
            f"/users/me/messages/{message_id}",
            params=params
        )

    async def get_message_content(self, message_id: str) -> Dict:
        """
        Get message with parsed content.

        Returns a simplified structure with:
        - subject
        - from
        - to
        - date
        - body_text
        - body_html
        - attachments

        Args:
            message_id: Gmail message ID

        Returns:
            Parsed message dict
        """
        message = await self.get_message(message_id, format="full")

        # Extract headers
        headers = {}
        for header in message.get("payload", {}).get("headers", []):
            name = header.get("name", "").lower()
            if name in ["subject", "from", "to", "date", "cc", "bcc"]:
                headers[name] = header.get("value", "")

        # Extract body
        body_text = ""
        body_html = ""
        attachments = []

        payload = message.get("payload", {})

        def extract_parts(parts):
            nonlocal body_text, body_html, attachments

            for part in parts:
                mime_type = part.get("mimeType", "")
                body = part.get("body", {})

                if "parts" in part:
                    extract_parts(part["parts"])
                elif mime_type == "text/plain":
                    data = body.get("data", "")
                    if data:
                        body_text = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                elif mime_type == "text/html":
                    data = body.get("data", "")
                    if data:
                        body_html = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                elif body.get("attachmentId"):
                    attachments.append({
                        "filename": part.get("filename", "attachment"),
                        "mimeType": mime_type,
                        "size": body.get("size", 0),
                        "attachmentId": body.get("attachmentId"),
                    })

        if "parts" in payload:
            extract_parts(payload["parts"])
        elif payload.get("body", {}).get("data"):
            # Single part message
            data = payload["body"]["data"]
            mime_type = payload.get("mimeType", "text/plain")
            decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            if mime_type == "text/html":
                body_html = decoded
            else:
                body_text = decoded

        return {
            "id": message.get("id"),
            "threadId": message.get("threadId"),
            "subject": headers.get("subject", "(No Subject)"),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "cc": headers.get("cc", ""),
            "date": headers.get("date", ""),
            "body_text": body_text,
            "body_html": body_html,
            "attachments": attachments,
            "labels": message.get("labelIds", []),
            "snippet": message.get("snippet", ""),
        }

    async def list_labels(self) -> List[Dict]:
        """
        List all labels in the mailbox.

        Returns:
            List of label dicts with id, name, type
        """
        self._log_info("Listing labels")

        response = await self._make_request(
            "GET",
            "/users/me/labels"
        )

        return response.get("labels", [])

    async def get_thread(self, thread_id: str) -> Dict:
        """
        Get a full thread with all messages.

        Args:
            thread_id: Gmail thread ID

        Returns:
            Thread dict with all messages
        """
        self._log_info(f"Getting thread {thread_id}")

        return await self._make_request(
            "GET",
            f"/users/me/threads/{thread_id}",
            params={"format": "full"}
        )

    # ========================================
    # HubIntegrationBase Implementation
    # ========================================

    async def check_health(self) -> Dict[str, Any]:
        """Check Gmail API health."""
        try:
            integration = self._get_integration()

            # Try listing labels as health check
            labels = await self.list_labels()

            # Get token expiration
            token = self.db.query(OAuthToken).filter(
                OAuthToken.integration_id == self.integration_id
            ).first()

            token_expires_at = token.expires_at.isoformat() + "Z" if token else None

            return {
                "status": IntegrationHealthStatus.HEALTHY,
                "last_check": datetime.utcnow().isoformat() + "Z",
                "details": {
                    "token_expires_at": token_expires_at,
                    "api_reachable": True,
                    "labels_count": len(labels),
                    "email": integration.email_address,
                },
                "errors": []
            }

        except TokenExpiredError as e:
            return {
                "status": IntegrationHealthStatus.UNAVAILABLE,
                "last_check": datetime.utcnow().isoformat() + "Z",
                "details": {},
                "errors": [str(e)]
            }
        except Exception as e:
            return {
                "status": IntegrationHealthStatus.DEGRADED,
                "last_check": datetime.utcnow().isoformat() + "Z",
                "details": {},
                "errors": [str(e)]
            }

    async def refresh_tokens(self) -> bool:
        """Refresh OAuth tokens."""
        from hub.google.oauth_handler import get_google_oauth_handler

        try:
            integration = self._get_integration()

            # Get tenant_id from base integration
            base = self.db.query(HubIntegration).filter(
                HubIntegration.id == self.integration_id
            ).first()

            if not base or not base.tenant_id:
                self._log_error("Cannot refresh token: tenant_id not found")
                return False

            handler = get_google_oauth_handler(
                self.db,
                base.tenant_id,
                self._encryption_key
            )

            new_token = await handler.refresh_access_token(
                self.integration_id,
                integration.email_address
            )

            return new_token is not None

        except Exception as e:
            self._log_error(f"Token refresh failed: {e}", exc_info=True)
            return False

    async def revoke_access(self) -> None:
        """Revoke OAuth access."""
        from hub.google.oauth_handler import get_google_oauth_handler

        integration = self._get_integration()
        base = self.db.query(HubIntegration).filter(
            HubIntegration.id == self.integration_id
        ).first()

        if base and base.tenant_id:
            handler = get_google_oauth_handler(
                self.db,
                base.tenant_id,
                self._encryption_key
            )
            await handler.disconnect_integration(self.integration_id)
        else:
            # Just delete tokens and deactivate
            self.db.query(OAuthToken).filter(
                OAuthToken.integration_id == self.integration_id
            ).delete()

            if base:
                base.is_active = False

            self.db.commit()

    def get_metrics(self) -> Dict[str, Any]:
        """Get service metrics."""
        integration = self._get_integration()

        # Get token expiration
        token = self.db.query(OAuthToken).filter(
            OAuthToken.integration_id == self.integration_id
        ).first()

        token_expires_in = 0
        if token:
            delta = token.expires_at - datetime.utcnow()
            token_expires_in = max(0, int(delta.total_seconds()))

        return {
            **self._metrics,
            "token_expires_in_seconds": token_expires_in,
            "email": integration.email_address,
        }
