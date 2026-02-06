"""
Agent Utility Functions

Shared utilities for agent processing, memory management, and tool execution.
"""

import logging

logger = logging.getLogger(__name__)


def summarize_tool_result(full_result: str, tool_name: str) -> str:
    """
    Summarize a tool execution result for memory storage.

    This prevents tool context (including target URLs, full outputs) from
    bleeding into future conversations. The summary is concise and doesn't
    include potentially sensitive or context-specific data.

    Args:
        full_result: Full tool execution result
        tool_name: Name of the tool that was executed

    Returns:
        Concise summary string for memory storage
    """
    try:
        # Extract key information from the result
        lines = full_result.split('\n')

        # Find status line (e.g., "Status: ✅ completed")
        status = "completed"
        for line in lines:
            if line.startswith("Status:"):
                if "completed" in line.lower():
                    status = "completed"
                elif "running" in line.lower():
                    status = "running"
                elif "failed" in line.lower() or "error" in line.lower():
                    status = "failed"
                break

        # Count output lines (rough measure of result size)
        output_lines = len([l for l in lines if l.strip()])

        # Extract execution time if present
        exec_time = ""
        for line in lines:
            if "Execution time:" in line:
                exec_time = line.strip()
                break

        # Build concise summary (no target URLs or full output)
        summary = f"[Tool: {tool_name} - {status}]"
        if exec_time:
            summary += f" ({exec_time})"
        if output_lines > 5:
            summary += f" [Output: {output_lines} lines]"

        return summary

    except Exception as e:
        logger.warning(f"Failed to summarize tool result: {e}")
        # Fallback to simple summary
        return f"[Tool: {tool_name} - executed]"
