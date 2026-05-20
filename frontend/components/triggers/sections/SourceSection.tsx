'use client'

/**
 * SourceSection
 *
 * Per-kind input field grid for the Trigger Overview tab. Handles
 * `jira`, repository triggers, `email`, and `webhook` (schedule retired in v0.7.0-fix Phase 2).
 */

import type { ReactNode } from 'react'
import Link from 'next/link'
import type { EmailTrigger, GitHubTrigger, GitLabTrigger, JiraTrigger, PublicIngressInfo, WebhookIntegration } from '@/lib/client'
import { formatRelative } from '@/lib/dateUtils'
import EmailSourceCard, { type EmailGmailIntegrationSummary } from './EmailSourceCard'
import WebhookSourceCard from './WebhookSourceCard'

type SourceKind = 'jira' | 'github' | 'gitlab' | 'email' | 'webhook'
type SourceTrigger = JiraTrigger | GitHubTrigger | GitLabTrigger | EmailTrigger | WebhookIntegration

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
  onRotateRepositorySecret?: () => void
  repositorySecretOnce?: string | null
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
  onRotateRepositorySecret,
  repositorySecretOnce,
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
            : <Link href="/hub?tab=tool-apis" className="text-yellow-200 hover:text-white">{jira.jira_integration_id ? `Integration #${jira.jira_integration_id}` : 'Connection not linked'}</Link>}
        />
        <Field label="Site" value={jira.site_url} />
        <Field label="Project" value={jira.project_key || 'Any project in JQL'} />
        <Field label="Poll interval" value={`${jira.poll_interval_seconds}s`} />
      </div>
    )
  }

  // repository providers
  const repository = trigger as GitHubTrigger | GitLabTrigger
  const isGitLab = kind === 'gitlab'
  const projectPath = isGitLab
    ? (repository as GitLabTrigger).project_path
    : `${(repository as GitHubTrigger).repo_owner}/${(repository as GitHubTrigger).repo_name}`
  const integrationName = isGitLab
    ? (repository as GitLabTrigger).gitlab_integration_name
    : (repository as GitHubTrigger).github_integration_name
  const integrationId = isGitLab
    ? (repository as GitLabTrigger).gitlab_integration_id
    : (repository as GitHubTrigger).github_integration_id
  const providerLabel = isGitLab ? 'GitLab' : 'GitHub'
  const integrationLinkClass = isGitLab ? 'text-orange-200 hover:text-white' : 'text-violet-200 hover:text-white'
  const reviewLabel = isGitLab ? 'MR' : 'PR'
  const reviewEvent = isGitLab ? 'merge_request' : 'pull_request'
  const providerSetup = repository.provider_webhook_setup
  const providerInboundUrl = absoluteInboundUrl || providerSetup?.inbound_url || providerSetup?.relative_inbound_url || repository.inbound_url || ''
  const configuredEvents = (providerSetup?.events || repository.events || []).length > 0 ? (providerSetup?.events || repository.events || []) : [reviewEvent]
  const providerSecretPreview = providerSetup?.webhook_secret_preview || providerSetup?.secret_preview || repository.webhook_secret_preview || 'No secret preview stored'
  const lastDelivery = repository.last_delivery_id
    ? `${repository.last_delivery_id}${repository.last_activity_at ? ` (${formatRelative(repository.last_activity_at)})` : ''}`
    : repository.last_activity_at
      ? `Last activity ${formatRelative(repository.last_activity_at)}`
      : 'No deliveries recorded'
  const providerSecretLabel = isGitLab ? 'Secret token' : 'Webhook secret'
  const providerSetupHint = isGitLab
    ? 'Create or update the project webhook in GitLab, paste this URL, enable the listed events, and set the secret token.'
    : 'Create or update the repository webhook in GitHub, paste this URL, choose application/json, enable the listed events, and set the webhook secret.'
  // v0.7.0: When the saved criteria envelope is a PR Submitted envelope,
  // render it as a read-only structured panel so operators can scan the
  // matching rules at a glance instead of decoding raw JSON.
  // Canonical envelope (per backend/channels/{github,gitlab}/criteria.py) — fields
  // live nested under `filters`, the discriminator key is `event` (not
  // `event_type` which was the pre-release-finishing legacy shape).
  const rawCriteria = repository.trigger_criteria as Record<string, unknown> | null | undefined
  const isPRCriteria = !!rawCriteria && (
    rawCriteria.event === reviewEvent ||
    (isGitLab && rawCriteria.event === 'pull_request')
  )
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
      <div className="rounded-xl border border-cyan-500/30 bg-cyan-500/5 p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="text-sm font-semibold text-white">{providerLabel} provider webhook setup</div>
            <p className="mt-1 max-w-3xl text-xs text-tsushin-slate">{providerSetupHint}</p>
          </div>
          {canWriteHub && onRotateRepositorySecret && (
            <button
              type="button"
              onClick={onRotateRepositorySecret}
              disabled={rotatingSecret}
              className="inline-flex shrink-0 items-center justify-center rounded-lg border border-amber-400/40 bg-amber-500/10 px-3 py-2 text-xs font-medium text-amber-100 hover:text-white disabled:opacity-50"
            >
              {rotatingSecret ? 'Rotating...' : 'Rotate secret'}
            </button>
          )}
        </div>

        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <DetailRow label="Inbound URL">
            <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center">
              <code className="min-w-0 flex-1 break-all rounded bg-black/30 px-2 py-1 text-xs text-cyan-100">
                {providerInboundUrl || 'Inbound URL unavailable'}
              </code>
              {onCopyInboundUrl && providerInboundUrl && (
                <button
                  type="button"
                  onClick={onCopyInboundUrl}
                  className="rounded-lg border border-cyan-400/40 px-2.5 py-1 text-xs text-cyan-100 hover:text-white"
                >
                  {copied ? 'Copied' : 'Copy'}
                </button>
              )}
            </div>
          </DetailRow>
          <DetailRow label="Events to enable">{configuredEvents.join(', ')}</DetailRow>
          <DetailRow label={`${providerSecretLabel} preview`}>
            {providerSecretPreview}
          </DetailRow>
          <DetailRow label="Last delivery">
            {repository.last_delivery_id ? <span className="font-mono">{lastDelivery}</span> : lastDelivery}
          </DetailRow>
        </div>

        {repositorySecretOnce && (
          <div className="mt-4 rounded-lg border border-amber-400/40 bg-amber-500/10 p-3 text-sm text-amber-50">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="font-medium">New {providerSecretLabel.toLowerCase()} shown once</div>
              <button
                type="button"
                onClick={() => navigator.clipboard?.writeText(repositorySecretOnce)}
                className="rounded-lg border border-amber-300/40 bg-amber-400/10 px-2.5 py-1 text-xs text-amber-100 hover:text-white"
              >
                Copy secret
              </button>
            </div>
            <code className="mt-2 block break-all rounded bg-black/30 px-2 py-1 text-xs text-amber-100">{repositorySecretOnce}</code>
            <p className="mt-2 text-xs text-amber-100/80">Update the provider-side webhook now. Tsushin will only show the masked preview after this page refreshes.</p>
          </div>
        )}

        {isGitLab && (
          <p className="mt-4 rounded-lg border border-orange-400/30 bg-orange-500/10 px-3 py-2 text-xs text-orange-100">
            GitLab review output is advisory/read-only in this release; generated reviewers recommend approve or hold, but do not perform MR approval or request-changes actions.
          </p>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Field label={isGitLab ? 'Project' : 'Repository'} value={projectPath} />
        <Field
          label="Hub integration"
          value={integrationName
            ? <Link href="/hub?tab=developer" className={integrationLinkClass}>{integrationName}</Link>
            : <Link href="/hub?tab=developer" className={integrationLinkClass}>{`${providerLabel} integration #${integrationId}`}</Link>}
        />
        <Field label="Events" value={(repository.events || []).length > 0 ? repository.events!.join(', ') : 'Default'} />
        <Field label="Branch" value={repository.branch_filter || 'Any branch'} />
      </div>
      {isPRCriteria && (
        <div className="rounded-xl border border-violet-500/30 bg-violet-500/5 p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-white">{reviewLabel} Submitted criteria</div>
              <p className="text-xs text-tsushin-slate">Structured envelope used by the dispatcher to decide which webhooks wake an agent.</p>
            </div>
            <span className="rounded-full border border-violet-500/30 bg-violet-500/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-violet-200">
              {reviewEvent}
            </span>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <DetailRow label="Actions">{prActions.length > 0 ? prActions.join(', ') : 'Any action'}</DetailRow>
            <DetailRow label={`Only non-draft ${reviewLabel}s`}>{prDraftOnly ? 'Yes' : 'No'}</DetailRow>
            <DetailRow label="Title contains">{prTitleContains || 'Any title'}</DetailRow>
            <DetailRow label="Body contains">{prBodyContains || 'Any body'}</DetailRow>
            <DetailRow label="Branch filter">{prBranchFilter || repository.branch_filter || 'Any branch'}</DetailRow>
            <DetailRow label="Author filter">{prAuthorFilter || repository.author_filter || 'Any author'}</DetailRow>
            <DetailRow label="Path filters">{prPathFilters.length > 0 ? prPathFilters.join(', ') : ((repository.path_filters || []).length > 0 ? (repository.path_filters || []).join(', ') : 'Any path')}</DetailRow>
          </div>
        </div>
      )}
    </div>
  )
}
