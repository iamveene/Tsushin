'use client'

/**
 * OutputsSection
 *
 * Vertical stack of per-kind output cards. Supports jira / github / gitlab /
 * email / webhook (schedule retired in v0.7.0-fix Phase 2).
 * Every kind also renders the shared `WiredFlowsCard` listing live
 * Flow bindings and the Create-from-this-trigger deep link.
 *
 * Jira renders the Manual Poll card. Email renders Manual Poll plus Managed
 * Triage. repository triggers / webhook render the WiredFlowsCard (which carries
 * empty-state messaging when no flows are bound).
 */

import { useState } from 'react'
import type {
  EmailPollNowResponse,
  EmailTrigger,
  FlowTriggerBinding,
  GitHubTrigger,
  GitLabTrigger,
  JiraPollNowResponse,
  JiraTrigger,
  WebhookIntegration,
} from '@/lib/client'
import JiraManualPollCard from '@/components/triggers/sections/JiraManualPollCard'
import EmailManagedTriageCard from '@/components/triggers/sections/EmailManagedTriageCard'
import EmailManualPollCard from '@/components/triggers/sections/EmailManualPollCard'
import WiredFlowsCard from '@/components/triggers/sections/WiredFlowsCard'
import WiredTeamsCard, {
  type WiredTeamsTriggerKind,
} from '@/components/triggers/sections/WiredTeamsCard'
import WiredContinuousCard from '@/components/triggers/sections/WiredContinuousCard'
import type { EmailGmailIntegrationSummary } from '@/components/triggers/sections/EmailSourceCard'
import { useRepositoryAutomationWizard } from '@/contexts/RepositoryAutomationWizardContext'
import { BotIcon, UsersIcon } from '@/components/ui/icons'

type OutputsKind = 'jira' | 'github' | 'gitlab' | 'email' | 'webhook'

// AgentTeamTrigger.trigger_kind validates jira/github/webhook/gmail. Email
// triggers persist as kind='gmail' (see _validate_team_trigger_instance and
// SUPPORTED_TEAM_TRIGGER_KINDS in agent_team_api_service). The frontend uses
// 'email' as the OutputsKind tag and translates to 'gmail' at the API edge.
const TEAM_KIND_BY_OUTPUT: Record<OutputsKind, WiredTeamsTriggerKind | null> = {
  jira: 'jira',
  github: 'github',
  gitlab: 'gitlab',
  webhook: 'webhook',
  email: 'gmail',
}

// Email triggers are subscribed via channel_type='gmail' on
// continuous_subscription — see trigger_dispatch_service. The frontend
// must apply the same translation when reading back.
function continuousChannelType(kind: OutputsKind): string {
  return kind === 'email' ? 'gmail' : kind
}
type OutputsTrigger = JiraTrigger | GitHubTrigger | GitLabTrigger | EmailTrigger | WebhookIntegration

interface Props {
  kind: OutputsKind
  trigger: OutputsTrigger
  canWriteHub: boolean
  // Jira-specific props
  jiraPollResult?: JiraPollNowResponse | null
  onJiraPollNow?: () => void
  jiraPolling?: boolean
  // Email-specific props
  emailGmailIntegration?: EmailGmailIntegrationSummary | null
  emailPollResult?: EmailPollNowResponse | null
  onEmailPollNow?: () => void
  emailPolling?: boolean
  onEnableEmailTriage?: () => void
  onChooseEmailTriageAgent?: () => void
  onReconnectEmailGmail?: () => void
  emailTriageLoading?: boolean
  emailGmailReauthLoading?: boolean
}

export default function OutputsSection({
  kind,
  trigger,
  canWriteHub,
  jiraPollResult = null,
  onJiraPollNow,
  jiraPolling = false,
  emailGmailIntegration = null,
  emailPollResult = null,
  onEmailPollNow,
  emailPolling = false,
  onEnableEmailTriage,
  onChooseEmailTriageAgent,
  onReconnectEmailGmail,
  emailTriageLoading = false,
  emailGmailReauthLoading = false,
}: Props) {
  const repositoryAutomationWizard = useRepositoryAutomationWizard()
  // Track bindings so WiredFlowsCard can refresh after local changes.
  const [, setBindings] = useState<FlowTriggerBinding[]>([])

  if (kind === 'jira') {
    const jira = trigger as JiraTrigger
    return (
      <div className="space-y-4">
        <JiraManualPollCard
          trigger={jira}
          pollResult={jiraPollResult}
          onPollNow={onJiraPollNow ?? (() => undefined)}
          polling={jiraPolling}
          canWriteHub={canWriteHub}
        />
        <WiredFlowsCard
          triggerKind="jira"
          triggerId={jira.id}
          onBindingsChange={setBindings}
        />
        <WiredTeamsCard triggerKind="jira" triggerId={jira.id} />
        <WiredContinuousCard
          channelType={continuousChannelType('jira')}
          channelInstanceId={jira.id}
        />
      </div>
    )
  }

  if (kind === 'email') {
    const email = trigger as EmailTrigger
    return (
      <div className="space-y-4">
        <EmailManualPollCard
          trigger={email}
          pollResult={emailPollResult}
          onPollNow={onEmailPollNow ?? (() => undefined)}
          polling={emailPolling}
          canWriteHub={canWriteHub}
        />
        <EmailManagedTriageCard
          trigger={email}
          gmailIntegration={emailGmailIntegration}
          onEnable={onEnableEmailTriage ?? (() => undefined)}
          onChooseDefaultAgent={onChooseEmailTriageAgent}
          onReconnectGmail={onReconnectEmailGmail}
          enabling={emailTriageLoading}
          reconnectingGmail={emailGmailReauthLoading}
          canWriteHub={canWriteHub}
        />
        <WiredFlowsCard
          triggerKind="email"
          triggerId={email.id}
          onBindingsChange={setBindings}
        />
        {/* AgentTeamTrigger.trigger_kind persists email triggers as 'gmail'
            (see _validate_team_trigger_instance + SUPPORTED_TEAM_TRIGGER_KINDS
            in agent_team_api_service). WiredTeamsCard re-translates back. */}
        <WiredTeamsCard triggerKind="gmail" triggerId={email.id} />
        <WiredContinuousCard
          channelType={continuousChannelType('email')}
          channelInstanceId={email.id}
        />
      </div>
    )
  }

  // repository triggers + webhook: no managed outputs — Wired Flows IS the
  // outputs surface. The card carries its own empty-state copy.
  const generic = trigger as { id: number }
  const teamKind = TEAM_KIND_BY_OUTPUT[kind]
  const repositoryLabel = kind === 'gitlab'
    ? (trigger as GitLabTrigger).project_path
    : kind === 'github'
      ? `${(trigger as GitHubTrigger).repo_owner}/${(trigger as GitHubTrigger).repo_name}`
      : ''
  return (
    <div className="space-y-4">
      {(kind === 'github' || kind === 'gitlab') && (
        <div className="rounded-xl border border-cyan-400/30 bg-cyan-500/10 p-5">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <h3 className="text-base font-semibold text-white">Repository automation</h3>
              <p className="mt-1 text-sm text-cyan-100/80">
                Create a review team or standalone reviewer agent from this {kind === 'gitlab' ? 'GitLab MR' : 'GitHub PR'} trigger.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => repositoryAutomationWizard.openWizard({
                  provider: kind,
                  templateId: 'repository_review_team',
                  triggerKind: kind,
                  triggerId: generic.id,
                  triggerName: (trigger as GitHubTrigger | GitLabTrigger).integration_name,
                  repositoryLabel,
                  source: 'trigger_detail',
                })}
                className="inline-flex items-center gap-2 rounded-lg border border-cyan-300/40 bg-cyan-500/10 px-3 py-2 text-sm text-cyan-50 hover:text-white"
              >
                <UsersIcon size={16} /> Create Review Team
              </button>
              <button
                type="button"
                onClick={() => repositoryAutomationWizard.openWizard({
                  provider: kind,
                  templateId: 'repository_pr_agent',
                  triggerKind: kind,
                  triggerId: generic.id,
                  triggerName: (trigger as GitHubTrigger | GitLabTrigger).integration_name,
                  repositoryLabel,
                  source: 'trigger_detail',
                })}
                className="inline-flex items-center gap-2 rounded-lg border border-tsushin-border bg-tsushin-surface/70 px-3 py-2 text-sm text-tsushin-fog hover:text-white"
              >
                <BotIcon size={16} /> Create Reviewer Agent
              </button>
            </div>
          </div>
        </div>
      )}
      <WiredFlowsCard
        triggerKind={kind}
        triggerId={generic.id}
        onBindingsChange={setBindings}
      />
      {teamKind && (
        <WiredTeamsCard triggerKind={teamKind} triggerId={generic.id} />
      )}
      <WiredContinuousCard
        channelType={continuousChannelType(kind)}
        channelInstanceId={generic.id}
      />
    </div>
  )
}
