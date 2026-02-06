"""
Tool Output Buffer - Layer 5 (Ephemeral)

Ephemeral in-memory buffer for storing recent tool outputs with selective injection.
Enables agentic follow-up interactions where the agent can analyze
and act on previous tool results within the same conversation.

Key characteristics:
- In-memory only (never persisted to database)
- Each execution gets a unique ID for selective retrieval
- Auto-expires after N messages without tool reference
- Keyed by (agent_id, sender_key) for conversation isolation
- Maximum 10 outputs per conversation, 10KB each
- Selective injection via /inject command or natural language
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# Patterns that indicate user wants to inject/review previous tool output
INJECTION_INTENT_PATTERNS = [
    # Direct injection requests
    r'\b(review|show|display|inject|load)\s+(the\s+)?(latest|last|previous|recent)\s+(command|tool|scan|execution|output|result)',
    r'\b(what|show)\s+(were|was|is|are)\s+(the\s+)?(result|output|scan)',
    r'\blet\s+me\s+see\s+(the\s+)?(result|output|scan)',
    r'\bshow\s+(me\s+)?(the\s+)?(result|output|scan)',
    r'\banalyze\s+(the\s+)?(last|previous|latest|recent)\s+(scan|command|execution)',
    r'\breview\s+(the\s+)?(scan|command|execution|output|result)',

    # Questions about tool output content
    r'\bwhat\s+did\s+(the\s+)?(scan|tool|command)\s+(find|show|return|detect)',
    r'\bwhat\s+ports?\s+(is|are|were)\s+open',
    r'\bwhat\s+(vulnerabilities|services|hosts)\s+(did|were)',

    # References with intent to analyze
    r'\bbased\s+on\s+(the|that|this)\s+(scan|result|output)',
    r'\baccording\s+to\s+(the|that|this)\s+(scan|result|output)',
    r'\bfrom\s+(the|that)\s+(scan|result|output)',

    # Explicit ID references
    r'\b(execution|scan|tool|output)\s*(id|#)?\s*\d+',
    r'#\d+',  # Direct ID reference like #7
]


@dataclass
class ToolExecution:
    """Represents a single tool execution with unique ID."""
    execution_id: int  # Unique ID within conversation
    tool_name: str
    command_name: str
    target: Optional[str]  # Target parameter if available (e.g., scanme.nmap.org)
    output: str  # Full output (truncated to max size)
    output_size: int  # Original size before truncation
    line_count: int  # Number of lines in output
    timestamp: datetime
    message_index: int  # Message count when tool was executed

    def to_reference_string(self) -> str:
        """Format as lightweight reference (minimal tokens)."""
        age = datetime.utcnow() - self.timestamp
        age_str = f"{int(age.total_seconds() / 60)}m ago" if age.total_seconds() < 3600 else f"{int(age.total_seconds() / 3600)}h ago"
        target_str = f" on {self.target}" if self.target else ""
        size_str = f"{self.output_size / 1024:.1f}KB" if self.output_size > 1024 else f"{self.output_size}B"

        return f"#{self.execution_id}: {self.tool_name}.{self.command_name}{target_str} ({self.line_count} lines, {size_str}, {age_str})"

    def to_full_context(self) -> str:
        """Format full output for prompt injection."""
        header = f"[Tool Execution #{self.execution_id} - {self.tool_name}.{self.command_name}]"
        if self.target:
            header += f"\nTarget: {self.target}"
        header += f"\nExecuted: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        header += f"\n{'=' * 60}\n"

        return header + self.output


@dataclass
class ConversationToolBuffer:
    """Buffer for a single conversation's tool executions."""
    executions: List[ToolExecution] = field(default_factory=list)
    next_execution_id: int = 1  # Auto-increment ID
    message_count: int = 0  # Total messages in conversation
    last_tool_reference: int = 0  # Message index of last tool reference
    pending_injection_id: Optional[int] = None  # Execution ID to inject on next message

    # Configuration
    MAX_EXECUTIONS: int = 10  # Keep last 10 executions
    MAX_OUTPUT_SIZE: int = 10000  # 10KB per output
    EXPIRATION_MESSAGES: int = 20  # Expire after 20 messages without reference


class ToolOutputBuffer:
    """
    Global buffer for all conversation tool outputs with selective injection.

    Features:
    - Execution IDs for selective retrieval
    - /inject command support
    - Natural language injection detection
    - Lightweight references (always available)
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # Dict[(agent_id, sender_key)] -> ConversationToolBuffer
        self._buffers: Dict[Tuple[int, str], ConversationToolBuffer] = defaultdict(ConversationToolBuffer)

        # Compile patterns for performance
        self._injection_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in INJECTION_INTENT_PATTERNS
        ]

        self.logger.info("ToolOutputBuffer initialized (Layer 5 - Ephemeral with Selective Injection)")

    def _get_buffer_key(self, agent_id: int, sender_key: str) -> Tuple[int, str]:
        """Get the buffer key for a conversation."""
        return (agent_id, sender_key)

    def _extract_target(self, tool_name: str, command_name: str, output: str) -> Optional[str]:
        """Try to extract the target from tool output."""
        # Common patterns for target extraction
        patterns = [
            r'(?:target|host|scanning|Nmap scan report for)\s*[:\s]+([^\s\n]+)',
            r'(?:URL|Domain|IP)\s*[:\s]+([^\s\n]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def add_tool_output(
        self,
        agent_id: int,
        sender_key: str,
        tool_name: str,
        command_name: str,
        output: str,
        target: Optional[str] = None
    ) -> int:
        """
        Add a tool output to the buffer.

        Returns:
            execution_id: The unique ID assigned to this execution
        """
        key = self._get_buffer_key(agent_id, sender_key)
        buffer = self._buffers[key]

        # Calculate stats before truncation
        original_size = len(output)
        line_count = output.count('\n') + 1

        # Truncate output to max size
        truncated_output = output
        if len(output) > buffer.MAX_OUTPUT_SIZE:
            truncated_output = output[:buffer.MAX_OUTPUT_SIZE] + f"\n\n[... output truncated at {buffer.MAX_OUTPUT_SIZE} chars, original size: {original_size} chars ...]"

        # Try to extract target if not provided
        if not target:
            target = self._extract_target(tool_name, command_name, output)

        # Create execution record with unique ID
        execution_id = buffer.next_execution_id
        buffer.next_execution_id += 1

        execution = ToolExecution(
            execution_id=execution_id,
            tool_name=tool_name,
            command_name=command_name,
            target=target,
            output=truncated_output,
            output_size=original_size,
            line_count=line_count,
            timestamp=datetime.utcnow(),
            message_index=buffer.message_count
        )

        # Add to buffer (maintain max size, remove oldest)
        buffer.executions.append(execution)
        if len(buffer.executions) > buffer.MAX_EXECUTIONS:
            removed = buffer.executions.pop(0)
            self.logger.debug(f"Evicted old execution: #{removed.execution_id} {removed.tool_name}.{removed.command_name}")

        # Reset expiration counter
        buffer.last_tool_reference = buffer.message_count

        self.logger.info(
            f"Added tool execution #{execution_id}: {tool_name}.{command_name} "
            f"({original_size} bytes, {line_count} lines) for agent={agent_id}, sender={sender_key}"
        )

        return execution_id

    def increment_message_count(self, agent_id: int, sender_key: str) -> None:
        """Increment message count for a conversation."""
        key = self._get_buffer_key(agent_id, sender_key)
        self._buffers[key].message_count += 1
        self._maybe_expire_buffer(key)

    def _maybe_expire_buffer(self, key: Tuple[int, str]) -> None:
        """Expire buffer if too many messages without tool reference."""
        buffer = self._buffers[key]

        if not buffer.executions:
            return

        messages_since_reference = buffer.message_count - buffer.last_tool_reference

        if messages_since_reference >= buffer.EXPIRATION_MESSAGES:
            self.logger.info(
                f"Expiring tool buffer for {key}: {messages_since_reference} messages since last reference"
            )
            buffer.executions.clear()

    def detect_injection_intent(self, message: str) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Detect if user wants to inject/review tool output.

        Returns:
            (has_intent, execution_id, tool_name)
            - has_intent: True if injection is requested
            - execution_id: Specific ID if mentioned (e.g., #7), else None for latest
            - tool_name: Specific tool if mentioned, else None for any
        """
        if not message:
            return (False, None, None)

        # Check for explicit execution ID reference
        id_match = re.search(r'#(\d+)|(?:execution|id)\s*(\d+)', message, re.IGNORECASE)
        execution_id = None
        if id_match:
            execution_id = int(id_match.group(1) or id_match.group(2))

        # Check for tool name reference
        tool_name = None
        tool_patterns = [
            # Security/scanning tools
            (r'\bnmap\b', 'nmap'),
            (r'\bnuclei\b', 'nuclei'),
            (r'\bkatana\b', 'katana'),
            (r'\bhttpx\b', 'httpx'),
            (r'\bsubfinder\b', 'subfinder'),
            # Phase 18.3.7: Shell command support
            (r'\bshell\b', 'shell'),
            (r'\bcommand\b', 'shell'),  # "review the command output"
            (r'\bbash\b', 'shell'),
            (r'\bterminal\b', 'shell'),
            (r'\bconsole\b', 'shell'),
        ]
        for pattern, name in tool_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                tool_name = name
                break

        # Check for injection intent
        for pattern in self._injection_patterns:
            if pattern.search(message):
                self.logger.debug(f"Injection intent detected via pattern: {pattern.pattern}")
                return (True, execution_id, tool_name)

        return (False, None, None)

    def get_execution_by_id(
        self,
        agent_id: int,
        sender_key: str,
        execution_id: int
    ) -> Optional[ToolExecution]:
        """Get a specific execution by ID."""
        key = self._get_buffer_key(agent_id, sender_key)
        buffer = self._buffers[key]

        for execution in buffer.executions:
            if execution.execution_id == execution_id:
                # Update reference marker
                buffer.last_tool_reference = buffer.message_count
                return execution

        return None

    def get_latest_execution(
        self,
        agent_id: int,
        sender_key: str,
        tool_name: Optional[str] = None
    ) -> Optional[ToolExecution]:
        """Get the most recent execution, optionally filtered by tool name."""
        key = self._get_buffer_key(agent_id, sender_key)
        buffer = self._buffers[key]

        if not buffer.executions:
            return None

        # Filter by tool name if specified
        if tool_name:
            matching = [e for e in buffer.executions if e.tool_name.lower() == tool_name.lower()]
            if matching:
                buffer.last_tool_reference = buffer.message_count
                return matching[-1]  # Most recent matching
            return None

        # Return most recent
        buffer.last_tool_reference = buffer.message_count
        return buffer.executions[-1]

    def list_available_executions(
        self,
        agent_id: int,
        sender_key: str
    ) -> List[str]:
        """Get lightweight references for all available executions."""
        key = self._get_buffer_key(agent_id, sender_key)
        buffer = self._buffers[key]

        return [e.to_reference_string() for e in buffer.executions]

    def clear_executions(
        self,
        agent_id: int,
        sender_key: str
    ) -> int:
        """
        Clear all injected tool outputs for a conversation.

        Returns:
            count: Number of executions cleared
        """
        key = self._get_buffer_key(agent_id, sender_key)
        buffer = self._buffers[key]

        count = len(buffer.executions)
        buffer.executions.clear()
        buffer.last_tool_reference = buffer.message_count

        self.logger.info(f"Cleared {count} tool executions for {key}")
        return count

    def mark_pending_injection(
        self,
        agent_id: int,
        sender_key: str,
        execution_id: int
    ) -> None:
        """
        Mark an execution for injection on the next message.

        This is called by the /inject command to ensure the execution
        content is included in the AI context for the next user message.
        """
        key = self._get_buffer_key(agent_id, sender_key)
        self._buffers[key].pending_injection_id = execution_id
        self.logger.info(f"Marked execution #{execution_id} for pending injection (agent={agent_id}, sender={sender_key})")

    def get_lightweight_reference(
        self,
        agent_id: int,
        sender_key: str
    ) -> Optional[str]:
        """
        Get a minimal token reference showing available executions.
        This is safe to always inject without exploding token usage.

        Returns ~100-200 tokens for typical usage.
        """
        key = self._get_buffer_key(agent_id, sender_key)
        buffer = self._buffers[key]

        if not buffer.executions:
            return None

        refs = self.list_available_executions(agent_id, sender_key)

        header = "[Available Tool Executions]"
        footer = 'Use "/inject [id]" or ask to "review execution #N" to analyze full output.'

        return f"{header}\n" + "\n".join(f"  {ref}" for ref in refs) + f"\n{footer}"

    def get_context_for_injection(
        self,
        agent_id: int,
        sender_key: str,
        current_message: str
    ) -> Optional[str]:
        """
        Get tool output context based on injection intent.

        Strategy:
        1. Check for pending injection from /inject command (highest priority)
        2. Detect if user wants injection (natural language or explicit ID)
        3. If yes, inject the requested output(s)
        4. If no, inject only lightweight reference

        This saves tokens when user doesn't need the full output.
        """
        key = self._get_buffer_key(agent_id, sender_key)
        buffer = self._buffers[key]

        if not buffer.executions:
            return None

        # Check for pending injection FIRST (from /inject command)
        if buffer.pending_injection_id:
            pending_id = buffer.pending_injection_id
            buffer.pending_injection_id = None  # Clear pending before retrieval
            execution = self.get_execution_by_id(agent_id, sender_key, pending_id)
            if execution:
                self.logger.info(f"Injecting pending execution #{pending_id} from /inject command")
                return execution.to_full_context()
            else:
                self.logger.warning(f"Pending injection #{pending_id} not found, falling back to lightweight reference")

        # Detect injection intent from natural language
        has_intent, execution_id, tool_name = self.detect_injection_intent(current_message)

        if has_intent:
            # User wants full output - inject it
            if execution_id:
                execution = self.get_execution_by_id(agent_id, sender_key, execution_id)
                if execution:
                    self.logger.info(f"Injecting full output for execution #{execution_id}")
                    return execution.to_full_context()
                else:
                    return f"[No execution found with ID #{execution_id}]\n" + self.get_lightweight_reference(agent_id, sender_key)
            else:
                execution = self.get_latest_execution(agent_id, sender_key, tool_name)
                if execution:
                    self.logger.info(f"Injecting full output for latest execution: {execution.tool_name}.{execution.command_name}")
                    return execution.to_full_context()

        # No injection intent - just show lightweight reference
        return self.get_lightweight_reference(agent_id, sender_key)

    def clear_buffer(self, agent_id: int, sender_key: str) -> None:
        """Clear tool buffer for a conversation."""
        key = self._get_buffer_key(agent_id, sender_key)
        if key in self._buffers:
            self._buffers[key].executions.clear()
            self.logger.debug(f"Cleared tool buffer for {key}")

    def get_stats(self) -> Dict:
        """Get buffer statistics."""
        total_executions = sum(len(b.executions) for b in self._buffers.values())
        active_conversations = sum(1 for b in self._buffers.values() if b.executions)

        return {
            "total_conversations": len(self._buffers),
            "active_conversations": active_conversations,
            "total_executions_buffered": total_executions
        }


# Global singleton instance
_tool_output_buffer: Optional[ToolOutputBuffer] = None


def get_tool_output_buffer() -> ToolOutputBuffer:
    """Get or create the global ToolOutputBuffer instance."""
    global _tool_output_buffer
    if _tool_output_buffer is None:
        _tool_output_buffer = ToolOutputBuffer()
    return _tool_output_buffer
