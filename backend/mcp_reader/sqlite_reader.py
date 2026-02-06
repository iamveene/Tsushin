import sqlite3
from typing import List, Dict
import logging

class MCPDatabaseReader:
    def __init__(self, db_path: str, contact_mappings: Dict = None):
        self.db_path = db_path
        self.contact_mappings = contact_mappings or {}
        self.logger = logging.getLogger(__name__)

    def get_new_messages(self, last_timestamp: str, limit: int = 500) -> List[Dict]:
        """
        Read new messages since last_timestamp.
        Returns list of normalized message dicts.
        """
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=10)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Convert last_timestamp to Unix epoch for comparison (handle both formats)
            # SQLite timestamp column can be integer (Unix epoch) or string (ISO format)
            # We need to convert our string timestamp to epoch for reliable comparison
            from datetime import datetime
            try:
                # Parse string timestamp to datetime
                dt = datetime.fromisoformat(last_timestamp.replace("+00:00", ""))
                epoch_timestamp = int(dt.timestamp())
            except:
                # If parsing fails, default to 0 (1970)
                epoch_timestamp = 0

            query = """
                SELECT
                    m.id,
                    m.chat_jid,
                    c.name as chat_name,
                    m.sender,
                    m.content,
                    CASE
                        WHEN typeof(m.timestamp) = 'integer'
                        THEN datetime(m.timestamp, 'unixepoch')
                        ELSE m.timestamp
                    END as timestamp,
                    m.is_from_me,
                    CASE WHEN m.chat_jid LIKE '%@g.us%' THEN 1 ELSE 0 END as is_group,
                    m.media_type,
                    m.filename,
                    m.url as media_url
                FROM messages m
                LEFT JOIN chats c ON m.chat_jid = c.jid
                WHERE (
                    CASE
                        WHEN typeof(m.timestamp) = 'integer'
                        THEN m.timestamp > ?
                        ELSE m.timestamp > datetime(?, 'unixepoch')
                    END
                )
                AND m.is_from_me = 0
                ORDER BY m.timestamp ASC
                LIMIT ?
            """

            cursor.execute(query, (epoch_timestamp, epoch_timestamp, limit))
            rows = cursor.fetchall()

            # Normalize to expected format
            messages = []
            for row in rows:
                msg = dict(row)

                # Try to get sender name from contact_mappings
                sender_id = msg["sender"]
                sender_name = None

                # Check contact_mappings for this sender (remove + if present)
                for contact_id, name in self.contact_mappings.items():
                    # Normalize both IDs (remove +)
                    norm_contact = contact_id.lstrip("+")
                    norm_sender = sender_id.lstrip("+")
                    if norm_contact == norm_sender:
                        sender_name = name
                        break

                # Map to expected format
                messages.append({
                    "id": msg["id"],
                    "chat_id": msg["chat_jid"],
                    "chat_jid": msg["chat_jid"],  # Keep original for media download API
                    "chat_name": msg.get("chat_name"),
                    "sender": msg["sender"],
                    "sender_name": sender_name,
                    "body": msg["content"],
                    "timestamp": msg["timestamp"],
                    "is_group": msg["is_group"],
                    # Phase 5.0: Media fields for audio transcription
                    "media_type": msg.get("media_type"),
                    "filename": msg.get("filename"),
                    "media_url": msg.get("media_url"),
                    # Phase 10.1.1: Channel tracking for multi-channel analytics
                    "channel": "whatsapp"
                })

            conn.close()

            return messages

        except sqlite3.Error as e:
            self.logger.error(f"Error reading MCP database: {e}")
            return []

    def get_latest_timestamp(self) -> str:
        """
        Get the most recent message timestamp in the database.
        Includes retry logic to handle DB locking issues.
        Raises sqlite3.Error if all retries fail.
        """
        import time
        max_retries = 3

        for attempt in range(max_retries):
            try:
                conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=10)
                cursor = conn.cursor()
                cursor.execute("SELECT MAX(timestamp) FROM messages")
                result = cursor.fetchone()
                conn.close()

                # If DB is empty, return default 1970 timestamp
                if not result or not result[0]:
                    self.logger.info("Database appears empty or no messages found, defaulting to 1970-01-01")
                    return "1970-01-01 00:00:00"

                timestamp_value = result[0]

                # Handle both integer (Unix epoch) and string timestamps
                if isinstance(timestamp_value, int):
                    from datetime import datetime
                    return datetime.utcfromtimestamp(timestamp_value).strftime("%Y-%m-%d %H:%M:%S+00:00")

                return timestamp_value

            except sqlite3.Error as e:
                self.logger.warning(f"Error getting latest timestamp (attempt {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)  # Wait 1s before retry
                else:
                    # On final failure, raise the exception instead of defaulting to 1970
                    # This prevents the bot from replying to all historical messages
                    self.logger.error("CRITICAL: Failed to get latest timestamp after retries. Raising exception to prevent historical message flood.")
                    raise

    def get_recent_messages(self, chat_id: str, before_timestamp: str, limit: int = 5) -> List[Dict]:
        """
        Get recent messages from a specific chat before a given timestamp.
        Used for building group context.

        Args:
            chat_id: The chat identifier (chat_jid)
            before_timestamp: Get messages before this timestamp
            limit: Maximum number of messages to return

        Returns:
            List of message dicts with timestamp, sender_name, body
        """
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=10)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = """
                SELECT m.timestamp, m.sender, m.content as body
                FROM messages m
                WHERE m.chat_jid = ? AND m.timestamp < ?
                ORDER BY m.timestamp DESC
                LIMIT ?
            """

            cursor.execute(query, (chat_id, before_timestamp, limit))
            rows = cursor.fetchall()

            messages = []
            for row in rows:
                msg = dict(row)

                # Try to get sender name from contact_mappings
                sender_id = msg["sender"]
                sender_name = sender_id  # Default to sender ID

                # Check contact_mappings for this sender
                for contact_id, name in self.contact_mappings.items():
                    norm_contact = contact_id.lstrip("+")
                    norm_sender = sender_id.lstrip("+")
                    if norm_contact == norm_sender:
                        sender_name = name
                        break

                messages.append({
                    "timestamp": msg["timestamp"],
                    "sender_name": sender_name,
                    "body": msg["body"]
                })

            conn.close()
            return messages

        except sqlite3.Error as e:
            self.logger.error(f"Error reading recent messages: {e}")
            return []
