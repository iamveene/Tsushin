"""
MCP API Reader - HTTP-based message retrieval

This module provides HTTP-based message retrieval from MCP containers,
bypassing Docker Desktop filesystem sync issues with bind-mounted SQLite databases.

Usage:
    reader = MCPAPIReader(api_url="http://container:8080/api", api_secret="...", contact_mappings={})
    messages = reader.get_new_messages("2026-01-01 00:00:00")
"""

import requests
import logging
from typing import List, Dict, Optional
from datetime import datetime

from services.mcp_auth_service import get_auth_headers


class MCPAPIReader:
    """
    Reads messages from MCP container via HTTP API.

    This bypasses the gRPC-FUSE filesystem sync issues on Docker Desktop macOS
    by fetching messages directly from the container's HTTP API instead of
    reading from bind-mounted SQLite files.
    """

    def __init__(
        self,
        api_url: str,
        contact_mappings: Dict = None,
        timeout: int = 10,
        api_secret: Optional[str] = None
    ):
        """
        Initialize the API reader.

        Args:
            api_url: Base API URL (e.g., "http://mcp-container:8080/api")
            contact_mappings: Dict mapping phone numbers to contact names
            timeout: HTTP request timeout in seconds
            api_secret: API authentication secret (Phase Security-1)
        """
        self.api_url = api_url.rstrip('/')
        self.contact_mappings = contact_mappings or {}
        self.timeout = timeout
        self.api_secret = api_secret
        self.logger = logging.getLogger(__name__)

    def get_new_messages(self, last_timestamp: str, limit: int = 500) -> List[Dict]:
        """
        Fetch new messages since last_timestamp via HTTP API.

        Args:
            last_timestamp: ISO format timestamp string
            limit: Maximum number of messages to return

        Returns:
            List of normalized message dicts compatible with watcher expectations
        """
        try:
            # Build request URL
            url = f"{self.api_url}/messages"
            params = {
                "since": last_timestamp,
                "limit": min(limit, 500)  # API max is 500
            }

            self.logger.debug(f"Fetching messages from {url} since {last_timestamp}")

            # Phase Security-1: Add authentication header
            headers = get_auth_headers(self.api_secret)
            response = requests.get(url, params=params, headers=headers, timeout=self.timeout)
            response.raise_for_status()

            data = response.json()

            if not data.get("success"):
                self.logger.error(f"API returned error: {data.get('error', 'Unknown error')}")
                return []

            raw_messages = data.get("messages") or []
            self.logger.debug(f"API returned {len(raw_messages)} messages")

            # Normalize to expected format
            messages = []
            for msg in raw_messages:
                # Get sender name from contact_mappings
                sender_id = msg.get("sender", "")
                sender_name = None

                for contact_id, name in self.contact_mappings.items():
                    norm_contact = contact_id.lstrip("+")
                    norm_sender = sender_id.lstrip("+")
                    if norm_contact == norm_sender:
                        sender_name = name
                        break

                # Determine if group chat
                chat_jid = msg.get("chat_jid", "")
                is_group = 1 if "@g.us" in chat_jid else 0

                # Map to expected format (same as SQLite reader output)
                messages.append({
                    "id": msg.get("id"),
                    "chat_id": chat_jid,
                    "chat_jid": chat_jid,
                    "chat_name": msg.get("chat_name"),
                    "sender": sender_id,
                    "sender_name": sender_name,
                    "body": msg.get("content", ""),
                    "timestamp": msg.get("timestamp"),
                    "is_group": is_group,
                    "media_type": msg.get("media_type"),
                    "filename": msg.get("filename"),
                    "media_url": msg.get("media_url"),
                    "channel": "whatsapp"
                })

            return messages

        except requests.exceptions.Timeout:
            self.logger.warning(f"Timeout fetching messages from MCP API: {self.api_url}")
            return []
        except requests.exceptions.ConnectionError as e:
            self.logger.warning(f"Connection error to MCP API: {e}")
            return []
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching messages from MCP API: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Unexpected error in MCP API reader: {e}", exc_info=True)
            return []

    def get_latest_timestamp(self) -> str:
        """
        Get the most recent message timestamp via API.

        Returns:
            Timestamp string in ISO format, or "1970-01-01 00:00:00" if empty

        Raises:
            Exception if API is unreachable (to prevent historical message flood)
        """
        try:
            # Use the /messages/latest endpoint to get the most recent timestamp
            url = f"{self.api_url}/messages/latest"

            # Phase Security-1: Add authentication header
            headers = get_auth_headers(self.api_secret)
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()

            data = response.json()

            if not data.get("success"):
                raise Exception(f"API error: {data.get('error', 'Unknown')}")

            timestamp = data.get("latest_timestamp")

            if not timestamp:
                self.logger.info("No messages found via API, using default timestamp")
                return "1970-01-01 00:00:00"

            self.logger.info(f"Got latest timestamp from API: {timestamp}")
            return timestamp

        except Exception as e:
            self.logger.error(f"CRITICAL: Failed to get latest timestamp from API: {e}")
            raise

    def get_recent_messages(
        self,
        chat_id: str,
        before_timestamp: str,
        limit: int = 5
    ) -> List[Dict]:
        """
        Get recent messages from a specific chat.

        Note: This method requires a specific endpoint that may not be implemented.
        For now, returns empty list as fallback.

        Args:
            chat_id: The chat identifier (chat_jid)
            before_timestamp: Get messages before this timestamp
            limit: Maximum number of messages to return

        Returns:
            List of message dicts with timestamp, sender_name, body
        """
        # TODO: Implement a /api/messages/chat endpoint for this functionality
        # For now, this is used for group context which is optional
        self.logger.debug(f"get_recent_messages not fully implemented for API reader")
        return []

    def is_available(self) -> bool:
        """
        Check if the MCP API is reachable.

        Returns:
            True if API health check succeeds, False otherwise
        """
        try:
            response = requests.get(
                f"{self.api_url}/health",
                timeout=5
            )
            return response.status_code == 200
        except:
            return False
