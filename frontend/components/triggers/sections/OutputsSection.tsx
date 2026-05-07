'use client'

/**
 * OutputsSection
 *
 * Vertical stack of per-kind output cards. Supports jira / github / email /
 * webhook (schedule retired in v0.7.0-fix Phase 2).
 * Every kind also renders the shared `WiredFlowsCard` listing live
 * Flow bindings and the Create-from-this-trigger deep link.
 *
 * Jira renders the Manual Poll card. Email renders Manual Poll plus Managed
 * Triage. github / webhook render the WiredFlowsCard (which carries
 * empty-state messaging when no flows are bound).
 */

import { useState } from 'react'
import type {
  EmailPollNowResponse,
  EmailTrigger,
  FlowTriggerBinding,
  GitHubTrigger,
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

type OutputsKind = 'jira' | 'github' | 'email' | 'webhook'

// AgentTeamTrigger.trigger_kind only validates jira/github/webhook today
// (see backend `_validate_team_trigger_instance`). Email is rejected by
// the team API, so the WiredTeamsCard hides on that kind.
const TEAM_KIND_BY_OUTPUT: Record<OutputsKind, WiredTeamsTriggerKind | null> = {
  jira: 'jira',
  github: 'github',
  webhook: 'webhook',
  email: null,
}

// Email triggers are subscribed via channel_type='gmail' on
// continuous_subscription — see trigger_dispatch_service. The frontend
// must apply the same translation when reading back.
function continuousChannelType(kind: OutputsKind): string {
  return kind === 'email' ? 'gmail' : kind
}
type OutputsTrigger = JiraTrigger | GitHubTrigger | EmailTrigger | WebhookIntegration

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
        {/* Agent Team triggers do not currently support email — the team
            API rejects `email`/`gmail` kinds. WiredTeamsCard is hidden here. */}
        <WiredContinuousCard
          channelType={continuousChannelType('email')}
          channelInstanceId={email.id}
        />
      </div>
    )
  }

  // github + webhook: no managed outputs — Wired Flows IS the
  // outputs surface. The card carries its own empty-state copy.
  const generic = trigger as { id: number }
  const teamKind = TEAM_KIND_BY_OUTPUT[kind]
  return (
    <div className="space-y-4">
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
