"""
Sentinel Profiles Service - Phase v1.6.0

Manages security profiles: CRUD, assignment, resolution, and hierarchy.
Profiles are named, reusable security policies assigned at tenant/agent/skill levels.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import (
    SentinelProfile,
    SentinelProfileAssignment,
    Agent,
    AgentSkill,
    Contact,
)
from .sentinel_effective_config import SentinelEffectiveConfig
from .sentinel_detections import DETECTION_REGISTRY

logger = logging.getLogger(__name__)


class SentinelProfilesService:
    """
    Service for Sentinel Security Profile management and resolution.

    Handles profile CRUD, assignment at tenant/agent/skill levels,
    hierarchical profile resolution, and cache management.
    """

    # Class-level cache shared across all instances (per-process)
    _profile_cache: Dict[str, Tuple[float, SentinelEffectiveConfig]] = {}
    PROFILE_CACHE_TTL = 300  # 5 minutes

    def __init__(self, db: Session, tenant_id: Optional[str] = None):
        self.db = db
        self.tenant_id = tenant_id

    # =========================================================================
    # Profile CRUD
    # =========================================================================

    def list_profiles(self, include_system: bool = True) -> List[SentinelProfile]:
        """List all profiles accessible to this tenant."""
        query = self.db.query(SentinelProfile)

        if include_system:
            # System profiles (tenant_id=NULL) + tenant-specific
            if self.tenant_id:
                query = query.filter(
                    (SentinelProfile.tenant_id.is_(None)) |
                    (SentinelProfile.tenant_id == self.tenant_id)
                )
            else:
                query = query.filter(SentinelProfile.tenant_id.is_(None))
        else:
            # Only tenant-specific
            if self.tenant_id:
                query = query.filter(SentinelProfile.tenant_id == self.tenant_id)
            else:
                return []

        return query.order_by(SentinelProfile.is_system.desc(), SentinelProfile.name).all()

    def get_profile(self, profile_id: int) -> Optional[SentinelProfile]:
        """Get a specific profile by ID."""
        profile = self.db.query(SentinelProfile).filter(
            SentinelProfile.id == profile_id
        ).first()

        # Access control: system profiles visible to all, tenant profiles only to that tenant
        if profile and profile.tenant_id and profile.tenant_id != self.tenant_id:
            return None

        return profile

    def create_profile(self, data: dict, created_by: Optional[int] = None) -> SentinelProfile:
        """Create a new tenant-scoped profile."""
        # Validate detection_overrides if provided
        detection_overrides = data.get("detection_overrides", "{}")
        if detection_overrides:
            self._validate_detection_overrides(detection_overrides)

        profile = SentinelProfile(
            tenant_id=self.tenant_id,
            is_system=False,
            created_by=created_by,
            **{k: v for k, v in data.items() if hasattr(SentinelProfile, k) and k not in ("id", "tenant_id", "is_system", "created_by", "created_at", "updated_at")}
        )

        # Handle is_default uniqueness
        if data.get("is_default"):
            self._clear_default(self.tenant_id)

        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)
        self._invalidate_cache()

        return profile

    def update_profile(self, profile_id: int, data: dict, updated_by: Optional[int] = None) -> Optional[SentinelProfile]:
        """Update a profile. Cannot modify system profiles."""
        profile = self.get_profile(profile_id)
        if not profile:
            return None

        if profile.is_system:
            raise ValueError("Cannot modify system profiles")

        # Validate detection_overrides if provided
        if "detection_overrides" in data:
            self._validate_detection_overrides(data["detection_overrides"])

        # Handle is_default uniqueness
        if data.get("is_default") and not profile.is_default:
            self._clear_default(profile.tenant_id)

        # Update fields
        for key, value in data.items():
            if hasattr(profile, key) and key not in ("id", "tenant_id", "is_system", "created_by", "created_at"):
                setattr(profile, key, value)

        if updated_by:
            profile.updated_by = updated_by

        self.db.commit()
        self.db.refresh(profile)
        self._invalidate_cache()

        return profile

    def delete_profile(self, profile_id: int) -> dict:
        """
        Delete a profile.

        Returns dict with 'deleted' boolean and optional 'assignments' list
        if profile has active assignments (409 case).
        """
        profile = self.get_profile(profile_id)
        if not profile:
            return {"deleted": False, "error": "Profile not found"}

        if profile.is_system:
            return {"deleted": False, "error": "Cannot delete system profiles"}

        # Check for active assignments
        assignments = self.db.query(SentinelProfileAssignment).filter(
            SentinelProfileAssignment.profile_id == profile_id
        ).all()

        if assignments:
            return {
                "deleted": False,
                "error": "Profile has active assignments",
                "assignment_count": len(assignments),
                "assignments": [
                    {
                        "id": a.id,
                        "tenant_id": a.tenant_id,
                        "agent_id": a.agent_id,
                        "skill_type": a.skill_type,
                    }
                    for a in assignments
                ],
            }

        self.db.delete(profile)
        self.db.commit()
        self._invalidate_cache()

        return {"deleted": True}

    def clone_profile(
        self,
        profile_id: int,
        new_name: str,
        new_slug: str,
        created_by: Optional[int] = None,
    ) -> Optional[SentinelProfile]:
        """Clone an existing profile with a new name/slug."""
        source = self.get_profile(profile_id)
        if not source:
            return None

        clone = SentinelProfile(
            name=new_name,
            slug=new_slug,
            description=f"Cloned from {source.name}",
            tenant_id=self.tenant_id,
            is_system=False,
            is_default=False,
            # Copy all settings
            is_enabled=source.is_enabled,
            detection_mode=source.detection_mode,
            aggressiveness_level=source.aggressiveness_level,
            enable_prompt_analysis=source.enable_prompt_analysis,
            enable_tool_analysis=source.enable_tool_analysis,
            enable_shell_analysis=source.enable_shell_analysis,
            enable_slash_command_analysis=source.enable_slash_command_analysis,
            llm_provider=source.llm_provider,
            llm_model=source.llm_model,
            llm_max_tokens=source.llm_max_tokens,
            llm_temperature=source.llm_temperature,
            cache_ttl_seconds=source.cache_ttl_seconds,
            max_input_chars=source.max_input_chars,
            timeout_seconds=source.timeout_seconds,
            block_on_detection=source.block_on_detection,
            log_all_analyses=source.log_all_analyses,
            enable_notifications=source.enable_notifications,
            notification_on_block=source.notification_on_block,
            notification_on_detect=source.notification_on_detect,
            notification_recipient=source.notification_recipient,
            notification_message_template=source.notification_message_template,
            detection_overrides=source.detection_overrides,
            created_by=created_by,
        )

        self.db.add(clone)
        self.db.commit()
        self.db.refresh(clone)

        return clone

    # =========================================================================
    # Assignment CRUD
    # =========================================================================

    def list_assignments(
        self,
        agent_id: Optional[int] = None,
        skill_type: Optional[str] = None,
    ) -> List[SentinelProfileAssignment]:
        """List profile assignments for this tenant."""
        query = self.db.query(SentinelProfileAssignment).filter(
            SentinelProfileAssignment.tenant_id == self.tenant_id
        )

        if agent_id is not None:
            query = query.filter(SentinelProfileAssignment.agent_id == agent_id)

        if skill_type is not None:
            query = query.filter(SentinelProfileAssignment.skill_type == skill_type)

        return query.all()

    def assign_profile(
        self,
        profile_id: int,
        agent_id: Optional[int] = None,
        skill_type: Optional[str] = None,
        assigned_by: Optional[int] = None,
    ) -> Optional[SentinelProfileAssignment]:
        """
        Assign a profile at a specific scope level.

        Replaces existing assignment at the same scope (UPSERT semantics).
        """
        # Validate profile exists and is accessible
        profile = self.get_profile(profile_id)
        if not profile:
            raise ValueError("Profile not found")

        # Cross-tenant guard
        if profile.tenant_id is not None and profile.tenant_id != self.tenant_id:
            raise ValueError("Cannot assign a profile from another tenant")

        # Skill-type requires agent_id
        if skill_type and not agent_id:
            raise ValueError("skill_type requires agent_id")

        # Find or create assignment (with race condition handling)
        existing = self.db.query(SentinelProfileAssignment).filter(
            SentinelProfileAssignment.tenant_id == self.tenant_id,
            SentinelProfileAssignment.agent_id == agent_id if agent_id else SentinelProfileAssignment.agent_id.is_(None),
            SentinelProfileAssignment.skill_type == skill_type if skill_type else SentinelProfileAssignment.skill_type.is_(None),
        ).first()

        if existing:
            existing.profile_id = profile_id
            existing.assigned_by = assigned_by
            self.db.commit()
            self.db.refresh(existing)
            self._invalidate_cache()
            return existing

        assignment = SentinelProfileAssignment(
            tenant_id=self.tenant_id,
            agent_id=agent_id,
            skill_type=skill_type,
            profile_id=profile_id,
            assigned_by=assigned_by,
        )

        try:
            self.db.add(assignment)
            self.db.commit()
            self.db.refresh(assignment)
        except IntegrityError:
            # Race condition: another request created the assignment concurrently
            self.db.rollback()
            existing = self.db.query(SentinelProfileAssignment).filter(
                SentinelProfileAssignment.tenant_id == self.tenant_id,
                SentinelProfileAssignment.agent_id == agent_id if agent_id else SentinelProfileAssignment.agent_id.is_(None),
                SentinelProfileAssignment.skill_type == skill_type if skill_type else SentinelProfileAssignment.skill_type.is_(None),
            ).first()
            if existing:
                existing.profile_id = profile_id
                existing.assigned_by = assigned_by
                self.db.commit()
                self.db.refresh(existing)
                self._invalidate_cache()
                return existing
            raise ValueError("Failed to create or update assignment")

        self._invalidate_cache()
        return assignment

    def remove_assignment(self, assignment_id: int) -> bool:
        """Remove a profile assignment."""
        assignment = self.db.query(SentinelProfileAssignment).filter(
            SentinelProfileAssignment.id == assignment_id,
            SentinelProfileAssignment.tenant_id == self.tenant_id,
        ).first()

        if not assignment:
            return False

        self.db.delete(assignment)
        self.db.commit()
        self._invalidate_cache()

        return True

    # =========================================================================
    # Profile Resolution
    # =========================================================================

    def get_effective_config(
        self,
        agent_id: Optional[int] = None,
        skill_type: Optional[str] = None,
    ) -> Optional[SentinelEffectiveConfig]:
        """
        Resolve the effective security configuration for a given scope.

        Resolution chain (full replace, NOT merge):
        1. Skill-level profile (tenant + agent + skill_type)
        2. Agent-level profile (tenant + agent)
        3. Tenant-level profile (tenant)
        4. System default profile (is_default=True, tenant_id=NULL)
        5. Returns None if nothing found (caller should fall back to legacy)

        Args:
            agent_id: Optional agent ID
            skill_type: Optional skill type

        Returns:
            SentinelEffectiveConfig or None if no profile found
        """
        # Check cache
        cache_key = self._cache_key(agent_id, skill_type)
        cached = self._profile_cache.get(cache_key)
        if cached:
            cache_time, cached_config = cached
            if time.time() - cache_time < self.PROFILE_CACHE_TTL:
                return cached_config

        # 1. Skill-level
        if agent_id and skill_type:
            profile = self._get_assigned_profile(self.tenant_id, agent_id, skill_type)
            if profile:
                result = self._resolve_profile(profile, "skill")
                self._profile_cache[cache_key] = (time.time(), result)
                return result

        # 2. Agent-level
        if agent_id:
            profile = self._get_assigned_profile(self.tenant_id, agent_id, None)
            if profile:
                result = self._resolve_profile(profile, "agent")
                self._profile_cache[cache_key] = (time.time(), result)
                return result

        # 3. Tenant-level
        if self.tenant_id:
            profile = self._get_assigned_profile(self.tenant_id, None, None)
            if profile:
                result = self._resolve_profile(profile, "tenant")
                self._profile_cache[cache_key] = (time.time(), result)
                return result

        # 4. System default
        profile = self.db.query(SentinelProfile).filter(
            SentinelProfile.is_system == True,
            SentinelProfile.is_default == True,
            SentinelProfile.tenant_id.is_(None),
        ).first()

        if profile:
            result = self._resolve_profile(profile, "system")
            self._profile_cache[cache_key] = (time.time(), result)
            return result

        # 5. No profile found
        return None

    def _get_assigned_profile(
        self,
        tenant_id: str,
        agent_id: Optional[int],
        skill_type: Optional[str],
    ) -> Optional[SentinelProfile]:
        """Get the profile assigned at a specific scope level."""
        query = self.db.query(SentinelProfileAssignment).filter(
            SentinelProfileAssignment.tenant_id == tenant_id,
        )

        if agent_id is not None:
            query = query.filter(SentinelProfileAssignment.agent_id == agent_id)
        else:
            query = query.filter(SentinelProfileAssignment.agent_id.is_(None))

        if skill_type is not None:
            query = query.filter(SentinelProfileAssignment.skill_type == skill_type)
        else:
            query = query.filter(SentinelProfileAssignment.skill_type.is_(None))

        assignment = query.first()
        if not assignment:
            return None

        return self.db.query(SentinelProfile).filter(
            SentinelProfile.id == assignment.profile_id
        ).first()

    def _resolve_profile(self, profile: SentinelProfile, source: str) -> SentinelEffectiveConfig:
        """
        Resolve a profile into a SentinelEffectiveConfig.

        Iterates DETECTION_REGISTRY, checks profile's detection_overrides JSON
        for each type, falls back to registry default_enabled if absent.
        """
        try:
            overrides = json.loads(profile.detection_overrides or "{}")
        except (json.JSONDecodeError, TypeError):
            overrides = {}

        detection_config = {}
        for det_type, registry_info in DETECTION_REGISTRY.items():
            override = overrides.get(det_type, {})
            detection_config[det_type] = {
                "enabled": override.get("enabled", registry_info.get("default_enabled", True)),
                "custom_prompt": override.get("custom_prompt", None),
            }

        return SentinelEffectiveConfig(
            profile_id=profile.id,
            profile_name=profile.name,
            profile_source=source,
            # Global settings
            is_enabled=profile.is_enabled,
            detection_mode=profile.detection_mode,
            aggressiveness_level=profile.aggressiveness_level,
            # Component toggles
            enable_prompt_analysis=profile.enable_prompt_analysis,
            enable_tool_analysis=profile.enable_tool_analysis,
            enable_shell_analysis=profile.enable_shell_analysis,
            enable_slash_command_analysis=profile.enable_slash_command_analysis,
            # LLM
            llm_provider=profile.llm_provider,
            llm_model=profile.llm_model,
            llm_max_tokens=profile.llm_max_tokens,
            llm_temperature=profile.llm_temperature,
            # Performance
            cache_ttl_seconds=profile.cache_ttl_seconds,
            max_input_chars=profile.max_input_chars,
            timeout_seconds=profile.timeout_seconds,
            # Actions
            block_on_detection=profile.block_on_detection,
            log_all_analyses=profile.log_all_analyses,
            # Notifications
            enable_notifications=profile.enable_notifications,
            notification_on_block=profile.notification_on_block,
            notification_on_detect=profile.notification_on_detect,
            notification_recipient=profile.notification_recipient,
            notification_message_template=profile.notification_message_template,
            # Detection config
            detection_config=detection_config,
        )

    # =========================================================================
    # Hierarchy (for graph view)
    # =========================================================================

    def get_hierarchy(self) -> dict:
        """
        Build full security hierarchy tree for graph visualization.

        Returns pre-built tree: Tenant -> Agents -> Skills with
        assigned and effective profiles at each level.
        """
        if not self.tenant_id:
            return {"tenant": None}

        # Get tenant-level assignment
        tenant_assignment = self.db.query(SentinelProfileAssignment).filter(
            SentinelProfileAssignment.tenant_id == self.tenant_id,
            SentinelProfileAssignment.agent_id.is_(None),
            SentinelProfileAssignment.skill_type.is_(None),
        ).first()

        tenant_profile = None
        if tenant_assignment:
            p = self.db.query(SentinelProfile).get(tenant_assignment.profile_id)
            if p:
                tenant_profile = {"id": p.id, "name": p.name, "slug": p.slug}

        # Get all agents for this tenant (join Contact for display name)
        agents = (
            self.db.query(Agent, Contact.friendly_name)
            .outerjoin(Contact, Agent.contact_id == Contact.id)
            .filter(Agent.tenant_id == self.tenant_id)
            .order_by(Contact.friendly_name)
            .all()
        )

        agent_list = []
        for agent, agent_name in agents:
            # Agent-level assignment
            agent_assignment = self.db.query(SentinelProfileAssignment).filter(
                SentinelProfileAssignment.tenant_id == self.tenant_id,
                SentinelProfileAssignment.agent_id == agent.id,
                SentinelProfileAssignment.skill_type.is_(None),
            ).first()

            agent_profile = None
            if agent_assignment:
                p = self.db.query(SentinelProfile).get(agent_assignment.profile_id)
                if p:
                    agent_profile = {"id": p.id, "name": p.name, "slug": p.slug}

            # Effective profile for agent
            effective = self.get_effective_config(agent_id=agent.id)
            effective_profile = None
            if effective:
                effective_profile = {
                    "id": effective.profile_id,
                    "name": effective.profile_name,
                    "slug": "",
                    "source": effective.profile_source,
                    "detection_mode": effective.detection_mode,
                    "aggressiveness_level": effective.aggressiveness_level,
                    "is_enabled": effective.is_enabled,
                }

            # All skills configured on this agent
            agent_skills = self.db.query(AgentSkill).filter(
                AgentSkill.agent_id == agent.id,
            ).all()

            # Skill-level security profile assignments
            skill_assignments = self.db.query(SentinelProfileAssignment).filter(
                SentinelProfileAssignment.tenant_id == self.tenant_id,
                SentinelProfileAssignment.agent_id == agent.id,
                SentinelProfileAssignment.skill_type.isnot(None),
            ).all()
            assignment_map = {sa.skill_type: sa for sa in skill_assignments}

            skills = []
            seen_skill_types = set()

            for skill_record in agent_skills:
                st = skill_record.skill_type
                seen_skill_types.add(st)

                sa = assignment_map.get(st)
                skill_profile = None
                if sa:
                    p = self.db.query(SentinelProfile).get(sa.profile_id)
                    if p:
                        skill_profile = {"id": p.id, "name": p.name, "slug": p.slug}

                skill_effective = self.get_effective_config(
                    agent_id=agent.id, skill_type=st
                )
                skill_effective_profile = None
                if skill_effective:
                    skill_effective_profile = {
                        "id": skill_effective.profile_id,
                        "name": skill_effective.profile_name,
                        "slug": "",
                        "source": skill_effective.profile_source,
                        "detection_mode": skill_effective.detection_mode,
                        "aggressiveness_level": skill_effective.aggressiveness_level,
                        "is_enabled": skill_effective.is_enabled,
                    }

                skills.append({
                    "skill_type": st,
                    "name": st,
                    "is_enabled": skill_record.is_enabled,
                    "profile": skill_profile,
                    "effective_profile": skill_effective_profile,
                })

            # Include orphaned assignments (skill removed but assignment remains)
            for sa in skill_assignments:
                if sa.skill_type not in seen_skill_types:
                    skill_profile = None
                    p = self.db.query(SentinelProfile).get(sa.profile_id)
                    if p:
                        skill_profile = {"id": p.id, "name": p.name, "slug": p.slug}

                    skill_effective = self.get_effective_config(
                        agent_id=agent.id, skill_type=sa.skill_type
                    )
                    skill_effective_profile = None
                    if skill_effective:
                        skill_effective_profile = {
                            "id": skill_effective.profile_id,
                            "name": skill_effective.profile_name,
                            "slug": "",
                            "source": skill_effective.profile_source,
                            "detection_mode": skill_effective.detection_mode,
                            "aggressiveness_level": skill_effective.aggressiveness_level,
                            "is_enabled": skill_effective.is_enabled,
                        }

                    skills.append({
                        "skill_type": sa.skill_type,
                        "name": sa.skill_type,
                        "is_enabled": False,
                        "profile": skill_profile,
                        "effective_profile": skill_effective_profile,
                    })

            agent_list.append({
                "id": agent.id,
                "name": agent_name or f"Agent {agent.id}",
                "is_active": agent.is_active,
                "profile": agent_profile,
                "effective_profile": effective_profile,
                "skills": skills,
            })

        return {
            "tenant": {
                "id": self.tenant_id,
                "name": self.tenant_id,
                "profile": tenant_profile,
                "agents": agent_list,
            }
        }

    # =========================================================================
    # Cache
    # =========================================================================

    def _cache_key(self, agent_id: Optional[int], skill_type: Optional[str]) -> str:
        return f"{self.tenant_id}:{agent_id}:{skill_type}"

    @classmethod
    def _invalidate_cache(cls):
        """Clear entire profile resolution cache."""
        cls._profile_cache.clear()

    # =========================================================================
    # Validation
    # =========================================================================

    def _validate_detection_overrides(self, json_str: str) -> dict:
        """
        Validate detection_overrides JSON.

        Rules:
        1. Must be valid JSON
        2. Top-level keys must be strings
        3. Values must be objects with only 'enabled' (bool) and/or 'custom_prompt' (str|null)
        4. Unknown top-level keys are allowed (forward-compatible)
        5. Unknown sub-keys rejected
        """
        try:
            data = json.loads(json_str)
        except (json.JSONDecodeError, TypeError) as e:
            raise ValueError(f"Invalid JSON in detection_overrides: {e}")

        if not isinstance(data, dict):
            raise ValueError("detection_overrides must be a JSON object")

        allowed_sub_keys = {"enabled", "custom_prompt"}

        for key, value in data.items():
            if not isinstance(key, str):
                raise ValueError(f"detection_overrides keys must be strings, got: {type(key)}")

            if not isinstance(value, dict):
                raise ValueError(f"detection_overrides['{key}'] must be an object")

            unknown_keys = set(value.keys()) - allowed_sub_keys
            if unknown_keys:
                raise ValueError(
                    f"detection_overrides['{key}'] has unknown keys: {unknown_keys}. "
                    f"Allowed: {allowed_sub_keys}"
                )

            if "enabled" in value and not isinstance(value["enabled"], bool):
                raise ValueError(f"detection_overrides['{key}'].enabled must be boolean")

            if "custom_prompt" in value and value["custom_prompt"] is not None:
                if not isinstance(value["custom_prompt"], str):
                    raise ValueError(f"detection_overrides['{key}'].custom_prompt must be string or null")

        return data

    def _clear_default(self, tenant_id: Optional[str]):
        """Clear is_default on all profiles for a given tenant scope."""
        query = self.db.query(SentinelProfile).filter(
            SentinelProfile.is_default == True,
        )

        if tenant_id:
            query = query.filter(SentinelProfile.tenant_id == tenant_id)
        else:
            query = query.filter(SentinelProfile.tenant_id.is_(None))

        for profile in query.all():
            profile.is_default = False
