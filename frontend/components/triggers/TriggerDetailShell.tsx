'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ComponentType, ReactNode } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { api, type GitHubTrigger, type JiraIssuePreview, type JiraManagedNotificationStatus, type JiraNotificationSubscriptionResponse, type JiraPollNowResponse, type JiraTrigger, type PageResponse, type ScheduleTrigger, type TriggerKind, type WakeEvent } from '@/lib/client'
import { formatDateTime, formatRelative } from '@/lib/dateUtils'
import { AlertTriangleIcon, BellIcon, CalendarDaysIcon, CodeIcon, GitHubIcon, PlayIcon, RefreshIcon, SparklesIcon, TrashIcon, WhatsAppIcon, type IconProps } from '@/components/ui/icons'
import CriteriaBuilder, { formatCriteriaText, parseCriteriaText, type CriteriaSourceValues } from '@/components/triggers/CriteriaBuilder'
import JiraIssuePreviewList from '@/components/triggers/JiraIssuePreviewList'

type BreadthTriggerKind = Extract<TriggerKind, 'jira' | 'schedule' | 'github'>
type BreadthTrigger = JiraTrigger | ScheduleTrigger | GitHubTrigger
type TabId = 'overview' | 'criteria' | 'events' | 'danger'

interface Props {
  kind: BreadthTriggerKind
}

const KIND_CONFIG: Record<BreadthTriggerKind, {
  label: string
  description: string
  Icon: ComponentType<IconProps>
  iconClass: string
  accentClass: string
}> = {
  jira: {
    label: 'Jira Trigger',
    description: 'JQL-polled wake source for matching issues.',
    Icon: CodeIcon,
    iconClass: 'text-blue-300',
    accentClass: 'border-blue-500/30 bg-blue-500/10 text-blue-100',
  },
  schedule: {
    label: 'Schedule Trigger',
    description: 'Cron-based wake source with structured payloads.',
    Icon: CalendarDaysIcon,
    iconClass: 'text-amber-300',
    accentClass: 'border-amber-500/30 bg-amber-500/10 text-amber-100',
  },
  github: {
    label: 'GitHub Trigger',
    description: 'Repository event source for engineering activity.',
    Icon: GitHubIcon,
    iconClass: 'text-violet-300',
    accentClass: 'border-violet-500/30 bg-violet-500/10 text-violet-100',
  },
}

const TABS: Array<{ id: TabId; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'criteria', label: 'Criteria' },
  { id: 'events', label: 'Recent wake events' },
  { id: 'danger', label: 'Danger zone' },
]

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function statusClass(trigger: BreadthTrigger): string {
  if (!trigger.is_active || trigger.status === 'paused') return 'bg-gray-500/10 text-gray-300 border-gray-500/30'
  if (trigger.status === 'error' || trigger.health_status === 'unhealthy') return 'bg-red-500/10 text-red-300 border-red-500/30'
  if (trigger.health_status === 'healthy') return 'bg-green-500/10 text-green-300 border-green-500/30'
  return 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30'
}

function statusLabel(trigger: BreadthTrigger): string {
  if (!trigger.is_active || trigger.status === 'paused') return 'paused'
  return trigger.status || 'unknown'
}

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-4">
      <div className="text-xs uppercase tracking-wide text-tsushin-slate">{label}</div>
      <div className="mt-2 break-words text-sm text-white">{value}</div>
    </div>
  )
}

function JsonBlock({ value, emptyLabel }: { value: unknown; emptyLabel: string }) {
  if (!value) {
    return (
      <div className="rounded-xl border border-dashed border-tsushin-border p-6 text-sm text-tsushin-slate">
        {emptyLabel}
      </div>
    )
  }
  return (
    <pre className="max-h-96 overflow-auto rounded-xl border border-tsushin-border bg-black/30 p-4 text-xs text-cyan-100">
      {JSON.stringify(value, null, 2)}
    </pre>
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

function formatJsonText(value: Record<string, unknown> | null | undefined): string {
  return value ? JSON.stringify(value, null, 2) : ''
}

function parseJsonObjectText(text: string, label: string): Record<string, unknown> | null {
  const trimmed = text.trim()
  if (!trimmed) return null
  const parsed = JSON.parse(trimmed)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON object`)
  }
  return parsed as Record<string, unknown>
}

function splitList(text?: string | null): string[] | null {
  const values = (text || '')
    .split(/[\n,]/)
    .map((value) => value.trim())
    .filter(Boolean)
  return values.length > 0 ? values : null
}

function jiraManagedNotificationFromTrigger(trigger: JiraTrigger): JiraManagedNotificationStatus | null {
  if (trigger.managed_notification_status) return trigger.managed_notification_status
  if (!trigger.managed_notification_enabled && !trigger.notification_subscription_status && !trigger.managed_notification_recipient_preview && !trigger.notification_recipient_preview) {
    return null
  }
  return {
    status: trigger.notification_subscription_status || (trigger.managed_notification_enabled ? 'active' : 'inactive'),
    recipient_preview: trigger.managed_notification_recipient_preview || trigger.notification_recipient_preview,
    agent_id: trigger.managed_notification_agent_id || trigger.default_agent_id,
    agent_name: trigger.managed_notification_agent_name,
    continuous_agent_id: trigger.managed_notification_continuous_agent_id,
    continuous_subscription_id: trigger.managed_notification_subscription_id,
  }
}

function notificationStatusLabel(status?: JiraManagedNotificationStatus | null): string {
  return status?.status || 'Not enabled'
}

function notificationRecipientPreview(status?: JiraManagedNotificationStatus | null): string {
  return status?.recipient_preview || 'Not configured'
}

function pollResultSummary(result: JiraPollNowResponse): string {
  if (result.success === false) return result.error || result.message || result.reason || 'Poll failed'
  const emitted = result.emitted_count ?? result.wake_event_count ?? result.dispatched_count ?? result.matched_count
  const processed = result.processed_count ?? result.issue_count ?? result.fetched_count
  if (processed !== undefined && emitted !== undefined) {
    return `Processed ${processed} issue(s), emitted ${emitted} wake event(s).`
  }
  if (processed !== undefined) return `Processed ${processed} issue(s).`
  return result.message || result.reason || 'Poll completed.'
}

function sourceFromTrigger(kind: BreadthTriggerKind, trigger: BreadthTrigger): CriteriaSourceValues {
  if (kind === 'jira') {
    const jira = trigger as JiraTrigger
    return {
      jiraJql: jira.jql,
      jiraProjectKey: jira.project_key || '',
    }
  }
  if (kind === 'schedule') {
    const schedule = trigger as ScheduleTrigger
    return {
      cronExpression: schedule.cron_expression,
      timezone: schedule.timezone,
      payloadTemplateText: formatJsonText(schedule.payload_template),
    }
  }
  const github = trigger as GitHubTrigger
  return {
    githubEventsText: (github.events || []).join(', '),
    githubBranchFilter: github.branch_filter || '',
    githubPathFiltersText: (github.path_filters || []).join('\n'),
    githubAuthorFilter: github.author_filter || '',
  }
}

export default function TriggerDetailShell({ kind }: Props) {
  const params = useParams()
  const router = useRouter()
  const triggerId = Number(params.id)
  const hasValidId = Number.isFinite(triggerId) && triggerId > 0
  const { hasPermission } = useAuth()
  const canWriteHub = hasPermission('hub.write')
  const config = KIND_CONFIG[kind]
  const Icon = config.Icon

  const [trigger, setTrigger] = useState<BreadthTrigger | null>(null)
  const [eventsPage, setEventsPage] = useState<PageResponse<WakeEvent> | null>(null)
  const [activeTab, setActiveTab] = useState<TabId>('overview')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [criteriaText, setCriteriaText] = useState('')
  const [sourceDraft, setSourceDraft] = useState<CriteriaSourceValues>({})
  const [jiraTesting, setJiraTesting] = useState(false)
  const [jiraTestMessage, setJiraTestMessage] = useState<string | null>(null)
  const [jiraSampleIssues, setJiraSampleIssues] = useState<JiraIssuePreview[]>([])
  const [jiraPolling, setJiraPolling] = useState(false)
  const [jiraPollResult, setJiraPollResult] = useState<JiraPollNowResponse | null>(null)
  const [jiraNotificationLoading, setJiraNotificationLoading] = useState(false)
  const [jiraNotificationStatus, setJiraNotificationStatus] = useState<JiraManagedNotificationStatus | null>(null)
  const [jiraNotificationRecipient, setJiraNotificationRecipient] = useState('')

  const loadData = useCallback(async () => {
    if (!hasValidId) return
    setLoading(true)
    setError(null)
    try {
      const [triggerData, wakeEvents] = await Promise.all([
        api.getTriggerDetail(kind, triggerId),
        api.getWakeEvents({ limit: 50, channel_type: kind, channel_instance_id: triggerId }).catch(() => null),
      ])
      const nextTrigger = triggerData as BreadthTrigger
      setTrigger(nextTrigger)
      setJiraNotificationStatus(kind === 'jira' ? jiraManagedNotificationFromTrigger(nextTrigger as JiraTrigger) : null)
      setCriteriaText(formatCriteriaText(nextTrigger.trigger_criteria))
      setSourceDraft(sourceFromTrigger(kind, nextTrigger))
      setEventsPage(wakeEvents)
    } catch (err: unknown) {
      setError(getErrorMessage(err, `Failed to load ${kind} trigger`))
    } finally {
      setLoading(false)
    }
  }, [hasValidId, kind, triggerId])

  useEffect(() => {
    if (!hasValidId) {
      router.replace('/hub?tab=communication')
      return
    }
    loadData()
  }, [hasValidId, loadData, router])

  const events = useMemo(
    () => (eventsPage?.items || []).filter((event) => event.channel_instance_id === triggerId),
    [eventsPage, triggerId],
  )

  const updateActive = async () => {
    if (!trigger) return
    setSaving(true)
    setError(null)
    try {
      const next = !trigger.is_active
      const updated = kind === 'jira'
        ? await api.updateJiraTrigger(trigger.id, { is_active: next })
        : kind === 'schedule'
        ? await api.updateScheduleTrigger(trigger.id, { is_active: next })
        : await api.updateGitHubTrigger(trigger.id, { is_active: next })
      setTrigger(updated)
      setSuccess(next ? 'Trigger resumed' : 'Trigger paused')
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to update trigger'))
    } finally {
      setSaving(false)
    }
  }

  const enableJiraNotification = async (target: JiraTrigger): Promise<JiraNotificationSubscriptionResponse | null> => {
    const recipient = jiraNotificationRecipient.trim()
    if (!recipient) {
      setError('WhatsApp recipient is required to enable Jira notifications')
      return null
    }
    const result = await api.createJiraNotificationSubscription(target.id, {
      recipient_phone: recipient,
    })
    setJiraNotificationStatus({
      ...result,
      status: 'active',
    })
    setJiraNotificationRecipient('')
    return result
  }

  const handleEnableJiraNotification = async () => {
    if (!trigger || kind !== 'jira') return
    setJiraNotificationLoading(true)
    setError(null)
    try {
      const result = await enableJiraNotification(trigger as JiraTrigger)
      if (!result) return
      setSuccess(result?.created_subscription ? 'Jira WhatsApp notification enabled' : 'Jira WhatsApp notification is active')
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to enable Jira WhatsApp notification'))
    } finally {
      setJiraNotificationLoading(false)
    }
  }

  const handleJiraPollNow = async () => {
    if (!trigger || kind !== 'jira') return
    setJiraPolling(true)
    setError(null)
    try {
      const result = await api.pollJiraTriggerNow(trigger.id)
      setJiraPollResult(result)
      if (result.success === false) {
        setError(result.error || result.message || 'Jira poll failed')
      } else {
        setSuccess(pollResultSummary(result))
        setTimeout(() => setSuccess(null), 3000)
      }
      await loadData()
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to poll Jira trigger'))
    } finally {
      setJiraPolling(false)
    }
  }

  const handleJiraTestQuery = async () => {
    if (!trigger || kind !== 'jira') return
    setJiraTesting(true)
    setJiraTestMessage(null)
    setJiraSampleIssues([])
    setError(null)
    try {
      const jira = trigger as JiraTrigger
      const result = await api.testSavedJiraTriggerQuery(jira.id, {
        jql: sourceDraft.jiraJql?.trim() || jira.jql,
        max_results: 5,
      })
      setJiraSampleIssues(result.sample_issues || result.issues || [])
      setJiraTestMessage(result.success
        ? `Query returned ${result.issue_count ?? result.total ?? 0} issue(s).`
        : result.error || result.message || 'Jira query test failed')
    } catch (err: unknown) {
      setJiraTestMessage(getErrorMessage(err, 'Failed to test Jira query'))
    } finally {
      setJiraTesting(false)
    }
  }

  const saveCriteria = async () => {
    if (!trigger) return
    setSaving(true)
    setError(null)
    try {
      const triggerCriteria = parseCriteriaText(criteriaText)
      const updated = kind === 'jira'
        ? await api.updateJiraTrigger(trigger.id, {
          trigger_criteria: triggerCriteria,
          project_key: sourceDraft.jiraProjectKey?.trim() || null,
          jql: sourceDraft.jiraJql?.trim() || (trigger as JiraTrigger).jql,
        })
        : kind === 'schedule'
        ? await api.updateScheduleTrigger(trigger.id, {
          trigger_criteria: triggerCriteria,
          cron_expression: sourceDraft.cronExpression?.trim() || (trigger as ScheduleTrigger).cron_expression,
          timezone: sourceDraft.timezone?.trim() || (trigger as ScheduleTrigger).timezone,
          payload_template: parseJsonObjectText(sourceDraft.payloadTemplateText || '', 'Payload template'),
        })
        : await api.updateGitHubTrigger(trigger.id, {
          trigger_criteria: triggerCriteria,
          events: splitList(sourceDraft.githubEventsText),
          branch_filter: sourceDraft.githubBranchFilter?.trim() || null,
          path_filters: splitList(sourceDraft.githubPathFiltersText),
          author_filter: sourceDraft.githubAuthorFilter?.trim() || null,
        })
      setTrigger(updated)
      setCriteriaText(formatCriteriaText(updated.trigger_criteria))
      setSourceDraft(sourceFromTrigger(kind, updated as BreadthTrigger))
      setSuccess('Criteria saved')
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to save criteria'))
    } finally {
      setSaving(false)
    }
  }

  const deleteTrigger = async () => {
    if (!trigger) return
    if (!confirm(`Delete ${kind} trigger "${trigger.integration_name}"? This cannot be undone.`)) return
    setSaving(true)
    setError(null)
    try {
      if (kind === 'jira') {
        await api.deleteJiraTrigger(trigger.id)
      } else if (kind === 'schedule') {
        await api.deleteScheduleTrigger(trigger.id)
      } else {
        await api.deleteGitHubTrigger(trigger.id)
      }
      router.push('/hub?tab=communication')
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to delete trigger'))
      setSaving(false)
    }
  }

  const renderSourceSummary = () => {
    if (!trigger) return null
    if (kind === 'jira') {
      const jira = trigger as JiraTrigger
      const status = jiraNotificationStatus || jiraManagedNotificationFromTrigger(jira)
      return (
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <Field label="Site" value={jira.site_url} />
            <Field label="Project" value={jira.project_key || 'Any project in JQL'} />
            <Field label="Poll interval" value={`${jira.poll_interval_seconds}s`} />
            <Field label="Auth email" value={jira.auth_email || 'Not reported'} />
          </div>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
              <h2 className="flex items-center gap-2 text-lg font-semibold text-white">
                <WhatsAppIcon size={18} /> Managed WhatsApp Notification
              </h2>
              <div className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                <DetailRow label="Status">{notificationStatusLabel(status)}</DetailRow>
                <DetailRow label="Recipient">{notificationRecipientPreview(status)}</DetailRow>
                <DetailRow label="Agent">{status?.agent_name || jira.default_agent_name || (jira.default_agent_id ? `Agent #${jira.default_agent_id}` : 'No default agent')}</DetailRow>
                <DetailRow label="Subscription">{status?.continuous_subscription_id ? `#${status.continuous_subscription_id}` : 'Not reported'}</DetailRow>
              </div>
              {!jira.default_agent_id && (
                <p className="mt-4 text-sm text-yellow-200">No default agent is selected; enabling creates or reuses the managed Jira agent.</p>
              )}
              {canWriteHub && (
                <div className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
                  <input
                    type="tel"
                    value={jiraNotificationRecipient}
                    onChange={(event) => setJiraNotificationRecipient(event.target.value)}
                    placeholder="+15551234567"
                    className="w-full rounded-lg border border-tsushin-border bg-black/25 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/30"
                  />
                  <button
                    type="button"
                    onClick={handleEnableJiraNotification}
                    disabled={jiraNotificationLoading || !jiraNotificationRecipient.trim()}
                    className="inline-flex items-center justify-center gap-2 rounded-lg border border-cyan-400/40 bg-cyan-500/10 px-4 py-2 text-sm text-cyan-100 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <SparklesIcon size={16} />
                    {jiraNotificationLoading ? 'Enabling...' : status?.status ? 'Update Notification' : 'Enable Notification'}
                  </button>
                </div>
              )}
            </div>
            <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
              <h2 className="flex items-center gap-2 text-lg font-semibold text-white">
                <RefreshIcon size={18} /> Manual Poll
              </h2>
              <p className="mt-2 text-sm text-tsushin-slate">
                Run the saved JQL now and dispatch matching wake events through the managed route.
              </p>
              {canWriteHub && (
                <button
                  type="button"
                  onClick={handleJiraPollNow}
                  disabled={jiraPolling || !jira.is_active}
                  className="mt-4 inline-flex items-center gap-2 rounded-lg border border-blue-400/40 bg-blue-500/10 px-4 py-2 text-sm text-blue-100 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <PlayIcon size={16} />
                  {jiraPolling ? 'Polling...' : 'Poll Now'}
                </button>
              )}
              {jiraPollResult && (
                <div className={`mt-4 rounded-xl border px-4 py-3 text-sm ${
                  jiraPollResult.success !== false
                    ? 'border-green-500/30 bg-green-500/10 text-green-200'
                    : 'border-red-500/30 bg-red-500/10 text-red-200'
                }`}>
                  {pollResultSummary(jiraPollResult)}
                  {(jiraPollResult.completed_at || jiraPollResult.status) && (
                    <div className="mt-1 text-xs opacity-80">
                      {jiraPollResult.status ? `Status: ${jiraPollResult.status}` : ''}
                      {jiraPollResult.completed_at ? ` Completed: ${formatDateTime(jiraPollResult.completed_at)}` : ''}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
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
    const github = trigger as GitHubTrigger
    return (
      <div className="grid gap-4 lg:grid-cols-2">
        <Field label="Repository" value={`${github.repo_owner}/${github.repo_name}`} />
        <Field label="Auth method" value={github.auth_method} />
        <Field label="Events" value={(github.events || []).length > 0 ? github.events!.join(', ') : 'Default'} />
        <Field label="Branch" value={github.branch_filter || 'Any branch'} />
      </div>
    )
  }

  const renderCriteriaTab = () => {
    if (!trigger) return null
    return (
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div>
          <CriteriaBuilder
            kind={kind}
            value={criteriaText}
            onChange={setCriteriaText}
            disabled={!canWriteHub || saving}
            source={sourceDraft}
            onSourceChange={(patch) => setSourceDraft((current) => ({ ...current, ...patch }))}
            readOnlyReason={!canWriteHub ? 'Read-only view. Your role can view criteria but cannot change it.' : null}
          />
          {canWriteHub && (
            <button
              type="button"
              onClick={saveCriteria}
              disabled={saving}
              className="mt-3 rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-4 py-2 text-sm text-cyan-200 hover:text-white disabled:opacity-50"
            >
              {saving ? 'Saving...' : 'Save Criteria'}
            </button>
          )}
        </div>
        <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
          <h2 className="text-lg font-semibold text-white">Source filters</h2>
          <div className="mt-4 space-y-4">
            {kind === 'jira' && (
              <>
                <DetailRow label="JQL">{(trigger as JiraTrigger).jql}</DetailRow>
                <DetailRow label="Project key">{(trigger as JiraTrigger).project_key || 'JQL controls scope'}</DetailRow>
                <button
                  type="button"
                  onClick={handleJiraTestQuery}
                  disabled={jiraTesting}
                  className="inline-flex items-center gap-2 rounded-lg border border-blue-500/40 bg-blue-500/10 px-3 py-2 text-sm text-blue-100 hover:text-white disabled:opacity-50"
                >
                  <PlayIcon size={14} />
                  {jiraTesting ? 'Testing...' : 'Test Query'}
                </button>
                {jiraTestMessage && (
                  <div className="rounded-xl border border-blue-500/30 bg-blue-500/10 px-4 py-3 text-sm text-blue-100">
                    {jiraTestMessage}
                  </div>
                )}
                <JiraIssuePreviewList
                  issues={jiraSampleIssues}
                  siteUrl={(trigger as JiraTrigger).site_url}
                  emptyLabel="Run the saved JQL to preview matching issues."
                />
              </>
            )}
            {kind === 'schedule' && (
              <>
                <DetailRow label="Cron">{(trigger as ScheduleTrigger).cron_expression}</DetailRow>
                <DetailRow label="Payload template">
                  <JsonBlock value={(trigger as ScheduleTrigger).payload_template} emptyLabel="No payload template saved." />
                </DetailRow>
              </>
            )}
            {kind === 'github' && (
              <>
                <DetailRow label="Events">{((trigger as GitHubTrigger).events || []).join(', ') || 'Default events'}</DetailRow>
                <DetailRow label="Path filters">{((trigger as GitHubTrigger).path_filters || []).join(', ') || 'Any path'}</DetailRow>
                <DetailRow label="Author">{(trigger as GitHubTrigger).author_filter || 'Any author'}</DetailRow>
              </>
            )}
          </div>
        </div>
      </div>
    )
  }

  const renderEventsTab = () => (
    <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-white">
          <BellIcon size={18} /> Recent wake events
        </h2>
        <Link href={`/hub/wake-events?channel_type=${kind}`} className="text-sm text-cyan-200 hover:text-white">
          Open browser
        </Link>
      </div>
      {events.length === 0 ? (
        <div className="rounded-xl border border-dashed border-tsushin-border p-8 text-center text-sm text-tsushin-slate">
          No wake events found for this trigger yet.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-tsushin-slate">
              <tr className="border-b border-tsushin-border">
                <th className="px-3 py-2">Event</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Occurred</th>
                <th className="px-3 py-2">Payload ref</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.id} className="border-b border-tsushin-border/60">
                  <td className="px-3 py-2">
                    <Link href={`/hub/wake-events?highlight=${event.id}`} className="font-mono text-cyan-200 hover:text-white">#{event.id}</Link>
                    <div className="text-xs text-tsushin-slate">{event.event_type}</div>
                  </td>
                  <td className="px-3 py-2 text-white">{event.status}</td>
                  <td className="px-3 py-2 text-tsushin-slate">{formatRelative(event.occurred_at)}</td>
                  <td className="px-3 py-2">
                    {event.payload_ref ? (
                      <code className="rounded bg-black/30 px-2 py-1 text-xs text-cyan-200">{event.payload_ref}</code>
                    ) : (
                      <span className="text-tsushin-slate">None</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )

  const renderDangerTab = () => {
    if (!trigger) return null
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-5">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-red-100">
          <AlertTriangleIcon size={18} /> Danger zone
        </h2>
        {!canWriteHub && (
          <p className="mt-3 text-sm text-red-100/80">Your role can view this trigger but cannot modify it.</p>
        )}
        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-red-500/20 bg-black/20 p-4">
            <div className="font-medium text-white">{trigger.is_active ? 'Pause trigger' : 'Resume trigger'}</div>
            <p className="mt-1 text-sm text-red-100/80">
              Pausing preserves configuration but stops new wake events from this source.
            </p>
            {canWriteHub && (
              <button
                type="button"
                onClick={updateActive}
                disabled={saving}
                className="mt-4 rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm text-red-100 hover:text-white disabled:opacity-50"
              >
                {trigger.is_active ? 'Pause Trigger' : 'Resume Trigger'}
              </button>
            )}
          </div>
          <div className="rounded-xl border border-red-500/20 bg-black/20 p-4">
            <div className="font-medium text-white">Delete trigger</div>
            <p className="mt-1 text-sm text-red-100/80">
              Delete this trigger and remove the saved source binding.
            </p>
            {canWriteHub && (
              <button
                type="button"
                onClick={deleteTrigger}
                disabled={saving}
                className="mt-4 inline-flex items-center gap-2 rounded-lg border border-red-500/50 bg-red-500/20 px-4 py-2 text-sm text-red-100 hover:text-white disabled:opacity-50"
              >
                <TrashIcon size={16} />
                Delete Trigger
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }

  if (!hasValidId) return null

  return (
    <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8 animate-fade-in">
      <div className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-3 text-sm text-tsushin-slate">
            <Link href="/hub?tab=communication" className="hover:text-white">Hub</Link>
            <span>/</span>
            <span>{config.label}</span>
          </div>
          <h1 className="flex items-center gap-3 text-3xl font-display font-bold text-white">
            <Icon size={26} className={config.iconClass} />
            {trigger?.integration_name || `${config.label} #${triggerId}`}
          </h1>
          <p className="mt-2 max-w-3xl text-sm text-tsushin-slate">{config.description}</p>
        </div>
        <button
          type="button"
          onClick={loadData}
          disabled={loading || saving}
          className="inline-flex items-center justify-center gap-2 rounded-lg border border-tsushin-border bg-tsushin-surface px-4 py-2 text-sm text-tsushin-fog hover:text-white disabled:opacity-50"
        >
          <RefreshIcon size={16} />
          Refresh
        </button>
      </div>

      {success && (
        <div className="mb-5 rounded-xl border border-green-500/30 bg-green-500/10 p-4 text-sm text-green-200">
          {success}
        </div>
      )}
      {error && (
        <div className="mb-5 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
          {error}
        </div>
      )}

      {loading ? (
        <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/50 p-10 text-center text-tsushin-slate">
          Loading {kind} trigger...
        </div>
      ) : !trigger ? (
        <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/50 p-10 text-center">
          <AlertTriangleIcon size={28} className="mx-auto mb-3 text-yellow-300" />
          <div className="text-white">{config.label} not found</div>
        </div>
      ) : (
        <div className="space-y-6">
          {!canWriteHub && (
            <div className="rounded-xl border border-yellow-500/30 bg-yellow-500/10 p-4 text-sm text-yellow-100">
              Read-only view. Your role does not have <code className="font-mono">hub.write</code>.
            </div>
          )}

          <div className="grid gap-4 md:grid-cols-4">
            <Field label="Status" value={<span className={`rounded-full border px-2.5 py-1 text-xs ${statusClass(trigger)}`}>{statusLabel(trigger)}</span>} />
            <Field label="Health" value={trigger.health_status || 'unknown'} />
            <Field label="Default agent" value={trigger.default_agent_name || (trigger.default_agent_id ? `Agent #${trigger.default_agent_id}` : 'None')} />
            <Field label="Last activity" value={trigger.last_activity_at ? formatRelative(trigger.last_activity_at) : 'No activity'} />
          </div>

          <div className={`rounded-xl border px-4 py-3 text-sm ${config.accentClass}`}>
            Created {formatDateTime(trigger.created_at)}
            {trigger.updated_at ? `; updated ${formatRelative(trigger.updated_at)}` : ''}
            {trigger.health_status_reason ? `; health note: ${trigger.health_status_reason}` : ''}
          </div>

          <div className="flex flex-wrap gap-2 border-b border-tsushin-border pb-2">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`rounded-lg px-3 py-1.5 text-sm transition-colors ${
                  activeTab === tab.id
                    ? 'bg-cyan-500/10 text-cyan-200'
                    : 'text-tsushin-slate hover:text-white'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {activeTab === 'overview' && (
            <div className="space-y-6">
              {renderSourceSummary()}
            </div>
          )}
          {activeTab === 'criteria' && renderCriteriaTab()}
          {activeTab === 'events' && renderEventsTab()}
          {activeTab === 'danger' && renderDangerTab()}
        </div>
      )}
    </div>
  )
}
