"""Shared schemas for Agent Teams CRUD APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from models import TeamStatus, TeamTopology, TeamTriggerKind


def _enum_values(enum_cls) -> set[str]:
    return {item.value for item in enum_cls}


class TeamToolPool(BaseModel):
    sandboxed_tool_ids: list[int] = Field(default_factory=list)

    @field_validator("sandboxed_tool_ids")
    @classmethod
    def dedupe_tool_ids(cls, value: list[int]) -> list[int]:
        return list(dict.fromkeys(int(item) for item in value))


class TeamMemberCreate(BaseModel):
    agent_id: int = Field(..., gt=0)
    execution_order: Optional[int] = Field(None, ge=0)
    is_required: bool = True
    position_x: Optional[float] = None
    position_y: Optional[float] = None


class TeamMemberAdd(BaseModel):
    agent_id: int = Field(..., gt=0)
    execution_order: Optional[int] = Field(None, ge=0)
    is_required: bool = True
    position_x: Optional[float] = None
    position_y: Optional[float] = None


class TeamMemberOrderItem(BaseModel):
    agent_id: int = Field(..., gt=0)
    execution_order: int = Field(..., ge=0)


class TeamMemberOrderUpdate(BaseModel):
    members: list[TeamMemberOrderItem] = Field(..., min_length=1)


class TeamTriggerCreate(BaseModel):
    trigger_kind: str
    trigger_instance_id: int = Field(..., gt=0)
    event_types: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True

    @field_validator("trigger_kind")
    @classmethod
    def validate_trigger_kind(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in _enum_values(TeamTriggerKind):
            raise ValueError("Unsupported team trigger kind")
        return normalized

    @field_validator("event_types")
    @classmethod
    def normalize_event_types(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            event_type = str(item).strip()
            if event_type and event_type not in normalized:
                normalized.append(event_type)
        return normalized


class TeamTriggerUpdate(BaseModel):
    trigger_instance_id: Optional[int] = Field(None, gt=0)
    event_types: Optional[list[str]] = None
    filters: Optional[dict[str, Any]] = None
    is_enabled: Optional[bool] = None

    @field_validator("event_types")
    @classmethod
    def normalize_event_types(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is None:
            return value
        normalized: list[str] = []
        for item in value:
            event_type = str(item).strip()
            if event_type and event_type not in normalized:
                normalized.append(event_type)
        return normalized


class TeamCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = None
    goal_text: Optional[str] = None
    topology: str = Field(default=TeamTopology.LINE.value)
    status: str = Field(default=TeamStatus.DRAFT.value)
    max_steps: int = Field(default=10, ge=1, le=100)
    max_total_tokens: Optional[int] = Field(None, ge=1)
    max_concurrent_runs: int = Field(default=1, ge=1, le=10)
    tools: TeamToolPool = Field(default_factory=TeamToolPool)
    members: list[TeamMemberCreate] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Team name is required")
        return normalized

    @field_validator("topology")
    @classmethod
    def validate_topology(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in _enum_values(TeamTopology):
            raise ValueError("Unsupported team topology")
        return normalized

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in _enum_values(TeamStatus):
            raise ValueError("Unsupported team status")
        return normalized


class TeamUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = None
    goal_text: Optional[str] = None
    topology: Optional[str] = None
    status: Optional[str] = None
    max_steps: Optional[int] = Field(None, ge=1, le=100)
    max_total_tokens: Optional[int] = Field(None, ge=1)
    max_concurrent_runs: Optional[int] = Field(None, ge=1, le=10)
    tools: Optional[TeamToolPool] = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("Team name is required")
        return normalized

    @field_validator("topology")
    @classmethod
    def validate_topology(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized not in _enum_values(TeamTopology):
            raise ValueError("Unsupported team topology")
        return normalized

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized not in _enum_values(TeamStatus):
            raise ValueError("Unsupported team status")
        return normalized


class TeamMemberResponse(BaseModel):
    id: int
    team_id: int
    agent_id: int
    agent_name: Optional[str] = None
    role: str
    execution_order: Optional[int] = None
    is_required: bool
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TeamTriggerResponse(BaseModel):
    id: int
    trigger_kind: str
    trigger_instance_id: int
    event_types: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    config_json: Optional[dict[str, Any]] = None
    is_enabled: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TeamRunMemberStep(BaseModel):
    id: int
    agent_team_member_id: Optional[int] = None
    agent_id: Optional[int] = None
    agent_name: Optional[str] = None
    step_index: int
    status: str
    output_summary: Optional[str] = None
    output_text: Optional[str] = None
    sentinel_decision_json: Optional[dict[str, Any]] = None
    error_json: Optional[dict[str, Any]] = None
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class TeamRunListItem(BaseModel):
    id: int
    team_id: int
    status: str
    trigger_event_id: Optional[int] = None
    goal_text_snapshot: Optional[str] = None
    topology_snapshot: str
    total_steps: int
    completed_steps: int
    failed_steps: int
    final_output_summary: Optional[str] = None
    error_json: Optional[dict[str, Any]] = None
    total_input_tokens: int
    total_output_tokens: int
    total_cost_cents: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TeamRunDetail(TeamRunListItem):
    member_runs: list[TeamRunMemberStep] = Field(default_factory=list)


class TeamRunStartResponse(BaseModel):
    run_id: int
    status: str
    poll_url: str


class TeamListItem(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    goal_text: Optional[str] = None
    topology: str
    status: str
    coordinator_agent_id: Optional[int] = None
    member_count: int = 0
    last_run_status: Optional[str] = None
    max_steps: int
    max_total_tokens: Optional[int] = None
    max_concurrent_runs: int
    tools: TeamToolPool = Field(default_factory=TeamToolPool)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TeamDetail(TeamListItem):
    members: list[TeamMemberResponse] = Field(default_factory=list)
    triggers: list[TeamTriggerResponse] = Field(default_factory=list)
    last_run: Optional[TeamRunListItem] = None


class TeamListResponse(BaseModel):
    items: list[TeamListItem]
    total: int
    page: int
    page_size: int


class TeamRunListResponse(BaseModel):
    items: list[TeamRunListItem]
    total: int
    page: int
    page_size: int


class V1TeamListResponse(BaseModel):
    data: list[TeamListItem]
    meta: dict[str, int]


class V1TeamRunListResponse(BaseModel):
    data: list[TeamRunListItem]
    meta: dict[str, int]
