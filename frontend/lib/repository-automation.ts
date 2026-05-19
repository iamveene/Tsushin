import type {
  GitHubIntegration,
  GitHubTrigger,
  GitLabIntegration,
  GitLabTrigger,
  TriggerKind,
} from '@/lib/client'
import type { TeamWizardDraft } from '@/lib/team-wizard/reducer'
import type { WizardDraft } from '@/lib/agent-wizard/reducer'
import { canonicalTeamTriggerEvents } from '@/lib/team-trigger-defaults'

export type RepositoryAutomationProvider = 'github' | 'gitlab'
export type RepositoryAutomationTemplateId = 'repository_review_team' | 'repository_pr_agent'
export type RepositoryAutomationRoutingMode = 'team_primary' | 'agent_flow'

export type RepositoryAutomationIntegration = GitHubIntegration | GitLabIntegration
export type RepositoryAutomationTrigger = GitHubTrigger | GitLabTrigger

export interface RepositoryAutomationOpenOptions {
  provider?: RepositoryAutomationProvider
  templateId?: RepositoryAutomationTemplateId
  integrationId?: number | null
  triggerKind?: Extract<TriggerKind, 'github' | 'gitlab'> | null
  triggerId?: number | null
  triggerName?: string | null
  repositoryLabel?: string | null
  source?: 'hub' | 'trigger_success' | 'trigger_detail' | 'flow_setup' | 'team_wizard'
}

export interface RepositoryAutomationDraft {
  templateId: RepositoryAutomationTemplateId
  provider: RepositoryAutomationProvider
  integrationId: number | null
  repositoryOwner: string
  repositoryName: string
  projectPath: string
  triggerId: number | null
  triggerName: string
  routingMode: RepositoryAutomationRoutingMode
  eventType: string
  branchFilter: string
  pathFiltersText: string
  authorFilter: string
}

export const REPOSITORY_AUTOMATION_TEMPLATES: Array<{
  id: RepositoryAutomationTemplateId
  name: string
  subtitle: string
  routingMode: RepositoryAutomationRoutingMode
  summary: string
}> = [
  {
    id: 'repository_review_team',
    name: 'Repository review team',
    subtitle: 'Coordinator, Reviewer, Merge Readiness',
    routingMode: 'team_primary',
    summary: 'Creates a line-topology review team, an inactive linked Flow surface, and a trigger binding that runs the team once.',
  },
  {
    id: 'repository_pr_agent',
    name: 'Standalone PR/MR reviewer',
    subtitle: 'Single reviewer agent with A2A enabled',
    routingMode: 'agent_flow',
    summary: 'Creates a reviewer agent with Code Repository read access and Agent-to-Agent communication, then routes the generated Flow to that agent.',
  },
]

export function defaultRepositoryAutomationDraft(options: RepositoryAutomationOpenOptions = {}): RepositoryAutomationDraft {
  const provider = options.provider || options.triggerKind || 'github'
  const templateId = options.templateId || 'repository_review_team'
  const repository = parseRepositoryLabel(provider, options.repositoryLabel || '')
  return {
    templateId,
    provider,
    integrationId: options.integrationId ?? null,
    repositoryOwner: repository.owner,
    repositoryName: repository.repo,
    projectPath: repository.projectPath,
    triggerId: options.triggerId ?? null,
    triggerName: options.triggerName || '',
    routingMode: templateId === 'repository_pr_agent' ? 'agent_flow' : 'team_primary',
    eventType: provider === 'gitlab' ? 'merge_request' : 'pull_request',
    branchFilter: '',
    pathFiltersText: '',
    authorFilter: '',
  }
}

export function integrationLabel(provider: RepositoryAutomationProvider, integration: RepositoryAutomationIntegration): string {
  return integration.integration_name || integration.name || `${provider === 'gitlab' ? 'GitLab' : 'GitHub'} connection #${integration.id}`
}

export function isActiveRepositoryIntegration(integration: RepositoryAutomationIntegration): boolean {
  return integration.is_active !== false
}

export function repositoryLabelFromIntegration(provider: RepositoryAutomationProvider, integration: RepositoryAutomationIntegration): string {
  if (provider === 'gitlab') {
    const gitlab = integration as GitLabIntegration
    return gitlab.default_project_path || [gitlab.default_namespace, gitlab.default_project].filter(Boolean).join('/') || ''
  }
  const github = integration as GitHubIntegration
  return github.default_owner && github.default_repo
    ? `${github.default_owner}/${github.default_repo}`
    : github.default_owner || ''
}

export function repositoryLabelFromDraft(draft: RepositoryAutomationDraft): string {
  if (draft.provider === 'gitlab') return draft.projectPath.trim()
  return [draft.repositoryOwner.trim(), draft.repositoryName.trim()].filter(Boolean).join('/')
}

export function parseRepositoryLabel(provider: RepositoryAutomationProvider, value: string): { owner: string; repo: string; projectPath: string } {
  const trimmed = value.trim()
  if (provider === 'gitlab') {
    return { owner: '', repo: '', projectPath: trimmed }
  }
  const [owner = '', repo = ''] = trimmed.split('/', 2)
  return { owner, repo, projectPath: '' }
}

export function triggerRepositoryLabel(provider: RepositoryAutomationProvider, trigger: RepositoryAutomationTrigger): string {
  if (provider === 'gitlab') return (trigger as GitLabTrigger).project_path
  const github = trigger as GitHubTrigger
  return `${github.repo_owner}/${github.repo_name}`
}

export function triggerDisplayName(provider: RepositoryAutomationProvider, trigger: RepositoryAutomationTrigger): string {
  return trigger.integration_name || triggerRepositoryLabel(provider, trigger)
}

export function teamPresetFromRepositoryAutomation(draft: RepositoryAutomationDraft): Partial<TeamWizardDraft> {
  const repositoryLabel = repositoryLabelFromDraft(draft)
  const triggerKind = draft.provider
  return {
    template_id: 'repository_review_team',
    name: repositoryLabel ? `${repositoryLabel} Review Team` : 'Repository Review Team',
    description: 'Coordinates repository review, evidence checks, and merge readiness.',
    goal_text: [
      'Coordinate repository review with three roles: Coordinator, Reviewer, and Merge Readiness.',
      'Use read-only Code Repository access by default.',
      'Summarize blocking risks, evidence, and a merge-ready or hold recommendation.',
    ].join(' '),
    topology: 'line',
    status: 'active',
    max_steps: 12,
    max_concurrent_runs: 1,
    triggers: draft.triggerId
      ? [{
          uid: `${triggerKind}:${draft.triggerId}:repository-review`,
          trigger_kind: triggerKind,
          trigger_instance_id: draft.triggerId,
          event_types: canonicalTeamTriggerEvents(triggerKind, [
            draft.provider === 'gitlab' ? 'merge_request' : 'pull_request',
          ]),
          filters_text: '{}',
          is_enabled: true,
          label: draft.triggerName || `${draft.provider === 'gitlab' ? 'GitLab' : 'GitHub'} trigger #${draft.triggerId}`,
        }]
      : [],
  }
}

export function agentPresetFromRepositoryAutomation(draft: RepositoryAutomationDraft): Partial<WizardDraft> {
  const repositoryLabel = repositoryLabelFromDraft(draft)
  const providerLabel = draft.provider === 'gitlab' ? 'GitLab' : 'GitHub'
  return {
    type: 'text',
    basics: {
      agent_name: repositoryLabel ? `${repositoryLabel} PR Reviewer` : 'Repository PR Reviewer',
      agent_phone: '',
      model_provider: '',
      model_name: '',
      provider_instance_id: null,
    },
    personality: {
      persona_id: null,
      tone_preset_id: null,
      custom_tone: '',
      skip_persona: true,
      system_prompt: [
        `You are a repository review agent for ${providerLabel}.`,
        'Review pull requests or merge requests with read-only Code Repository tools.',
        'Check changed files, tests, risks, security concerns, and merge readiness.',
        'Use Agent-to-Agent handoff when another specialist can improve the review.',
        'Never modify the repository unless the operator explicitly grants write capability later.',
      ].join(' '),
    },
    skills: {
      builtIns: {
        code_repository: {
          is_enabled: true,
          config: {
            provider: draft.provider,
            integration_id: draft.integrationId,
            default_repository: draft.provider === 'github' ? repositoryLabel : undefined,
            default_project_path: draft.provider === 'gitlab' ? repositoryLabel : undefined,
            read_repository: true,
            list_pull_requests: true,
            list_merge_requests: true,
            comment_on_review: false,
            write_repository: false,
          },
        },
        agent_communication: {
          is_enabled: true,
          config: {
            allow_target_skills: true,
            default_timeout: 60,
          },
        },
      },
      customIds: [],
    },
    channels: ['playground'],
  }
}
