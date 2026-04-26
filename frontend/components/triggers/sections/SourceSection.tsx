'use client'

/**
 * SourceSection
 *
 * Per-kind input field grid for the Trigger Overview tab. Wave 2 of the
 * Triggers ↔ Flows unification — handles `jira`, `github`, and `schedule`.
 * Wave 3 adds `email` and `webhook` branches, retiring the standalone fork
 * pages.
 *
 * Lifted from `TriggerDetailShell.renderSourceSummary` (jira/schedule/github
 * branches), and from the Inbox Binding (email) / Inbound Endpoint (webhook)
 * cards of the pre-Wave-3 fork pages.
 */

import type { ReactNode } from 'react'
import Link from 'next/link'
import type { EmailTrigger, GitHubTrigger, JiraTrigger, PublicIngressInfo, ScheduleTrigger, WebhookIntegration } from '@/lib/client'
import { formatDateTime } from '@/lib/dateUtils'
import EmailSourceCard, { type EmailGmailIntegrationSummary } from './EmailSourceCard'
import WebhookSourceCard from './WebhookSourceCard'

type SourceKind = 'jira' | 'github' | 'schedule' | 'email' | 'webhook'
type SourceTrigger = JiraTrigger | GitHubTrigger | ScheduleTrigger | EmailTrigger | WebhookIntegration

interface Props {
  kind: SourceKind
  trigger: SourceTrigger
  // Email-specific props
  gmailIntegration?: EmailGmailIntegrationSummary | null
  // Webhook-specific props
  publicIngress?: PublicIngressInfo | null
  absoluteInboundUrl?: string
  copied?: boolean
  onCopyInboundUrl?: () => void
  rotatingSecret?: boolean
  onRotateWebhookSecret?: () => void
  canWriteHub?: boolean
}

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-4">
      <div className="text-xs uppercase tracking-wide text-tsushin-slate">{label}</div>
      <div className="mt-2 break-words text-sm text-white">{value}</div>
    </div>
  )
}

function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="text-xs text-tsushin-slate">{label}</div>
      <div className="mt-1 break-words text-sm text-white">{children}</div>
    </div>
  )
}

export default function SourceSection({
  kind,
  trigger,
  gmailIntegration,
  publicIngress,
  absoluteInboundUrl,
  copied = false,
  onCopyInboundUrl,
  rotatingSecret = false,
  onRotateWebhookSecret,
  canWriteHub = false,
}: Props) {
  if (kind === 'email') {
    return <EmailSourceCard trigger={trigger as EmailTrigger} gmailIntegration={gmailIntegration} />
  }

  if (kind === 'webhook') {
    return (
      <WebhookSourceCard
        trigger={trigger as WebhookIntegration}
        publicIngress={publicIngress}
        absoluteInboundUrl={absoluteInboundUrl || ''}
        copied={copied}
        onCopy={onCopyInboundUrl ?? (() => undefined)}
        rotating={rotatingSecret}
        onRotateSecret={onRotateWebhookSecret}
        canWriteHub={canWriteHub}
      />
    )
  }

  if (kind === 'jira') {
    const jira = trigger as JiraTrigger
    return (
      <div className="grid gap-4 lg:grid-cols-2">
        <Field
          label="Jira connection"
          value={jira.jira_integration_name
            ? <Link href="/hub?tab=tool-apis" className="text-cyan-200 hover:text-white">{jira.jira_integration_name}</Link>
            : <Link href="/hub?tab=tool-apis" className="text-yellow-200 hover:text-white">Legacy trigger credentials</Link>}
        />
        <Field label="Site" value={jira.site_url} />
        <Field label="Project" value={jira.project_key || 'Any project in JQL'} />
        <Field label="Poll interval" value={`${jira.poll_interval_seconds}s`} />
        <Field label="Auth email" value={jira.auth_email || 'Not reported'} />
      </div>
    )
  }

  if (kind === 'schedule') {
    const schedule = trigger as ScheduleTrigger
    return (
      <div className="grid gap-4 lg:grid-cols-2">
        <Field label="Cron" value={<code className="text-amber-200">{schedule.cron_expression}</code>} />
        <Field label="Timezone" value={schedule.timezone} />
        <Field label="Next fire" value={schedule.next_fire_at ? formatDateTime(schedule.next_fire_at) : 'Not scheduled'} />
        <Field label="Last fire" value={schedule.last_fire_at ? formatDateTime(schedule.last_fire_at) : 'No fires recorded'} />
      </div>
    )
  }

  // github
  const github = trigger as GitHubTrigger
  // v0.7.0: When the saved criteria envelope is a PR Submitted envelope,
  // render it as a read-only structured panel so operators can scan the
  // matching rules at a glance instead of decoding raw JSON.
  // Canonical envelope (per backend/channels/github/criteria.py) — fields
  // live nested under `filters`, the discriminator key is `event` (not
  // `event_type` which was the pre-release-finishing legacy shape).
  const rawCriteria = github.trigger_criteria as Record<string, unknown> | null | undefined
  const isPRCriteria = !!rawCriteria && rawCriteria.event === 'pull_request'
  const prFilters = isPRCriteria && rawCriteria!.filters && typeof rawCriteria!.filters === 'object'
    ? (rawCriteria!.filters as Record<string, unknown>)
    : {}
  const prActions = isPRCriteria && Array.isArray(rawCriteria!.actions) ? (rawCriteria!.actions as string[]) : []
  const prDraftOnly = isPRCriteria ? Boolean(prFilters.exclude_drafts) : false
  const prTitleContains = isPRCriteria ? (prFilters.title_contains as string | null | undefined) : null
  const prBodyContains = isPRCriteria ? (prFilters.body_contains as string | null | undefined) : null
  const prBranchFilter = isPRCriteria ? (prFilters.branch_filter as string | null | undefined) : null
  const prAuthorFilter = isPRCriteria ? (prFilters.author_filter as string | null | undefined) : null
  const prPathFilters = isPRCriteria && Array.isArray(prFilters.path_filters)
    ? (prFilters.path_filters as string[])
    : []

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <Field label="Repository" value={`${github.repo_owner}/${github.repo_name}`} />
        <Field label="Auth method" value={github.auth_method} />
        <Field label="Events" value={(github.events || []).length > 0 ? github.events!.join(', ') : 'Default'} />
        <Field label="Branch" value={github.branch_filter || 'Any branch'} />
      </div>
      {isPRCriteria && (
        <div className="rounded-xl border border-violet-500/30 bg-violet-500/5 p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-white">PR Submitted criteria</div>
              <p className="text-xs text-tsushin-slate">Structured envelope used by the dispatcher to decide which webhooks wake an agent.</p>
            </div>
            <span className="rounded-full border border-violet-500/30 bg-violet-500/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-violet-200">
              pull_request
            </span>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <DetailRow label="Actions">{prActions.length > 0 ? prActions.join(', ') : 'Any action'}</DetailRow>
            <DetailRow label="Only non-draft PRs">{prDraftOnly ? 'Yes' : 'No'}</DetailRow>
            <DetailRow label="Title contains">{prTitleContains || 'Any title'}</DetailRow>
            <DetailRow label="Body contains">{prBodyContains || 'Any body'}</DetailRow>
            <DetailRow label="Branch filter">{prBranchFilter || github.branch_filter || 'Any branch'}</DetailRow>
            <DetailRow label="Author filter">{prAuthorFilter || github.author_filter || 'Any author'}</DetailRow>
            <DetailRow label="Path filters">{prPathFilters.length > 0 ? prPathFilters.join(', ') : ((github.path_filters || []).length > 0 ? (github.path_filters || []).join(', ') : 'Any path')}</DetailRow>
          </div>
        </div>
      )}
    </div>
  )
}
