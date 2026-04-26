'use client'

/**
 * OutputsSection
 *
 * Vertical stack of per-kind managed output cards (Wave 2 supports jira,
 * github, schedule). Jira renders the Managed WhatsApp Notification +
 * Manual Poll cards. github + schedule render an empty state pointing
 * operators at the Flows editor.
 *
 * The "Wire a custom Flow" CTA is visually present but inert in Wave 2;
 * Wave 4 wires it to the Flow editor deep-link with `?source_trigger_kind`
 * + `?source_trigger_id`.
 *
 * Wave 2 of the Triggers ↔ Flows unification.
 */

import type { GitHubTrigger, JiraManagedNotificationStatus, JiraPollNowResponse, JiraTrigger, ScheduleTrigger } from '@/lib/client'
import JiraManagedNotificationCard from '@/components/triggers/sections/JiraManagedNotificationCard'
import JiraManualPollCard from '@/components/triggers/sections/JiraManualPollCard'

type OutputsKind = 'jira' | 'github' | 'schedule'
type OutputsTrigger = JiraTrigger | GitHubTrigger | ScheduleTrigger

interface Props {
  kind: OutputsKind
  trigger: OutputsTrigger
  canWriteHub: boolean
  // Jira-specific props (only consumed when kind === 'jira')
  jiraNotificationStatus?: JiraManagedNotificationStatus | null
  jiraPhoneInput?: string
  onJiraPhoneChange?: (value: string) => void
  onEnableJiraNotification?: () => void
  jiraNotificationLoading?: boolean
  jiraPollResult?: JiraPollNowResponse | null
  onJiraPollNow?: () => void
  jiraPolling?: boolean
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

  // github + schedule: no managed outputs in Wave 2
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
