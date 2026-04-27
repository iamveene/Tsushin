from collections import deque
from typing import List, Dict, Optional
from datetime import datetime
import json

class SenderMemory:
    def __init__(self, max_size: int = 10):
        self.max_size = max_size
        self.memories: Dict[str, deque] = {}

    def add_message(self, sender_key: str, role: str, content: str, metadata: Optional[Dict] = None, message_id: Optional[str] = None):
        """Add a message to sender's memory ring buffer

        Args:
            sender_key: Unique identifier for the sender
            role: Message role ('user' or 'assistant')
            content: Message content
            metadata: Optional metadata (e.g., is_tool_output, tool_used)
            message_id: Optional unique message identifier (Phase 14.2)
        """
        if sender_key not in self.memories:
            self.memories[sender_key] = deque(maxlen=self.max_size)

        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

        # Include message_id if provided (Phase 14.2: for message operations)
        if message_id:
            message["message_id"] = message_id

        # Include metadata if provided (for tool output tracking, etc.)
        if metadata:
            message["metadata"] = metadata

        self.memories[sender_key].append(message)

    def get_messages(self, sender_key: str) -> List[Dict]:
        """Get all messages for a sender"""
        if sender_key not in self.memories:
            return []
        return list(self.memories[sender_key])

    def clear(self, sender_key: str):
        """Clear memory for a sender"""
        if sender_key in self.memories:
            del self.memories[sender_key]

    def serialize(self, sender_key: str) -> str:
        """Serialize sender's memory to JSON"""
        return json.dumps(self.get_messages(sender_key))

    def deserialize(self, sender_key: str, data: list):
        """Deserialize list to sender's memory"""
        self.memories[sender_key] = deque(data, maxlen=self.max_size)
