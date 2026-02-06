#!/usr/bin/env python
"""MCP Client to send messages back to WhatsApp (Async - Phase 6.11.1)

Enhanced with:
- Retry logic with exponential backoff for transient failures
- Health check before sending to avoid timeouts
- Better error handling for keepalive timeout scenarios
- API authentication (Phase Security-1: SSRF Prevention)
"""
import httpx
import logging
import asyncio
from typing import Optional, List, Tuple, Dict

logger = logging.getLogger(__name__)

# WhatsApp message character limit (safe limit, actual is ~4096)
# BUG FIX 2026-01-17: Reduced from 3800 to 2500 to avoid WhatsApp bridge truncation issues
# Empirical testing shows messages around 2800-3000 chars get truncated mid-word
WHATSAPP_MAX_MESSAGE_LENGTH = 2500

# Retry configuration for handling keepalive timeouts
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 2.0  # seconds
MAX_RETRY_DELAY = 16.0  # seconds
HEALTH_CHECK_TIMEOUT = 5.0  # seconds


class MCPSender:
    """Client to send messages via WhatsApp bridge API (async)

    Features:
    - Automatic retry with exponential backoff for transient failures
    - Health check before sending to detect unhealthy connections early
    - Graceful degradation when MCP container is unavailable
    """

    def __init__(self, api_url: Optional[str] = None, api_secret: Optional[str] = None):
        """
        Initialize MCP sender

        Args:
            api_url: Optional MCP API URL (e.g., http://127.0.0.1:8080/api)
                    If not provided, must be specified per-message via send_message()
            api_secret: Optional API authentication secret (Phase Security-1)
                    If not provided, must be specified per-message via send_message()

        Phase 8: Support dynamic URLs for multi-tenant MCP instances
        """
        self.api_url = api_url
        self.api_secret = api_secret
        self.client = httpx.AsyncClient(timeout=60.0)  # Increased from 30s to handle slow responses
        self._health_cache: dict = {}  # Cache health status to avoid repeated checks
        self._health_cache_ttl = 10.0  # seconds
        self._last_health_check: dict = {}  # Track last health check time per URL
        # Phase Security-1: Cache for auth secrets per URL
        self._auth_secrets: Dict[str, str] = {}

    async def check_health(self, api_url: Optional[str] = None) -> Tuple[bool, dict]:
        """
        Check if the MCP API is healthy and connected to WhatsApp.

        Args:
            api_url: Optional API URL (uses instance URL if not provided)

        Returns:
            Tuple of (is_healthy, health_data)
        """
        target_url = api_url or self.api_url
        if not target_url:
            return False, {"error": "No API URL"}

        # Check cache first
        import time
        cache_key = target_url
        cached = self._health_cache.get(cache_key)
        last_check = self._last_health_check.get(cache_key, 0)

        if cached and (time.time() - last_check) < self._health_cache_ttl:
            return cached.get('healthy', False), cached

        try:
            response = await self.client.get(
                f"{target_url}/health",
                timeout=HEALTH_CHECK_TIMEOUT
            )

            if response.status_code == 200:
                data = response.json()
                is_healthy = data.get('connected', False) and data.get('authenticated', False)

                # Check for reconnection issues
                reconnect_attempts = data.get('reconnect_attempts', 0)
                is_reconnecting = data.get('is_reconnecting', False)

                if reconnect_attempts >= 3 or is_reconnecting:
                    logger.warning(
                        f"MCP API at {target_url} is unstable: "
                        f"reconnect_attempts={reconnect_attempts}, is_reconnecting={is_reconnecting}"
                    )
                    is_healthy = False

                data['healthy'] = is_healthy
                self._health_cache[cache_key] = data
                self._last_health_check[cache_key] = time.time()
                return is_healthy, data
            else:
                logger.warning(f"Health check failed for {target_url}: HTTP {response.status_code}")
                return False, {"error": f"HTTP {response.status_code}"}

        except httpx.TimeoutException:
            logger.warning(f"Health check timeout for {target_url}")
            return False, {"error": "timeout"}
        except Exception as e:
            logger.warning(f"Health check error for {target_url}: {e}")
            return False, {"error": str(e)}

    def _get_auth_headers(self, api_secret: Optional[str] = None) -> Dict[str, str]:
        """
        Get authentication headers for MCP API requests.

        Args:
            api_secret: Optional secret to use (overrides instance secret)

        Returns:
            Dict with authorization header, or empty dict if no secret
        """
        secret = api_secret or self.api_secret
        headers = {"Content-Type": "application/json"}
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        return headers

    async def _send_with_retry(
        self,
        target_url: str,
        payload: dict,
        max_retries: int = MAX_RETRIES,
        api_secret: Optional[str] = None
    ) -> Tuple[bool, Optional[dict]]:
        """
        Send a message with exponential backoff retry.

        Args:
            target_url: MCP API URL
            payload: Message payload
            max_retries: Maximum number of retry attempts
            api_secret: Optional API authentication secret (Phase Security-1)

        Returns:
            Tuple of (success, response_data)
        """
        delay = INITIAL_RETRY_DELAY
        last_error = None

        # Phase Security-1: Add authentication header
        headers = self._get_auth_headers(api_secret)

        for attempt in range(max_retries):
            try:
                response = await self.client.post(
                    f"{target_url}/send",
                    json=payload,
                    headers=headers
                )

                if response.status_code == 200:
                    result = response.json()
                    if result.get("success", False):
                        return True, result
                    else:
                        # API returned error but request succeeded - don't retry
                        return False, result
                elif response.status_code >= 500:
                    # Server error - retry
                    last_error = f"HTTP {response.status_code}"
                    logger.warning(f"Send attempt {attempt + 1}/{max_retries} failed: {last_error}")
                else:
                    # Client error - don't retry
                    return False, {"error": f"HTTP {response.status_code}"}

            except httpx.TimeoutException as e:
                last_error = f"timeout: {e}"
                logger.warning(f"Send attempt {attempt + 1}/{max_retries} timed out")

                # Clear health cache on timeout - connection may be unstable
                self._health_cache.pop(target_url, None)

            except httpx.ConnectError as e:
                last_error = f"connection error: {e}"
                logger.warning(f"Send attempt {attempt + 1}/{max_retries} connection failed")

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Send attempt {attempt + 1}/{max_retries} failed: {e}")

            # Wait before retrying (exponential backoff)
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {delay}s...")
                await asyncio.sleep(delay)
                delay = min(delay * 2, MAX_RETRY_DELAY)

        logger.error(f"All {max_retries} send attempts failed. Last error: {last_error}")
        return False, {"error": last_error}

    def _split_message(self, message: str, max_length: int = WHATSAPP_MAX_MESSAGE_LENGTH) -> List[str]:
        """
        Split a long message into multiple parts that fit WhatsApp's character limit.
        Tries to split at natural boundaries (newlines, then spaces).

        Args:
            message: The message to split
            max_length: Maximum length per message part

        Returns:
            List of message parts
        """
        if len(message) <= max_length:
            return [message]

        parts = []
        remaining = message
        part_num = 1

        while remaining:
            if len(remaining) <= max_length:
                parts.append(remaining)
                break

            # Find a good split point
            split_point = max_length

            # Try to split at a double newline (paragraph break)
            double_newline = remaining.rfind('\n\n', 0, max_length)
            if double_newline > max_length // 2:
                split_point = double_newline + 2
            else:
                # Try to split at a single newline
                single_newline = remaining.rfind('\n', 0, max_length)
                if single_newline > max_length // 2:
                    split_point = single_newline + 1
                else:
                    # Try to split at a space
                    space = remaining.rfind(' ', 0, max_length)
                    if space > max_length // 2:
                        split_point = space + 1
                    # Otherwise just split at max_length

            part = remaining[:split_point].rstrip()
            remaining = remaining[split_point:].lstrip()

            if part:
                parts.append(part)
            part_num += 1

        # Add continuation indicators if we split
        if len(parts) > 1:
            total = len(parts)
            parts = [f"{part}\n\n📄 ({i+1}/{total})" if i < total - 1 else part
                     for i, part in enumerate(parts)]

        return parts

    async def send_message(
        self,
        recipient: str,
        message: str,
        media_path: Optional[str] = None,
        api_url: Optional[str] = None,
        check_health_first: bool = True,
        api_secret: Optional[str] = None
    ) -> bool:
        """
        Send a message via WhatsApp bridge API with automatic retry.

        Args:
            recipient: Phone number or group JID (e.g., "5500000000001@s.whatsapp.net")
            message: Text message to send (used as caption for media)
            media_path: Optional path to media file (audio, image, video, document)
            api_url: Optional MCP API URL for this specific message (overrides constructor URL)
                    Phase 8: Allows routing to different MCP instances per message
            check_health_first: If True, check MCP health before sending (default: True)
            api_secret: Optional API authentication secret (Phase Security-1)
                    Overrides constructor secret for this specific message

        Returns:
            True if successful, False otherwise
        """
        # Phase 8: Use provided api_url or fall back to instance URL
        target_url = api_url or self.api_url

        if not target_url:
            logger.error("No API URL provided (neither in constructor nor send_message)")
            return False

        # Optional health check before sending
        if check_health_first:
            is_healthy, health_data = await self.check_health(target_url)
            if not is_healthy:
                logger.warning(
                    f"MCP at {target_url} is not healthy before sending. "
                    f"Health: {health_data}. Will attempt anyway with retries."
                )

        # Split long messages into parts (only for text messages, not media)
        if media_path:
            message_parts = [message]  # Don't split media captions
        else:
            message_parts = self._split_message(message)
            if len(message_parts) > 1:
                logger.info(f"Splitting long message ({len(message)} chars) into {len(message_parts)} parts")

        success = True
        for i, part in enumerate(message_parts):
            payload = {
                "recipient": recipient,
                "message": part
            }

            # Phase 7.3: Add media_path for audio responses (only on first part)
            if media_path and i == 0:
                payload["media_path"] = media_path
                logger.info(f"Sending media message to {recipient} via {target_url}: media={media_path}")
            else:
                logger.info(f"Sending message part {i+1}/{len(message_parts)} to {recipient} via {target_url}: {part[:50]}...")

            # Use retry logic for sending (with Phase Security-1 auth)
            part_success, result = await self._send_with_retry(target_url, payload, api_secret=api_secret)

            if part_success:
                if media_path and i == 0:
                    logger.info(f"Media message sent successfully to {recipient}")
                else:
                    logger.info(f"Message part {i+1}/{len(message_parts)} sent successfully to {recipient}")
            else:
                error_msg = result.get('message') if result else 'Unknown error'
                if result and 'error' in result:
                    error_msg = result.get('error', error_msg)
                logger.error(f"Failed to send part {i+1} after retries: {error_msg}")
                success = False
                # Don't continue with remaining parts if one fails
                break

            # Small delay between parts to maintain order
            if i < len(message_parts) - 1:
                await asyncio.sleep(0.5)

        return success

    async def close(self):
        """Close the HTTP client (async)"""
        await self.client.aclose()
