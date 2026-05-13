"""Agent Teams — Public API v1."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from api.api_auth import ApiCaller, require_api_permission
from api.schemas.teams import (
    TeamCreate,
    TeamDetail,
    TeamMemberAdd,
    TeamMemberOrderUpdate,
    TeamMemberPatch,
    TeamMemberResponse,
    TeamRunDetail,
    TeamRunStartResponse,
    TeamTriggerCreate,
    TeamTriggerResponse,
    TeamTriggerUpdate,
    TeamUpdate,
    V1TeamListResponse,
    V1TeamRunListResponse,
)
from api.v1.schemas import COMMON_RESPONSES, NOT_FOUND_RESPONSE, VALIDATION_RESPONSE
from db import get_db
from services.agent_team_api_service import AgentTeamApiError, AgentTeamApiService, run_team_background

router = APIRouter()


def _service(db: Session, caller: ApiCaller) -> AgentTeamApiService:
    return AgentTeamApiService(db, caller.tenant_id, user_id=caller.user_id)


def _raise_api_error(exc: AgentTeamApiError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/api/v1/teams", response_model=V1TeamListResponse, responses=COMMON_RESPONSES)
async def list_teams(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    include_archived: bool = Query(False),
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.read")),
):
    try:
        result = _service(db, caller).list_teams(
            page=page,
            page_size=per_page,
            status=status_filter,
            include_archived=include_archived,
        )
        return {
            "data": result["items"],
            "meta": {"total": result["total"], "page": page, "per_page": per_page},
        }
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.post(
    "/api/v1/teams",
    response_model=TeamDetail,
    status_code=status.HTTP_201_CREATED,
    responses={**COMMON_RESPONSES, **VALIDATION_RESPONSE},
)
async def create_team(
    payload: TeamCreate,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.write")),
):
    try:
        return _service(db, caller).create_team(payload)
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.get("/api/v1/teams/{team_id}", response_model=TeamDetail, responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE})
async def get_team(
    team_id: int,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.read")),
):
    try:
        return _service(db, caller).get_team(team_id)
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.put(
    "/api/v1/teams/{team_id}",
    response_model=TeamDetail,
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE, **VALIDATION_RESPONSE},
)
async def update_team(
    team_id: int,
    payload: TeamUpdate,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.write")),
):
    try:
        return _service(db, caller).update_team(team_id, payload)
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.delete("/api/v1/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT, responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE})
async def archive_team(
    team_id: int,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.delete")),
):
    try:
        _service(db, caller).archive_team(team_id)
        return None
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.delete(
    "/api/v1/teams/{team_id}/permanent",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE},
)
async def delete_team_permanently(
    team_id: int,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.delete")),
):
    try:
        _service(db, caller).delete_team_permanently(team_id)
        return None
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.post(
    "/api/v1/teams/{team_id}/members",
    response_model=TeamMemberResponse,
    status_code=status.HTTP_201_CREATED,
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE, **VALIDATION_RESPONSE},
)
async def add_member(
    team_id: int,
    payload: TeamMemberAdd,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.write")),
):
    try:
        return _service(db, caller).add_member(team_id, payload)
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.delete("/api/v1/teams/{team_id}/members/{agent_id}", status_code=status.HTTP_204_NO_CONTENT, responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE})
async def remove_member(
    team_id: int,
    agent_id: int,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.write")),
):
    try:
        _service(db, caller).remove_member(team_id, agent_id)
        return None
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.patch(
    "/api/v1/teams/{team_id}/members/{agent_id}",
    response_model=TeamMemberResponse,
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE, **VALIDATION_RESPONSE},
)
async def update_member(
    team_id: int,
    agent_id: int,
    payload: TeamMemberPatch,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.write")),
):
    try:
        return _service(db, caller).update_member(team_id, agent_id, payload)
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.put(
    "/api/v1/teams/{team_id}/members/order",
    response_model=TeamDetail,
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE, **VALIDATION_RESPONSE},
)
async def reorder_members(
    team_id: int,
    payload: TeamMemberOrderUpdate,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.write")),
):
    try:
        return _service(db, caller).reorder_members(team_id, payload)
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.post(
    "/api/v1/teams/{team_id}/triggers",
    response_model=TeamTriggerResponse,
    status_code=status.HTTP_201_CREATED,
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE, **VALIDATION_RESPONSE},
)
async def create_team_trigger_binding(
    team_id: int,
    payload: TeamTriggerCreate,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.write")),
):
    try:
        return _service(db, caller).create_trigger_binding(team_id, payload)
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.put(
    "/api/v1/teams/{team_id}/triggers/{trigger_id}",
    response_model=TeamTriggerResponse,
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE, **VALIDATION_RESPONSE},
)
async def update_team_trigger_binding(
    team_id: int,
    trigger_id: int,
    payload: TeamTriggerUpdate,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.write")),
):
    try:
        return _service(db, caller).update_trigger_binding(team_id, trigger_id, payload)
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.delete(
    "/api/v1/teams/{team_id}/triggers/{trigger_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE},
)
async def delete_team_trigger_binding(
    team_id: int,
    trigger_id: int,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.write")),
):
    try:
        _service(db, caller).delete_trigger_binding(team_id, trigger_id)
        return None
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.post(
    "/api/v1/teams/{team_id}/runs",
    response_model=TeamRunStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE},
)
async def start_team_run(
    team_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.execute")),
):
    try:
        run = _service(db, caller).precreate_manual_run(team_id)
        background_tasks.add_task(run_team_background, tenant_id=caller.tenant_id, team_id=team_id, run_id=run.id)
        return {"run_id": run.id, "status": run.status, "poll_url": f"/api/v1/teams/{team_id}/runs/{run.id}"}
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.get(
    "/api/v1/teams/{team_id}/runs",
    response_model=V1TeamRunListResponse,
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE},
)
async def list_team_runs(
    team_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.read")),
):
    try:
        result = _service(db, caller).list_runs(team_id, page=page, page_size=per_page)
        return {
            "data": result["items"],
            "meta": {"total": result["total"], "page": page, "per_page": per_page},
        }
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.post(
    "/api/v1/teams/{team_id}/runs/{run_id}/cancel",
    response_model=TeamRunDetail,
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE},
)
async def cancel_team_run(
    team_id: int,
    run_id: int,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.execute")),
):
    try:
        return _service(db, caller).cancel_run(team_id, run_id)
    except AgentTeamApiError as exc:
        _raise_api_error(exc)


@router.get("/api/v1/teams/{team_id}/runs/{run_id}", response_model=TeamRunDetail, responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE})
async def get_team_run(
    team_id: int,
    run_id: int,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.read")),
):
    try:
        return _service(db, caller).get_run(team_id, run_id)
    except AgentTeamApiError as exc:
        _raise_api_error(exc)
