"""Tenant/team/run scoped scratch state for Agent Team executions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from models import AgentTeamRun, TeamRunScratch


class TeamRunScratchValidationError(ValueError):
    """Raised when a scratch operation targets an invalid tenant/team/run."""


class TeamRunScratchService:
    """Read/write scratch values isolated to one Agent Team run."""

    def __init__(self, db: Session):
        self.db = db

    def set(
        self,
        *,
        tenant_id: str,
        team_id: int,
        team_run_id: int,
        key: str,
        value: Any,
    ) -> TeamRunScratch:
        """Create or update one scratch value after validating the run scope."""
        normalized_key = self._normalize_key(key)
        self._validate_run(tenant_id=tenant_id, team_id=team_id, team_run_id=team_run_id)

        item = self._query_item(
            tenant_id=tenant_id,
            team_id=team_id,
            team_run_id=team_run_id,
            key=normalized_key,
        ).first()
        now = datetime.utcnow()
        if item:
            item.value_json = value
            item.updated_at = now
        else:
            item = TeamRunScratch(
                tenant_id=tenant_id,
                team_id=team_id,
                team_run_id=team_run_id,
                key=normalized_key,
                value_json=value,
                created_at=now,
                updated_at=now,
            )
            self.db.add(item)

        self.db.commit()
        self.db.refresh(item)
        return item

    def get(
        self,
        *,
        tenant_id: str,
        team_id: int,
        team_run_id: int,
        key: str,
        default: Any = None,
    ) -> Any:
        """Return a scratch value for a valid run scope, or default when absent."""
        normalized_key = self._normalize_key(key)
        self._validate_run(tenant_id=tenant_id, team_id=team_id, team_run_id=team_run_id)
        item = self._query_item(
            tenant_id=tenant_id,
            team_id=team_id,
            team_run_id=team_run_id,
            key=normalized_key,
        ).first()
        return item.value_json if item else default

    def list_keys(self, *, tenant_id: str, team_id: int, team_run_id: int) -> list[str]:
        """List scratch keys for a valid run scope."""
        self._validate_run(tenant_id=tenant_id, team_id=team_id, team_run_id=team_run_id)
        return [
            row[0]
            for row in (
                self.db.query(TeamRunScratch.key)
                .filter(
                    TeamRunScratch.tenant_id == tenant_id,
                    TeamRunScratch.team_id == team_id,
                    TeamRunScratch.team_run_id == team_run_id,
                )
                .order_by(TeamRunScratch.key.asc())
                .all()
            )
        ]

    def _validate_run(self, *, tenant_id: str, team_id: int, team_run_id: int) -> AgentTeamRun:
        run = (
            self.db.query(AgentTeamRun)
            .filter(
                AgentTeamRun.tenant_id == tenant_id,
                AgentTeamRun.team_id == team_id,
                AgentTeamRun.id == team_run_id,
            )
            .first()
        )
        if run is None:
            raise TeamRunScratchValidationError(
                f"Invalid team scratch scope: tenant={tenant_id}, team={team_id}, run={team_run_id}"
            )
        return run

    def _query_item(self, *, tenant_id: str, team_id: int, team_run_id: int, key: str):
        return self.db.query(TeamRunScratch).filter(
            TeamRunScratch.tenant_id == tenant_id,
            TeamRunScratch.team_id == team_id,
            TeamRunScratch.team_run_id == team_run_id,
            TeamRunScratch.key == key,
        )

    @staticmethod
    def _normalize_key(key: str) -> str:
        normalized = (key or "").strip()
        if not normalized:
            raise ValueError("scratch key is required")
        return normalized
