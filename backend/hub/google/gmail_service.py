"""
Gmail Service

Provides Gmail API integration through HubIntegrationBase.
Supports inbound and outbound email access for agents.

Features:
- List emails with filtering
- Get specific email content
- Search emails with Gmail query syntax
- List labels
- Send emails
- Create drafts
- Reply to existing threads

Required Gmail API Scopes:
- https://www.googleapis.com/auth/gmail.readonly
- https://www.googleapis.com/auth/gmail.send (send/reply)
- https://www.googleapis.com/auth/gmail.compose, gmail.modify, or mail.google.com/ (drafts)
"""

import base64
import logging
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime, getaddresses
from typing import Any, Dict, List, Optional, Sequence
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

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
GMAIL_MODIFY_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
GMAIL_FULL_ACCESS_SCOPE = "https://mail.google.com/"

GMAIL_SEND_COMPATIBLE_SCOPES = frozenset(
    {
        GMAIL_SEND_SCOPE,
        GMAIL_COMPOSE_SCOPE,
        GMAIL_MODIFY_SCOPE,
        GMAIL_FULL_ACCESS_SCOPE,
    }
)
GMAIL_DRAFT_COMPATIBLE_SCOPES = frozenset(
    {
        GMAIL_COMPOSE_SCOPE,
        GMAIL_MODIFY_SCOPE,
        GMAIL_FULL_ACCESS_SCOPE,
    }
)


class InsufficientScopesError(PermissionError):
    """Raised when the stored Gmail OAuth token lacks scopes for the requested action.

    Subclasses PermissionError so legacy `except PermissionError` blocks still
    catch the new typed exception while new code can branch on
    InsufficientScopesError to surface a structured 409 with `missing_scopes`.
    """

    def __init__(self, missing_scopes: List[str], message: str = ""):
        self.missing_scopes = list(missing_scopes)
        super().__init__(message or f"Missing OAuth scopes: {self.missing_scopes}")


class GmailService(HubIntegrationBase):
    """
    Gmail API service.

    Provides inbound and outbound Gmail access for agents.
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
        json_data: Optional[Dict] = None,
        timeout: float = 10.0,
    ) -> Dict:
        """
        Make authenticated request to Gmail API.

        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint (relative to BASE_URL)
            params: Query parameters
            json_data: JSON body data
            timeout: httpx request timeout (seconds). Default 10s — BUG-684:
                was 30s, which caused the DB session to be held for 30s per
                failing call. When `*.googleapis.com` was unreachable, the
                FastAPI worker's `QueuePool` exhausted at ~50 concurrent
                failing calls and the backend deadlocked. 10s is well inside
                normal Gmail latency but caps the blast radius of outages.

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

            async with httpx.AsyncClient(timeout=timeout) as client:
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

    def _get_latest_token(self) -> Optional[OAuthToken]:
        """Return the newest OAuth token row for this integration."""
        return self.db.query(OAuthToken).filter(
            OAuthToken.integration_id == self.integration_id
        ).order_by(OAuthToken.created_at.desc()).first()

    def _get_token_scopes(self) -> set[str]:
        """Return the latest OAuth token scopes as a normalized set."""
        token = self._get_latest_token()
        if not token or not token.scope:
            return set()
        return {scope for scope in token.scope.split() if scope}

    def has_send_scope(self) -> bool:
        """
        Whether the stored OAuth token explicitly includes gmail.send.

        Returns False when the token row is missing or its scope string does not
        mention gmail.send. A missing scope string is treated as unknown and also
        returns False so callers can surface an actionable re-auth hint.
        """
        return GMAIL_SEND_SCOPE in self._get_token_scopes()

    def has_compose_scope(self) -> bool:
        """Whether the stored OAuth token explicitly includes gmail.compose."""
        return GMAIL_COMPOSE_SCOPE in self._get_token_scopes()

    def can_send_messages(self) -> bool:
        """Whether the current Gmail scopes allow users.messages.send."""
        return bool(self._get_token_scopes() & GMAIL_SEND_COMPATIBLE_SCOPES)

    def can_create_drafts(self) -> bool:
        """Whether the current Gmail scopes allow users.drafts.create."""
        return bool(self._get_token_scopes() & GMAIL_DRAFT_COMPATIBLE_SCOPES)

    def _ensure_send_capability(self) -> None:
        """Require a Gmail write scope that supports users.messages.send."""
        if not self.can_send_messages():
            raise InsufficientScopesError(
                missing_scopes=[GMAIL_SEND_SCOPE, GMAIL_COMPOSE_SCOPE],
                message=(
                    "Gmail integration is missing outbound Gmail send permission. "
                    "Re-authorize the integration to enable send and reply operations."
                ),
            )

    def _ensure_draft_capability(self) -> None:
        """Require a Gmail write scope that supports users.drafts.create."""
        if not self.can_create_drafts():
            raise InsufficientScopesError(
                missing_scopes=[GMAIL_COMPOSE_SCOPE],
                message=(
                    "Gmail integration is missing gmail.compose. "
                    "Re-authorize the integration to enable draft creation."
                ),
            )

    @staticmethod
    def _normalize_recipients(recipients: Optional[Sequence[str] | str]) -> List[str]:
        """Normalize a string or sequence of recipients into a clean list."""
        if recipients is None:
            return []
        if isinstance(recipients, str):
            return [item.strip() for item in recipients.split(",") if item.strip()]
        return [str(item).strip() for item in recipients if str(item).strip()]

    @staticmethod
    def _dedupe_recipients(*groups: Sequence[str]) -> List[str]:
        """Merge recipient lists while preserving order and uniqueness."""
        seen = set()
        ordered: List[str] = []
        for group in groups:
            for recipient in group:
                lowered = recipient.lower()
                if lowered in seen:
                    continue
                seen.add(lowered)
                ordered.append(recipient)
        return ordered

    def _build_raw_message(
        self,
        *,
        to: Sequence[str],
        subject: str,
        body_text: str,
        cc: Optional[Sequence[str]] = None,
        bcc: Optional[Sequence[str]] = None,
        body_html: Optional[str] = None,
        thread_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a base64url-encoded MIME message payload for Gmail."""
        integration = self._get_integration()
        recipients = self._normalize_recipients(to)
        if not recipients:
            raise ValueError("At least one recipient is required")

        cc_list = self._normalize_recipients(cc)
        bcc_list = self._normalize_recipients(bcc)

        message = EmailMessage()
        message["From"] = integration.email_address
        message["To"] = ", ".join(recipients)
        message["Subject"] = subject.strip() or "(No Subject)"
        message["Date"] = format_datetime(datetime.now(timezone.utc))

        if cc_list:
            message["Cc"] = ", ".join(cc_list)
        if bcc_list:
            message["Bcc"] = ", ".join(bcc_list)
        if in_reply_to:
            message["In-Reply-To"] = in_reply_to
        if references:
            message["References"] = references

        if body_html:
            message.set_content(body_text or "")
            message.add_alternative(body_html, subtype="html")
        else:
            message.set_content(body_text or "")

        payload: Dict[str, Any] = {
            "raw": base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        }
        if thread_id:
            payload["threadId"] = thread_id
        return payload

    @staticmethod
    def _extract_headers(message: Dict[str, Any]) -> Dict[str, str]:
        """Flatten Gmail payload headers into a lowercase lookup map."""
        headers: Dict[str, str] = {}
        for header in message.get("payload", {}).get("headers", []):
            name = header.get("name", "").lower()
            if name:
                headers[name] = header.get("value", "")
        return headers

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
        all_headers = self._extract_headers(message)
        headers = {
            name: value
            for name, value in all_headers.items()
            if name in ["subject", "from", "to", "date", "cc", "bcc"]
        }

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

    async def send_message(
        self,
        *,
        to: Sequence[str] | str,
        subject: str,
        body_text: str,
        cc: Optional[Sequence[str] | str] = None,
        bcc: Optional[Sequence[str] | str] = None,
        body_html: Optional[str] = None,
        thread_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a Gmail message immediately.

        Raises:
            PermissionError: If the integration lacks a Gmail send-compatible scope.
        """
        self._ensure_send_capability()
        payload = self._build_raw_message(
            to=self._normalize_recipients(to),
            subject=subject,
            body_text=body_text,
            cc=self._normalize_recipients(cc),
            bcc=self._normalize_recipients(bcc),
            body_html=body_html,
            thread_id=thread_id,
            in_reply_to=in_reply_to,
            references=references,
        )

        self._log_info("Sending Gmail message")
        return await self._make_request(
            "POST",
            "/users/me/messages/send",
            json_data=payload,
        )

    async def create_draft(
        self,
        *,
        to: Sequence[str] | str,
        subject: str,
        body_text: str,
        cc: Optional[Sequence[str] | str] = None,
        bcc: Optional[Sequence[str] | str] = None,
        body_html: Optional[str] = None,
        thread_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a Gmail draft without sending it.

        Raises:
            PermissionError: If the integration lacks a Gmail draft-compatible scope.
        """
        self._ensure_draft_capability()
        message_payload = self._build_raw_message(
            to=self._normalize_recipients(to),
            subject=subject,
            body_text=body_text,
            cc=self._normalize_recipients(cc),
            bcc=self._normalize_recipients(bcc),
            body_html=body_html,
            thread_id=thread_id,
            in_reply_to=in_reply_to,
            references=references,
        )

        self._log_info("Creating Gmail draft")
        return await self._make_request(
            "POST",
            "/users/me/drafts",
            json_data={"message": message_payload},
        )

    async def reply_to_message(
        self,
        message_id: str,
        *,
        body_text: str,
        body_html: Optional[str] = None,
        reply_all: bool = False,
        cc: Optional[Sequence[str] | str] = None,
        bcc: Optional[Sequence[str] | str] = None,
    ) -> Dict[str, Any]:
        """
        Reply to an existing Gmail message in-thread.

        Args:
            message_id: Gmail message ID to reply to.
            reply_all: When true, include original To/Cc recipients except the
                connected mailbox itself.

        Raises:
            PermissionError: If the integration lacks a Gmail send-compatible scope.
            ValueError: If the original message is missing reply metadata.
        """
        self._ensure_send_capability()
        original = await self.get_message(message_id, format="full")
        headers = self._extract_headers(original)
        integration_email = self._get_integration().email_address.lower()

        to_recipients = [
            address for _, address in getaddresses([
                headers.get("reply-to") or headers.get("from", "")
            ])
            if address
        ]
        if not to_recipients:
            raise ValueError(f"Could not determine reply recipient for Gmail message {message_id}")

        cc_recipients: List[str] = []
        if reply_all:
            original_to = [address for _, address in getaddresses([headers.get("to", "")]) if address]
            original_cc = [address for _, address in getaddresses([headers.get("cc", "")]) if address]
            cc_recipients = [
                address
                for address in self._dedupe_recipients(original_to, original_cc)
                if address.lower() not in {integration_email, *(addr.lower() for addr in to_recipients)}
            ]

        requested_cc = self._normalize_recipients(cc)
        requested_bcc = self._normalize_recipients(bcc)
        reply_subject = headers.get("subject", "").strip() or "(No Subject)"
        if not reply_subject.lower().startswith("re:"):
            reply_subject = f"Re: {reply_subject}"

        references = " ".join(
            part for part in [
                headers.get("references", "").strip(),
                headers.get("message-id", "").strip(),
            ]
            if part
        ) or None

        return await self.send_message(
            to=to_recipients,
            subject=reply_subject,
            body_text=body_text,
            cc=self._dedupe_recipients(cc_recipients, requested_cc),
            bcc=requested_bcc,
            body_html=body_html,
            thread_id=original.get("threadId"),
            in_reply_to=headers.get("message-id"),
            references=references,
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
                    "send_enabled": self.can_send_messages(),
                    "draft_enabled": self.can_create_drafts(),
                    "send_scope_present": self.has_send_scope(),
                    "compose_scope_present": self.has_compose_scope(),
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
