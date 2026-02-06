"""
Shell Security Service - Phase 5: Security & Approval Workflow
Phase 19: Database-backed pattern customization

Provides security controls for shell command execution:
- High-risk command detection
- Command whitelisting validation
- Path restriction validation
- Rate limiting per integration
- IP allowlist validation
- Tenant-customizable security patterns (Phase 19)
"""

import re
import time
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import or_

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk levels for shell commands."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def severity(self) -> int:
        """Return numeric severity for comparison."""
        return {"low": 1, "medium": 2, "high": 3, "critical": 4}[self.value]

    def __gt__(self, other: "RiskLevel") -> bool:
        return self.severity > other.severity

    def __lt__(self, other: "RiskLevel") -> bool:
        return self.severity < other.severity

    def __ge__(self, other: "RiskLevel") -> bool:
        return self.severity >= other.severity

    def __le__(self, other: "RiskLevel") -> bool:
        return self.severity <= other.severity


@dataclass
class SecurityCheckResult:
    """Result of a security check on a command."""
    allowed: bool
    risk_level: RiskLevel
    requires_approval: bool
    blocked_reason: Optional[str] = None
    matched_patterns: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# High-risk command patterns that require approval
HIGH_RISK_PATTERNS = [
    # Destructive file operations
    (r"rm\s+(-[rf]+\s+|--force\s+|--recursive\s+)", RiskLevel.CRITICAL, "Force/recursive delete"),
    (r"rm\s+-[a-z]*r[a-z]*\s+", RiskLevel.CRITICAL, "Recursive delete"),
    (r"rm\s+\*", RiskLevel.HIGH, "Wildcard delete"),
    (r"rm\s+/", RiskLevel.CRITICAL, "Root delete"),

    # Disk operations
    (r"mkfs", RiskLevel.CRITICAL, "Format filesystem"),
    (r"fdisk", RiskLevel.CRITICAL, "Partition disk"),
    (r"dd\s+", RiskLevel.CRITICAL, "Disk dump"),
    (r">\s*/dev/sd", RiskLevel.CRITICAL, "Write to disk device"),
    (r">\s*/dev/nvme", RiskLevel.CRITICAL, "Write to NVMe device"),

    # Permission changes
    (r"chmod\s+777", RiskLevel.HIGH, "Insecure permissions (777)"),
    (r"chmod\s+-R\s+777", RiskLevel.CRITICAL, "Recursive insecure permissions"),
    (r"chown\s+-R\s+", RiskLevel.HIGH, "Recursive ownership change"),

    # System modifications
    (r"systemctl\s+(stop|disable|mask)\s+", RiskLevel.HIGH, "Stop/disable service"),
    (r"service\s+\S+\s+(stop|disable)", RiskLevel.HIGH, "Stop/disable service"),
    (r"/etc/passwd", RiskLevel.HIGH, "Access password file"),
    (r"/etc/shadow", RiskLevel.CRITICAL, "Access shadow file"),

    # Network operations
    (r"iptables\s+", RiskLevel.HIGH, "Modify firewall rules"),
    (r"ufw\s+(disable|delete)", RiskLevel.HIGH, "Disable firewall"),
    (r"netcat\s+-l", RiskLevel.MEDIUM, "Network listener"),
    (r"nc\s+-l", RiskLevel.MEDIUM, "Network listener"),

    # Fork bombs and malicious patterns
    (r":\(\)\s*{\s*:\|:\s*&\s*}\s*;", RiskLevel.CRITICAL, "Fork bomb"),
    (r"\$\(.*\)\s*&", RiskLevel.MEDIUM, "Background command execution"),

    # Remote code execution
    (r"wget.*\|\s*(ba)?sh", RiskLevel.CRITICAL, "Remote script execution"),
    (r"curl.*\|\s*(ba)?sh", RiskLevel.CRITICAL, "Remote script execution"),
    (r"curl.*-o\s+/tmp.*&&.*sh", RiskLevel.CRITICAL, "Download and execute"),

    # Package management (potentially destructive)
    (r"(apt|yum|dnf)\s+(remove|purge)\s+-y", RiskLevel.HIGH, "Force remove packages"),
    (r"pip\s+uninstall\s+-y", RiskLevel.MEDIUM, "Force uninstall Python packages"),

    # Database operations
    (r"(mysql|psql).*DROP\s+(DATABASE|TABLE)", RiskLevel.CRITICAL, "Drop database/table"),
    (r"(mongo|redis-cli)\s+.*--eval.*drop", RiskLevel.CRITICAL, "Drop database"),

    # Container/virtualization
    (r"docker\s+rm\s+-f", RiskLevel.HIGH, "Force remove container"),
    (r"docker\s+system\s+prune\s+-a", RiskLevel.HIGH, "Remove all Docker resources"),
    (r"kubectl\s+delete\s+", RiskLevel.HIGH, "Delete Kubernetes resources"),

    # Sensitive data access
    (r"cat\s+.*\.(pem|key|crt|p12)", RiskLevel.MEDIUM, "Access certificates/keys"),
    (r"cat\s+.*\.env", RiskLevel.MEDIUM, "Access environment file"),
    (r"printenv", RiskLevel.LOW, "Print environment variables"),

    # History and credential access
    (r"history", RiskLevel.LOW, "Access command history"),
    (r"cat\s+.*history", RiskLevel.MEDIUM, "Read history file"),
    (r"cat\s+.*credentials", RiskLevel.HIGH, "Access credentials file"),
]

# Commands that are always blocked (cannot be approved)
BLOCKED_PATTERNS = [
    # Fork bombs - various forms
    (r":\(\)\s*\{", "Fork bomb detected"),  # :(){ pattern
    (r":\s*\(\s*\)\s*\{", "Fork bomb detected"),  # : ( ) { with spaces
    # Direct disk access
    (r">\s*/dev/sd[a-z]", "Direct write to disk device"),
    (r">\s*/dev/nvme", "Direct write to NVMe device"),
    # Root filesystem destruction
    (r"mv\s+/\s", "Move root filesystem"),
    (r"rm\s+-rf\s+/\s*$", "Delete root filesystem"),
    (r"rm\s+-rf\s+/\*", "Delete all files"),
    (r"rm\s+-rf\s+--no-preserve-root\s+/", "Delete root (no preserve)"),
    # Disk formatting
    (r"mkfs\.\w+\s+/dev/sd[a-z]", "Format disk device"),
    (r"mkfs\.\w+\s+/dev/nvme", "Format NVMe device"),
]


class ShellSecurityService:
    """
    Service for validating shell commands against security policies.

    Provides:
    - High-risk command detection
    - Command whitelisting
    - Path restrictions
    - Rate limiting
    - IP allowlisting
    - Tenant-customizable patterns (Phase 19)
    """

    def __init__(self):
        """Initialize the security service."""
        # Rate limiting: track commands per integration
        self._rate_limits: Dict[int, List[float]] = defaultdict(list)
        self._default_rate_limit = 60  # commands per minute
        self._rate_window = 60  # seconds

        # Phase 19: Pattern cache with TTL
        # Cache structure: {cache_key: {'blocked': [...], 'high_risk': [...], 'expires': timestamp}}
        self._pattern_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 300  # 5 minutes

    def get_patterns_for_tenant(
        self,
        tenant_id: Optional[str],
        db: Session
    ) -> Tuple[List[Tuple[str, str]], List[Tuple[str, RiskLevel, str]]]:
        """
        Get blocked and high-risk patterns for a tenant.

        Merges system defaults (tenant_id=NULL) with tenant-specific patterns.
        Uses TTL-based caching for performance.

        Args:
            tenant_id: Tenant ID (or None for system-only patterns)
            db: Database session

        Returns:
            Tuple of (blocked_patterns, high_risk_patterns)
            - blocked_patterns: List of (pattern, description)
            - high_risk_patterns: List of (pattern, RiskLevel, description)
        """
        cache_key = f"patterns:{tenant_id or 'system'}"
        now = time.time()

        # Check cache
        cached = self._pattern_cache.get(cache_key)
        if cached and cached['expires'] > now:
            return cached['blocked'], cached['high_risk']

        # Load from DB
        from models import ShellSecurityPattern

        query = db.query(ShellSecurityPattern).filter(
            ShellSecurityPattern.is_active == True
        )

        # Include system defaults (tenant_id=NULL) and tenant-specific patterns
        if tenant_id:
            query = query.filter(
                or_(
                    ShellSecurityPattern.tenant_id.is_(None),  # System defaults
                    ShellSecurityPattern.tenant_id == tenant_id  # Tenant patterns
                )
            )
        else:
            # Only system defaults
            query = query.filter(ShellSecurityPattern.tenant_id.is_(None))

        patterns = query.all()

        blocked = []
        high_risk = []

        for p in patterns:
            if p.pattern_type == 'blocked':
                blocked.append((p.pattern, p.description))
            elif p.pattern_type == 'high_risk':
                # Convert string risk level to RiskLevel enum
                try:
                    risk = RiskLevel(p.risk_level) if p.risk_level else RiskLevel.HIGH
                except ValueError:
                    risk = RiskLevel.HIGH
                high_risk.append((p.pattern, risk, p.description))

        # Fall back to hardcoded patterns if DB is empty
        if not blocked:
            blocked = BLOCKED_PATTERNS
        if not high_risk:
            high_risk = HIGH_RISK_PATTERNS

        # Cache results
        self._pattern_cache[cache_key] = {
            'blocked': blocked,
            'high_risk': high_risk,
            'expires': now + self._cache_ttl
        }

        logger.debug(f"Loaded {len(blocked)} blocked and {len(high_risk)} high-risk patterns for tenant {tenant_id}")

        return blocked, high_risk

    def invalidate_cache(self, tenant_id: Optional[str] = None) -> None:
        """
        Invalidate pattern cache for a tenant or all tenants.

        Args:
            tenant_id: Specific tenant to invalidate, or None to clear all
        """
        if tenant_id:
            cache_key = f"patterns:{tenant_id}"
            self._pattern_cache.pop(cache_key, None)
            # Also invalidate system-only cache since patterns may have changed
            self._pattern_cache.pop("patterns:system", None)
            logger.debug(f"Invalidated pattern cache for tenant {tenant_id}")
        else:
            self._pattern_cache.clear()
            logger.debug("Invalidated all pattern caches")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring."""
        now = time.time()
        active_caches = sum(1 for c in self._pattern_cache.values() if c['expires'] > now)
        expired_caches = len(self._pattern_cache) - active_caches

        return {
            'total_cached': len(self._pattern_cache),
            'active_caches': active_caches,
            'expired_caches': expired_caches,
            'cache_ttl_seconds': self._cache_ttl
        }

    def check_command(
        self,
        command: str,
        allowed_commands: Optional[List[str]] = None,
        allowed_paths: Optional[List[str]] = None,
        require_approval_for_high_risk: bool = True,
        tenant_id: Optional[str] = None,
        db: Optional[Session] = None
    ) -> SecurityCheckResult:
        """
        Check a command against security policies.

        Phase 19: Now supports tenant-customizable patterns from database.

        Args:
            command: The shell command to check
            allowed_commands: Optional whitelist of allowed commands
            allowed_paths: Optional list of allowed paths
            require_approval_for_high_risk: Whether high-risk commands need approval
            tenant_id: Tenant ID for loading tenant-specific patterns (Phase 19)
            db: Database session for loading patterns (Phase 19)

        Returns:
            SecurityCheckResult with validation details
        """
        # Clean and normalize command
        command = command.strip()

        if not command:
            return SecurityCheckResult(
                allowed=False,
                risk_level=RiskLevel.LOW,
                requires_approval=False,
                blocked_reason="Empty command"
            )

        # Phase 19: Load patterns from DB if tenant_id and db provided, else use hardcoded
        if tenant_id and db:
            blocked_patterns, high_risk_patterns = self.get_patterns_for_tenant(tenant_id, db)
        else:
            blocked_patterns = BLOCKED_PATTERNS
            high_risk_patterns = HIGH_RISK_PATTERNS

        # Check for blocked patterns (always denied)
        for pattern, reason in blocked_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                logger.warning(f"BLOCKED command detected: {command[:100]} - {reason}")
                return SecurityCheckResult(
                    allowed=False,
                    risk_level=RiskLevel.CRITICAL,
                    requires_approval=False,
                    blocked_reason=f"BLOCKED: {reason}",
                    matched_patterns=[pattern]
                )

        # Check command whitelist if provided
        if allowed_commands:
            base_command = self._extract_base_command(command)
            if not self._is_command_allowed(base_command, allowed_commands):
                return SecurityCheckResult(
                    allowed=False,
                    risk_level=RiskLevel.MEDIUM,
                    requires_approval=False,
                    blocked_reason=f"Command '{base_command}' not in whitelist"
                )

        # Check path restrictions if provided
        if allowed_paths:
            path_check = self._check_path_restrictions(command, allowed_paths)
            if not path_check[0]:
                return SecurityCheckResult(
                    allowed=False,
                    risk_level=RiskLevel.MEDIUM,
                    requires_approval=False,
                    blocked_reason=path_check[1]
                )

        # Check for high-risk patterns
        matched_patterns = []
        warnings = []
        max_risk_level = RiskLevel.LOW

        for pattern, risk_level, description in high_risk_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                matched_patterns.append(description)
                warnings.append(f"⚠️ {description} (Risk: {risk_level.value})")
                if risk_level > max_risk_level:
                    max_risk_level = risk_level

        # Determine if approval is required
        requires_approval = (
            require_approval_for_high_risk and
            max_risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
        )

        return SecurityCheckResult(
            allowed=True,
            risk_level=max_risk_level,
            requires_approval=requires_approval,
            matched_patterns=matched_patterns,
            warnings=warnings
        )

    def check_commands(
        self,
        commands: List[str],
        allowed_commands: Optional[List[str]] = None,
        allowed_paths: Optional[List[str]] = None,
        require_approval_for_high_risk: bool = True
    ) -> Tuple[bool, SecurityCheckResult]:
        """
        Check multiple commands and return aggregated result.

        Args:
            commands: List of commands to check
            allowed_commands: Optional whitelist
            allowed_paths: Optional path restrictions
            require_approval_for_high_risk: Whether to require approval for high-risk

        Returns:
            Tuple of (all_allowed, aggregated_result)
        """
        all_patterns = []
        all_warnings = []
        max_risk = RiskLevel.LOW
        requires_approval = False

        for cmd in commands:
            result = self.check_command(
                cmd,
                allowed_commands,
                allowed_paths,
                require_approval_for_high_risk
            )

            if not result.allowed:
                return False, result

            all_patterns.extend(result.matched_patterns)
            all_warnings.extend(result.warnings)

            if result.risk_level > max_risk:
                max_risk = result.risk_level

            if result.requires_approval:
                requires_approval = True

        return True, SecurityCheckResult(
            allowed=True,
            risk_level=max_risk,
            requires_approval=requires_approval,
            matched_patterns=all_patterns,
            warnings=all_warnings
        )

    def check_rate_limit(
        self,
        integration_id: int,
        limit: Optional[int] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if an integration is within rate limits.

        Args:
            integration_id: Shell integration ID
            limit: Optional custom rate limit (commands per minute)

        Returns:
            Tuple of (allowed, error_message)
        """
        rate_limit = limit or self._default_rate_limit
        now = time.time()
        window_start = now - self._rate_window

        # Clean old entries
        self._rate_limits[integration_id] = [
            ts for ts in self._rate_limits[integration_id]
            if ts > window_start
        ]

        # Check count
        current_count = len(self._rate_limits[integration_id])

        if current_count >= rate_limit:
            return False, f"Rate limit exceeded ({rate_limit} commands/minute)"

        # Record this request
        self._rate_limits[integration_id].append(now)

        return True, None

    def check_ip_allowlist(
        self,
        client_ip: str,
        allowed_ips: Optional[List[str]] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if client IP is allowed.

        Args:
            client_ip: Client IP address
            allowed_ips: Optional list of allowed IPs/CIDR ranges

        Returns:
            Tuple of (allowed, error_message)
        """
        if not allowed_ips:
            return True, None  # No restrictions

        import ipaddress

        try:
            client = ipaddress.ip_address(client_ip)
        except ValueError:
            return False, f"Invalid IP address: {client_ip}"

        for allowed in allowed_ips:
            try:
                if '/' in allowed:
                    # CIDR notation
                    network = ipaddress.ip_network(allowed, strict=False)
                    if client in network:
                        return True, None
                else:
                    # Single IP
                    if client == ipaddress.ip_address(allowed):
                        return True, None
            except ValueError:
                continue

        return False, f"IP {client_ip} not in allowlist"

    def _extract_base_command(self, command: str) -> str:
        """Extract the base command (first word) from a command string."""
        # Handle sudo prefix
        parts = command.strip().split()
        if not parts:
            return ""

        if parts[0] == "sudo" and len(parts) > 1:
            return parts[1]

        return parts[0]

    def _is_command_allowed(self, base_command: str, allowed: List[str]) -> bool:
        """Check if a base command is in the allowed list."""
        # Support glob patterns
        import fnmatch

        for pattern in allowed:
            if fnmatch.fnmatch(base_command, pattern):
                return True

        return False

    def _check_path_restrictions(
        self,
        command: str,
        allowed_paths: List[str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if command operates within allowed paths.

        Args:
            command: The command to check
            allowed_paths: List of allowed path prefixes

        Returns:
            Tuple of (allowed, error_message)
        """
        # Extract potential paths from command
        # This is a simplified check - real implementation would be more sophisticated
        path_pattern = r'["\']?(/[a-zA-Z0-9_./-]+)'
        matches = re.findall(path_pattern, command)

        for path in matches:
            # Normalize path
            path = path.rstrip('/')

            # Check if path is within allowed directories
            allowed = any(
                path.startswith(allowed_path.rstrip('/'))
                for allowed_path in allowed_paths
            )

            if not allowed:
                return False, f"Path '{path}' not in allowed directories"

        return True, None

    def get_risk_summary(self, result: SecurityCheckResult) -> str:
        """Generate a human-readable summary of security check result."""
        if not result.allowed:
            return f"❌ BLOCKED: {result.blocked_reason}"

        risk_emoji = {
            RiskLevel.LOW: "✅",
            RiskLevel.MEDIUM: "⚠️",
            RiskLevel.HIGH: "🔶",
            RiskLevel.CRITICAL: "🔴"
        }

        summary = f"{risk_emoji[result.risk_level]} Risk Level: {result.risk_level.value.upper()}"

        if result.requires_approval:
            summary += " - Approval Required"

        if result.warnings:
            summary += "\n" + "\n".join(result.warnings)

        return summary


# Singleton instance
_security_service: Optional[ShellSecurityService] = None


def get_security_service() -> ShellSecurityService:
    """Get or create the security service singleton."""
    global _security_service
    if _security_service is None:
        _security_service = ShellSecurityService()
    return _security_service
