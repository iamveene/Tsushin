'use client'

/**
 * OutputsSection
 *
 * Vertical stack of per-kind managed output cards. Supports jira /
 * github / email / webhook (schedule retired in v0.7.0-fix Phase 2).
 * Every kind also renders the shared `WiredFlowsCard` listing live
 * Flow bindings and the Create-from-this-trigger deep link.
 *
 * Jira renders the Managed WhatsApp Notification + Manual Poll cards.
 * Email renders the Managed WhatsApp Notification + Manual Poll cards
 * (matching Jira's grid layout — visual smell #5 fix) plus the Managed
 * Triage card. github / webhook render the WiredFlowsCard
 * (which carries empty-state messaging when no flows are bound).
 *
 * Wave 4 also propagates a `suppressedByBinding` prop into the Managed
 * Notification cards so they can render a "disabled — flow X has taken
 * over" banner when an active binding suppresses the default agent.
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
  // Jira-specific props (managed notification props retired in
  // v0.7.0-fix Phase 4 — left as no-ops for callsite back-compat).
  jiraNotificationStatus?: unknown
  jiraPhoneInput?: string
  onJiraPhoneChange?: (value: string) => void
  onEnableJiraNotification?: () => void
  jiraNotificationLoading?: boolean
  jiraPollResult?: JiraPollNowResponse | null
  onJiraPollNow?: () => void
  jiraPolling?: boolean
  // Email-specific props
  emailGmailIntegration?: EmailGmailIntegrationSummary | null
  emailPhoneInput?: string
  onEmailPhoneChange?: (value: string) => void
  onEnableEmailNotification?: () => void
  emailNotificationLoading?: boolean
  emailPollResult?: EmailPollNowResponse | null
  onEmailPollNow?: () => void
  emailPolling?: boolean
  onEnableEmailTriage?: () => void
  emailTriageLoading?: boolean
}

export default function OutputsSection({
  kind,
  trigger,
  canWriteHub,
  jiraNotificationStatus = null,
  jiraPhoneInput = '',
  onJiraPhoneChange,
  onEnableJiraNotification,
  jiraNotificationLoading = false,
  jiraPollResult = null,
  onJiraPollNow,
  jiraPolling = false,
  emailGmailIntegration = null,
  emailPhoneInput = '',
  onEmailPhoneChange,
  onEnableEmailNotification,
  emailNotificationLoading = false,
  emailPollResult = null,
  onEmailPollNow,
  emailPolling = false,
  onEnableEmailTriage,
  emailTriageLoading = false,
}: Props) {
  // Wave 4: track active bindings so the Managed Notification cards know
  // whether a Flow has taken over routing for this trigger.
  // bindings state still tracked so WiredFlowsCard can refresh; suppressor
  // logic was retired with the managed notification cards in Phase 4.
  const [, setBindings] = useState<FlowTriggerBinding[]>([])

  if (kind === 'jira') {
    const jira = trigger as JiraTrigger
    return (
      <div className="space-y-4">
        {/* v0.7.0-fix Phase 4: legacy JiraManagedNotificationCard retired.
            Notification config now lives on the auto-flow's Notification node
            (see Wired Flows below). The Manual Poll card stays. */}
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
        {/* v0.7.0-fix Phase 4: legacy EmailManagedNotificationCard retired
            for symmetry with Jira; notification config now lives on the
            auto-flow Notification node (see Wired Flows below). */}
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
          enabling={emailTriageLoading}
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
