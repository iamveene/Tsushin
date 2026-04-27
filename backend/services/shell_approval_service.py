"""
Shell Approval Service - Phase 5: Security & Approval Workflow

Manages the approval workflow for high-risk shell commands:
- Create pending approvals for risky commands
- Process approval/rejection
- Notify users via WebSocket and optional WhatsApp
- Enhanced audit logging
"""

import logging
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.orm import Session

from models import ShellCommand, ShellIntegration
from services.shell_security_service import (
    get_security_service,
    SecurityCheckResult,
    RiskLevel
)

logger = logging.getLogger(__name__)


class ApprovalStatus(Enum):
    """Status of an approval request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    AUTO_APPROVED = "auto_approved"


@dataclass
class ApprovalRequest:
    """Approval request for a shell command."""
    command_id: str
    shell_id: int
    tenant_id: str
    commands: List[str]
    initiated_by: str
    risk_level: str
    security_warnings: List[str]
    status: ApprovalStatus
    created_at: datetime
    expires_at: datetime
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None


class ShellApprovalService:
    """
    Service for managing shell command approvals.

    Provides:
    - Approval request creation
    - Approval/rejection processing
    - Expiration handling
    - Notification dispatch
    - Audit logging
    """

    # Default approval expiration in minutes
    DEFAULT_EXPIRATION_MINUTES = 60

    def __init__(self, db: Session):
        """
        Initialize the approval service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self.security_service = get_security_service()

    def create_approval_request(
        self,
        command: ShellCommand,
        security_result: SecurityCheckResult,
        expiration_minutes: Optional[int] = None
    ) -> ApprovalRequest:
        """
        Create an approval request for a high-risk command.

        Args:
            command: The ShellCommand requiring approval
            security_result: Security check result with risk details
            expiration_minutes: Optional custom expiration time

        Returns:
            ApprovalRequest object
        """
        expiration = expiration_minutes or self.DEFAULT_EXPIRATION_MINUTES
        now = datetime.utcnow()

        # Update command status to pending approval
        command.status = "pending_approval"
        command.approval_required = True
        self.db.commit()

        approval = ApprovalRequest(
            command_id=command.id,
            shell_id=command.shell_id,
            tenant_id=command.tenant_id,
            commands=command.commands,
            initiated_by=command.initiated_by,
            risk_level=security_result.risk_level.value,
            security_warnings=security_result.warnings,
            status=ApprovalStatus.PENDING,
            created_at=now,
            expires_at=now + timedelta(minutes=expiration)
        )

        logger.info(
            f"Created approval request for command {command.id} "
            f"(risk: {security_result.risk_level.value})"
        )

        # Log audit entry
        self._log_audit_event(
            command_id=command.id,
            action="approval_requested",
            details={
                "risk_level": security_result.risk_level.value,
                "warnings": security_result.warnings,
                "initiated_by": command.initiated_by,
                "commands": command.commands
            }
        )

        return approval

    def approve_command(
        self,
        command_id: str,
        approved_by: str,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Approve a pending command.

        Args:
            command_id: ID of the command to approve
            approved_by: User who approved the command
            notes: Optional approval notes

        Returns:
            Dict with result details
        """
        command = self.db.query(ShellCommand).filter(
            ShellCommand.id == command_id
        ).first()

        if not command:
            return {"success": False, "error": "Command not found"}

        if command.status != "pending_approval":
            return {
                "success": False,
                "error": f"Command is not pending approval (status: {command.status})"
            }

        # Update command status
        command.status = "queued"  # Ready for beacon to pick up
        command.approval_required = False
        command.approved_by_user_id = self._get_user_id(approved_by)
        command.approved_at = datetime.utcnow()

        self.db.commit()

        logger.info(f"Command {command_id} approved by {approved_by}")

        # Log audit entry
        self._log_audit_event(
            command_id=command_id,
            action="approved",
            details={
                "approved_by": approved_by,
                "notes": notes,
                "risk_level": "high"  # Only high-risk commands need approval
            }
        )

        # Push command to beacon if connected
        self._push_approved_command(command)

        return {
            "success": True,
            "command_id": command_id,
            "status": "queued",
            "message": "Command approved and queued for execution"
        }

    def reject_command(
        self,
        command_id: str,
        rejected_by: str,
        reason: str
    ) -> Dict[str, Any]:
        """
        Reject a pending command.

        Args:
            command_id: ID of the command to reject
            rejected_by: User who rejected the command
            reason: Reason for rejection

        Returns:
            Dict with result details
        """
        command = self.db.query(ShellCommand).filter(
            ShellCommand.id == command_id
        ).first()

        if not command:
            return {"success": False, "error": "Command not found"}

        if command.status != "pending_approval":
            return {
                "success": False,
                "error": f"Command is not pending approval (status: {command.status})"
            }

        # Update command status
        command.status = "rejected"
        command.error_message = f"Rejected by {rejected_by}: {reason}"
        command.completed_at = datetime.utcnow()

        self.db.commit()

        logger.info(f"Command {command_id} rejected by {rejected_by}: {reason}")

        # Log audit entry
        self._log_audit_event(
            command_id=command_id,
            action="rejected",
            details={
                "rejected_by": rejected_by,
                "reason": reason
            }
        )

        return {
            "success": True,
            "command_id": command_id,
            "status": "rejected",
            "message": f"Command rejected: {reason}"
        }

    def get_pending_approvals(
        self,
        tenant_id: str,
        shell_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all pending approval requests for a tenant.

        Args:
            tenant_id: Tenant identifier
            shell_id: Optional filter by shell integration

        Returns:
            List of pending approval details
        """
        query = self.db.query(ShellCommand).filter(
            ShellCommand.tenant_id == tenant_id,
            ShellCommand.status == "pending_approval"
        )

        if shell_id:
            query = query.filter(ShellCommand.shell_id == shell_id)

        commands = query.order_by(ShellCommand.queued_at.desc()).all()

        now = datetime.utcnow()
        results = []

        for cmd in commands:
            # Check if expired
            expiration = cmd.queued_at + timedelta(minutes=self.DEFAULT_EXPIRATION_MINUTES)
            is_expired = now > expiration

            if is_expired:
                # Auto-expire the command
                cmd.status = "expired"
                cmd.error_message = "Approval request expired"
                cmd.completed_at = now
                self.db.commit()
                continue

            # Get security analysis
            security_result = self.security_service.check_commands(cmd.commands)

            results.append({
                "command_id": cmd.id,
                "shell_id": cmd.shell_id,
                "commands": cmd.commands,
                "initiated_by": cmd.initiated_by,
                "queued_at": cmd.queued_at.isoformat(),
                "expires_at": expiration.isoformat(),
                "time_remaining_seconds": int((expiration - now).total_seconds()),
                "risk_level": security_result[1].risk_level.value if security_result[0] else "unknown",
                "security_warnings": security_result[1].warnings if security_result[0] else [],
            })

        return results

    def expire_old_approvals(self) -> int:
        """
        Expire approval requests that have passed their deadline.

        Returns:
            Number of expired requests
        """
        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=self.DEFAULT_EXPIRATION_MINUTES)

        expired = self.db.query(ShellCommand).filter(
            ShellCommand.status == "pending_approval",
            ShellCommand.queued_at < cutoff
        ).all()

        count = 0
        for cmd in expired:
            cmd.status = "expired"
            cmd.error_message = "Approval request expired"
            cmd.completed_at = now
            count += 1

            self._log_audit_event(
                command_id=cmd.id,
                action="expired",
                details={"reason": "Approval timeout"}
            )

        if count > 0:
            self.db.commit()
            logger.info(f"Expired {count} pending approval requests")

        return count

    async def send_approval_notification(
        self,
        approval: ApprovalRequest,
        notify_whatsapp: bool = False,
        whatsapp_numbers: Optional[List[str]] = None
    ) -> Dict[str, bool]:
        """
        Send notifications for an approval request.

        Args:
            approval: The approval request
            notify_whatsapp: Whether to send WhatsApp notifications
            whatsapp_numbers: Phone numbers for WhatsApp notifications

        Returns:
            Dict with notification results per channel
        """
        from websocket_manager import manager

        results = {"websocket": False, "whatsapp": False}

        # Build notification payload
        notification = {
            "type": "shell_approval_required",
            "command_id": approval.command_id,
            "shell_id": approval.shell_id,
            "commands": approval.commands,
            "risk_level": approval.risk_level,
            "warnings": approval.security_warnings,
            "initiated_by": approval.initiated_by,
            "expires_at": approval.expires_at.isoformat(),
            "message": f"🔐 Shell command requires approval\nRisk: {approval.risk_level.upper()}\nCommands: {'; '.join(approval.commands[:3])}"
        }

        # Send WebSocket notification to all admin connections
        try:
            await manager.broadcast_to_tenant(
                tenant_id=approval.tenant_id,
                message=notification,
                permission_required="shell.approve"
            )
            results["websocket"] = True
        except Exception as e:
            logger.error(f"Failed to send WebSocket notification: {e}")

        # Send WhatsApp notification if configured
        if notify_whatsapp and whatsapp_numbers:
            try:
                message = (
                    f"🔐 *Shell Approval Required*\n\n"
                    f"Risk Level: {approval.risk_level.upper()}\n"
                    f"Commands:\n```\n{chr(10).join(approval.commands)}\n```\n\n"
                    f"Initiated by: {approval.initiated_by}\n"
                    f"Expires: {approval.expires_at.strftime('%H:%M:%S UTC')}\n\n"
                    f"Reply APPROVE {approval.command_id[:8]} or REJECT {approval.command_id[:8]}"
                )

                # Import WhatsApp sender
                from mcp_sender import send_whatsapp_message

                for number in whatsapp_numbers:
                    await send_whatsapp_message(number, message)

                results["whatsapp"] = True
            except Exception as e:
                logger.error(f"Failed to send WhatsApp notification: {e}")

        return results

    def _push_approved_command(self, command: ShellCommand):
        """Push an approved command to the beacon via WebSocket if connected."""
        try:
            from websocket_manager import manager
            import asyncio

            if manager.is_beacon_online(command.shell_id):
                # Push command to beacon
                asyncio.create_task(
                    manager.send_to_beacon(command.shell_id, {
                        "type": "command",
                        "id": command.id,
                        "commands": command.commands,
                        "timeout": command.timeout_seconds
                    })
                )

                # Update status to sent
                command.status = "sent"
                command.sent_at = datetime.utcnow()
                self.db.commit()

                logger.info(f"Pushed approved command {command.id} to beacon")
        except Exception as e:
            logger.error(f"Failed to push approved command: {e}")

    def _get_user_id(self, user_identifier: str) -> Optional[int]:
        """Get user ID from identifier string (email or user:X format)."""
        if user_identifier.startswith("user:"):
            try:
                return int(user_identifier.split(":")[1])
            except (IndexError, ValueError):
                pass

        # Try to find user by email
        from models_rbac import User
        user = self.db.query(User).filter(User.email == user_identifier).first()
        return user.id if user else None

    def _log_audit_event(
        self,
        command_id: str,
        action: str,
        details: Dict[str, Any]
    ):
        """
        Log an audit event for shell command approval workflow.

        Args:
            command_id: The command ID
            action: The action taken (approval_requested, approved, rejected, expired)
            details: Additional details about the action
        """
        # Get command for context
        command = self.db.query(ShellCommand).filter(
            ShellCommand.id == command_id
        ).first()

        if not command:
            return

        # Get shell integration for hostname
        shell = self.db.query(ShellIntegration).filter(
            ShellIntegration.id == command.shell_id
        ).first()

        # Import audit log function if available
        try:
            from services.audit_service import log_audit_event

            log_audit_event(
                tenant_id=command.tenant_id,
                category="shell",
                action=f"shell.{action}",
                resource_type="shell_command",
                resource_id=command_id,
                details={
                    **details,
                    "shell_id": command.shell_id,
                    "shell_hostname": shell.hostname if shell else None,
                    "commands": command.commands
                },
                severity="warning" if action in ["rejected", "expired"] else "info"
            )
        except ImportError:
            # Audit service not available, log to standard logger
            logger.info(
                f"AUDIT: shell.{action} | command={command_id} | "
                f"shell={command.shell_id} | details={details}"
            )


def get_approval_service(db: Session) -> ShellApprovalService:
    """Factory function to create an approval service."""
    return ShellApprovalService(db)
