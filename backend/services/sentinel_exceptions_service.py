"""
Sentinel Exceptions Service - Phase 20 Enhancement

Manages exception rules that can bypass LLM analysis for known-safe operations.

Design Principle: NO hardcoded detection patterns here. The LLM handles threat
detection semantically. Exceptions only whitelist known-safe operations
to skip the LLM call for performance and reduce false positives.

Exception Hierarchy (evaluated in order):
1. System defaults (tenant_id=NULL) - ships with fresh installs
2. Tenant exceptions (tenant_id=<id>) - per-organization rules
3. Agent exceptions (agent_id=<id>) - per-agent overrides

Higher priority exceptions are evaluated first within each level.
"""

import re
import fnmatch
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import or_

from models import SentinelException

logger = logging.getLogger(__name__)


class SentinelExceptionsService:
    """
    Manages exception rules that can bypass LLM analysis.

    Thread-safe with in-memory caching for performance.
    Cache is invalidated when exceptions are modified.
    """

    # Class-level cache: {cache_key: (timestamp, exceptions_list)}
    _cache: Dict[str, Tuple[datetime, List[SentinelException]]] = {}
    _cache_ttl = timedelta(minutes=5)

    def __init__(self, db: Session, tenant_id: Optional[str] = None):
        """
        Initialize the service.

        Args:
            db: Database session
            tenant_id: Current tenant ID (None for system-level operations)
        """
        self.db = db
        self.tenant_id = tenant_id

    def get_exceptions(
        self,
        agent_id: Optional[int] = None,
        detection_type: Optional[str] = None,
        exception_type: Optional[str] = None,
        active_only: bool = True,
    ) -> List[SentinelException]:
        """
        Get applicable exceptions for the given context.

        Combines system-level, tenant-level, and agent-level exceptions.
        Returns in priority order (highest first).

        Args:
            agent_id: Optional agent ID to include agent-specific exceptions
            detection_type: Optional detection type filter (e.g., "shell_malicious")
            exception_type: Optional exception type filter (e.g., "domain", "pattern")
            active_only: If True, only return active exceptions

        Returns:
            List of matching exceptions, sorted by priority (highest first)
        """
        cache_key = f"{self.tenant_id}:{agent_id}:{detection_type}:{exception_type}:{active_only}"

        # Check cache
        if cache_key in self._cache:
            cached_time, cached_exceptions = self._cache[cache_key]
            if datetime.utcnow() - cached_time < self._cache_ttl:
                return cached_exceptions

        # Build query
        query = self.db.query(SentinelException)

        # Include system defaults, tenant exceptions, and agent exceptions
        scope_filters = [SentinelException.tenant_id.is_(None)]  # System defaults

        if self.tenant_id:
            # Tenant-level exceptions (agent_id must be NULL for tenant-wide)
            scope_filters.append(
                (SentinelException.tenant_id == self.tenant_id) &
                (SentinelException.agent_id.is_(None))
            )

        if agent_id:
            # Agent-specific exceptions
            scope_filters.append(SentinelException.agent_id == agent_id)

        query = query.filter(or_(*scope_filters))

        if active_only:
            query = query.filter(SentinelException.is_active == True)

        if exception_type:
            query = query.filter(SentinelException.exception_type == exception_type)

        if detection_type:
            # Match exceptions that apply to this detection type or all types ("*")
            query = query.filter(
                or_(
                    SentinelException.detection_types == "*",
                    SentinelException.detection_types.contains(detection_type)
                )
            )

        # Order by priority (highest first)
        exceptions = query.order_by(SentinelException.priority.desc()).all()

        # Cache results
        self._cache[cache_key] = (datetime.utcnow(), exceptions)

        return exceptions

    def check_exception(
        self,
        content: str,
        detection_type: str,
        analysis_type: str,
        agent_id: Optional[int] = None,
        tool_name: Optional[str] = None,
        target_domain: Optional[str] = None,
    ) -> Optional[SentinelException]:
        """
        Check if content matches any exception rule.

        If matched: Skip LLM analysis, return the matched exception
        If not matched: Return None (proceed to LLM analysis)

        Args:
            content: The input content to check
            detection_type: Type of detection (e.g., "shell_malicious", "prompt_injection")
            analysis_type: Type of analysis (e.g., "shell", "prompt", "tool")
            agent_id: Optional agent ID for agent-specific exceptions
            tool_name: Optional tool name for tool-type exceptions
            target_domain: Optional domain extracted from URLs

        Returns:
            Matched SentinelException or None
        """
        exceptions = self.get_exceptions(agent_id, detection_type)

        for exc in exceptions:
            if self._matches_exception(exc, content, tool_name, target_domain):
                logger.info(f"Sentinel exception '{exc.name}' matched - skipping LLM analysis")
                return exc

        return None  # No exception - proceed to LLM analysis

    def _matches_exception(
        self,
        exc: SentinelException,
        content: str,
        tool_name: Optional[str],
        target_domain: Optional[str],
    ) -> bool:
        """
        Check if content matches a specific exception rule.

        Args:
            exc: The exception rule to check
            content: The input content
            tool_name: Optional tool name
            target_domain: Optional domain

        Returns:
            True if exception matches
        """
        try:
            if exc.exception_type == "pattern":
                # Match against input content
                return self._match_pattern(exc.pattern, content, exc.match_mode)

            elif exc.exception_type == "domain":
                # Match against provided domain or extract from content
                if target_domain:
                    return self._match_pattern(exc.pattern, target_domain, exc.match_mode)
                # Try to extract domains from content
                domains = self._extract_domains(content)
                return any(
                    self._match_pattern(exc.pattern, domain, exc.match_mode)
                    for domain in domains
                )

            elif exc.exception_type == "tool":
                # Match against tool name
                if not tool_name:
                    return False
                return self._match_pattern(exc.pattern, tool_name, exc.match_mode)

            elif exc.exception_type == "network_target":
                # Match against extracted network targets (hosts, IPs, domains)
                targets = self._extract_network_targets(content)
                return any(
                    self._match_pattern(exc.pattern, target, exc.match_mode)
                    for target in targets
                )

            return False

        except Exception as e:
            logger.error(f"Error matching exception {exc.id} ({exc.name}): {e}")
            return False

    def _match_pattern(self, pattern: str, text: str, mode: str) -> bool:
        """
        Match text against pattern using specified mode.

        Args:
            pattern: The pattern to match
            text: The text to check
            mode: Match mode - 'exact', 'glob', or 'regex'

        Returns:
            True if pattern matches text
        """
        if not text:
            return False

        try:
            if mode == "exact":
                return pattern.lower() == text.lower()
            elif mode == "glob":
                return fnmatch.fnmatch(text.lower(), pattern.lower())
            else:  # regex (default)
                return bool(re.search(pattern, text, re.IGNORECASE))
        except re.error as e:
            logger.warning(f"Invalid regex pattern '{pattern}': {e}")
            return False

    def _extract_domains(self, content: str) -> List[str]:
        """
        Extract domain names from content.

        Args:
            content: Text content to scan

        Returns:
            List of unique domain names found
        """
        domains = set()

        # Extract from URLs
        url_pattern = r'https?://([^/\s:]+)'
        domains.update(re.findall(url_pattern, content, re.IGNORECASE))

        return list(domains)

    def _extract_network_targets(self, content: str) -> List[str]:
        """
        Extract network targets (hostnames, domains, IPs) from content.

        Args:
            content: Text content to scan

        Returns:
            List of unique network targets found
        """
        targets = set()

        # URLs - extract hostnames
        url_pattern = r'https?://([^/\s:]+)'
        targets.update(re.findall(url_pattern, content, re.IGNORECASE))

        # IP addresses (IPv4)
        ip_pattern = r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b'
        targets.update(re.findall(ip_pattern, content))

        # Domain names (simple pattern - word.tld or sub.word.tld)
        domain_pattern = r'\b([a-zA-Z0-9][-a-zA-Z0-9]*(?:\.[a-zA-Z0-9][-a-zA-Z0-9]*)*\.[a-zA-Z]{2,})\b'
        targets.update(re.findall(domain_pattern, content))

        # Filter out common false positives
        targets = {t for t in targets if not t.endswith('.py') and not t.endswith('.js')}

        return list(targets)

    def invalidate_cache(
        self,
        tenant_id: Optional[str] = None,
        agent_id: Optional[int] = None
    ) -> int:
        """
        Invalidate exception cache.

        Args:
            tenant_id: If provided, only invalidate cache for this tenant
            agent_id: If provided, only invalidate cache entries that include this agent

        Returns:
            Number of cache entries invalidated
        """
        if tenant_id is None and agent_id is None:
            count = len(self._cache)
            self._cache.clear()
            return count

        keys_to_remove = []
        for key in self._cache:
            if tenant_id and key.startswith(f"{tenant_id}:"):
                keys_to_remove.append(key)
            elif agent_id and f":{agent_id}:" in key:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self._cache[key]

        return len(keys_to_remove)

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    def create_exception(
        self,
        name: str,
        exception_type: str,
        pattern: str,
        detection_types: str = "*",
        match_mode: str = "regex",
        action: str = "skip_llm",
        description: Optional[str] = None,
        agent_id: Optional[int] = None,
        priority: int = 100,
        created_by: Optional[int] = None,
    ) -> SentinelException:
        """
        Create a new exception rule.

        Args:
            name: Human-readable name for the exception
            exception_type: Type of exception ('pattern', 'domain', 'tool', 'network_target')
            pattern: The pattern to match
            detection_types: Comma-separated detection types or "*" for all
            match_mode: Match mode ('regex', 'glob', 'exact')
            action: Action when matched ('skip_llm', 'allow')
            description: Optional description
            agent_id: Optional agent ID for agent-specific exception
            priority: Priority (higher = evaluated first)
            created_by: ID of user creating the exception

        Returns:
            Created SentinelException
        """
        exception = SentinelException(
            tenant_id=self.tenant_id,
            agent_id=agent_id,
            name=name,
            description=description,
            detection_types=detection_types,
            exception_type=exception_type,
            pattern=pattern,
            match_mode=match_mode,
            action=action,
            priority=priority,
            is_active=True,
            created_by=created_by,
        )

        self.db.add(exception)
        self.db.commit()
        self.db.refresh(exception)

        # Invalidate cache
        self.invalidate_cache(self.tenant_id, agent_id)

        logger.info(f"Created Sentinel exception: {name} (id={exception.id})")
        return exception

    def update_exception(
        self,
        exception_id: int,
        updated_by: Optional[int] = None,
        **updates
    ) -> Optional[SentinelException]:
        """
        Update an existing exception rule.

        Args:
            exception_id: ID of exception to update
            updated_by: ID of user updating the exception
            **updates: Fields to update

        Returns:
            Updated SentinelException or None if not found/unauthorized
        """
        exception = self.db.query(SentinelException).filter(
            SentinelException.id == exception_id
        ).first()

        if not exception:
            return None

        # Verify access (system exceptions can only be updated by system admins)
        if exception.tenant_id is not None and exception.tenant_id != self.tenant_id:
            logger.warning(f"Unauthorized attempt to update exception {exception_id}")
            return None

        # Update allowed fields
        allowed_fields = {
            'name', 'description', 'detection_types', 'exception_type',
            'pattern', 'match_mode', 'action', 'is_active', 'priority', 'agent_id'
        }

        for field, value in updates.items():
            if field in allowed_fields and hasattr(exception, field):
                setattr(exception, field, value)

        exception.updated_by = updated_by
        exception.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(exception)

        # Invalidate cache
        self.invalidate_cache(exception.tenant_id, exception.agent_id)

        logger.info(f"Updated Sentinel exception: {exception.name} (id={exception_id})")
        return exception

    def delete_exception(self, exception_id: int) -> bool:
        """
        Delete an exception rule.

        Args:
            exception_id: ID of exception to delete

        Returns:
            True if deleted, False if not found/unauthorized
        """
        exception = self.db.query(SentinelException).filter(
            SentinelException.id == exception_id
        ).first()

        if not exception:
            return False

        # Verify access (system exceptions cannot be deleted via tenant API)
        if exception.tenant_id is None:
            logger.warning(f"Attempt to delete system exception {exception_id}")
            return False

        if exception.tenant_id != self.tenant_id:
            logger.warning(f"Unauthorized attempt to delete exception {exception_id}")
            return False

        tenant_id = exception.tenant_id
        agent_id = exception.agent_id
        name = exception.name

        self.db.delete(exception)
        self.db.commit()

        # Invalidate cache
        self.invalidate_cache(tenant_id, agent_id)

        logger.info(f"Deleted Sentinel exception: {name} (id={exception_id})")
        return True

    def toggle_exception(
        self,
        exception_id: int,
        updated_by: Optional[int] = None
    ) -> Optional[SentinelException]:
        """
        Toggle exception active status.

        Args:
            exception_id: ID of exception to toggle
            updated_by: ID of user toggling the exception

        Returns:
            Updated SentinelException or None if not found/unauthorized
        """
        exception = self.db.query(SentinelException).filter(
            SentinelException.id == exception_id
        ).first()

        if not exception:
            return None

        # Verify access
        if exception.tenant_id is not None and exception.tenant_id != self.tenant_id:
            return None

        exception.is_active = not exception.is_active
        exception.updated_by = updated_by
        exception.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(exception)

        # Invalidate cache
        self.invalidate_cache(exception.tenant_id, exception.agent_id)

        logger.info(
            f"Toggled Sentinel exception: {exception.name} (id={exception_id}) -> "
            f"is_active={exception.is_active}"
        )
        return exception

    def test_exception(
        self,
        exception_id: int,
        test_content: str,
        tool_name: Optional[str] = None,
        target_domain: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Test if content would match an exception rule.

        Args:
            exception_id: ID of exception to test
            test_content: Content to test against the pattern
            tool_name: Optional tool name for tool-type exceptions
            target_domain: Optional domain for domain-type exceptions

        Returns:
            Dict with test results
        """
        exception = self.db.query(SentinelException).filter(
            SentinelException.id == exception_id
        ).first()

        if not exception:
            return {"error": "Exception not found", "matches": False}

        # Verify access
        if exception.tenant_id is not None and exception.tenant_id != self.tenant_id:
            return {"error": "Access denied", "matches": False}

        matches = self._matches_exception(exception, test_content, tool_name, target_domain)

        result = {
            "matches": matches,
            "would_skip_analysis": matches,
            "exception_id": exception.id,
            "exception_name": exception.name,
            "exception_type": exception.exception_type,
            "pattern": exception.pattern,
            "match_mode": exception.match_mode,
        }

        # Add debug info for network_target type
        if exception.exception_type == "network_target":
            result["extracted_targets"] = self._extract_network_targets(test_content)
        elif exception.exception_type == "domain":
            result["extracted_domains"] = self._extract_domains(test_content)

        return result

    def get_exception_by_id(self, exception_id: int) -> Optional[SentinelException]:
        """
        Get a specific exception by ID.

        Args:
            exception_id: ID of exception

        Returns:
            SentinelException or None if not found/unauthorized
        """
        exception = self.db.query(SentinelException).filter(
            SentinelException.id == exception_id
        ).first()

        if not exception:
            return None

        # System exceptions are visible to all
        if exception.tenant_id is None:
            return exception

        # Tenant exceptions only visible to that tenant
        if exception.tenant_id == self.tenant_id:
            return exception

        return None

    def list_exceptions(
        self,
        agent_id: Optional[int] = None,
        exception_type: Optional[str] = None,
        active_only: bool = False,
        include_system: bool = True,
    ) -> List[SentinelException]:
        """
        List all exceptions accessible to the current tenant.

        Args:
            agent_id: Optional filter by agent ID
            exception_type: Optional filter by exception type
            active_only: If True, only return active exceptions
            include_system: If True, include system-level exceptions

        Returns:
            List of SentinelException
        """
        query = self.db.query(SentinelException)

        # Build scope filter
        scope_filters = []

        if include_system:
            scope_filters.append(SentinelException.tenant_id.is_(None))

        if self.tenant_id:
            scope_filters.append(SentinelException.tenant_id == self.tenant_id)

        if scope_filters:
            query = query.filter(or_(*scope_filters))

        if agent_id is not None:
            query = query.filter(
                or_(
                    SentinelException.agent_id.is_(None),
                    SentinelException.agent_id == agent_id
                )
            )

        if exception_type:
            query = query.filter(SentinelException.exception_type == exception_type)

        if active_only:
            query = query.filter(SentinelException.is_active == True)

        return query.order_by(
            SentinelException.priority.desc(),
            SentinelException.created_at.desc()
        ).all()
