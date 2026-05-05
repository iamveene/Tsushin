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
import type { EmailGmailIntegrationSummary } from '@/components/triggers/sections/EmailSourceCard'

type OutputsKind = 'jira' | 'github' | 'email' | 'webhook'
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
      </div>
    )
  }

  // github + webhook: no managed outputs — Wired Flows IS the
  // outputs surface. The card carries its own empty-state copy.
  return (
    <div className="space-y-4">
      <WiredFlowsCard
        triggerKind={kind}
        triggerId={(trigger as { id: number }).id}
        onBindingsChange={setBindings}
      />
    </div>
  )
}
