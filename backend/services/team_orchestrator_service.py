"""Agent Teams line-topology orchestration.

Phase 2 intentionally keeps this as an internal backend service: no API,
queue dispatch, trigger wiring, UI, or team memory scoping is introduced here.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy.orm import Session

from models import (
    Agent,
    AgentTeam,
    AgentTeamMember,
    AgentTeamMemberRun,
    AgentTeamRun,
    TeamMemberRole,
    TeamMemberRunStatus,
    TeamRunStatus,
    TeamStatus,
    TeamTopology,
)
from services.team_coordinator_service import (
    CoordinatorCommand,
    TeamCoordinatorCommandError,
    ensure_hidden_team_coordinator,
    parse_coordinator_command,
)


class TeamOrchestrationError(RuntimeError):
    """Base error for Agent Teams orchestration failures."""


class TeamValidationError(TeamOrchestrationError):
    """Raised before a run is created when a team is not runnable."""


AgentInvokeFn = Callable[..., Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class _RunnableMember:
    member: AgentTeamMember
    agent: Agent


def _build_agent_config(db: Session, agent: Agent) -> dict[str, Any]:
    """Mirror the non-UI AgentService config shape used by A2A/playground."""
    config = {
        "agent_id": agent.id,
        "model_provider": agent.model_provider,
        "model_name": agent.model_name,
        "provider_instance_id": getattr(agent, "provider_instance_id", None),
        "system_prompt": agent.system_prompt,
        "keywords": agent.keywords or [],
        "memory_size": agent.memory_size or 1000,
        "enabled_tools": [],
        "response_template": agent.response_template,
        "enable_semantic_search": agent.enable_semantic_search or False,
        "context_message_count": agent.context_message_count or 10,
        "memory_isolation_mode": agent.memory_isolation_mode or "isolated",
        "max_agentic_rounds": getattr(agent, "max_agentic_rounds", None),
        "max_agentic_loop_bytes": getattr(agent, "max_agentic_loop_bytes", None),
    }
    try:
        from models import Config

        platform_config = db.query(Config).first()
        if platform_config:
            config["platform_min_agentic_rounds"] = getattr(platform_config, "platform_min_agentic_rounds", None)
            config["platform_max_agentic_rounds"] = getattr(platform_config, "platform_max_agentic_rounds", None)
    except Exception:
        # Platform bounds are optional for the internal smoke path.
        pass
    return config


async def _invoke_agent_for_team_member(
    *,
    db: Session,
    tenant_id: str,
    team: AgentTeam,
    team_run: AgentTeamRun,
    member: AgentTeamMember,
    agent: Agent,
    message_text: str,
    token_tracker=None,
    agent_service_factory=None,
) -> dict[str, Any]:
    """Invoke one team member through the existing AgentService path."""
    from agent.agent_service import AgentService

    factory = agent_service_factory or AgentService
    service = factory(
        _build_agent_config(db, agent),
        db=db,
        agent_id=agent.id,
        token_tracker=token_tracker,
        tenant_id=tenant_id,
        persona_id=agent.persona_id,
        disable_skills=False,
        team_run_id=team_run.id,
    )
    return await service.process_message(
        sender_key=f"team:{team.id}:run:{team_run.id}",
        message_text=message_text,
        original_query=team.goal_text or message_text,
    )


def _last_json_object(text: str) -> Optional[dict[str, Any]]:
    decoder = json.JSONDecoder()
    last_obj: Optional[dict[str, Any]] = None
    last_command_obj: Optional[dict[str, Any]] = None
    for index, char in enumerate(text or ""):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            last_obj = parsed
            if isinstance(parsed.get("command"), str):
                last_command_obj = parsed
    return last_command_obj or last_obj


def _parse_member_answer(answer: str) -> tuple[str, dict[str, Any]]:
    parsed = _last_json_object(answer)
    if parsed and isinstance(parsed.get("summary"), str) and parsed["summary"].strip():
        return parsed["summary"].strip(), parsed

    fallback = " ".join((answer or "").strip().split())
    return fallback[:500] or "[No output]", {
        "summary": fallback[:500] or "[No output]",
        "key_findings": [],
        "open_questions": [],
        "parse_fallback": True,
    }


def _token_counts(token_usage: Any) -> tuple[int, int]:
    if not isinstance(token_usage, dict):
        return 0, 0
    prompt = token_usage.get("prompt", token_usage.get("prompt_tokens", token_usage.get("input", 0)))
    completion = token_usage.get(
        "completion",
        token_usage.get("completion_tokens", token_usage.get("output", 0)),
    )
    try:
        return int(prompt or 0), int(completion or 0)
    except (TypeError, ValueError):
        return 0, 0


class TeamRunOrchestrator:
    """Run an Agent Team using the internal topology runtime."""

    def __init__(
        self,
        db: Session,
        tenant_id: str,
        team_id: int,
        token_tracker=None,
        agent_service_factory=None,
        wall_clock_seconds: int = 600,
        agent_invoke_fn: Optional[AgentInvokeFn] = None,
    ):
        self.db = db
        self.tenant_id = tenant_id
        self.team_id = team_id
        self.token_tracker = token_tracker
        self.agent_service_factory = agent_service_factory
        self.wall_clock_seconds = wall_clock_seconds
        self.agent_invoke_fn = agent_invoke_fn or _invoke_agent_for_team_member

    async def run(self, trigger_event_id: Optional[int] = None) -> AgentTeamRun:
        team = self._load_active_team()
        if team.topology == TeamTopology.LINE.value:
            return await self.run_line(trigger_event_id=trigger_event_id)
        if team.topology == TeamTopology.MESH.value:
            return await self.run_mesh(trigger_event_id=trigger_event_id)
        raise TeamValidationError("unsupported_topology")

    async def run_line(self, trigger_event_id: Optional[int] = None) -> AgentTeamRun:
        team, runnable_members = self._load_runnable_line_team()
        if team.max_steps is not None and len(runnable_members) > team.max_steps:
            raise TeamValidationError("team_max_steps_too_low")
        team_run = self._create_run(team, trigger_event_id)
        start_monotonic = time.monotonic()

        prior_summaries: list[str] = []
        previous_output = ""
        previous_summary = ""

        for step_index, runnable in enumerate(runnable_members, start=1):
            if self._elapsed(start_monotonic) >= self.wall_clock_seconds:
                self._finish_run(
                    team_run,
                    TeamRunStatus.TIMEOUT.value,
                    error={"reason": "wall_clock_timeout"},
                    skipped_members=runnable_members[step_index - 1 :],
                    first_skipped_step=step_index,
                )
                return team_run

            prompt = self._build_line_prompt(
                team=team,
                step_index=step_index,
                member=runnable.member,
                prior_summaries=prior_summaries,
                previous_output=previous_output,
            )
            member_run = self._create_member_run(
                team_run=team_run,
                runnable=runnable,
                step_index=step_index,
                prompt=prompt,
                prior_summaries=prior_summaries,
                previous_output=previous_output,
            )

            try:
                remaining = max(0.001, self.wall_clock_seconds - self._elapsed(start_monotonic))
                result = await asyncio.wait_for(
                    self.agent_invoke_fn(
                        db=self.db,
                        tenant_id=self.tenant_id,
                        team=team,
                        team_run=team_run,
                        member=runnable.member,
                        agent=runnable.agent,
                        message_text=prompt,
                        token_tracker=self.token_tracker,
                        agent_service_factory=self.agent_service_factory,
                    ),
                    timeout=remaining,
                )
            except asyncio.TimeoutError:
                self._mark_member_failed(member_run, {"reason": "wall_clock_timeout"})
                self._finish_run(
                    team_run,
                    TeamRunStatus.TIMEOUT.value,
                    error={"reason": "wall_clock_timeout"},
                    skipped_members=runnable_members[step_index:],
                    first_skipped_step=step_index + 1,
                )
                return team_run
            except Exception as exc:
                self._mark_member_failed(member_run, {"reason": "member_exception", "message": str(exc)[:500]})
                self._finish_run(
                    team_run,
                    TeamRunStatus.FAILED.value,
                    error={"reason": "member_exception", "member_id": runnable.member.id, "message": str(exc)[:500]},
                    skipped_members=runnable_members[step_index:],
                    first_skipped_step=step_index + 1,
                )
                return team_run

            if result.get("error"):
                self._mark_member_failed(member_run, {"reason": "member_error", "message": str(result["error"])[:500]})
                self._finish_run(
                    team_run,
                    TeamRunStatus.FAILED.value,
                    error={"reason": "member_error", "member_id": runnable.member.id, "message": str(result["error"])[:500]},
                    skipped_members=runnable_members[step_index:],
                    first_skipped_step=step_index + 1,
                )
                return team_run

            answer = result.get("answer") or ""
            summary, parsed = _parse_member_answer(answer)
            input_tokens, output_tokens = _token_counts(result.get("tokens"))
            self._mark_member_completed(
                member_run,
                answer=answer,
                summary=summary,
                parsed_summary=parsed,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

            team_run.completed_steps += 1
            team_run.total_input_tokens += input_tokens
            team_run.total_output_tokens += output_tokens
            previous_output = answer
            previous_summary = summary
            prior_summaries.append(summary)
            self.db.commit()

            if (
                team.max_total_tokens is not None
                and (team_run.total_input_tokens + team_run.total_output_tokens) > team.max_total_tokens
            ):
                self._finish_run(
                    team_run,
                    TeamRunStatus.FAILED.value,
                    error={"reason": "max_total_tokens_exceeded"},
                    skipped_members=runnable_members[step_index:],
                    first_skipped_step=step_index + 1,
                )
                return team_run

        team_run.status = TeamRunStatus.COMPLETED.value
        team_run.completed_at = datetime.utcnow()
        team_run.final_output_summary = previous_summary or previous_output[:1000]
        self.db.commit()
        self.db.refresh(team_run)
        return team_run

    async def run_mesh(self, trigger_event_id: Optional[int] = None) -> AgentTeamRun:
        team, coordinator, runnable_members = self._load_runnable_mesh_team()
        team_run = self._create_run(team, trigger_event_id)
        start_monotonic = time.monotonic()
        transcript: list[dict[str, Any]] = []
        dispatch_signatures: set[tuple[tuple[int, str], ...]] = set()
        step_index = 1

        while True:
            if self._limit_reached(team=team, team_run=team_run, step_index=step_index, start_monotonic=start_monotonic):
                self._finish_mesh_limit(team_run, team, step_index, start_monotonic)
                return team_run

            coordinator_prompt = self._build_mesh_coordinator_prompt(
                team=team,
                coordinator_member=coordinator.member,
                runnable_members=runnable_members,
                transcript=transcript,
            )
            coordinator_run = self._create_member_run(
                team_run=team_run,
                runnable=coordinator,
                step_index=step_index,
                prompt=coordinator_prompt,
                prior_summaries=[entry.get("summary", "") for entry in transcript if entry.get("summary")],
                previous_output=json.dumps(transcript[-5:]) if transcript else "",
            )
            step_index += 1

            coordinator_result = await self._invoke_with_limits(
                team=team,
                team_run=team_run,
                member_run=coordinator_run,
                runnable=coordinator,
                message_text=coordinator_prompt,
                start_monotonic=start_monotonic,
            )
            if coordinator_result is None:
                return team_run

            answer = coordinator_result.get("answer") or ""
            input_tokens, output_tokens = _token_counts(coordinator_result.get("tokens"))
            parsed = _last_json_object(answer)
            try:
                command = parse_coordinator_command(parsed)
            except TeamCoordinatorCommandError as exc:
                self._mark_member_failed(coordinator_run, {"reason": str(exc), "answer_preview": answer[:500]})
                self._finish_run(team_run, TeamRunStatus.FAILED.value, error={"reason": str(exc)}, skipped_members=[], first_skipped_step=step_index)
                return team_run

            self._mark_member_completed(
                coordinator_run,
                answer=answer,
                summary=self._coordinator_summary(command),
                parsed_summary={"coordinator_command": command.raw},
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            self._add_tokens(team_run, input_tokens, output_tokens)
            self.db.commit()

            if self._token_limit_exceeded(team, team_run):
                self._finish_run(team_run, TeamRunStatus.FAILED.value, error={"reason": "max_total_tokens_exceeded"}, skipped_members=[], first_skipped_step=step_index)
                return team_run

            if command.command == "finish":
                team_run.status = TeamRunStatus.COMPLETED.value
                team_run.completed_at = datetime.utcnow()
                team_run.final_output_summary = command.summary
                self.db.commit()
                self.db.refresh(team_run)
                return team_run

            if command.command == "escalate":
                self._finish_run(
                    team_run,
                    TeamRunStatus.GOAL_NOT_ACHIEVED.value,
                    error={"reason": "coordinator_escalated", "message": command.reason},
                    skipped_members=[],
                    first_skipped_step=step_index,
                )
                team_run.final_output_summary = command.summary or command.reason
                self.db.commit()
                self.db.refresh(team_run)
                return team_run

            signature = self._dispatch_signature(command)
            if signature in dispatch_signatures:
                self._finish_run(
                    team_run,
                    TeamRunStatus.FAILED.value,
                    error={"reason": "repeated_dispatch_loop_detected", "dispatches": list(signature)},
                    skipped_members=[],
                    first_skipped_step=step_index,
                )
                return team_run
            dispatch_signatures.add(signature)

            for dispatch in command.dispatches:
                if self._limit_reached(team=team, team_run=team_run, step_index=step_index, start_monotonic=start_monotonic):
                    self._finish_mesh_limit(team_run, team, step_index, start_monotonic)
                    return team_run
                runnable = self._runnable_by_member_id(runnable_members, dispatch["member_id"])
                if runnable is None:
                    self._finish_run(
                        team_run,
                        TeamRunStatus.FAILED.value,
                        error={"reason": "dispatch_member_not_found", "member_id": dispatch["member_id"]},
                        skipped_members=[],
                        first_skipped_step=step_index,
                    )
                    return team_run

                member_prompt = self._build_mesh_member_prompt(
                    team=team,
                    dispatch=dispatch,
                    transcript=transcript,
                    coordinator_reason=command.reason,
                )
                member_run = self._create_member_run(
                    team_run=team_run,
                    runnable=runnable,
                    step_index=step_index,
                    prompt=member_prompt,
                    prior_summaries=[entry.get("summary", "") for entry in transcript if entry.get("summary")],
                    previous_output=json.dumps(transcript[-5:]) if transcript else "",
                )
                step_index += 1
                result = await self._invoke_with_limits(
                    team=team,
                    team_run=team_run,
                    member_run=member_run,
                    runnable=runnable,
                    message_text=member_prompt,
                    start_monotonic=start_monotonic,
                )
                if result is None:
                    return team_run

                answer = result.get("answer") or ""
                summary, parsed_summary = _parse_member_answer(answer)
                input_tokens, output_tokens = _token_counts(result.get("tokens"))
                self._mark_member_completed(
                    member_run,
                    answer=answer,
                    summary=summary,
                    parsed_summary=parsed_summary,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
                self._add_tokens(team_run, input_tokens, output_tokens)
                team_run.completed_steps += 1
                transcript.append(
                    {
                        "member_id": runnable.member.id,
                        "agent_id": runnable.agent.id,
                        "summary": summary,
                        "dispatch": dispatch["message"],
                    }
                )
                self.db.commit()

                if self._token_limit_exceeded(team, team_run):
                    self._finish_run(team_run, TeamRunStatus.FAILED.value, error={"reason": "max_total_tokens_exceeded"}, skipped_members=[], first_skipped_step=step_index)
                    return team_run

    def _load_active_team(self) -> AgentTeam:
        team = (
            self.db.query(AgentTeam)
            .filter(AgentTeam.id == self.team_id, AgentTeam.tenant_id == self.tenant_id)
            .first()
        )
        if team is None:
            raise TeamValidationError("team_not_found")
        if team.status != TeamStatus.ACTIVE.value:
            raise TeamValidationError("team_not_active")
        return team

    def _load_runnable_line_team(self) -> tuple[AgentTeam, list[_RunnableMember]]:
        team = self._load_active_team()
        if team.topology != TeamTopology.LINE.value:
            raise TeamValidationError("unsupported_topology")
        return team, self._load_runnable_members(team, include_coordinator=False)

    def _load_runnable_mesh_team(self) -> tuple[AgentTeam, _RunnableMember, list[_RunnableMember]]:
        team = self._load_active_team()
        if team.topology != TeamTopology.MESH.value:
            raise TeamValidationError("unsupported_topology")
        coordinator_member, coordinator_agent = ensure_hidden_team_coordinator(self.db, self.tenant_id, team)
        if not coordinator_agent.is_active:
            raise TeamValidationError("team_coordinator_agent_inactive")
        runnable_members = self._load_runnable_members(team, include_coordinator=False)
        if not runnable_members:
            raise TeamValidationError("team_has_no_members")
        return team, _RunnableMember(member=coordinator_member, agent=coordinator_agent), runnable_members

    def _load_runnable_members(self, team: AgentTeam, *, include_coordinator: bool) -> list[_RunnableMember]:
        members = (
            self.db.query(AgentTeamMember)
            .filter(AgentTeamMember.team_id == team.id, AgentTeamMember.tenant_id == self.tenant_id)
            .all()
        )
        if not include_coordinator:
            members = [member for member in members if member.role != TeamMemberRole.COORDINATOR.value]
        ordered_members = sorted(
            members,
            key=lambda member: (
                member.execution_order is None,
                member.execution_order if member.execution_order is not None else 0,
                member.id,
            ),
        )
        if not ordered_members:
            raise TeamValidationError("team_has_no_members")

        runnable: list[_RunnableMember] = []
        for member in ordered_members:
            agent = (
                self.db.query(Agent)
                .filter(Agent.id == member.agent_id, Agent.tenant_id == self.tenant_id)
                .first()
            )
            if agent is None:
                raise TeamValidationError("team_member_agent_not_found")
            if not agent.is_active:
                raise TeamValidationError("team_member_agent_inactive")
            runnable.append(_RunnableMember(member=member, agent=agent))

        return runnable

    def _create_run(self, team: AgentTeam, trigger_event_id: Optional[int]) -> AgentTeamRun:
        now = datetime.utcnow()
        team_run = AgentTeamRun(
            tenant_id=self.tenant_id,
            team_id=team.id,
            status=TeamRunStatus.RUNNING.value,
            trigger_event_id=trigger_event_id,
            goal_text_snapshot=team.goal_text,
            topology_snapshot=team.topology,
            started_at=now,
            total_steps=0,
            completed_steps=0,
            failed_steps=0,
        )
        self.db.add(team_run)
        self.db.commit()
        self.db.refresh(team_run)
        return team_run

    def _create_member_run(
        self,
        *,
        team_run: AgentTeamRun,
        runnable: _RunnableMember,
        step_index: int,
        prompt: str,
        prior_summaries: list[str],
        previous_output: str,
    ) -> AgentTeamMemberRun:
        member_run = AgentTeamMemberRun(
            tenant_id=self.tenant_id,
            team_run_id=team_run.id,
            agent_team_member_id=runnable.member.id,
            agent_id=runnable.agent.id,
            step_index=step_index,
            status=TeamMemberRunStatus.RUNNING.value,
            input_context_json={
                "prompt": prompt,
                "prior_summaries": list(prior_summaries),
                "previous_output_preview": previous_output[:1000] if previous_output else None,
            },
            started_at=datetime.utcnow(),
        )
        team_run.total_steps += 1
        self.db.add(member_run)
        self.db.commit()
        self.db.refresh(member_run)
        self.db.refresh(team_run)
        return member_run

    def _build_line_prompt(
        self,
        *,
        team: AgentTeam,
        step_index: int,
        member: AgentTeamMember,
        prior_summaries: list[str],
        previous_output: str,
    ) -> str:
        summaries = "\n".join(f"{idx + 1}. {summary}" for idx, summary in enumerate(prior_summaries))
        summaries = summaries or "[No prior member summaries]"
        previous = previous_output or "[No previous member output]"
        return (
            f"You are executing step {step_index} in a line-topology Agent Team.\n\n"
            f"Team goal:\n{team.goal_text or '[No explicit team goal]'}\n\n"
            f"Your team member id: {member.id}\n"
            f"Prior member summaries:\n{summaries}\n\n"
            f"Previous member full output:\n{previous}\n\n"
            "Do your assigned part of the team goal. Respond normally first, then append one final JSON object "
            'with exactly these keys: {"summary": "...", "key_findings": ["..."], "open_questions": ["..."]}.'
        )

    def _build_mesh_coordinator_prompt(
        self,
        *,
        team: AgentTeam,
        coordinator_member: AgentTeamMember,
        runnable_members: list[_RunnableMember],
        transcript: list[dict[str, Any]],
    ) -> str:
        members = "\n".join(
            f"- member_id={runnable.member.id}, agent_id={runnable.agent.id}, role={runnable.member.role}, "
            f"order={runnable.member.execution_order}"
            for runnable in runnable_members
        )
        history = json.dumps(transcript[-10:], ensure_ascii=True)
        return (
            "You are coordinating a mesh-topology Agent Team.\n\n"
            f"Team goal:\n{team.goal_text or '[No explicit team goal]'}\n\n"
            f"Coordinator member id: {coordinator_member.id}\n"
            f"Max steps: {team.max_steps}\n"
            f"Max total tokens: {team.max_total_tokens if team.max_total_tokens is not None else '[unbounded]'}\n\n"
            f"Runnable members:\n{members}\n\n"
            f"Recent mesh transcript JSON:\n{history or '[]'}\n\n"
            "Choose the next action. Append one final JSON command object: dispatch, finish, or escalate."
        )

    def _build_mesh_member_prompt(
        self,
        *,
        team: AgentTeam,
        dispatch: dict[str, Any],
        transcript: list[dict[str, Any]],
        coordinator_reason: str,
    ) -> str:
        history = json.dumps(transcript[-10:], ensure_ascii=True)
        return (
            "You are a member in a mesh-topology Agent Team.\n\n"
            f"Team goal:\n{team.goal_text or '[No explicit team goal]'}\n\n"
            f"Coordinator reason:\n{coordinator_reason or '[No reason supplied]'}\n\n"
            f"Your dispatched task:\n{dispatch['message']}\n\n"
            f"Recent mesh transcript JSON:\n{history or '[]'}\n\n"
            "Complete only the dispatched task. Respond normally first, then append one final JSON object "
            'with exactly these keys: {"summary": "...", "key_findings": ["..."], "open_questions": ["..."]}.'
        )

    async def _invoke_with_limits(
        self,
        *,
        team: AgentTeam,
        team_run: AgentTeamRun,
        member_run: AgentTeamMemberRun,
        runnable: _RunnableMember,
        message_text: str,
        start_monotonic: float,
    ) -> Optional[dict[str, Any]]:
        try:
            remaining = max(0.001, self.wall_clock_seconds - self._elapsed(start_monotonic))
            result = await asyncio.wait_for(
                self.agent_invoke_fn(
                    db=self.db,
                    tenant_id=self.tenant_id,
                    team=team,
                    team_run=team_run,
                    member=runnable.member,
                    agent=runnable.agent,
                    message_text=message_text,
                    token_tracker=self.token_tracker,
                    agent_service_factory=self.agent_service_factory,
                ),
                timeout=remaining,
            )
        except asyncio.TimeoutError:
            self._mark_member_failed(member_run, {"reason": "wall_clock_timeout"})
            self._finish_run(
                team_run,
                TeamRunStatus.TIMEOUT.value,
                error={"reason": "wall_clock_timeout"},
                skipped_members=[],
                first_skipped_step=member_run.step_index + 1,
            )
            return None
        except Exception as exc:
            self._mark_member_failed(member_run, {"reason": "member_exception", "message": str(exc)[:500]})
            self._finish_run(
                team_run,
                TeamRunStatus.FAILED.value,
                error={"reason": "member_exception", "member_id": runnable.member.id, "message": str(exc)[:500]},
                skipped_members=[],
                first_skipped_step=member_run.step_index + 1,
            )
            return None

        if result.get("error"):
            self._mark_member_failed(member_run, {"reason": "member_error", "message": str(result["error"])[:500]})
            self._finish_run(
                team_run,
                TeamRunStatus.FAILED.value,
                error={"reason": "member_error", "member_id": runnable.member.id, "message": str(result["error"])[:500]},
                skipped_members=[],
                first_skipped_step=member_run.step_index + 1,
            )
            return None
        return result

    @staticmethod
    def _coordinator_summary(command: CoordinatorCommand) -> str:
        if command.command == "dispatch":
            return f"dispatch:{len(command.dispatches)}"
        if command.command == "finish":
            return command.summary
        if command.command == "escalate":
            return command.summary or command.reason
        return command.command

    @staticmethod
    def _dispatch_signature(command: CoordinatorCommand) -> tuple[tuple[int, str], ...]:
        return tuple(sorted((dispatch["member_id"], " ".join(dispatch["message"].split())) for dispatch in command.dispatches))

    @staticmethod
    def _runnable_by_member_id(
        runnable_members: list[_RunnableMember],
        member_id: int,
    ) -> Optional[_RunnableMember]:
        for runnable in runnable_members:
            if runnable.member.id == member_id:
                return runnable
        return None

    @staticmethod
    def _add_tokens(team_run: AgentTeamRun, input_tokens: int, output_tokens: int) -> None:
        team_run.total_input_tokens += input_tokens
        team_run.total_output_tokens += output_tokens

    @staticmethod
    def _token_limit_exceeded(team: AgentTeam, team_run: AgentTeamRun) -> bool:
        return (
            team.max_total_tokens is not None
            and (team_run.total_input_tokens + team_run.total_output_tokens) > team.max_total_tokens
        )

    def _limit_reached(
        self,
        *,
        team: AgentTeam,
        team_run: AgentTeamRun,
        step_index: int,
        start_monotonic: float,
    ) -> bool:
        if self._elapsed(start_monotonic) >= self.wall_clock_seconds:
            return True
        if team.max_steps is not None and step_index > team.max_steps:
            return True
        return self._token_limit_exceeded(team, team_run)

    def _finish_mesh_limit(
        self,
        team_run: AgentTeamRun,
        team: AgentTeam,
        step_index: int,
        start_monotonic: float,
    ) -> None:
        if self._elapsed(start_monotonic) >= self.wall_clock_seconds:
            status = TeamRunStatus.TIMEOUT.value
            error = {"reason": "wall_clock_timeout"}
        elif self._token_limit_exceeded(team, team_run):
            status = TeamRunStatus.FAILED.value
            error = {"reason": "max_total_tokens_exceeded"}
        else:
            status = TeamRunStatus.FAILED.value
            error = {"reason": "max_steps_exceeded", "max_steps": team.max_steps}
        self._finish_run(team_run, status, error=error, skipped_members=[], first_skipped_step=step_index)

    def _mark_member_completed(
        self,
        member_run: AgentTeamMemberRun,
        *,
        answer: str,
        summary: str,
        parsed_summary: dict[str, Any],
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        member_run.status = TeamMemberRunStatus.COMPLETED.value
        member_run.output_text = answer
        member_run.output_summary = summary
        member_run.completed_at = datetime.utcnow()
        if member_run.started_at:
            member_run.duration_ms = int((member_run.completed_at - member_run.started_at).total_seconds() * 1000)
        member_run.input_tokens = input_tokens
        member_run.output_tokens = output_tokens
        context = dict(member_run.input_context_json or {})
        context["parsed_summary"] = parsed_summary
        member_run.input_context_json = context

    def _mark_member_failed(self, member_run: AgentTeamMemberRun, error: dict[str, Any]) -> None:
        member_run.status = TeamMemberRunStatus.FAILED.value
        member_run.error_json = error
        member_run.completed_at = datetime.utcnow()
        if member_run.started_at:
            member_run.duration_ms = int((member_run.completed_at - member_run.started_at).total_seconds() * 1000)
        self.db.commit()

    def _finish_run(
        self,
        team_run: AgentTeamRun,
        status: str,
        *,
        error: Optional[dict[str, Any]] = None,
        skipped_members: list[_RunnableMember],
        first_skipped_step: int,
    ) -> None:
        for offset, runnable in enumerate(skipped_members):
            self.db.add(
                AgentTeamMemberRun(
                    tenant_id=self.tenant_id,
                    team_run_id=team_run.id,
                    agent_team_member_id=runnable.member.id,
                    agent_id=runnable.agent.id,
                    step_index=first_skipped_step + offset,
                    status=TeamMemberRunStatus.SKIPPED.value,
                    error_json={"reason": "previous_member_failed" if status == TeamRunStatus.FAILED.value else status},
                )
            )
            team_run.total_steps += 1
        if status in (TeamRunStatus.FAILED.value, TeamRunStatus.TIMEOUT.value):
            team_run.failed_steps += 1
        team_run.status = status
        team_run.error_json = error
        team_run.completed_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(team_run)

    @staticmethod
    def _elapsed(start_monotonic: float) -> float:
        return time.monotonic() - start_monotonic
