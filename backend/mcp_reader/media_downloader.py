"""
Media Downloader for WhatsApp MCP
Downloads media files (audio, images, videos) from WhatsApp MCP REST API.
"""

import logging
import httpx
import os
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class MediaDownloader:
    """
    Downloads media files from WhatsApp MCP REST API.

    The MCP bridge exposes a `/api/download` endpoint that downloads
    media files from WhatsApp and returns the local file path.
    """

    def __init__(self, mcp_api_url: str = "http://localhost:8080"):
        """
        Initialize media downloader.

        Args:
            mcp_api_url: Base URL for MCP REST API (default: http://localhost:8080)
        """
        self.mcp_api_url = mcp_api_url.rstrip("/")
        self.download_endpoint = f"{self.mcp_api_url}/api/download"

    async def download_media(self, message_id: str, chat_jid: str, mcp_api_url: Optional[str] = None, api_secret: Optional[str] = None) -> Optional[str]:
        """
        Download media file from WhatsApp via MCP API.

        Args:
            message_id: Message ID from MCP database
            chat_jid: Chat JID (WhatsApp identifier)
            mcp_api_url: Optional MCP API URL to override default (for multi-tenant support)
            api_secret: Optional API secret for authentication with the MCP instance

        Returns:
            Local file path if successful, None otherwise
        """
        try:
            # Use provided MCP URL or fall back to default
            download_endpoint = self.download_endpoint
            if mcp_api_url:
                # Ensure URL ends with /api/download
                base_url = mcp_api_url.rstrip("/")
                if base_url.endswith("/api"):
                    download_endpoint = f"{base_url}/download"
                else:
                    download_endpoint = f"{base_url}/api/download"

            logger.info(f"Downloading media for message {message_id} from chat {chat_jid} via {download_endpoint}")

            # Build headers with authorization if api_secret is provided
            headers = {}
            if api_secret:
                headers["Authorization"] = f"Bearer {api_secret}"

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    download_endpoint,
                    json={
                        "message_id": message_id,
                        "chat_jid": chat_jid
                    },
                    headers=headers
                )

                if response.status_code != 200:
                    logger.error(f"Media download failed: HTTP {response.status_code} - {response.text}")
                    return None

                result = response.json()

                if not result.get("success"):
                    logger.error(f"Media download failed: {result.get('message', 'Unknown error')}")
                    return None

                filename = result.get("filename")
                file_content_b64 = result.get("file_content")

                if not filename or not file_content_b64:
                    logger.error("Media download succeeded but no filename/content returned")
                    return None

                # Decode base64 file content
                import base64
                import tempfile

                try:
                    file_data = base64.b64decode(file_content_b64)
                except Exception as e:
                    logger.error(f"Failed to decode base64 file content: {e}")
                    return None

                # Create a local temporary file to store the audio
                # Extract file extension from filename
                file_ext = os.path.splitext(filename)[1] or '.ogg'
                temp_file = tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=file_ext,
                    prefix=f"audio_{message_id}_"
                )

                # Write the decoded bytes to file
                temp_file.write(file_data)
                temp_file.close()

                local_path = temp_file.name
                file_size = len(file_data)

                logger.info(f"Media downloaded successfully: {local_path} ({file_size} bytes)")

                return local_path

        except httpx.TimeoutException:
            logger.error(f"Timeout downloading media for message {message_id}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Request error downloading media: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error downloading media: {e}", exc_info=True)
            return None

    def is_audio_message(self, media_type: Optional[str]) -> bool:
        """
        Check if message has audio media.

        Args:
            media_type: Media type from database

        Returns:
            True if audio message
        """
        if not media_type:
            return False

        return media_type.lower() in [
            "audio",
            "audio/ogg",
            "audio/mpeg",
            "audio/mp3",
            "audio/wav",
            "audio/m4a"
        ]

    def is_image_message(self, media_type: Optional[str]) -> bool:
        """
        Check if message has image media.

        Args:
            media_type: Media type from database

        Returns:
            True if image message
        """
        if not media_type:
            return False

        return media_type.lower() in [
            "image",
            "image/jpeg",
            "image/jpg",
            "image/png",
            "image/webp",
            "image/gif"
        ]
