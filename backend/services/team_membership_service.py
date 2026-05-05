"""Agent Team membership A2A permission snapshot/restore helpers.

This service owns only the membership-side permission choreography:
external A2A rows are snapshotted and disabled while an agent is inside a
team, and team-created in-team grants are tracked so removal only deletes
rows this service created.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models import (
    Agent,
    AgentCommunicationPermission,
    AgentTeam,
    AgentTeamMember,
    AgentTeamMemberA2ASnapshot,
    TeamMemberRole,
)
from models_rbac import Tenant


SERVICE_CREATED_GRANT_KIND = "service_created_in_team_grant"


class TeamMembershipError(ValueError):
    """Raised when a membership mutation fails validation."""


@dataclass(frozen=True)
class TeamMembershipChange:
    tenant_id: str
    team_id: int
    agent_id: int
    membership_id: Optional[int] = None
    disabled_permission_ids: tuple[int, ...] = field(default_factory=tuple)
    restored_permission_ids: tuple[int, ...] = field(default_factory=tuple)
    created_in_team_permission_ids: tuple[int, ...] = field(default_factory=tuple)
    removed_in_team_permission_ids: tuple[int, ...] = field(default_factory=tuple)


def serialize_a2a_permission_payload(permission: AgentCommunicationPermission) -> dict[str, Any]:
    """Return the byte-stable permission payload restored on team removal."""
    return {
        "tenant_id": permission.tenant_id,
        "source_agent_id": permission.source_agent_id,
        "target_agent_id": permission.target_agent_id,
        "is_enabled": bool(permission.is_enabled),
        "max_depth": permission.max_depth,
        "rate_limit_rpm": permission.rate_limit_rpm,
        "allow_target_skills": bool(permission.allow_target_skills),
    }


class TeamMembershipService:
    DEFAULT_MAX_DEPTH = 3
    DEFAULT_RATE_LIMIT_RPM = 30
    DEFAULT_ALLOW_TARGET_SKILLS = False

    def __init__(self, db: Session, tenant_id: str, *, auto_commit: bool = True):
        self.db = db
        self.tenant_id = tenant_id
        self.auto_commit = auto_commit

    def add_agent_to_team(self, *, team_id: int, agent_id: int, commit: Optional[bool] = None) -> TeamMembershipChange:
        """Add an external agent as a user-visible team member."""
        manage_transaction = self._manage_transaction(commit)
        try:
            self._validate_tenant()
            team = self._get_team(team_id)
            agent = self._get_agent(agent_id)
            self._validate_user_member_agent(team, agent)

            membership = self._get_membership(team_id, agent_id)
            if membership is None:
                self._reject_other_team_membership(agent_id, team_id)
                membership = AgentTeamMember(
                    tenant_id=self.tenant_id,
                    team_id=team_id,
                    agent_id=agent_id,
                    role=TeamMemberRole.MEMBER.value,
                    execution_order=self._next_execution_order(team_id),
                    is_required=True,
                )
                self.db.add(membership)
                self.db.flush()
            elif membership.role == TeamMemberRole.COORDINATOR.value:
                raise TeamMembershipError("internal_coordinator_cannot_be_user_member")

            agent.is_team_member = True
            agent.current_team_id = team_id
            self.db.flush()

            current_member_ids = self._current_team_member_agent_ids(team_id)
            disabled_permission_ids = self._snapshot_and_disable_external_permissions(
                team_id=team_id,
                agent_id=agent_id,
                current_member_ids=current_member_ids,
            )
            created_in_team_permission_ids = self._grant_in_team_permissions(team_id)

            self._commit_or_flush(manage_transaction)
            return TeamMembershipChange(
                tenant_id=self.tenant_id,
                team_id=team_id,
                agent_id=agent_id,
                membership_id=membership.id,
                disabled_permission_ids=tuple(disabled_permission_ids),
                created_in_team_permission_ids=tuple(created_in_team_permission_ids),
            )
        except Exception:
            self._rollback_if_managed(manage_transaction)
            raise

    def remove_agent_from_team(self, *, team_id: int, agent_id: int, commit: Optional[bool] = None) -> TeamMembershipChange:
        """Remove an agent from a team and restore its external A2A state."""
        manage_transaction = self._manage_transaction(commit)
        try:
            self._validate_tenant()
            self._get_team(team_id)
            agent = self._get_agent(agent_id)
            membership = self._get_membership(team_id, agent_id)
            if membership is None:
                raise TeamMembershipError("agent_not_member_of_team")
            if membership.role == TeamMemberRole.COORDINATOR.value:
                raise TeamMembershipError("internal_coordinator_cannot_be_removed_as_user_member")
            membership_id = membership.id

            removed_in_team_permission_ids = self._remove_service_created_grants_for_agent(
                team_id=team_id,
                agent_id=agent_id,
            )
            restored_permission_ids = self._restore_external_snapshots_for_agent(
                team_id=team_id,
                agent_id=agent_id,
            )

            self.db.delete(membership)
            agent.is_team_member = False
            if agent.current_team_id == team_id:
                agent.current_team_id = None

            self._commit_or_flush(manage_transaction)
            return TeamMembershipChange(
                tenant_id=self.tenant_id,
                team_id=team_id,
                agent_id=agent_id,
                membership_id=membership_id,
                restored_permission_ids=tuple(restored_permission_ids),
                removed_in_team_permission_ids=tuple(removed_in_team_permission_ids),
            )
        except Exception:
            self._rollback_if_managed(manage_transaction)
            raise

    def _manage_transaction(self, commit: Optional[bool]) -> bool:
        return self.auto_commit if commit is None else bool(commit)

    def _commit_or_flush(self, manage_transaction: bool) -> None:
        if manage_transaction:
            self.db.commit()
        else:
            self.db.flush()

    def _rollback_if_managed(self, manage_transaction: bool) -> None:
        if manage_transaction:
            self.db.rollback()

    def _validate_tenant(self) -> None:
        tenant = self.db.query(Tenant.id).filter(Tenant.id == self.tenant_id).first()
        if tenant is None:
            raise TeamMembershipError("tenant_not_found")

    def _get_team(self, team_id: int) -> AgentTeam:
        team = (
            self.db.query(AgentTeam)
            .filter(
                AgentTeam.id == team_id,
                AgentTeam.tenant_id == self.tenant_id,
            )
            .first()
        )
        if team is None:
            raise TeamMembershipError("team_not_found_for_tenant")
        return team

    def _get_agent(self, agent_id: int) -> Agent:
        agent = (
            self.db.query(Agent)
            .filter(
                Agent.id == agent_id,
                Agent.tenant_id == self.tenant_id,
            )
            .first()
        )
        if agent is None:
            raise TeamMembershipError("agent_not_found_for_tenant")
        return agent

    def _validate_user_member_agent(self, team: AgentTeam, agent: Agent) -> None:
        if agent.is_internal or team.coordinator_agent_id == agent.id:
            raise TeamMembershipError("internal_coordinator_cannot_be_user_member")

    def _get_membership(self, team_id: int, agent_id: int) -> Optional[AgentTeamMember]:
        return (
            self.db.query(AgentTeamMember)
            .filter(
                AgentTeamMember.tenant_id == self.tenant_id,
                AgentTeamMember.team_id == team_id,
                AgentTeamMember.agent_id == agent_id,
            )
            .first()
        )

    def _reject_other_team_membership(self, agent_id: int, team_id: int) -> None:
        existing = (
            self.db.query(AgentTeamMember.id)
            .filter(
                AgentTeamMember.tenant_id == self.tenant_id,
                AgentTeamMember.agent_id == agent_id,
                AgentTeamMember.team_id != team_id,
            )
            .first()
        )
        if existing is not None:
            raise TeamMembershipError("agent_already_member_of_another_team")

    def _next_execution_order(self, team_id: int) -> int:
        orders = (
            order
            for (order,) in self.db.query(AgentTeamMember.execution_order)
            .filter(
                AgentTeamMember.tenant_id == self.tenant_id,
                AgentTeamMember.team_id == team_id,
                AgentTeamMember.role != TeamMemberRole.COORDINATOR.value,
            )
            .all()
            if order is not None
        )
        return max(orders, default=0) + 1

    def _current_team_member_agent_ids(self, team_id: int) -> set[int]:
        return {
            agent_id
            for (agent_id,) in self.db.query(AgentTeamMember.agent_id)
            .filter(
                AgentTeamMember.tenant_id == self.tenant_id,
                AgentTeamMember.team_id == team_id,
            )
            .all()
        }

    def _current_non_coordinator_member_agent_ids(self, team_id: int) -> list[int]:
        rows = (
            self.db.query(AgentTeamMember.agent_id)
            .join(Agent, Agent.id == AgentTeamMember.agent_id)
            .filter(
                AgentTeamMember.tenant_id == self.tenant_id,
                AgentTeamMember.team_id == team_id,
                AgentTeamMember.role != TeamMemberRole.COORDINATOR.value,
                Agent.tenant_id == self.tenant_id,
                Agent.is_internal.is_(False),
            )
            .order_by(AgentTeamMember.execution_order, AgentTeamMember.id)
            .all()
        )
        return [agent_id for (agent_id,) in rows]

    def _snapshot_and_disable_external_permissions(
        self,
        *,
        team_id: int,
        agent_id: int,
        current_member_ids: set[int],
    ) -> list[int]:
        now = datetime.utcnow()
        disabled_permission_ids: list[int] = []
        permissions = (
            self.db.query(AgentCommunicationPermission)
            .filter(
                AgentCommunicationPermission.tenant_id == self.tenant_id,
                or_(
                    AgentCommunicationPermission.source_agent_id == agent_id,
                    AgentCommunicationPermission.target_agent_id == agent_id,
                ),
            )
            .order_by(AgentCommunicationPermission.id)
            .all()
        )

        for permission in permissions:
            other_agent_id = (
                permission.target_agent_id
                if permission.source_agent_id == agent_id
                else permission.source_agent_id
            )
            if other_agent_id in current_member_ids:
                continue

            snapshot = self._get_snapshot(team_id, agent_id, permission.id)
            if snapshot is None:
                snapshot = AgentTeamMemberA2ASnapshot(
                    tenant_id=self.tenant_id,
                    team_id=team_id,
                    agent_id=agent_id,
                    permission_id=permission.id,
                    permission_payload_json=serialize_a2a_permission_payload(permission),
                    disabled_at=now,
                )
                self.db.add(snapshot)
            elif snapshot.disabled_at is None:
                snapshot.disabled_at = now

            if permission.is_enabled:
                disabled_permission_ids.append(permission.id)
            permission.is_enabled = False
            permission.updated_at = now

        self.db.flush()
        return disabled_permission_ids

    def _grant_in_team_permissions(self, team_id: int) -> list[int]:
        agent_ids = self._current_non_coordinator_member_agent_ids(team_id)
        created_permission_ids: list[int] = []

        for source_agent_id in agent_ids:
            for target_agent_id in agent_ids:
                if source_agent_id == target_agent_id:
                    continue
                permission = self._get_permission(source_agent_id, target_agent_id)
                if permission is not None:
                    marker = self._get_snapshot(team_id, source_agent_id, permission.id)
                    if marker is not None and self._is_service_created_grant(marker):
                        self._apply_default_grant(permission)
                    elif marker is not None:
                        self._enable_preexisting_in_team_permission(permission)
                    continue

                permission = AgentCommunicationPermission(
                    tenant_id=self.tenant_id,
                    source_agent_id=source_agent_id,
                    target_agent_id=target_agent_id,
                    is_enabled=True,
                    max_depth=self.DEFAULT_MAX_DEPTH,
                    rate_limit_rpm=self.DEFAULT_RATE_LIMIT_RPM,
                    allow_target_skills=self.DEFAULT_ALLOW_TARGET_SKILLS,
                )
                self.db.add(permission)
                self.db.flush()
                self.db.add(
                    AgentTeamMemberA2ASnapshot(
                        tenant_id=self.tenant_id,
                        team_id=team_id,
                        agent_id=source_agent_id,
                        permission_id=permission.id,
                        permission_payload_json={
                            "snapshot_kind": SERVICE_CREATED_GRANT_KIND,
                            "source_agent_id": source_agent_id,
                            "target_agent_id": target_agent_id,
                        },
                    )
                )
                created_permission_ids.append(permission.id)

        self.db.flush()
        return created_permission_ids

    def _remove_service_created_grants_for_agent(self, *, team_id: int, agent_id: int) -> list[int]:
        removed_permission_ids: list[int] = []
        snapshots = (
            self.db.query(AgentTeamMemberA2ASnapshot)
            .filter(
                AgentTeamMemberA2ASnapshot.tenant_id == self.tenant_id,
                AgentTeamMemberA2ASnapshot.team_id == team_id,
            )
            .order_by(AgentTeamMemberA2ASnapshot.id)
            .all()
        )

        for snapshot in snapshots:
            if not self._is_service_created_grant(snapshot):
                continue
            payload = snapshot.permission_payload_json or {}
            source_agent_id = payload.get("source_agent_id")
            target_agent_id = payload.get("target_agent_id")
            if agent_id not in (source_agent_id, target_agent_id):
                continue

            permission_id = snapshot.permission_id
            permission = None
            if permission_id is not None:
                permission = (
                    self.db.query(AgentCommunicationPermission)
                    .filter(
                        AgentCommunicationPermission.tenant_id == self.tenant_id,
                        AgentCommunicationPermission.id == permission_id,
                    )
                    .first()
                )
            self.db.delete(snapshot)
            self.db.flush()
            if permission is not None:
                removed_permission_ids.append(permission.id)
                self.db.delete(permission)

        self.db.flush()
        return removed_permission_ids

    def _restore_external_snapshots_for_agent(self, *, team_id: int, agent_id: int) -> list[int]:
        restored_permission_ids: list[int] = []
        snapshots = (
            self.db.query(AgentTeamMemberA2ASnapshot)
            .filter(
                AgentTeamMemberA2ASnapshot.tenant_id == self.tenant_id,
                AgentTeamMemberA2ASnapshot.team_id == team_id,
                AgentTeamMemberA2ASnapshot.agent_id == agent_id,
            )
            .order_by(AgentTeamMemberA2ASnapshot.id)
            .all()
        )

        for snapshot in snapshots:
            if self._is_service_created_grant(snapshot):
                continue
            payload = snapshot.permission_payload_json or {}
            self._validate_permission_payload(payload)
            permission = self._permission_for_snapshot(snapshot, payload)
            self._restore_permission_payload(permission, payload)
            restored_permission_ids.append(permission.id)
            snapshot.restored_at = datetime.utcnow()
            self.db.delete(snapshot)

        self.db.flush()
        return restored_permission_ids

    def _permission_for_snapshot(
        self,
        snapshot: AgentTeamMemberA2ASnapshot,
        payload: dict[str, Any],
    ) -> AgentCommunicationPermission:
        permission = None
        if snapshot.permission_id is not None:
            permission = (
                self.db.query(AgentCommunicationPermission)
                .filter(
                    AgentCommunicationPermission.tenant_id == self.tenant_id,
                    AgentCommunicationPermission.id == snapshot.permission_id,
                )
                .first()
            )
        if permission is None:
            permission = self._get_permission(
                int(payload["source_agent_id"]),
                int(payload["target_agent_id"]),
            )
        if permission is None:
            permission = AgentCommunicationPermission(
                tenant_id=self.tenant_id,
                source_agent_id=int(payload["source_agent_id"]),
                target_agent_id=int(payload["target_agent_id"]),
            )
            self.db.add(permission)
            self.db.flush()
        return permission

    def _validate_permission_payload(self, payload: dict[str, Any]) -> None:
        required_keys = {
            "tenant_id",
            "source_agent_id",
            "target_agent_id",
            "is_enabled",
            "max_depth",
            "rate_limit_rpm",
            "allow_target_skills",
        }
        if set(payload) != required_keys:
            raise TeamMembershipError("invalid_a2a_snapshot_payload")
        if payload["tenant_id"] != self.tenant_id:
            raise TeamMembershipError("cross_tenant_a2a_snapshot_payload")

        for key in ("source_agent_id", "target_agent_id"):
            agent = (
                self.db.query(Agent.id)
                .filter(
                    Agent.id == int(payload[key]),
                    Agent.tenant_id == self.tenant_id,
                )
                .first()
            )
            if agent is None:
                raise TeamMembershipError("snapshot_agent_not_found_for_tenant")

    def _restore_permission_payload(
        self,
        permission: AgentCommunicationPermission,
        payload: dict[str, Any],
    ) -> None:
        permission.tenant_id = payload["tenant_id"]
        permission.source_agent_id = int(payload["source_agent_id"])
        permission.target_agent_id = int(payload["target_agent_id"])
        permission.is_enabled = bool(payload["is_enabled"])
        permission.max_depth = payload["max_depth"]
        permission.rate_limit_rpm = payload["rate_limit_rpm"]
        permission.allow_target_skills = bool(payload["allow_target_skills"])

    def _apply_default_grant(self, permission: AgentCommunicationPermission) -> None:
        permission.is_enabled = True
        permission.max_depth = self.DEFAULT_MAX_DEPTH
        permission.rate_limit_rpm = self.DEFAULT_RATE_LIMIT_RPM
        permission.allow_target_skills = self.DEFAULT_ALLOW_TARGET_SKILLS

    @staticmethod
    def _enable_preexisting_in_team_permission(permission: AgentCommunicationPermission) -> None:
        permission.is_enabled = True
        permission.updated_at = datetime.utcnow()

    def _get_permission(
        self,
        source_agent_id: int,
        target_agent_id: int,
    ) -> Optional[AgentCommunicationPermission]:
        return (
            self.db.query(AgentCommunicationPermission)
            .filter(
                AgentCommunicationPermission.tenant_id == self.tenant_id,
                AgentCommunicationPermission.source_agent_id == source_agent_id,
                AgentCommunicationPermission.target_agent_id == target_agent_id,
            )
            .first()
        )

    def _get_snapshot(
        self,
        team_id: int,
        agent_id: int,
        permission_id: int,
    ) -> Optional[AgentTeamMemberA2ASnapshot]:
        return (
            self.db.query(AgentTeamMemberA2ASnapshot)
            .filter(
                AgentTeamMemberA2ASnapshot.tenant_id == self.tenant_id,
                AgentTeamMemberA2ASnapshot.team_id == team_id,
                AgentTeamMemberA2ASnapshot.agent_id == agent_id,
                AgentTeamMemberA2ASnapshot.permission_id == permission_id,
            )
            .first()
        )

    @staticmethod
    def _is_service_created_grant(snapshot: AgentTeamMemberA2ASnapshot) -> bool:
        payload = snapshot.permission_payload_json or {}
        return payload.get("snapshot_kind") == SERVICE_CREATED_GRANT_KIND
