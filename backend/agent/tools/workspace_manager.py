"""
Phase 6.1: Workspace Manager for Custom Tools
Manages secure sandboxed workspaces for custom tool execution.
"""

import os
import shutil
from pathlib import Path
from typing import Optional
import logging


class SecurityError(Exception):
    """Raised when security validation fails."""
    pass


class WorkspaceManager:
    """Manages secure sandboxed workspaces for custom tools."""

    def __init__(self, base_dir: str = "./data/workspace"):
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"WorkspaceManager initialized with base_dir: {self.base_dir}")

    def get_tool_workspace(self, tool_name: str) -> Path:
        """Get or create workspace directory for a tool."""
        # Sanitize tool name to prevent directory traversal
        safe_tool_name = self._sanitize_name(tool_name)
        tool_dir = self.base_dir / safe_tool_name
        tool_dir.mkdir(exist_ok=True)
        self.logger.debug(f"Workspace for tool '{tool_name}': {tool_dir}")
        return tool_dir

    def validate_path(self, tool_name: str, file_path: str) -> Path:
        """
        Validate and resolve path to prevent directory traversal.

        Args:
            tool_name: Name of the tool (used to determine workspace)
            file_path: Relative path within the tool's workspace

        Returns:
            Resolved absolute path within workspace

        Raises:
            SecurityError: If path is outside workspace (directory traversal attempt)
        """
        tool_workspace = self.get_tool_workspace(tool_name)

        # Resolve the full path
        full_path = (tool_workspace / file_path).resolve()

        # Security: Ensure path is within workspace
        if not str(full_path).startswith(str(tool_workspace)):
            self.logger.error(f"Path traversal attempt blocked: {file_path} -> {full_path}")
            raise SecurityError(f"Path traversal attempt blocked: {file_path}")

        return full_path

    def create_file(self, tool_name: str, file_path: str, content: str = "") -> Path:
        """
        Create a file within the tool's workspace.

        Args:
            tool_name: Name of the tool
            file_path: Relative path within workspace
            content: Optional content to write to file

        Returns:
            Path to created file

        Raises:
            SecurityError: If path is invalid
        """
        validated_path = self.validate_path(tool_name, file_path)

        # Create parent directories if needed
        validated_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        validated_path.write_text(content, encoding="utf-8")
        self.logger.info(f"Created file: {validated_path}")

        return validated_path

    def read_file(self, tool_name: str, file_path: str) -> str:
        """
        Read a file from the tool's workspace.

        Args:
            tool_name: Name of the tool
            file_path: Relative path within workspace

        Returns:
            File content as string

        Raises:
            SecurityError: If path is invalid
            FileNotFoundError: If file doesn't exist
        """
        validated_path = self.validate_path(tool_name, file_path)

        if not validated_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        return validated_path.read_text(encoding="utf-8")

    def list_files(self, tool_name: str, subdirectory: str = "") -> list[str]:
        """
        List files in the tool's workspace.

        Args:
            tool_name: Name of the tool
            subdirectory: Optional subdirectory to list

        Returns:
            List of relative file paths

        Raises:
            SecurityError: If path is invalid
        """
        if subdirectory:
            base_path = self.validate_path(tool_name, subdirectory)
        else:
            base_path = self.get_tool_workspace(tool_name)

        if not base_path.exists() or not base_path.is_dir():
            return []

        # Get all files recursively
        files = []
        workspace_root = self.get_tool_workspace(tool_name)

        for file_path in base_path.rglob("*"):
            if file_path.is_file():
                # Get relative path from workspace root
                rel_path = file_path.relative_to(workspace_root)
                files.append(str(rel_path))

        return sorted(files)

    def delete_file(self, tool_name: str, file_path: str) -> bool:
        """
        Delete a file from the tool's workspace.

        Args:
            tool_name: Name of the tool
            file_path: Relative path within workspace

        Returns:
            True if file was deleted, False if it didn't exist

        Raises:
            SecurityError: If path is invalid
        """
        validated_path = self.validate_path(tool_name, file_path)

        if not validated_path.exists():
            return False

        if validated_path.is_file():
            validated_path.unlink()
            self.logger.info(f"Deleted file: {validated_path}")
            return True
        else:
            self.logger.warning(f"Path is not a file: {validated_path}")
            return False

    def clean_workspace(self, tool_name: str) -> None:
        """
        Delete all files in the tool's workspace.

        Args:
            tool_name: Name of the tool
        """
        tool_workspace = self.get_tool_workspace(tool_name)

        if tool_workspace.exists():
            shutil.rmtree(tool_workspace)
            tool_workspace.mkdir()
            self.logger.info(f"Cleaned workspace: {tool_workspace}")

    def get_workspace_size(self, tool_name: str) -> int:
        """
        Get total size of files in tool's workspace (in bytes).

        Args:
            tool_name: Name of the tool

        Returns:
            Total size in bytes
        """
        tool_workspace = self.get_tool_workspace(tool_name)
        total_size = 0

        for file_path in tool_workspace.rglob("*"):
            if file_path.is_file():
                total_size += file_path.stat().st_size

        return total_size

    def _sanitize_name(self, name: str) -> str:
        """
        Sanitize tool name to prevent directory traversal.

        Args:
            name: Raw tool name

        Returns:
            Sanitized name (alphanumeric + underscore/dash only)
        """
        # Replace invalid characters with underscore
        safe_chars = []
        for char in name:
            if char.isalnum() or char in ('_', '-'):
                safe_chars.append(char)
            else:
                safe_chars.append('_')

        sanitized = ''.join(safe_chars)

        # Prevent empty names or names starting with dot
        if not sanitized or sanitized.startswith('.'):
            sanitized = 'tool_' + sanitized

        return sanitized
