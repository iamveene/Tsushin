"""
Shell Command Service - Phase 18.3/18.4: Tool Integration with WebSocket Push

Core service layer for shell command execution via C2 architecture.

Provides:
- Command queueing and result retrieval
- Target resolution (default, hostname, @all)
- Timeout handling with DB polling
- Multi-tenant isolation
- WebSocket push for real-time delivery (Phase 18.4)
- Security validation (CRIT-005 fix)
"""

import uuid
import time
import logging
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy.orm import Session
from sqlalchemy import text

from models import ShellIntegration, ShellCommand, Agent
from websocket_manager import manager
from services.shell_security_service import (
    get_security_service,
    SecurityCheckResult,
    RiskLevel
)

logger = logging.getLogger(__name__)


class CommandStatus(Enum):
    """Shell command lifecycle states."""
    QUEUED = "queued"
    SENT = "sent"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    # Security-related statuses (CRIT-005)
    BLOCKED = "blocked"                     # Blocked by security policy
    PENDING_APPROVAL = "pending_approval"   # Waiting for admin approval
    REJECTED = "rejected"                   # Admin rejected the command
    EXPIRED = "expired"                     # Approval request expired


@dataclass
class CommandResult:
    """Result of a shell command execution."""
    success: bool
    command_id: str
    status: str
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    execution_time_ms: Optional[int] = None
    error_message: Optional[str] = None
    timed_out: bool = False
    # Security-related fields (CRIT-005)
    blocked: bool = False
    blocked_reason: Optional[str] = None
    requires_approval: bool = False
    risk_level: Optional[str] = None
    security_warnings: Optional[List[str]] = field(default_factory=list)
    yolo_mode_auto_approved: bool = False

    def to_agent_response(self) -> str:
        """Format result for agent consumption."""
        # Handle blocked commands
        if self.blocked:
            warnings_text = ""
            if self.security_warnings:
                warnings_text = "\n".join(f"  - {w}" for w in self.security_warnings)
                warnings_text = f"\n**Security Warnings:**\n{warnings_text}"
            return (
                f"⛔ **Command Blocked by Security Policy**\n"
                f"**Reason:** {self.blocked_reason or 'Security violation'}\n"
                f"**Risk Level:** {self.risk_level or 'unknown'}{warnings_text}"
            )

        # Handle pending approval
        if self.requires_approval:
            return (
                f"🔐 **Command Requires Admin Approval**\n"
                f"**Command ID:** `{self.command_id}`\n"
                f"**Risk Level:** {self.risk_level or 'high'}\n"
                f"**Status:** Waiting for approval\n\n"
                f"_An administrator must approve this command before it can execute._"
            )

        if self.timed_out:
            return f"⏱️ Command timed out (ID: {self.command_id}). The beacon may still be processing it."

        if not self.success:
            error = self.error_message or self.stderr or "Unknown error"
            return f"❌ Command failed (exit code: {self.exit_code})\n```\n{error}\n```"

        output = self.stdout or "(no output)"
        if len(output) > 2000:
            output = output[:2000] + "\n... (truncated)"

        # Add YOLO mode indicator if auto-approved
        yolo_note = ""
        if self.yolo_mode_auto_approved:
            yolo_note = " (YOLO mode - auto-approved)"

        return f"✅ Command completed successfully{yolo_note} (exit code: {self.exit_code})\n```\n{output}\n```"


class ShellCommandService:
    """
    Service for managing shell command execution.

    Handles:
    - Command queueing to database
    - Waiting for beacon execution with timeout
    - Target resolution (default, hostname, @all)
    - Multi-tenant isolation
    """

    def __init__(self, db: Session):
        """
        Initialize the service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def get_available_shells(
        self,
        tenant_id: str,
        agent_id: Optional[int] = None,
        online_only: bool = False
    ) -> List[ShellIntegration]:
        """
        Get all shell integrations available to a tenant.

        Args:
            tenant_id: Tenant identifier
            agent_id: Optional agent ID for future per-agent filtering
            online_only: Only return online beacons

        Returns:
            List of ShellIntegration records
        """
        query = self.db.query(ShellIntegration).filter(
            ShellIntegration.tenant_id == tenant_id,
            ShellIntegration.is_active == True
        )

        shells = query.all()

        if online_only:
            shells = [s for s in shells if s.is_online]

        return shells

    def get_targets_os_context(self, tenant_id: str) -> str:
        """
        Get formatted OS information for all available shell targets.

        This context is injected into the AI's system prompt so it can
        generate OS-appropriate commands (e.g., `top -l 1` for macOS
        instead of `top -bn1` for Linux).

        Args:
            tenant_id: Tenant identifier

        Returns:
            Formatted string with OS details for each target, or empty string if none.
        """
        shells = self.get_available_shells(tenant_id)

        if not shells:
            return ""

        contexts = []
        for shell in shells:
            hostname = shell.hostname or shell.name or f"shell-{shell.id}"
            os_info = shell.os_info or {}
            system = os_info.get("system", "Unknown")

            # Build OS description based on detected system
            if system == "Darwin":
                release = os_info.get("release", "")
                os_desc = f"macOS {release}".strip()
            elif system == "Linux":
                distro = os_info.get("distro", "")
                release = os_info.get("release", "")
                os_desc = distro if distro else f"Linux {release}".strip()
            elif system == "Windows":
                release = os_info.get("release", "")
                os_desc = f"Windows {release}".strip()
            else:
                release = os_info.get("release", "")
                os_desc = f"{system} {release}".strip() if system else "Unknown OS"

            # Include online status
            status = "online" if shell.is_online else "offline"

            contexts.append(f"- {hostname}: {os_desc} ({status})")

        return "\n".join(contexts)

    def find_shell_by_target(
        self,
        target: str,
        tenant_id: str
    ) -> Tuple[Optional[ShellIntegration], Optional[str]]:
        """
        Resolve a target string to a ShellIntegration.

        Args:
            target: Target string - "default", hostname, or "@all"
            tenant_id: Tenant identifier

        Returns:
            Tuple of (ShellIntegration or None, error message or None)
        """
        if target == "@all":
            # @all is handled separately in execute methods
            return None, None

        # Get available shells
        shells = self.get_available_shells(tenant_id)

        if not shells:
            return None, f"No shell integrations configured for this tenant"

        if target == "default":
            # Return first active shell (prefer online)
            online_shells = [s for s in shells if s.is_online]
            if online_shells:
                return online_shells[0], None
            # Return first shell even if offline (command will queue)
            return shells[0], None

        # Find by hostname
        for shell in shells:
            if shell.hostname and shell.hostname.lower() == target.lower():
                return shell, None

        # Find by name
        for shell in shells:
            if shell.name and shell.name.lower() == target.lower():
                return shell, None

        return None, f"No shell found with hostname or name '{target}'"

    # =========================================================================
    # Security Methods (CRIT-005 Fix)
    # =========================================================================

    def _check_command_security(
        self,
        commands: List[str],
        shell: ShellIntegration,
        tenant_id: str
    ) -> Tuple[bool, Optional[SecurityCheckResult], Optional[str]]:
        """
        Perform security checks on commands before queueing.

        Validates commands against:
        - BLOCKED_PATTERNS (always rejected, even in YOLO mode)
        - HIGH_RISK_PATTERNS (require approval or YOLO mode)
        - Command whitelist (if configured)
        - Path restrictions (if configured)
        - Rate limits

        Args:
            commands: List of commands to check
            shell: Target ShellIntegration with security config
            tenant_id: Tenant identifier

        Returns:
            Tuple of (allowed, security_result, error_message)
            - allowed: True if commands can proceed (queued or needs approval)
            - security_result: Details of security check
            - error_message: Reason for blocking if not allowed
        """
        security_service = get_security_service()

        # Check rate limit first
        rate_allowed, rate_error = security_service.check_rate_limit(shell.id)
        if not rate_allowed:
            logger.warning(f"Rate limit exceeded for shell {shell.id}: {rate_error}")
            return False, None, rate_error

        # Get shell's security configuration
        allowed_commands = shell.allowed_commands or []
        allowed_paths = shell.allowed_paths or []

        # Check all commands against patterns
        all_allowed, security_result = security_service.check_commands(
            commands=commands,
            allowed_commands=allowed_commands if allowed_commands else None,
            allowed_paths=allowed_paths if allowed_paths else None,
            require_approval_for_high_risk=True
        )

        if not all_allowed:
            logger.warning(
                f"Command blocked by security check: {security_result.blocked_reason}"
            )
            return False, security_result, security_result.blocked_reason

        return True, security_result, None

    def _log_blocked_command(
        self,
        commands: List[str],
        shell_id: int,
        tenant_id: str,
        initiated_by: str,
        blocked_reason: str,
        security_result: Optional[SecurityCheckResult] = None,
        agent_id: Optional[int] = None
    ) -> ShellCommand:
        """
        Log a blocked command to the database for audit purposes.

        Even blocked commands are recorded for security auditing.
        They are stored with status='blocked' and will not be executed.

        Args:
            commands: The blocked commands
            shell_id: Target shell integration ID
            tenant_id: Tenant identifier
            initiated_by: Who initiated the command
            blocked_reason: Why the command was blocked
            security_result: Security check result details
            agent_id: Optional agent ID

        Returns:
            ShellCommand record with status='blocked'
        """
        from sqlalchemy.orm import sessionmaker
        import db

        command_id = str(uuid.uuid4())

        command = ShellCommand(
            id=command_id,
            shell_id=shell_id,
            tenant_id=tenant_id,
            commands=commands,
            initiated_by=initiated_by,
            executed_by_agent_id=agent_id,
            status=CommandStatus.BLOCKED.value,
            error_message=blocked_reason,
            completed_at=datetime.utcnow()
        )

        # Use fresh session for immediate visibility
        if db._global_engine:
            FreshSession = sessionmaker(bind=db._global_engine, expire_on_commit=False)
            fresh_db = FreshSession()
            try:
                fresh_db.add(command)
                fresh_db.commit()
                logger.warning(
                    f"Logged blocked command {command_id}: {blocked_reason} "
                    f"(tenant={tenant_id}, initiated_by={initiated_by})"
                )
            finally:
                fresh_db.close()
        else:
            self.db.add(command)
            self.db.commit()

        return command

    def _log_yolo_mode_execution(
        self,
        commands: List[str],
        shell: ShellIntegration,
        security_result: SecurityCheckResult,
        initiated_by: str
    ) -> None:
        """
        Log when a high-risk command is auto-approved via YOLO mode.

        This is important for audit trails - YOLO mode bypasses the approval
        workflow but we still want to track high-risk command executions.

        Args:
            commands: Commands being executed
            shell: Shell integration with YOLO mode enabled
            security_result: Security check result with risk details
            initiated_by: Who initiated the command
        """
        logger.warning(
            f"YOLO MODE: Auto-approving high-risk command on shell {shell.id} "
            f"(hostname={shell.hostname}, tenant={shell.tenant_id})\n"
            f"  Risk Level: {security_result.risk_level.value}\n"
            f"  Patterns Matched: {security_result.matched_patterns}\n"
            f"  Commands: {commands}\n"
            f"  Initiated By: {initiated_by}"
        )

    async def _handle_approval_required(
        self,
        commands: List[str],
        shell: ShellIntegration,
        tenant_id: str,
        initiated_by: str,
        agent_id: Optional[int],
        timeout_seconds: int,
        security_result: SecurityCheckResult,
        wait_for_result: bool
    ) -> CommandResult:
        """
        Handle commands that require approval before execution.

        Creates a pending approval request and returns immediately.
        The command will not execute until an admin approves it.

        Args:
            commands: Commands requiring approval
            shell: Target shell integration
            tenant_id: Tenant identifier
            initiated_by: Who initiated the command
            agent_id: Optional agent ID
            timeout_seconds: Timeout for execution after approval
            security_result: Security check result
            wait_for_result: Whether caller wanted to wait

        Returns:
            CommandResult with requires_approval=True
        """
        from services.shell_approval_service import get_approval_service
        from sqlalchemy.orm import sessionmaker
        import db

        command_id = str(uuid.uuid4())

        # Create command in pending_approval status
        command = ShellCommand(
            id=command_id,
            shell_id=shell.id,
            tenant_id=tenant_id,
            commands=commands,
            initiated_by=initiated_by,
            executed_by_agent_id=agent_id,
            status=CommandStatus.PENDING_APPROVAL.value,
            approval_required=True,
            timeout_seconds=timeout_seconds
        )

        # Use fresh session for insert
        if db._global_engine:
            FreshSession = sessionmaker(bind=db._global_engine, expire_on_commit=False)
            fresh_db = FreshSession()
            try:
                fresh_db.add(command)
                fresh_db.commit()
            finally:
                fresh_db.close()
        else:
            self.db.add(command)
            self.db.commit()

        # Create approval request and send notifications
        try:
            approval_service = get_approval_service(self.db)
            approval = approval_service.create_approval_request(
                command=command,
                security_result=security_result
            )

            # Send notification asynchronously
            try:
                await approval_service.send_approval_notification(approval)
            except Exception as e:
                logger.error(f"Failed to send approval notification: {e}")

        except Exception as e:
            logger.error(f"Failed to create approval request: {e}")

        logger.info(
            f"Command {command_id} requires approval "
            f"(risk: {security_result.risk_level.value}, "
            f"patterns: {security_result.matched_patterns})"
        )

        return CommandResult(
            success=False,  # Not executed yet
            command_id=command_id,
            status=CommandStatus.PENDING_APPROVAL.value,
            requires_approval=True,
            risk_level=security_result.risk_level.value,
            security_warnings=security_result.warnings,
            error_message=(
                f"Command requires approval. "
                f"Risk level: {security_result.risk_level.value.upper()}. "
                f"Patterns matched: {', '.join(security_result.matched_patterns)}"
            )
        )

    # =========================================================================
    # End Security Methods
    # =========================================================================

    def queue_command(
        self,
        shell_id: int,
        commands: List[str],
        initiated_by: str,
        tenant_id: str,
        agent_id: Optional[int] = None,
        timeout_seconds: int = 300
    ) -> ShellCommand:
        """
        Queue a command for execution by a beacon.

        Phase 18.4: Now tries to push command via WebSocket if beacon is connected.

        FIX (2026-01-30): Use a dedicated fresh session for the insert to ensure
        the command is immediately visible to beacon check-in sessions.

        FIX (2026-01-30 v2): Added explicit connection close and small delay
        to ensure SQLite fully releases locks and data is visible to other sessions.

        Args:
            shell_id: ID of the target ShellIntegration
            commands: List of commands to execute
            initiated_by: Identifier of who initiated (e.g., "agent:1", "user:email")
            tenant_id: Tenant identifier
            agent_id: Optional agent ID if initiated by agent
            timeout_seconds: Maximum time to wait for completion

        Returns:
            Created ShellCommand record
        """
        import time as time_module
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import text
        import db

        command_id = str(uuid.uuid4())

        command = ShellCommand(
            id=command_id,
            shell_id=shell_id,
            tenant_id=tenant_id,
            commands=commands,
            initiated_by=initiated_by,
            executed_by_agent_id=agent_id,
            status=CommandStatus.QUEUED.value,
            timeout_seconds=timeout_seconds
        )

        logger.debug(f"[SHELL-QUEUE] queue_command: id={command_id}, shell_id={shell_id}, commands={commands}, initiated_by={initiated_by}")

        if db._global_engine:
            # Create a fresh session with explicit autocommit behavior
            FreshSession = sessionmaker(
                bind=db._global_engine,
                expire_on_commit=False  # Keep object usable after commit
            )
            fresh_db = FreshSession()
            try:
                fresh_db.add(command)
                fresh_db.commit()

                # FIX: Force SQLite to checkpoint/sync the write
                # This ensures the data is actually written to disk and visible to other connections
                fresh_db.execute(text("SELECT 1"))  # Force any pending operations

                logger.debug(f"[SHELL-QUEUE] Committed command {command_id} with status=queued")

                # Verify in a SEPARATE fresh session to confirm visibility
                verify_session = FreshSession()
                try:
                    verify = verify_session.query(ShellCommand).filter(ShellCommand.id == command_id).first()
                    if verify:
                        logger.debug(f"[SHELL-QUEUE] Verified: id={verify.id[:8]}, status={verify.status}, shell_id={verify.shell_id}")
                    else:
                        logger.error(f"[SHELL-QUEUE] CRITICAL: Command {command_id} NOT visible in verify session!")
                finally:
                    verify_session.close()

            except Exception as e:
                fresh_db.rollback()
                logger.error(f"[SHELL-QUEUE] Failed to queue command: {e}")
                raise
            finally:
                fresh_db.close()

            # FIX: Small delay to ensure SQLite fully releases locks
            # This gives the database time to complete the transaction before beacon polls
            time_module.sleep(0.1)  # 100ms delay

        else:
            logger.debug("[SHELL-QUEUE] FALLBACK: Using passed session (db._global_engine is None)")
            self.db.add(command)
            self.db.commit()
            self.db.refresh(command)

        # Phase 18.4: Try to push via WebSocket if beacon is connected
        self._try_push_command(shell_id, command)

        return command

    def _try_push_command(self, shell_id: int, command: ShellCommand):
        """
        Attempt to push command to beacon via WebSocket.

        If beacon is connected, command is sent immediately and status updated to 'sent'.
        If beacon is not connected, command remains 'queued' for HTTP polling.

        Args:
            shell_id: Target ShellIntegration ID
            command: ShellCommand to push
        """
        if not manager.is_beacon_online(shell_id):
            logger.debug(f"Beacon {shell_id} not connected, command {command.id} will be polled")
            return

        # Create async task to push the command
        try:
            # Get the current event loop or create one
            try:
                loop = asyncio.get_running_loop()
                # We're in an async context, create a task
                asyncio.create_task(self._async_push_command(shell_id, command))
            except RuntimeError:
                # No running loop - we're in a sync context
                # Use asyncio.run in a thread-safe way
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(self._async_push_command(shell_id, command))
                finally:
                    loop.close()
        except Exception as e:
            logger.error(f"Error pushing command {command.id} to beacon: {e}")

    async def _async_push_command(self, shell_id: int, command: ShellCommand):
        """
        Async helper to push command to beacon.

        Args:
            shell_id: Target ShellIntegration ID
            command: ShellCommand to push
        """
        try:
            success = await manager.send_to_beacon(shell_id, {
                "type": "command",
                "id": command.id,
                "commands": command.commands,
                "timeout": command.timeout_seconds
            })

            if success:
                # Update command status to 'sent'
                command.status = CommandStatus.SENT.value
                command.sent_at = datetime.utcnow()
                self.db.commit()
                logger.info(f"Pushed command {command.id} to beacon {shell_id} via WebSocket")
            else:
                logger.debug(f"Failed to push command {command.id} to beacon {shell_id}")

        except Exception as e:
            logger.error(f"Error in async push for command {command.id}: {e}")

    async def wait_for_completion_async(
        self,
        command_id: str,
        timeout_seconds: int = 60,
        poll_interval: float = 1.0
    ) -> CommandResult:
        """
        Wait for a command to complete by polling the database (ASYNC version).

        FIX (2026-01-30): This async version uses asyncio.sleep() instead of time.sleep()
        to avoid blocking the event loop and allow other requests (like beacon checkins)
        to be processed during the wait.

        Args:
            command_id: UUID of the command
            timeout_seconds: Maximum time to wait
            poll_interval: Time between polls in seconds

        Returns:
            CommandResult with execution details
        """
        from sqlalchemy.orm import sessionmaker
        import db

        start_time = time.time()
        deadline = start_time + timeout_seconds

        while time.time() < deadline:
            # Use a fresh session for each poll to see beacon's commits
            if db._global_engine:
                FreshSession = sessionmaker(bind=db._global_engine)
                poll_db = FreshSession()
                try:
                    command = poll_db.query(ShellCommand).filter(
                        ShellCommand.id == command_id
                    ).first()
                finally:
                    poll_db.close()
            else:
                # Fallback to original session with expire
                self.db.expire_all()
                command = self.db.query(ShellCommand).filter(
                    ShellCommand.id == command_id
                ).first()

            if not command:
                return CommandResult(
                    success=False,
                    command_id=command_id,
                    status="not_found",
                    error_message="Command not found"
                )

            # Check if completed
            if command.status in [
                CommandStatus.COMPLETED.value,
                CommandStatus.FAILED.value,
                CommandStatus.CANCELLED.value
            ]:
                return CommandResult(
                    success=command.status == CommandStatus.COMPLETED.value,
                    command_id=command_id,
                    status=command.status,
                    exit_code=command.exit_code,
                    stdout=command.stdout,
                    stderr=command.stderr,
                    execution_time_ms=command.execution_time_ms,
                    error_message=command.error_message
                )

            # CRITICAL FIX: Use asyncio.sleep() to not block the event loop
            # This allows beacon checkin requests to be processed during the wait
            await asyncio.sleep(poll_interval)

        # Timeout reached
        logger.warning(f"Command {command_id} timed out after {timeout_seconds}s")

        # Mark command as timed out using fresh session
        if db._global_engine:
            FreshSession = sessionmaker(bind=db._global_engine)
            timeout_db = FreshSession()
            try:
                command = timeout_db.query(ShellCommand).filter(
                    ShellCommand.id == command_id
                ).first()

                if command and command.status in [
                    CommandStatus.QUEUED.value,
                    CommandStatus.SENT.value,
                    CommandStatus.EXECUTING.value
                ]:
                    command.status = CommandStatus.TIMEOUT.value
                    command.error_message = f"Timed out after {timeout_seconds} seconds"
                    timeout_db.commit()
            finally:
                timeout_db.close()
        else:
            command = self.db.query(ShellCommand).filter(
                ShellCommand.id == command_id
            ).first()

            if command and command.status in [
                CommandStatus.QUEUED.value,
                CommandStatus.SENT.value,
                CommandStatus.EXECUTING.value
            ]:
                command.status = CommandStatus.TIMEOUT.value
                command.error_message = f"Timed out after {timeout_seconds} seconds"
                self.db.commit()

        return CommandResult(
            success=False,
            command_id=command_id,
            status=CommandStatus.TIMEOUT.value,
            error_message=f"Timed out after {timeout_seconds} seconds",
            timed_out=True
        )

    def wait_for_completion(
        self,
        command_id: str,
        timeout_seconds: int = 60,
        poll_interval: float = 1.0
    ) -> CommandResult:
        """
        Wait for a command to complete by polling the database (SYNC version).

        DEPRECATED: Use wait_for_completion_async() in async contexts.
        This sync version blocks the thread and should only be used in sync contexts.

        Args:
            command_id: UUID of the command
            timeout_seconds: Maximum time to wait
            poll_interval: Time between polls in seconds

        Returns:
            CommandResult with execution details
        """
        from sqlalchemy.orm import sessionmaker
        import db

        start_time = time.time()
        deadline = start_time + timeout_seconds

        while time.time() < deadline:
            if db._global_engine:
                FreshSession = sessionmaker(bind=db._global_engine)
                poll_db = FreshSession()
                try:
                    command = poll_db.query(ShellCommand).filter(
                        ShellCommand.id == command_id
                    ).first()
                finally:
                    poll_db.close()
            else:
                self.db.expire_all()
                command = self.db.query(ShellCommand).filter(
                    ShellCommand.id == command_id
                ).first()

            if not command:
                return CommandResult(
                    success=False,
                    command_id=command_id,
                    status="not_found",
                    error_message="Command not found"
                )

            if command.status in [
                CommandStatus.COMPLETED.value,
                CommandStatus.FAILED.value,
                CommandStatus.CANCELLED.value
            ]:
                return CommandResult(
                    success=command.status == CommandStatus.COMPLETED.value,
                    command_id=command_id,
                    status=command.status,
                    exit_code=command.exit_code,
                    stdout=command.stdout,
                    stderr=command.stderr,
                    execution_time_ms=command.execution_time_ms,
                    error_message=command.error_message
                )

            time.sleep(poll_interval)

        logger.warning(f"Command {command_id} timed out after {timeout_seconds}s")

        if db._global_engine:
            FreshSession = sessionmaker(bind=db._global_engine)
            timeout_db = FreshSession()
            try:
                command = timeout_db.query(ShellCommand).filter(
                    ShellCommand.id == command_id
                ).first()

                if command and command.status in [
                    CommandStatus.QUEUED.value,
                    CommandStatus.SENT.value,
                    CommandStatus.EXECUTING.value
                ]:
                    command.status = CommandStatus.TIMEOUT.value
                    command.error_message = f"Timed out after {timeout_seconds} seconds"
                    timeout_db.commit()
            finally:
                timeout_db.close()
        else:
            command = self.db.query(ShellCommand).filter(
                ShellCommand.id == command_id
            ).first()

            if command and command.status in [
                CommandStatus.QUEUED.value,
                CommandStatus.SENT.value,
                CommandStatus.EXECUTING.value
            ]:
                command.status = CommandStatus.TIMEOUT.value
                command.error_message = f"Timed out after {timeout_seconds} seconds"
                self.db.commit()

        return CommandResult(
            success=False,
            command_id=command_id,
            status=CommandStatus.TIMEOUT.value,
            error_message=f"Timed out after {timeout_seconds} seconds",
            timed_out=True
        )

    def get_command(self, command_id: str) -> Optional[ShellCommand]:
        """
        Get a command by ID.

        Args:
            command_id: UUID of the command

        Returns:
            ShellCommand or None
        """
        return self.db.query(ShellCommand).filter(
            ShellCommand.id == command_id
        ).first()

    def get_command_result(self, command_id: str) -> CommandResult:
        """
        Get the result of a command (without waiting).

        Args:
            command_id: UUID of the command

        Returns:
            CommandResult with current state
        """
        command = self.get_command(command_id)

        if not command:
            return CommandResult(
                success=False,
                command_id=command_id,
                status="not_found",
                error_message="Command not found"
            )

        return CommandResult(
            success=command.status == CommandStatus.COMPLETED.value,
            command_id=command_id,
            status=command.status,
            exit_code=command.exit_code,
            stdout=command.stdout,
            stderr=command.stderr,
            execution_time_ms=command.execution_time_ms,
            error_message=command.error_message,
            timed_out=command.status == CommandStatus.TIMEOUT.value
        )

    async def execute_command_async(
        self,
        script: str,
        target: str,
        tenant_id: str,
        initiated_by: str,
        agent_id: Optional[int] = None,
        timeout_seconds: int = 60,
        wait_for_result: bool = True
    ) -> CommandResult:
        """
        High-level async method to execute a shell command.

        SECURITY (CRIT-005): Commands are now validated against security policies
        before being queued. Dangerous commands are blocked, high-risk commands
        require approval (unless YOLO mode is enabled).

        FIX (2026-01-30): This async version uses asyncio.sleep() for waiting,
        which doesn't block the event loop and allows beacon checkins to be processed.

        Args:
            script: Command or multi-line script to execute
            target: Target - "default", hostname, or "@all"
            tenant_id: Tenant identifier
            initiated_by: Who initiated the command
            agent_id: Optional agent ID
            timeout_seconds: Max wait time
            wait_for_result: If False, return immediately after queueing

        Returns:
            CommandResult with execution details
        """
        # Parse script into commands (split by newline)
        commands = [cmd.strip() for cmd in script.strip().split('\n') if cmd.strip()]

        if not commands:
            return CommandResult(
                success=False,
                command_id="",
                status="invalid",
                error_message="No commands to execute"
            )

        # Handle @all target - security check against first shell
        if target == "@all":
            shells = self.get_available_shells(tenant_id)
            if shells:
                # Use first shell for security check (should have consistent policies)
                allowed, security_result, error_msg = self._check_command_security(
                    commands, shells[0], tenant_id
                )

                if not allowed:
                    # Log blocked attempt for each shell
                    for shell in shells:
                        self._log_blocked_command(
                            commands, shell.id, tenant_id, initiated_by,
                            error_msg, security_result, agent_id
                        )
                    return CommandResult(
                        success=False,
                        command_id="",
                        status=CommandStatus.BLOCKED.value,
                        blocked=True,
                        blocked_reason=error_msg,
                        error_message=f"Command blocked: {error_msg}",
                        risk_level=security_result.risk_level.value if security_result else None,
                        security_warnings=security_result.warnings if security_result else []
                    )

                # Check if approval required
                if security_result and security_result.requires_approval:
                    # Check if ANY shell has YOLO mode - if all do, auto-approve
                    all_yolo = all(s.yolo_mode for s in shells)
                    if all_yolo:
                        for shell in shells:
                            self._log_yolo_mode_execution(commands, shell, security_result, initiated_by)
                    else:
                        # Need approval - use first shell for the request
                        return await self._handle_approval_required(
                            commands=commands,
                            shell=shells[0],
                            tenant_id=tenant_id,
                            initiated_by=initiated_by,
                            agent_id=agent_id,
                            timeout_seconds=timeout_seconds,
                            security_result=security_result,
                            wait_for_result=wait_for_result
                        )

            return await self._execute_on_all_async(
                commands=commands,
                tenant_id=tenant_id,
                initiated_by=initiated_by,
                agent_id=agent_id,
                timeout_seconds=timeout_seconds,
                wait_for_result=wait_for_result
            )

        # Resolve target
        shell, error = self.find_shell_by_target(target, tenant_id)

        if error:
            return CommandResult(
                success=False,
                command_id="",
                status="invalid_target",
                error_message=error
            )

        if not shell:
            return CommandResult(
                success=False,
                command_id="",
                status="no_shell",
                error_message="No shell available"
            )

        # =====================================================================
        # SECURITY CHECK (CRIT-005 Fix)
        # =====================================================================
        allowed, security_result, error_msg = self._check_command_security(
            commands, shell, tenant_id
        )

        if not allowed:
            # Log the blocked attempt for audit
            blocked_cmd = self._log_blocked_command(
                commands, shell.id, tenant_id, initiated_by,
                error_msg, security_result, agent_id
            )
            return CommandResult(
                success=False,
                command_id=blocked_cmd.id,
                status=CommandStatus.BLOCKED.value,
                blocked=True,
                blocked_reason=error_msg,
                error_message=f"Command blocked: {error_msg}",
                risk_level=security_result.risk_level.value if security_result else None,
                security_warnings=security_result.warnings if security_result else []
            )

        # Check if approval is required
        if security_result and security_result.requires_approval:
            # Check YOLO mode - auto-approve if enabled
            if shell.yolo_mode:
                self._log_yolo_mode_execution(commands, shell, security_result, initiated_by)
                # Continue to queue_command() - command will execute
            else:
                # Approval required and YOLO mode not enabled
                return await self._handle_approval_required(
                    commands=commands,
                    shell=shell,
                    tenant_id=tenant_id,
                    initiated_by=initiated_by,
                    agent_id=agent_id,
                    timeout_seconds=timeout_seconds,
                    security_result=security_result,
                    wait_for_result=wait_for_result
                )

        # Track if this was YOLO mode auto-approved
        yolo_auto_approved = (
            security_result and
            security_result.requires_approval and
            shell.yolo_mode
        )
        # =====================================================================
        # END SECURITY CHECK
        # =====================================================================

        # =====================================================================
        # SENTINEL LLM ANALYSIS (Phase 20)
        # Only runs AFTER pattern matching passes, for commands that need
        # deeper semantic analysis. Check sentinel_protected flag on beacon.
        # =====================================================================
        if getattr(shell, 'sentinel_protected', False):
            try:
                from services.sentinel_service import SentinelService
                sentinel = SentinelService(self.db, tenant_id)

                # Run async Sentinel analysis
                script = "\n".join(commands)
                sentinel_result = await sentinel.analyze_shell_command(
                    command=script,
                    agent_id=agent_id,
                    sender_key=initiated_by,
                    skill_type="shell",
                )

                if sentinel_result.is_threat_detected and sentinel_result.action == "blocked":
                    logger.warning(
                        f"SENTINEL: Shell command blocked - {sentinel_result.detection_type}: {sentinel_result.threat_reason}"
                    )
                    # Log the blocked attempt
                    blocked_cmd = self._log_blocked_command(
                        commands, shell.id, tenant_id, initiated_by,
                        f"Sentinel: {sentinel_result.threat_reason}",
                        security_result, agent_id
                    )
                    return CommandResult(
                        success=False,
                        command_id=blocked_cmd.id,
                        status=CommandStatus.BLOCKED.value,
                        blocked=True,
                        blocked_reason=f"Sentinel Security: {sentinel_result.threat_reason}",
                        error_message=f"Command blocked by Sentinel AI: {sentinel_result.threat_reason}",
                        risk_level=security_result.risk_level.value if security_result else "high",
                        security_warnings=[f"Sentinel detected: {sentinel_result.detection_type}"]
                    )
                elif sentinel_result.is_threat_detected and sentinel_result.action == "warned":
                    logger.warning(
                        f"SENTINEL: Shell command flagged (warning) - {sentinel_result.detection_type}: {sentinel_result.threat_reason}"
                    )
                    # Add warning but continue execution
                    if security_result:
                        security_result.warnings.append(
                            f"Sentinel warning: {sentinel_result.threat_reason}"
                        )
            except Exception as e:
                # Fail open - don't block commands if Sentinel fails
                logger.error(f"Sentinel shell analysis failed: {e}", exc_info=True)
        # =====================================================================
        # END SENTINEL ANALYSIS
        # =====================================================================

        # Queue the command (passed security check)
        command = self.queue_command(
            shell_id=shell.id,
            commands=commands,
            initiated_by=initiated_by,
            tenant_id=tenant_id,
            agent_id=agent_id,
            timeout_seconds=timeout_seconds
        )

        # Fire and forget mode
        if not wait_for_result:
            return CommandResult(
                success=True,
                command_id=command.id,
                status=CommandStatus.QUEUED.value,
                error_message=None,
                risk_level=security_result.risk_level.value if security_result else "low",
                security_warnings=security_result.warnings if security_result else [],
                yolo_mode_auto_approved=yolo_auto_approved
            )

        # Wait for result using async version
        result = await self.wait_for_completion_async(
            command_id=command.id,
            timeout_seconds=timeout_seconds
        )

        # Add YOLO mode indicator to result
        if yolo_auto_approved:
            result.yolo_mode_auto_approved = True

        return result

    def execute_command(
        self,
        script: str,
        target: str,
        tenant_id: str,
        initiated_by: str,
        agent_id: Optional[int] = None,
        timeout_seconds: int = 60,
        wait_for_result: bool = True
    ) -> CommandResult:
        """
        High-level sync method to execute a shell command.

        DEPRECATED: Use execute_command_async() in async contexts.
        This version blocks the thread when waiting for results.

        SECURITY (CRIT-005): Commands are validated against security policies.
        Note: Approval workflow is not fully supported in sync mode - high-risk
        commands will be blocked rather than pending approval.

        Args:
            script: Command or multi-line script to execute
            target: Target - "default", hostname, or "@all"
            tenant_id: Tenant identifier
            initiated_by: Who initiated the command
            agent_id: Optional agent ID
            timeout_seconds: Max wait time
            wait_for_result: If False, return immediately after queueing

        Returns:
            CommandResult with execution details
        """
        # Parse script into commands (split by newline)
        commands = [cmd.strip() for cmd in script.strip().split('\n') if cmd.strip()]

        if not commands:
            return CommandResult(
                success=False,
                command_id="",
                status="invalid",
                error_message="No commands to execute"
            )

        # Handle @all target
        if target == "@all":
            # Security check for @all - simplified for sync mode
            shells = self.get_available_shells(tenant_id)
            if shells:
                allowed, security_result, error_msg = self._check_command_security(
                    commands, shells[0], tenant_id
                )
                if not allowed:
                    for shell in shells:
                        self._log_blocked_command(
                            commands, shell.id, tenant_id, initiated_by,
                            error_msg, security_result, agent_id
                        )
                    return CommandResult(
                        success=False,
                        command_id="",
                        status=CommandStatus.BLOCKED.value,
                        blocked=True,
                        blocked_reason=error_msg,
                        error_message=f"Command blocked: {error_msg}"
                    )
                # In sync mode, if approval required and not YOLO mode, block
                if security_result and security_result.requires_approval:
                    all_yolo = all(s.yolo_mode for s in shells)
                    if not all_yolo:
                        return CommandResult(
                            success=False,
                            command_id="",
                            status=CommandStatus.BLOCKED.value,
                            blocked=True,
                            blocked_reason="High-risk command requires approval (use async API)",
                            error_message="Command requires approval - use async API for approval workflow",
                            requires_approval=True,
                            risk_level=security_result.risk_level.value
                        )

            return self._execute_on_all(
                commands=commands,
                tenant_id=tenant_id,
                initiated_by=initiated_by,
                agent_id=agent_id,
                timeout_seconds=timeout_seconds,
                wait_for_result=wait_for_result
            )

        # Resolve target
        shell, error = self.find_shell_by_target(target, tenant_id)

        if error:
            return CommandResult(
                success=False,
                command_id="",
                status="invalid_target",
                error_message=error
            )

        if not shell:
            return CommandResult(
                success=False,
                command_id="",
                status="no_shell",
                error_message="No shell available"
            )

        # =====================================================================
        # SECURITY CHECK (CRIT-005 Fix) - Sync version
        # =====================================================================
        allowed, security_result, error_msg = self._check_command_security(
            commands, shell, tenant_id
        )

        if not allowed:
            blocked_cmd = self._log_blocked_command(
                commands, shell.id, tenant_id, initiated_by,
                error_msg, security_result, agent_id
            )
            return CommandResult(
                success=False,
                command_id=blocked_cmd.id,
                status=CommandStatus.BLOCKED.value,
                blocked=True,
                blocked_reason=error_msg,
                error_message=f"Command blocked: {error_msg}",
                risk_level=security_result.risk_level.value if security_result else None,
                security_warnings=security_result.warnings if security_result else []
            )

        # Check if approval required
        yolo_auto_approved = False
        if security_result and security_result.requires_approval:
            if shell.yolo_mode:
                self._log_yolo_mode_execution(commands, shell, security_result, initiated_by)
                yolo_auto_approved = True
            else:
                # Sync mode doesn't support approval workflow
                return CommandResult(
                    success=False,
                    command_id="",
                    status=CommandStatus.BLOCKED.value,
                    blocked=True,
                    blocked_reason="High-risk command requires approval (use async API)",
                    error_message="Command requires approval - use async API for approval workflow",
                    requires_approval=True,
                    risk_level=security_result.risk_level.value
                )
        # =====================================================================
        # END SECURITY CHECK
        # =====================================================================

        # Queue the command
        command = self.queue_command(
            shell_id=shell.id,
            commands=commands,
            initiated_by=initiated_by,
            tenant_id=tenant_id,
            agent_id=agent_id,
            timeout_seconds=timeout_seconds
        )

        # Fire and forget mode
        if not wait_for_result:
            return CommandResult(
                success=True,
                command_id=command.id,
                status=CommandStatus.QUEUED.value,
                error_message=None,
                yolo_mode_auto_approved=yolo_auto_approved
            )

        # Wait for result
        result = self.wait_for_completion(
            command_id=command.id,
            timeout_seconds=timeout_seconds
        )
        if yolo_auto_approved:
            result.yolo_mode_auto_approved = True
        return result

    async def _execute_on_all_async(
        self,
        commands: List[str],
        tenant_id: str,
        initiated_by: str,
        agent_id: Optional[int],
        timeout_seconds: int,
        wait_for_result: bool
    ) -> CommandResult:
        """
        Execute command on all available shells (async version).
        """
        shells = self.get_available_shells(tenant_id)

        if not shells:
            return CommandResult(
                success=False,
                command_id="",
                status="no_shells",
                error_message="No shell integrations available"
            )

        results = []
        all_success = True
        combined_stdout = []
        combined_stderr = []

        for shell in shells:
            command = self.queue_command(
                shell_id=shell.id,
                commands=commands,
                initiated_by=initiated_by,
                tenant_id=tenant_id,
                agent_id=agent_id,
                timeout_seconds=timeout_seconds
            )

            if wait_for_result:
                result = await self.wait_for_completion_async(
                    command_id=command.id,
                    timeout_seconds=timeout_seconds
                )

                hostname = shell.hostname or f"shell-{shell.id}"

                if result.stdout:
                    combined_stdout.append(f"=== {hostname} ===\n{result.stdout}")
                if result.stderr:
                    combined_stderr.append(f"=== {hostname} ===\n{result.stderr}")

                if not result.success:
                    all_success = False

                results.append({
                    "shell_id": shell.id,
                    "hostname": hostname,
                    "result": result
                })
            else:
                results.append({
                    "shell_id": shell.id,
                    "hostname": shell.hostname or f"shell-{shell.id}",
                    "command_id": command.id
                })

        if wait_for_result:
            return CommandResult(
                success=all_success,
                command_id=",".join([str(r.get("result", {}).command_id) for r in results if r.get("result")]),
                status=CommandStatus.COMPLETED.value if all_success else CommandStatus.FAILED.value,
                exit_code=0 if all_success else 1,
                stdout="\n\n".join(combined_stdout) if combined_stdout else None,
                stderr="\n\n".join(combined_stderr) if combined_stderr else None
            )
        else:
            return CommandResult(
                success=True,
                command_id=",".join([r.get("command_id", "") for r in results]),
                status=CommandStatus.QUEUED.value,
                error_message=f"Queued on {len(shells)} shell(s)"
            )

    def _execute_on_all(
        self,
        commands: List[str],
        tenant_id: str,
        initiated_by: str,
        agent_id: Optional[int],
        timeout_seconds: int,
        wait_for_result: bool
    ) -> CommandResult:
        """
        Execute command on all available shells.

        Commands are queued sequentially and results are aggregated.
        """
        shells = self.get_available_shells(tenant_id)

        if not shells:
            return CommandResult(
                success=False,
                command_id="",
                status="no_shells",
                error_message="No shell integrations available"
            )

        results = []
        all_success = True
        combined_stdout = []
        combined_stderr = []

        for shell in shells:
            # Queue command for each shell
            command = self.queue_command(
                shell_id=shell.id,
                commands=commands,
                initiated_by=initiated_by,
                tenant_id=tenant_id,
                agent_id=agent_id,
                timeout_seconds=timeout_seconds
            )

            if wait_for_result:
                result = self.wait_for_completion(
                    command_id=command.id,
                    timeout_seconds=timeout_seconds
                )

                hostname = shell.hostname or f"shell-{shell.id}"

                if result.stdout:
                    combined_stdout.append(f"=== {hostname} ===\n{result.stdout}")
                if result.stderr:
                    combined_stderr.append(f"=== {hostname} ===\n{result.stderr}")

                if not result.success:
                    all_success = False

                results.append({
                    "shell_id": shell.id,
                    "hostname": hostname,
                    "result": result
                })
            else:
                results.append({
                    "shell_id": shell.id,
                    "hostname": shell.hostname or f"shell-{shell.id}",
                    "command_id": command.id
                })

        # Aggregate results
        if wait_for_result:
            return CommandResult(
                success=all_success,
                command_id=",".join([str(r.get("result", {}).command_id) for r in results if r.get("result")]),
                status=CommandStatus.COMPLETED.value if all_success else CommandStatus.FAILED.value,
                exit_code=0 if all_success else 1,
                stdout="\n\n".join(combined_stdout) if combined_stdout else None,
                stderr="\n\n".join(combined_stderr) if combined_stderr else None
            )
        else:
            return CommandResult(
                success=True,
                command_id=",".join([r.get("command_id", "") for r in results]),
                status=CommandStatus.QUEUED.value,
                error_message=f"Queued on {len(shells)} shell(s)"
            )
