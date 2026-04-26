'use client'

/**
 * OutputsSection
 *
 * Vertical stack of per-kind managed output cards. Wave 2 supports jira /
 * github / schedule. Wave 3 adds email (Notification + Triage + Manual
 * Poll) and webhook (no managed outputs — empty state).
 *
 * Jira renders the Managed WhatsApp Notification + Manual Poll cards.
 * Email renders the Managed WhatsApp Notification + Manual Poll cards
 * (matching Jira's grid layout — visual smell #5 fix) plus the Managed
 * Triage card. github / schedule / webhook render an empty state pointing
 * operators at the Flows editor.
 *
 * The "Wire a custom Flow" CTA is visually present but inert in Wave 2;
 * Wave 4 wires it to the Flow editor deep-link with `?source_trigger_kind`
 * + `?source_trigger_id`.
 *
 * Wave 3 of the Triggers ↔ Flows unification.
 */

import type {
  EmailPollNowResponse,
  EmailTrigger,
  GitHubTrigger,
  JiraManagedNotificationStatus,
  JiraPollNowResponse,
  JiraTrigger,
  ScheduleTrigger,
  WebhookIntegration,
} from '@/lib/client'
import JiraManagedNotificationCard from '@/components/triggers/sections/JiraManagedNotificationCard'
import JiraManualPollCard from '@/components/triggers/sections/JiraManualPollCard'
import EmailManagedNotificationCard from '@/components/triggers/sections/EmailManagedNotificationCard'
import EmailManagedTriageCard from '@/components/triggers/sections/EmailManagedTriageCard'
import EmailManualPollCard from '@/components/triggers/sections/EmailManualPollCard'
import type { EmailGmailIntegrationSummary } from '@/components/triggers/sections/EmailSourceCard'

type OutputsKind = 'jira' | 'github' | 'schedule' | 'email' | 'webhook'
type OutputsTrigger = JiraTrigger | GitHubTrigger | ScheduleTrigger | EmailTrigger | WebhookIntegration

interface Props {
  kind: OutputsKind
  trigger: OutputsTrigger
  canWriteHub: boolean
  // Jira-specific props
  jiraNotificationStatus?: JiraManagedNotificationStatus | null
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
  if (kind === 'jira') {
    const jira = trigger as JiraTrigger
    return (
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <JiraManagedNotificationCard
          trigger={jira}
          notificationStatus={jiraNotificationStatus}
          phoneInput={jiraPhoneInput}
          onPhoneChange={onJiraPhoneChange ?? (() => undefined)}
          onEnable={onEnableJiraNotification ?? (() => undefined)}
          enabling={jiraNotificationLoading}
          canWriteHub={canWriteHub}
        />
        <JiraManualPollCard
          trigger={jira}
          pollResult={jiraPollResult}
          onPollNow={onJiraPollNow ?? (() => undefined)}
          polling={jiraPolling}
          canWriteHub={canWriteHub}
        />
      </div>
    )
  }

  if (kind === 'email') {
    const email = trigger as EmailTrigger
    return (
      <div className="space-y-4">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <EmailManagedNotificationCard
            trigger={email}
            phoneInput={emailPhoneInput}
            onPhoneChange={onEmailPhoneChange ?? (() => undefined)}
            onEnable={onEnableEmailNotification ?? (() => undefined)}
            enabling={emailNotificationLoading}
            canWriteHub={canWriteHub}
          />
          <EmailManualPollCard
            trigger={email}
            pollResult={emailPollResult}
            onPollNow={onEmailPollNow ?? (() => undefined)}
            polling={emailPolling}
            canWriteHub={canWriteHub}
          />
        </div>
        <EmailManagedTriageCard
          trigger={email}
          gmailIntegration={emailGmailIntegration}
          onEnable={onEnableEmailTriage ?? (() => undefined)}
          enabling={emailTriageLoading}
          canWriteHub={canWriteHub}
        />
      </div>
    )
  }

  // github + schedule + webhook: no managed outputs in Wave 3
  return (
    <div className="rounded-xl border border-dashed border-tsushin-border bg-tsushin-surface/40 p-6">
      <p className="text-sm text-tsushin-slate">
        This channel has no managed outputs. Use Flows to define what happens when this trigger fires.
      </p>
      <button
        type="button"
        disabled
        title="Coming in Wave 4 — wire a Flow from this trigger"
        className="mt-4 inline-flex cursor-not-allowed items-center gap-2 rounded-lg border border-tsushin-border bg-tsushin-surface/60 px-3 py-1.5 text-xs text-tsushin-slate opacity-60"
      >
        + Wire a custom Flow
      </button>
    </div>
  )
}
