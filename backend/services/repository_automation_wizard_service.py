"""Backend implementation for the Repository Automation Wizard."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from api.schemas.repository_automation import RepositoryAutomationRequest
from channels.github.trigger import (
    encrypt_webhook_secret as encrypt_github_webhook_secret,
    generate_webhook_secret as generate_github_webhook_secret,
    normalize_github_events,
    normalize_path_filters,
    normalize_repo_part,
    preview_secret as preview_github_secret,
)
from channels.gitlab.trigger import (
    encrypt_webhook_secret as encrypt_gitlab_webhook_secret,
    generate_webhook_secret as generate_gitlab_webhook_secret,
    normalize_gitlab_events,
    normalize_project_path,
    preview_secret as preview_gitlab_secret,
)
from channels.repository.events import GITHUB_EVENT_MAP, GITLAB_EVENT_MAP, canonical_event
from channels.github.criteria import validate_pr_criteria
from channels.repository.criteria import validate_repository_criteria
from channels.trigger_criteria import validate_criteria
from models import (
    Agent,
    AgentSkill,
    AgentSkillIntegration,
    AgentTeam,
    AgentTeamMember,
    AgentTeamTrigger,
    Contact,
    FlowNode,
    GitHubChannelInstance,
    GitHubIntegration,
    GitLabChannelInstance,
    GitLabIntegration,
    HubIntegration,
    TeamStatus,
    TeamTopology,
)
from services.flow_binding_service import (
    ensure_system_managed_flow_for_trigger,
    sync_system_managed_flow_default_agent,
)
from services.team_membership_service import TeamMembershipError, TeamMembershipService


SUPPORTED_REPOSITORY_TEAM_EVENTS = {
    *GITHUB_EVENT_MAP.values(),
    *GITLAB_EVENT_MAP.values(),
}


class RepositoryAutomationWizardError(ValueError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _display_name(row: Any) -> str:
    return (
        getattr(row, "display_name", None)
        or getattr(row, "name", None)
        or getattr(row, "integration_name", None)
        or f"#{getattr(row, 'id', 'unknown')}"
    )


def _active(row: Any) -> bool:
    return bool(getattr(row, "is_active", True)) and (getattr(row, "status", None) or "active") == "active"


def _repository_label(payload: RepositoryAutomationRequest) -> str:
    if payload.provider == "github":
        return f"{payload.repo_owner}/{payload.repo_name}"
    return payload.project_path or "repository"


def _provider_label(provider: str) -> str:
    return "GitHub" if provider == "github" else "GitLab"


def _default_trigger_name(payload: RepositoryAutomationRequest) -> str:
    return payload.trigger_name or payload.integration_name or f"{_provider_label(payload.provider)} Review: {_repository_label(payload)}"


def _provider_event(provider: str, canonical: str) -> str:
    if canonical.startswith(f"{provider}."):
        return canonical.split(".", 1)[1]
    return canonical


def _canonicalize_events(provider: str, events: list[str]) -> tuple[list[str], list[str]]:
    requested = events or (["pull_request"] if provider == "github" else ["merge_request"])
    canonical: list[str] = []
    for event in requested:
        event_value = str(event or "").strip()
        if not event_value:
            continue
        if event_value == "*":
            raise RepositoryAutomationWizardError(422, "Wildcard repository team events are not supported")
        if event_value.startswith("github.") or event_value.startswith("gitlab."):
            event_provider, provider_event = event_value.split(".", 1)
            if event_provider != provider:
                raise RepositoryAutomationWizardError(422, f"{event_value} is not valid for provider {provider}")
            canonical_value = canonical_event(provider, provider_event)
        else:
            canonical_value = canonical_event(provider, event_value)
        if canonical_value not in SUPPORTED_REPOSITORY_TEAM_EVENTS:
            raise RepositoryAutomationWizardError(422, f"Unsupported repository team event: {event_value}")
        if not canonical_value.startswith(f"{provider}."):
            raise RepositoryAutomationWizardError(422, f"{event_value} is not valid for provider {provider}")
        if canonical_value not in canonical:
            canonical.append(canonical_value)

    if not canonical:
        raise RepositoryAutomationWizardError(422, "At least one repository event is required")

    provider_events = [_provider_event(provider, item) for item in canonical]
    return provider_events, canonical


def _validated_trigger_criteria(provider: str, criteria: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if criteria is None:
        return None
    if not isinstance(criteria, dict):
        raise RepositoryAutomationWizardError(422, "trigger_criteria must be an object")
    event = str(criteria.get("event") or "").strip().lower()
    try:
        if provider == "github" and event == "pull_request":
            return validate_pr_criteria(criteria)
        if event:
            return validate_repository_criteria(criteria)
        return validate_criteria(criteria)
    except ValueError as exc:
        raise RepositoryAutomationWizardError(422, f"invalid_repository_criteria: {exc}") from exc


def _flow_node_config(node: FlowNode) -> dict[str, Any]:
    try:
        data = json.loads(node.config_json) if isinstance(node.config_json, str) else (node.config_json or {})
    except Exception:
        data = {}
    return data if isinstance(data, dict) else {}


class RepositoryAutomationWizardService:
    def __init__(self, db: Session, tenant_id: Optional[str], *, user_id: Optional[int] = None):
        if not tenant_id:
            raise RepositoryAutomationWizardError(400, "Tenant context is required")
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def create(self, payload: RepositoryAutomationRequest) -> dict[str, Any]:
        try:
            integration = self._load_integration(payload.provider, payload.integration_id)
            provider_events, canonical_events = _canonicalize_events(payload.provider, payload.events)
            trigger_criteria = _validated_trigger_criteria(payload.provider, payload.trigger_criteria)
            trigger, trigger_reused = self._create_or_reuse_trigger(payload, provider_events)
            self._apply_trigger_preferences(payload, trigger, provider_events, trigger_criteria)

            agents: list[Agent]
            team_ref: Optional[dict[str, Any]] = None
            if payload.template_id == "repository_review_team":
                agents, team_ref = self._create_or_reuse_review_team(payload, integration)
                default_agent_id = None
            else:
                agents = [self._create_or_reuse_reviewer_agent(payload, integration, role_suffix="Reviewer")]
                default_agent_id = agents[0].id

            if trigger.default_agent_id != default_agent_id:
                trigger.default_agent_id = default_agent_id
                trigger.updated_at = datetime.utcnow()
            self.db.flush()

            flow, flow_binding, flow_created = ensure_system_managed_flow_for_trigger(
                self.db,
                tenant_id=self.tenant_id,
                trigger_kind=payload.provider,
                trigger_instance_id=trigger.id,
                default_agent_id=default_agent_id,
            )
            sync_system_managed_flow_default_agent(
                self.db,
                tenant_id=self.tenant_id,
                trigger_kind=payload.provider,
                trigger_instance_id=trigger.id,
                default_agent_id=default_agent_id,
            )
            if payload.flow_name and flow.name != payload.flow_name:
                flow.name = payload.flow_name
                flow.updated_at = datetime.utcnow()

            if payload.template_id == "repository_review_team":
                flow_binding.is_active = False
                flow_binding.suppress_default_agent = True
            else:
                flow_binding.is_active = True
                flow_binding.suppress_default_agent = True
            flow_binding.updated_at = datetime.utcnow()
            self.db.flush()

            team_binding_ref: Optional[dict[str, Any]] = None
            if team_ref is not None:
                team_binding_ref = self._bind_team_to_trigger(
                    int(team_ref["id"]),
                    payload=payload,
                    trigger_id=trigger.id,
                    canonical_events=canonical_events,
                )

            self._sync_flow_conversation(flow.id, default_agent_id)
            self.db.commit()
            self.db.refresh(trigger)
            self.db.refresh(flow)
            self.db.refresh(flow_binding)

            links = {
                "trigger": f"/hub/triggers/{payload.provider}/{trigger.id}",
                "trigger_inbound": f"/api/triggers/{payload.provider}/{trigger.id}/inbound",
                "flow": f"/flows?edit={flow.id}",
            }
            if team_ref is not None:
                links["team"] = f"/studio/teams/{team_ref['id']}"
            if agents:
                links["agent"] = f"/agents/{agents[0].id}"

            bindings = [
                {
                    "id": flow_binding.id,
                    "kind": "flow",
                    "trigger_kind": payload.provider,
                    "trigger_instance_id": trigger.id,
                    "event_types": canonical_events,
                    "is_active": bool(flow_binding.is_active),
                    "flow_definition_id": flow.id,
                    "suppress_default_agent": bool(flow_binding.suppress_default_agent),
                }
            ]
            if team_binding_ref is not None:
                bindings.append(team_binding_ref)

            return {
                "integration": {
                    "id": integration.id,
                    "provider": payload.provider,
                    "name": _display_name(integration),
                    "reused": True,
                },
                "trigger": {
                    "id": trigger.id,
                    "provider": payload.provider,
                    "name": trigger.integration_name,
                    "events": list(trigger.events or []),
                    "canonical_events": canonical_events,
                    "reused": trigger_reused,
                    "is_active": bool(trigger.is_active),
                    "inbound_url": f"/api/triggers/{payload.provider}/{trigger.id}/inbound",
                },
                "flow": {
                    "id": flow.id,
                    "name": flow.name,
                    "default_agent_id": flow.default_agent_id,
                    "is_active": bool(flow.is_active),
                    "created": flow_created,
                },
                "team": team_ref,
                "agents": [
                    {
                        "id": agent.id,
                        "name": self._agent_name(agent),
                        "skills": self._agent_skill_types(agent.id),
                    }
                    for agent in agents
                ],
                "bindings": bindings,
                "links": links,
                "routing_mode": payload.routing_mode,
                "created_at": datetime.utcnow(),
            }
        except Exception:
            self.db.rollback()
            raise

    def _load_integration(self, provider: str, integration_id: int) -> HubIntegration:
        table = GitHubIntegration if provider == "github" else GitLabIntegration
        integration = (
            self.db.query(table)
            .filter(table.id == integration_id, table.tenant_id == self.tenant_id)
            .first()
        )
        if integration is None:
            raise RepositoryAutomationWizardError(404, f"{provider} integration not found")
        if not bool(integration.is_active):
            raise RepositoryAutomationWizardError(409, f"{provider} integration is inactive")
        if getattr(integration, "type", provider) != provider:
            raise RepositoryAutomationWizardError(400, f"Integration {integration_id} is not a {provider} integration")
        return integration

    def _create_or_reuse_trigger(
        self,
        payload: RepositoryAutomationRequest,
        provider_events: list[str],
    ) -> tuple[Any, bool]:
        if payload.existing_trigger_id is not None:
            trigger = self._load_trigger(payload.provider, payload.existing_trigger_id, require_active=True)
            self._validate_trigger_matches(payload, trigger)
            return trigger, True

        trigger = self._find_matching_trigger(payload)
        if trigger is not None:
            if not _active(trigger):
                raise RepositoryAutomationWizardError(409, f"{payload.provider} trigger is inactive")
            return trigger, True

        if payload.provider == "github":
            secret = generate_github_webhook_secret()
            trigger = GitHubChannelInstance(
                tenant_id=self.tenant_id,
                integration_name=_default_trigger_name(payload),
                github_integration_id=payload.integration_id,
                repo_owner=normalize_repo_part(payload.repo_owner or "", "repo_owner"),
                repo_name=normalize_repo_part(payload.repo_name or "", "repo_name"),
                webhook_secret_encrypted=encrypt_github_webhook_secret(self.db, self.tenant_id, secret),
                webhook_secret_preview=preview_github_secret(secret),
                events=normalize_github_events(provider_events),
                branch_filter=payload.branch_filter,
                path_filters=normalize_path_filters(payload.path_filters),
                author_filter=payload.author_filter,
                trigger_criteria=_validated_trigger_criteria(payload.provider, payload.trigger_criteria),
                is_active=True,
                status="active",
                health_status="unknown",
                created_by=self.user_id or 0,
            )
        else:
            secret = generate_gitlab_webhook_secret()
            trigger = GitLabChannelInstance(
                tenant_id=self.tenant_id,
                integration_name=_default_trigger_name(payload),
                gitlab_integration_id=payload.integration_id,
                project_path=normalize_project_path(payload.project_path or ""),
                webhook_secret_encrypted=encrypt_gitlab_webhook_secret(self.db, self.tenant_id, secret),
                webhook_secret_preview=preview_gitlab_secret(secret),
                events=normalize_gitlab_events(provider_events),
                branch_filter=payload.branch_filter,
                path_filters=normalize_path_filters(payload.path_filters),
                author_filter=payload.author_filter,
                trigger_criteria=_validated_trigger_criteria(payload.provider, payload.trigger_criteria),
                is_active=True,
                status="active",
                health_status="unknown",
                created_by=self.user_id or 0,
            )
        self.db.add(trigger)
        self.db.flush()
        return trigger, False

    def _apply_trigger_preferences(
        self,
        payload: RepositoryAutomationRequest,
        trigger: Any,
        provider_events: list[str],
        trigger_criteria: Optional[dict[str, Any]],
    ) -> None:
        if payload.provider == "github":
            normalized_events = normalize_github_events(provider_events)
        else:
            normalized_events = normalize_gitlab_events(provider_events)

        trigger.events = normalized_events
        trigger.branch_filter = payload.branch_filter
        trigger.path_filters = normalize_path_filters(payload.path_filters)
        trigger.author_filter = payload.author_filter
        trigger.trigger_criteria = trigger_criteria
        if payload.trigger_name:
            trigger.integration_name = payload.trigger_name
        trigger.updated_at = datetime.utcnow()
        self.db.flush()

    def _load_trigger(self, provider: str, trigger_id: int, *, require_active: bool) -> Any:
        table = GitHubChannelInstance if provider == "github" else GitLabChannelInstance
        trigger = (
            self.db.query(table)
            .filter(table.id == trigger_id, table.tenant_id == self.tenant_id)
            .first()
        )
        if trigger is None:
            raise RepositoryAutomationWizardError(404, f"{provider} trigger not found")
        if require_active and not _active(trigger):
            raise RepositoryAutomationWizardError(409, f"{provider} trigger is inactive")
        return trigger

    def _find_matching_trigger(self, payload: RepositoryAutomationRequest) -> Any:
        if payload.provider == "github":
            return (
                self.db.query(GitHubChannelInstance)
                .filter(
                    GitHubChannelInstance.tenant_id == self.tenant_id,
                    GitHubChannelInstance.github_integration_id == payload.integration_id,
                    GitHubChannelInstance.repo_owner == payload.repo_owner,
                    GitHubChannelInstance.repo_name == payload.repo_name,
                )
                .order_by(GitHubChannelInstance.id.asc())
                .first()
            )
        return (
            self.db.query(GitLabChannelInstance)
            .filter(
                GitLabChannelInstance.tenant_id == self.tenant_id,
                GitLabChannelInstance.gitlab_integration_id == payload.integration_id,
                GitLabChannelInstance.project_path == payload.project_path,
            )
            .order_by(GitLabChannelInstance.id.asc())
            .first()
        )

    def _validate_trigger_matches(self, payload: RepositoryAutomationRequest, trigger: Any) -> None:
        if payload.provider == "github":
            if trigger.github_integration_id != payload.integration_id:
                raise RepositoryAutomationWizardError(409, "GitHub trigger belongs to a different integration")
            if trigger.repo_owner != payload.repo_owner or trigger.repo_name != payload.repo_name:
                raise RepositoryAutomationWizardError(409, "GitHub trigger belongs to a different repository")
        else:
            if trigger.gitlab_integration_id != payload.integration_id:
                raise RepositoryAutomationWizardError(409, "GitLab trigger belongs to a different integration")
            if trigger.project_path != payload.project_path:
                raise RepositoryAutomationWizardError(409, "GitLab trigger belongs to a different project")

    def _create_or_reuse_review_team(
        self,
        payload: RepositoryAutomationRequest,
        integration: HubIntegration,
    ) -> tuple[list[Agent], dict[str, Any]]:
        base = payload.team_name or f"{_provider_label(payload.provider)} {_repository_label(payload)} Review Team"
        coordinator = self._create_or_reuse_reviewer_agent(payload, integration, role_suffix="Coordinator")
        reviewer = self._create_or_reuse_reviewer_agent(payload, integration, role_suffix="Reviewer")
        merge_readiness = self._create_or_reuse_reviewer_agent(payload, integration, role_suffix="Merge Readiness")
        team_agents = [coordinator, reviewer, merge_readiness]

        existing = (
            self.db.query(AgentTeam)
            .filter(
                AgentTeam.tenant_id == self.tenant_id,
                AgentTeam.name == base,
                AgentTeam.status != TeamStatus.ARCHIVED.value,
            )
            .first()
        )
        if existing is not None:
            team = existing
            team.description = team.description or f"Automated repository review team for {_repository_label(payload)}."
            team.goal_text = team.goal_text or self._review_team_goal_text()
            team.topology = TeamTopology.LINE.value
        else:
            team = AgentTeam(
                tenant_id=self.tenant_id,
                name=base,
                description=f"Automated repository review team for {_repository_label(payload)}.",
                goal_text=self._review_team_goal_text(),
                topology=TeamTopology.LINE.value,
                status=TeamStatus.ACTIVE.value,
                max_steps=12,
                max_concurrent_runs=1,
                created_by_user_id=self.user_id,
            )
            self.db.add(team)
            self.db.flush()

        if team is None:
            raise RepositoryAutomationWizardError(500, "Failed to create repository review team")
        if team.status != TeamStatus.ACTIVE.value:
            team.status = TeamStatus.ACTIVE.value
        self._ensure_team_members(team, team_agents)
        self.db.flush()
        member_count = (
            self.db.query(AgentTeamMember)
            .filter(
                AgentTeamMember.tenant_id == self.tenant_id,
                AgentTeamMember.team_id == team.id,
            )
            .count()
        )
        return team_agents, {
            "id": team.id,
            "name": team.name,
            "status": team.status,
            "member_count": member_count,
        }

    @staticmethod
    def _review_team_goal_text() -> str:
        return (
            "Review repository pull or merge request events in a visible line topology: "
            "Coordinator frames the goal and routes context, Reviewer inspects code and risks, "
            "and Merge Readiness produces the final merge-ready or hold recommendation."
        )

    def _ensure_team_members(self, team: AgentTeam, agents: list[Agent]) -> None:
        service = TeamMembershipService(self.db, self.tenant_id, auto_commit=False)
        for index, agent in enumerate(agents, start=1):
            membership = (
                self.db.query(AgentTeamMember)
                .filter(
                    AgentTeamMember.tenant_id == self.tenant_id,
                    AgentTeamMember.team_id == team.id,
                    AgentTeamMember.agent_id == agent.id,
                )
                .first()
            )
            try:
                if membership is None:
                    service.add_agent_to_team(team_id=team.id, agent_id=agent.id, commit=False)
                    membership = (
                        self.db.query(AgentTeamMember)
                        .filter(
                            AgentTeamMember.tenant_id == self.tenant_id,
                            AgentTeamMember.team_id == team.id,
                            AgentTeamMember.agent_id == agent.id,
                        )
                        .first()
                    )
            except TeamMembershipError as exc:
                raise RepositoryAutomationWizardError(409, str(exc)) from exc

            if membership is not None:
                membership.execution_order = index
                membership.is_required = True
                membership.updated_at = datetime.utcnow()

    def _create_or_reuse_reviewer_agent(
        self,
        payload: RepositoryAutomationRequest,
        integration: HubIntegration,
        *,
        role_suffix: str,
    ) -> Agent:
        if payload.template_id == "repository_pr_agent" and payload.agent_name:
            name = payload.agent_name
        else:
            name = f"{_provider_label(payload.provider)} {_repository_label(payload)} {role_suffix}"
        contact = (
            self.db.query(Contact)
            .filter(Contact.tenant_id == self.tenant_id, Contact.friendly_name == name, Contact.role == "agent")
            .first()
        )
        if contact is None:
            contact = Contact(friendly_name=name, role="agent", tenant_id=self.tenant_id, is_active=True)
            self.db.add(contact)
            self.db.flush()

        agent = (
            self.db.query(Agent)
            .filter(Agent.tenant_id == self.tenant_id, Agent.contact_id == contact.id)
            .first()
        )
        if agent is None:
            agent = Agent(
                contact_id=contact.id,
                tenant_id=self.tenant_id,
                user_id=self.user_id,
                system_prompt=(
                    "You are a repository automation reviewer. Inspect pull or merge request context, "
                    "use the Code Repository skill for repository facts, and provide concise review findings."
                ),
                description=f"Repository automation {role_suffix.lower()} for {_repository_label(payload)}.",
                model_provider="gemini",
                model_name="gemini-2.5-pro",
                is_active=True,
                enabled_channels=["playground", "webhook"],
            )
            self.db.add(agent)
            self.db.flush()
        elif not agent.is_active:
            raise RepositoryAutomationWizardError(409, f"Agent {name} is inactive")

        self._ensure_agent_skill(agent.id, "code_repository")
        self._ensure_agent_skill(agent.id, "agent_communication")
        self._ensure_code_repository_integration(agent.id, payload, integration)
        self.db.flush()
        return agent

    def _ensure_agent_skill(self, agent_id: int, skill_type: str) -> None:
        skill = (
            self.db.query(AgentSkill)
            .filter(AgentSkill.agent_id == agent_id, AgentSkill.skill_type == skill_type)
            .first()
        )
        default_config = (
            {
                "default_timeout": 60,
                "__tsn_auto_managed_permission_skill__": True,
            }
            if skill_type == "agent_communication"
            else {}
        )
        if skill is None:
            self.db.add(AgentSkill(agent_id=agent_id, skill_type=skill_type, is_enabled=True, config=default_config))
            return
        skill.is_enabled = True
        if skill_type == "agent_communication" and not skill.config:
            skill.config = default_config
        skill.updated_at = datetime.utcnow()

    def _ensure_code_repository_integration(
        self,
        agent_id: int,
        payload: RepositoryAutomationRequest,
        integration: HubIntegration,
    ) -> None:
        config = {
            "provider": payload.provider,
            "repository": _repository_label(payload),
            "permissions": {"read": True, "write": False},
        }
        existing = (
            self.db.query(AgentSkillIntegration)
            .filter(
                AgentSkillIntegration.agent_id == agent_id,
                AgentSkillIntegration.skill_type == "code_repository",
            )
            .first()
        )
        if existing is None:
            self.db.add(
                AgentSkillIntegration(
                    agent_id=agent_id,
                    skill_type="code_repository",
                    integration_id=integration.id,
                    config=config,
                )
            )
            return
        existing.integration_id = integration.id
        existing.config = config
        existing.updated_at = datetime.utcnow()

    def _bind_team_to_trigger(
        self,
        team_id: int,
        *,
        payload: RepositoryAutomationRequest,
        trigger_id: int,
        canonical_events: list[str],
    ) -> dict[str, Any]:
        self._load_trigger(payload.provider, trigger_id, require_active=True)
        config = {
            "trigger_instance_id": int(trigger_id),
            "event_types": list(canonical_events),
            "filters": {},
            "is_enabled": True,
        }
        existing = None
        rows = (
            self.db.query(AgentTeamTrigger)
            .filter(
                AgentTeamTrigger.tenant_id == self.tenant_id,
                AgentTeamTrigger.team_id == team_id,
                AgentTeamTrigger.trigger_kind == payload.provider,
            )
            .all()
        )
        for row in rows:
            row_config = row.config_json if isinstance(row.config_json, dict) else {}
            if int(row_config.get("trigger_instance_id") or 0) == int(trigger_id):
                existing = row
                break

        if existing is None:
            existing = AgentTeamTrigger(
                tenant_id=self.tenant_id,
                team_id=team_id,
                trigger_kind=payload.provider,
                config_json=config,
                is_enabled=True,
            )
            self.db.add(existing)
        else:
            existing.config_json = config
            existing.is_enabled = True
            existing.updated_at = datetime.utcnow()
        self.db.flush()

        return {
            "id": existing.id,
            "kind": "team",
            "trigger_kind": existing.trigger_kind,
            "trigger_instance_id": trigger_id,
            "event_types": canonical_events,
            "is_active": bool(existing.is_enabled),
            "team_id": team_id,
        }

    def _sync_flow_conversation(self, flow_id: int, default_agent_id: Optional[int]) -> None:
        nodes = (
            self.db.query(FlowNode)
            .filter(FlowNode.flow_definition_id == flow_id, FlowNode.type == "conversation")
            .all()
        )
        for node in nodes:
            node.agent_id = default_agent_id
            config = _flow_node_config(node)
            config["repository_automation"] = True
            config["route_to_agent_id"] = default_agent_id
            node.config_json = json.dumps(config)
            node.updated_at = datetime.utcnow()

    def _agent_name(self, agent: Agent) -> str:
        contact = self.db.get(Contact, agent.contact_id)
        return contact.friendly_name if contact is not None else f"Agent {agent.id}"

    def _agent_skill_types(self, agent_id: int) -> list[str]:
        rows = (
            self.db.query(AgentSkill.skill_type)
            .filter(AgentSkill.agent_id == agent_id, AgentSkill.is_enabled.is_(True))
            .order_by(AgentSkill.skill_type.asc())
            .all()
        )
        return [row[0] for row in rows]
