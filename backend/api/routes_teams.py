"""Agent Teams CRUD API routes."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from api.schemas.teams import (
    TeamCreate,
    TeamDetail,
    TeamListResponse,
    TeamMemberAdd,
    TeamMemberOrderUpdate,
    TeamMemberPatch,
    TeamMemberResponse,
    TeamRunDetail,
    TeamRunListResponse,
    TeamRunStartResponse,
    TeamTriggerCreate,
    TeamTriggerResponse,
    TeamTriggerUpdate,
    TeamUpdate,
)
from auth_dependencies import TenantContext, get_tenant_context, require_permission
from models_rbac import User
from services.agent_team_api_service import AgentTeamApiError, AgentTeamApiService, run_team_background

router = APIRouter(prefix="/api/teams", tags=["agent-teams"])


def _service(ctx: TenantContext, current_user: User) -> AgentTeamApiService:
    return AgentTeamApiService(ctx.db, ctx.tenant_id, user_id=current_user.id)


def _raise_api_error(exc: AgentTeamApiError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("", response_model=TeamListResponse, include_in_schema=False)
@router.get("/", response_model=TeamListResponse)
async def list_teams(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    include_archived: bool = Query(False),
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("agents.read")),
):
    try:
        return _service(ctx, current_user).list_teams(
            page=page,
            page_size=page_size,
            status=status_filter,
            include_archived=include_archived,
        )
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.post("", response_model=TeamDetail, status_code=status.HTTP_201_CREATED, include_in_schema=False)
@router.post("/", response_model=TeamDetail, status_code=status.HTTP_201_CREATED)
async def create_team(
    payload: TeamCreate,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("agents.write")),
):
    try:
        return _service(ctx, current_user).create_team(payload)
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.get("/{team_id}", response_model=TeamDetail)
async def get_team(
    team_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("agents.read")),
):
    try:
        return _service(ctx, current_user).get_team(team_id)
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.put("/{team_id}", response_model=TeamDetail)
async def update_team(
    team_id: int,
    payload: TeamUpdate,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("agents.write")),
):
    try:
        return _service(ctx, current_user).update_team(team_id, payload)
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_team(
    team_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("agents.delete")),
):
    try:
        _service(ctx, current_user).archive_team(team_id)
        return None
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.post("/{team_id}/members", response_model=TeamMemberResponse, status_code=status.HTTP_201_CREATED)
async def add_member(
    team_id: int,
    payload: TeamMemberAdd,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("agents.write")),
):
    try:
        return _service(ctx, current_user).add_member(team_id, payload)
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.delete("/{team_id}/members/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    team_id: int,
    agent_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("agents.write")),
):
    try:
        _service(ctx, current_user).remove_member(team_id, agent_id)
        return None
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.patch("/{team_id}/members/{agent_id}", response_model=TeamMemberResponse)
async def update_member(
    team_id: int,
    agent_id: int,
    payload: TeamMemberPatch,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("agents.write")),
):
    try:
        return _service(ctx, current_user).update_member(team_id, agent_id, payload)
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.put("/{team_id}/members/order", response_model=TeamDetail)
async def reorder_members(
    team_id: int,
    payload: TeamMemberOrderUpdate,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("agents.write")),
):
    try:
        return _service(ctx, current_user).reorder_members(team_id, payload)
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.post("/{team_id}/triggers", response_model=TeamTriggerResponse, status_code=status.HTTP_201_CREATED)
async def create_team_trigger_binding(
    team_id: int,
    payload: TeamTriggerCreate,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("agents.write")),
):
    try:
        return _service(ctx, current_user).create_trigger_binding(team_id, payload)
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.put("/{team_id}/triggers/{trigger_id}", response_model=TeamTriggerResponse)
async def update_team_trigger_binding(
    team_id: int,
    trigger_id: int,
    payload: TeamTriggerUpdate,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("agents.write")),
):
    try:
        return _service(ctx, current_user).update_trigger_binding(team_id, trigger_id, payload)
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.delete("/{team_id}/triggers/{trigger_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team_trigger_binding(
    team_id: int,
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("agents.write")),
):
    try:
        _service(ctx, current_user).delete_trigger_binding(team_id, trigger_id)
        return None
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.post("/{team_id}/runs", response_model=TeamRunStartResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_team_run(
    team_id: int,
    background_tasks: BackgroundTasks,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("agents.execute")),
):
    try:
        run = _service(ctx, current_user).precreate_manual_run(team_id)
        background_tasks.add_task(run_team_background, tenant_id=ctx.tenant_id, team_id=team_id, run_id=run.id)
        return {"run_id": run.id, "status": run.status, "poll_url": f"/api/teams/{team_id}/runs/{run.id}"}
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.get("/{team_id}/runs", response_model=TeamRunListResponse)
async def list_team_runs(
    team_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("agents.read")),
):
    try:
        return _service(ctx, current_user).list_runs(team_id, page=page, page_size=page_size)
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.post("/{team_id}/runs/{run_id}/cancel", response_model=TeamRunDetail)
async def cancel_team_run(
    team_id: int,
    run_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("agents.execute")),
):
    try:
        return _service(ctx, current_user).cancel_run(team_id, run_id)
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.get("/{team_id}/runs/{run_id}", response_model=TeamRunDetail)
async def get_team_run(
    team_id: int,
    run_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("agents.read")),
):
    try:
        return _service(ctx, current_user).get_run(team_id, run_id)
    except AgentTeamApiError as exc:
        _raise_api_error(exc)
