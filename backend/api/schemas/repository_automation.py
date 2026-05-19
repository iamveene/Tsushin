"""Schemas for the Repository Automation Wizard backend endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


RepositoryProvider = Literal["github", "gitlab"]
RepositoryAutomationTemplate = Literal["repository_review_team", "repository_pr_agent"]
RepositoryRoutingMode = Literal["team_primary", "agent_flow"]


class RepositoryAutomationRequest(BaseModel):
    provider: RepositoryProvider
    integration_id: int = Field(..., gt=0)
    template_id: RepositoryAutomationTemplate

    repo_owner: Optional[str] = Field(default=None, min_length=1, max_length=100)
    repo_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    project_path: Optional[str] = Field(default=None, min_length=3, max_length=500)
    target: dict[str, Any] = Field(default_factory=dict)

    existing_trigger_id: Optional[int] = Field(default=None, gt=0)
    events: list[str] = Field(default_factory=list)
    branch_filter: Optional[str] = Field(default=None, max_length=255)
    path_filters: Optional[list[str]] = None
    author_filter: Optional[str] = Field(default=None, max_length=255)
    trigger_criteria: Optional[dict[str, Any]] = None

    integration_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    trigger_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    agent_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    team_name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    flow_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    routing_mode: Optional[RepositoryRoutingMode] = None

    @field_validator("provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        return str(value).strip().lower()

    @field_validator(
        "repo_owner",
        "repo_name",
        "project_path",
        "branch_filter",
        "author_filter",
        "integration_name",
        "trigger_name",
        "agent_name",
        "team_name",
        "flow_name",
    )
    @classmethod
    def normalize_optional_string(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("events")
    @classmethod
    def normalize_events(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value or []:
            event = str(item or "").strip()
            if event and event not in normalized:
                normalized.append(event)
        return normalized

    @field_validator("path_filters")
    @classmethod
    def normalize_path_filters(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is None:
            return None
        normalized: list[str] = []
        for item in value:
            path = str(item or "").strip()
            if path and path not in normalized:
                normalized.append(path)
        return normalized or None

    @model_validator(mode="after")
    def validate_target(self) -> "RepositoryAutomationRequest":
        target = self.target or {}
        if self.provider == "github":
            owner = self.repo_owner or target.get("owner") or target.get("repo_owner")
            repo = self.repo_name or target.get("repo") or target.get("repo_name")
            if not owner or not repo:
                raise ValueError("GitHub repository automation requires repo_owner and repo_name")
            self.repo_owner = str(owner).strip()
            self.repo_name = str(repo).strip()
        elif self.provider == "gitlab":
            project_path = self.project_path or target.get("project_path")
            if not project_path and target.get("namespace") and target.get("project"):
                project_path = f"{target['namespace']}/{target['project']}"
            if not project_path:
                raise ValueError("GitLab repository automation requires project_path")
            self.project_path = str(project_path).strip()

        effective_mode = self.routing_mode
        if effective_mode is None:
            effective_mode = "team_primary" if self.template_id == "repository_review_team" else "agent_flow"
            self.routing_mode = effective_mode
        if self.template_id == "repository_review_team" and effective_mode != "team_primary":
            raise ValueError("repository_review_team must use team_primary routing")
        if self.template_id == "repository_pr_agent" and effective_mode != "agent_flow":
            raise ValueError("repository_pr_agent must use agent_flow routing")
        return self


class RepositoryAutomationIntegrationRef(BaseModel):
    id: int
    provider: RepositoryProvider
    name: str
    reused: bool


class RepositoryAutomationTriggerRef(BaseModel):
    id: int
    provider: RepositoryProvider
    name: str
    events: list[str]
    canonical_events: list[str]
    reused: bool
    is_active: bool
    inbound_url: str


class RepositoryAutomationFlowRef(BaseModel):
    id: int
    name: str
    default_agent_id: Optional[int] = None
    is_active: bool
    created: bool


class RepositoryAutomationAgentRef(BaseModel):
    id: int
    name: str
    skills: list[str]


class RepositoryAutomationTeamRef(BaseModel):
    id: int
    name: str
    status: str
    member_count: int


class RepositoryAutomationBindingRef(BaseModel):
    id: int
    kind: str
    trigger_kind: str
    trigger_instance_id: int
    event_types: list[str] = Field(default_factory=list)
    is_active: bool
    flow_definition_id: Optional[int] = None
    team_id: Optional[int] = None
    suppress_default_agent: Optional[bool] = None


class RepositoryAutomationResponse(BaseModel):
    integration: RepositoryAutomationIntegrationRef
    trigger: RepositoryAutomationTriggerRef
    flow: RepositoryAutomationFlowRef
    team: Optional[RepositoryAutomationTeamRef] = None
    agents: list[RepositoryAutomationAgentRef]
    bindings: list[RepositoryAutomationBindingRef]
    links: dict[str, str]
    routing_mode: RepositoryRoutingMode
    created_at: datetime
