'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ComponentType, ReactNode } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import {
  api,
  authenticatedFetch,
  type EmailMessagePreview,
  type EmailPollNowResponse,
  type EmailTestQueryResponse,
  type EmailTrigger,
  type GitHubTrigger,
  type JiraIssuePreview,
  type JiraManagedNotificationStatus,
  type JiraNotificationSubscriptionResponse,
  type JiraPollNowResponse,
  type JiraTrigger,
  type PageResponse,
  type PublicIngressInfo,
  type ScheduleTrigger,
  type TriggerKind,
  type WakeEvent,
  type WebhookIntegration,
} from '@/lib/client'
import { formatDateTime, formatRelative } from '@/lib/dateUtils'
import {
  AlertTriangleIcon,
  BellIcon,
  CalendarDaysIcon,
  CodeIcon,
  EnvelopeIcon,
  GitHubIcon,
  PlayIcon,
  RefreshIcon,
  TrashIcon,
  WebhookIcon,
  type IconProps,
} from '@/components/ui/icons'
import CriteriaBuilder, {
  buildCriteriaTemplate,
  buildEmailSearchQuery,
  emailSourceFromSearchQuery,
  formatCriteriaText,
  parseCriteriaText,
  type CriteriaSourceValues,
} from '@/components/triggers/CriteriaBuilder'
import JiraIssuePreviewList from '@/components/triggers/JiraIssuePreviewList'
import DefaultAgentChip from '@/components/triggers/DefaultAgentChip'
import SectionHeader from '@/components/triggers/SectionHeader'
import Divider from '@/components/triggers/Divider'
import SourceSection from '@/components/triggers/sections/SourceSection'
import RoutingSection from '@/components/triggers/sections/RoutingSection'
import OutputsSection from '@/components/triggers/sections/OutputsSection'
import type { EmailGmailIntegrationSummary } from '@/components/triggers/sections/EmailSourceCard'

// Wave 3 of the Triggers ↔ Flows unification: the shared shell now also
// handles `email` and `webhook` kinds. The standalone fork pages are
// reduced to one-line wrappers around `<TriggerDetailShell kind=...>`.
type BreadthTriggerKind = Extract<TriggerKind, 'jira' | 'schedule' | 'github' | 'email' | 'webhook'>
type BreadthTrigger = JiraTrigger | ScheduleTrigger | GitHubTrigger | EmailTrigger | WebhookIntegration
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
  email: {
    label: 'Email Trigger',
    description: 'Gmail-backed wake source with managed notification + triage outputs.',
    Icon: EnvelopeIcon,
    iconClass: 'text-emerald-300',
    accentClass: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100',
  },
  webhook: {
    label: 'Webhook Trigger',
    description: 'Signed HTTP wake source — pair with a Flow to define behavior.',
    Icon: WebhookIcon,
    iconClass: 'text-cyan-300',
    accentClass: 'border-cyan-500/30 bg-cyan-500/10 text-cyan-100',
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
  // Webhook-specific: open circuit-breaker is also a hard error state
  const cb = (trigger as WebhookIntegration).circuit_breaker_state
  if (cb === 'open') return 'bg-red-500/10 text-red-300 border-red-500/30'
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

function emailPollSummary(result: EmailPollNowResponse): string {
  const fetched = result.fetched_count ?? 0
  const dispatched = result.dispatched_count ?? 0
  const processed = result.processed_count ?? 0
  const duplicates = result.duplicate_count ?? 0
  const failed = result.failed_count ?? 0
  return `Poll ${result.status || 'finished'}: ${fetched} fetched, ${dispatched} dispatched, ${processed} processed, ${duplicates} duplicate, ${failed} failed.`
}

function emailSamplesFromResult(result?: EmailTestQueryResponse | null): EmailMessagePreview[] {
  return result?.sample_messages || result?.messages || []
}

function gmailScopeLabel(integration?: EmailGmailIntegrationSummary | null): string {
  if (!integration) return 'Scope unknown'
  if (integration.can_send && integration.can_draft) return 'Read + send/draft'
  if (integration.can_send) return 'Read + send/reply'
  return 'Read-only'
}

function gmailScopeClass(integration?: EmailGmailIntegrationSummary | null): string {
  if (!integration) return 'bg-gray-500/10 text-gray-300 border-gray-500/30'
  if (integration.can_send && integration.can_draft) return 'bg-green-500/10 text-green-300 border-green-500/30'
  if (integration.can_send) return 'bg-yellow-500/10 text-yellow-200 border-yellow-500/30'
  return 'bg-gray-500/10 text-gray-300 border-gray-500/30'
}

function gmailScopeMessage(integration?: EmailGmailIntegrationSummary | null): string {
  if (!integration) {
    return 'This trigger can still monitor Gmail. Open the Gmail integration details in Hub to confirm outbound send and draft access.'
  }
  if (integration.can_send && integration.can_draft) {
    return 'This trigger only watches Gmail. The reused account also has outbound send and compose access for agents that use it.'
  }
  if (integration.can_send) {
    return 'This trigger can monitor Gmail. Agents using this account can send and reply, but draft creation needs gmail.compose reauthorization.'
  }
  return 'This trigger can monitor Gmail with read access. Agents using this account need outbound reauthorization before they can send or create drafts.'
}

async function fetchGmailIntegrations(): Promise<EmailGmailIntegrationSummary[]> {
  const response = await authenticatedFetch('/api/hub/google/gmail/integrations')
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  const data = await response.json()
  return Array.isArray(data.integrations) ? data.integrations : []
}

function emailCriteriaSourceFrom(trigger: EmailTrigger): CriteriaSourceValues {
  const source = emailSourceFromSearchQuery(trigger.search_query)
  const criteria = trigger.trigger_criteria
  const filters = criteria && typeof criteria === 'object' && !Array.isArray(criteria)
    ? (criteria.filters as Record<string, unknown> | undefined)
    : undefined
  const email = filters && typeof filters.email === 'object' && !Array.isArray(filters.email)
    ? filters.email as Record<string, unknown>
    : undefined
  const bodyKeyword = typeof email?.body_contains === 'string' ? email.body_contains : ''
  return {
    ...source,
    emailBodyKeyword: bodyKeyword,
  }
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
  if (kind === 'github') {
    const github = trigger as GitHubTrigger
    return {
      githubEventsText: (github.events || []).join(', '),
      githubBranchFilter: github.branch_filter || '',
      githubPathFiltersText: (github.path_filters || []).join('\n'),
      githubAuthorFilter: github.author_filter || '',
    }
  }
  if (kind === 'email') {
    return emailCriteriaSourceFrom(trigger as EmailTrigger)
  }
  // webhook has no per-source draft fields; the criteria builder handles its own state
  return {}
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

  // Jira-specific state
  const [jiraTesting, setJiraTesting] = useState(false)
  const [jiraTestMessage, setJiraTestMessage] = useState<string | null>(null)
  const [jiraSampleIssues, setJiraSampleIssues] = useState<JiraIssuePreview[]>([])
  const [jiraPolling, setJiraPolling] = useState(false)
  const [jiraPollResult, setJiraPollResult] = useState<JiraPollNowResponse | null>(null)
  const [jiraNotificationLoading, setJiraNotificationLoading] = useState(false)
  const [jiraNotificationStatus, setJiraNotificationStatus] = useState<JiraManagedNotificationStatus | null>(null)
  const [jiraNotificationRecipient, setJiraNotificationRecipient] = useState('')

  // Email-specific state
  const [gmailIntegrations, setGmailIntegrations] = useState<EmailGmailIntegrationSummary[]>([])
  const [emailNotificationRecipient, setEmailNotificationRecipient] = useState('')
  const [emailNotificationLoading, setEmailNotificationLoading] = useState(false)
  const [emailTriageLoading, setEmailTriageLoading] = useState(false)
  const [emailPolling, setEmailPolling] = useState(false)
  const [emailPollResult, setEmailPollResult] = useState<EmailPollNowResponse | null>(null)
  const [emailQueryTesting, setEmailQueryTesting] = useState(false)
  const [emailQueryResult, setEmailQueryResult] = useState<EmailTestQueryResponse | null>(null)

  // Webhook-specific state
  const [publicIngress, setPublicIngress] = useState<PublicIngressInfo | null>(null)
  const [webhookCopied, setWebhookCopied] = useState(false)
  const [webhookRotating, setWebhookRotating] = useState(false)

  const loadData = useCallback(async () => {
    if (!hasValidId) return
    setLoading(true)
    setError(null)
    try {
      const triggerPromise = api.getTriggerDetail(kind, triggerId)
      const eventsPromise = api.getWakeEvents({ limit: 50, channel_type: kind, channel_instance_id: triggerId }).catch(() => null)
      const gmailPromise = kind === 'email' ? fetchGmailIntegrations().catch(() => []) : Promise.resolve([] as EmailGmailIntegrationSummary[])
      const ingressPromise = kind === 'webhook' ? api.getMyPublicIngress().catch(() => null) : Promise.resolve(null)
      const [triggerData, wakeEvents, integrations, ingressData] = await Promise.all([
        triggerPromise,
        eventsPromise,
        gmailPromise,
        ingressPromise,
      ])
      const nextTrigger = triggerData as BreadthTrigger
      setTrigger(nextTrigger)
      setJiraNotificationStatus(kind === 'jira' ? jiraManagedNotificationFromTrigger(nextTrigger as JiraTrigger) : null)
      setCriteriaText(formatCriteriaText(nextTrigger.trigger_criteria))
      setSourceDraft(sourceFromTrigger(kind, nextTrigger))
      setEventsPage(wakeEvents)
      setGmailIntegrations(integrations)
      setPublicIngress(ingressData)
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

  const gmailIntegration = useMemo(() => {
    if (kind !== 'email' || !trigger) return null
    const email = trigger as EmailTrigger
    return (
      gmailIntegrations.find((integration) => integration.id === email.gmail_integration_id) ||
      gmailIntegrations.find((integration) => integration.email_address === email.gmail_account_email) ||
      null
    )
  }, [gmailIntegrations, kind, trigger])

  const absoluteInboundUrl = useMemo(() => {
    if (kind !== 'webhook' || !trigger) return ''
    const webhook = trigger as WebhookIntegration
    const base = publicIngress?.url || (typeof window !== 'undefined' ? window.location.origin : '')
    return `${base}${webhook.inbound_url}`
  }, [kind, publicIngress, trigger])

  const updateActive = async () => {
    if (!trigger) return
    setSaving(true)
    setError(null)
    try {
      const next = !trigger.is_active
      let updated: BreadthTrigger
      if (kind === 'jira') updated = await api.updateJiraTrigger(trigger.id, { is_active: next })
      else if (kind === 'schedule') updated = await api.updateScheduleTrigger(trigger.id, { is_active: next })
      else if (kind === 'github') updated = await api.updateGitHubTrigger(trigger.id, { is_active: next })
      else if (kind === 'email') updated = await api.updateEmailTrigger(trigger.id, { is_active: next })
      else updated = await api.updateWebhookIntegration(trigger.id, { is_active: next })
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

  const handleEnableEmailNotification = async () => {
    if (!trigger || kind !== 'email') return
    const recipient = emailNotificationRecipient.trim()
    if (!recipient) {
      setError('WhatsApp recipient is required to enable email notifications')
      return
    }
    setEmailNotificationLoading(true)
    setError(null)
    try {
      const result = await api.createEmailNotificationSubscription(trigger.id, { recipient_phone: recipient })
      setSuccess(result.created_subscription ? 'Email WhatsApp notification enabled' : 'Email WhatsApp notification is already active')
      setEmailNotificationRecipient('')
      const refreshed = await api.getEmailTrigger(trigger.id)
      setTrigger(refreshed)
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to enable email WhatsApp notification'))
    } finally {
      setEmailNotificationLoading(false)
    }
  }

  const handleEnableEmailTriage = async () => {
    if (!trigger || kind !== 'email') return
    setEmailTriageLoading(true)
    setError(null)
    try {
      const result = await api.createEmailTriageSubscription(trigger.id)
      setSuccess(result.created_subscription ? 'Email triage flow enabled' : 'Email triage flow is already active')
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to enable email triage'))
    } finally {
      setEmailTriageLoading(false)
    }
  }

  const handleEmailPollNow = async () => {
    if (!trigger || kind !== 'email') return
    setEmailPolling(true)
    setError(null)
    try {
      const result = await api.pollEmailTriggerNow(trigger.id)
      setEmailPollResult(result)
      if (result.success === false) {
        setError(result.error || result.message || 'Email poll failed')
      } else {
        setSuccess(emailPollSummary(result))
        setTimeout(() => setSuccess(null), 5000)
      }
      await loadData()
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to poll email trigger'))
    } finally {
      setEmailPolling(false)
    }
  }

  const handleEmailTestQuery = async () => {
    if (!trigger || kind !== 'email') return
    setEmailQueryTesting(true)
    setError(null)
    try {
      const email = trigger as EmailTrigger
      const searchQuery = buildEmailSearchQuery(sourceDraft) || email.search_query || null
      const triggerCriteria = parseCriteriaText(criteriaText) || buildCriteriaTemplate('email', sourceDraft)
      const result = await api.testSavedEmailTriggerQuery(email.id, {
        search_query: searchQuery,
        trigger_criteria: triggerCriteria,
        max_results: 3,
      })
      setEmailQueryResult(result)
      setSuccess(result.message || `Query returned ${result.message_count ?? 0} message(s)`)
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: unknown) {
      setEmailQueryResult(null)
      setError(getErrorMessage(err, 'Failed to test email query'))
    } finally {
      setEmailQueryTesting(false)
    }
  }

  const handleCopyInboundUrl = async () => {
    if (!absoluteInboundUrl) return
    try {
      await navigator.clipboard.writeText(absoluteInboundUrl)
      setWebhookCopied(true)
      setTimeout(() => setWebhookCopied(false), 2000)
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to copy inbound URL'))
    }
  }

  const handleRotateWebhookSecret = async () => {
    if (!trigger || kind !== 'webhook') return
    if (!confirm('Rotate the webhook signing secret? Any callers using the previous secret will start failing immediately.')) return
    setWebhookRotating(true)
    setError(null)
    try {
      const result = await api.rotateWebhookSecret(trigger.id)
      setSuccess(`New secret: ${result.api_secret} — copy it now; it will not be shown again.`)
      // Refresh trigger to update preview
      const refreshed = await api.getWebhookIntegration(trigger.id)
      setTrigger(refreshed)
      setTimeout(() => setSuccess(null), 12000)
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to rotate webhook secret'))
    } finally {
      setWebhookRotating(false)
    }
  }

  const saveCriteria = async () => {
    if (!trigger) return
    setSaving(true)
    setError(null)
    try {
      const triggerCriteria = parseCriteriaText(criteriaText)
      let updated: BreadthTrigger
      if (kind === 'jira') {
        updated = await api.updateJiraTrigger(trigger.id, {
          trigger_criteria: triggerCriteria,
          project_key: sourceDraft.jiraProjectKey?.trim() || null,
          jql: sourceDraft.jiraJql?.trim() || (trigger as JiraTrigger).jql,
        })
      } else if (kind === 'schedule') {
        updated = await api.updateScheduleTrigger(trigger.id, {
          trigger_criteria: triggerCriteria,
          cron_expression: sourceDraft.cronExpression?.trim() || (trigger as ScheduleTrigger).cron_expression,
          timezone: sourceDraft.timezone?.trim() || (trigger as ScheduleTrigger).timezone,
          payload_template: parseJsonObjectText(sourceDraft.payloadTemplateText || '', 'Payload template'),
        })
      } else if (kind === 'github') {
        updated = await api.updateGitHubTrigger(trigger.id, {
          trigger_criteria: triggerCriteria,
          events: splitList(sourceDraft.githubEventsText),
          branch_filter: sourceDraft.githubBranchFilter?.trim() || null,
          path_filters: splitList(sourceDraft.githubPathFiltersText),
          author_filter: sourceDraft.githubAuthorFilter?.trim() || null,
        })
      } else if (kind === 'email') {
        const nextSearchQuery = buildEmailSearchQuery(sourceDraft) || null
        updated = await api.updateEmailTrigger(trigger.id, {
          search_query: nextSearchQuery,
          trigger_criteria: triggerCriteria,
        })
      } else {
        updated = await api.updateWebhookIntegration(trigger.id, {
          trigger_criteria: triggerCriteria,
        })
      }
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
      } else if (kind === 'github') {
        await api.deleteGitHubTrigger(trigger.id)
      } else if (kind === 'email') {
        await api.deleteEmailTrigger(trigger.id)
      } else {
        await api.deleteWebhookIntegration(trigger.id)
      }
      router.push('/hub?tab=communication')
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to delete trigger'))
      setSaving(false)
    }
  }

  // Email's CriteriaBuilder regenerates the criteria text whenever the
  // structured source patch changes — preserving the pre-Wave-3 behavior.
  const handleSourceChange = (patch: Partial<CriteriaSourceValues>) => {
    setSourceDraft((current) => {
      const next = { ...current, ...patch }
      if (kind === 'email') {
        setCriteriaText(formatCriteriaText(buildCriteriaTemplate('email', next)))
      }
      return next
    })
  }

  // Wave 3 of the Triggers ↔ Flows unification: Overview tab renders three
  // explicit sections (Source / Routing / Outputs) for jira, github, schedule,
  // email, and webhook.
  const renderOverview = () => {
    if (!trigger) return null
    const status = kind === 'jira'
      ? jiraNotificationStatus || jiraManagedNotificationFromTrigger(trigger as JiraTrigger)
      : null
    return (
      <div className="space-y-6">
        <SectionHeader title="Source" subtitle="Where events come from." />
        <SourceSection
          kind={kind}
          trigger={trigger}
          gmailIntegration={kind === 'email' ? gmailIntegration : null}
          publicIngress={kind === 'webhook' ? publicIngress : null}
          absoluteInboundUrl={kind === 'webhook' ? absoluteInboundUrl : ''}
          copied={webhookCopied}
          onCopyInboundUrl={handleCopyInboundUrl}
          rotatingSecret={webhookRotating}
          onRotateWebhookSecret={kind === 'webhook' ? handleRotateWebhookSecret : undefined}
          canWriteHub={canWriteHub}
        />

        <Divider />

        <SectionHeader
          title="Routing"
          subtitle="Which agent handles events when no Flow is bound."
        />
        <RoutingSection
          kind={kind}
          trigger={trigger}
          canEdit={canWriteHub}
          onUpdate={(next) =>
            setTrigger((current) => (current ? { ...current, ...next } as BreadthTrigger : current))
          }
        />

        <Divider />

        <SectionHeader title="Outputs" subtitle="What happens when this trigger fires." />
        <OutputsSection
          kind={kind}
          trigger={trigger}
          canWriteHub={canWriteHub}
          jiraNotificationStatus={status}
          jiraPhoneInput={jiraNotificationRecipient}
          onJiraPhoneChange={setJiraNotificationRecipient}
          onEnableJiraNotification={handleEnableJiraNotification}
          jiraNotificationLoading={jiraNotificationLoading}
          jiraPollResult={jiraPollResult}
          onJiraPollNow={handleJiraPollNow}
          jiraPolling={jiraPolling}
          emailGmailIntegration={kind === 'email' ? gmailIntegration : null}
          emailPhoneInput={emailNotificationRecipient}
          onEmailPhoneChange={setEmailNotificationRecipient}
          onEnableEmailNotification={handleEnableEmailNotification}
          emailNotificationLoading={emailNotificationLoading}
          emailPollResult={emailPollResult}
          onEmailPollNow={handleEmailPollNow}
          emailPolling={emailPolling}
          onEnableEmailTriage={handleEnableEmailTriage}
          emailTriageLoading={emailTriageLoading}
        />
      </div>
    )
  }

  const renderCriteriaTab = () => {
    if (!trigger) return null
    const showSidePanel = kind === 'jira' || kind === 'schedule' || kind === 'github'
    const webhookId = trigger.id
    return (
      <div className={showSidePanel ? 'grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]' : 'space-y-3'}>
        <div>
          <CriteriaBuilder
            kind={kind}
            value={criteriaText}
            onChange={setCriteriaText}
            disabled={!canWriteHub || saving}
            source={sourceDraft}
            onSourceChange={handleSourceChange}
            readOnlyReason={!canWriteHub ? 'Read-only view. Your role can view criteria but cannot change it.' : null}
            onTest={kind === 'webhook'
              ? (triggerCriteria, payload) =>
                  api.testWebhookCriteria(webhookId, { payload, trigger_criteria: triggerCriteria })
              : undefined}
          />
          {canWriteHub && (
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={saveCriteria}
                disabled={saving}
                className="rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-4 py-2 text-sm text-cyan-200 hover:text-white disabled:opacity-50"
              >
                {saving ? 'Saving...' : 'Save Criteria'}
              </button>
              {kind === 'email' && (
                <button
                  type="button"
                  onClick={handleEmailTestQuery}
                  disabled={emailQueryTesting}
                  className="inline-flex items-center gap-2 rounded-lg border border-tsushin-border bg-tsushin-surface px-4 py-2 text-sm text-tsushin-fog hover:text-white disabled:opacity-50"
                >
                  <PlayIcon size={16} />
                  {emailQueryTesting ? 'Testing...' : 'Test Query'}
                </button>
              )}
            </div>
          )}
          {kind === 'email' && emailQueryResult && (
            <div className="mt-3 rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-4">
              <div className="mb-3 text-sm font-semibold text-white">
                Sample messages ({emailQueryResult.message_count ?? emailSamplesFromResult(emailQueryResult).length})
              </div>
              {emailSamplesFromResult(emailQueryResult).length === 0 ? (
                <div className="rounded-lg border border-dashed border-tsushin-border p-5 text-center text-sm text-tsushin-slate">
                  No sample messages matched this query.
                </div>
              ) : (
                <div className="space-y-3">
                  {emailSamplesFromResult(emailQueryResult).map((message) => (
                    <div key={message.id} className="rounded-lg border border-tsushin-border/70 bg-black/20 p-3">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="break-words text-sm font-medium text-white">{message.subject}</div>
                          <div className="mt-1 text-xs text-tsushin-slate">{message.from_address || 'Unknown sender'}</div>
                        </div>
                        {message.link && (
                          <a href={message.link} target="_blank" rel="noreferrer" className="text-xs text-cyan-200 hover:text-white">
                            Open
                          </a>
                        )}
                      </div>
                      {message.description_preview && (
                        <p className="mt-2 line-clamp-3 text-xs text-tsushin-slate">{message.description_preview}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
        {showSidePanel && (
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
        )}
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
            <Field
              label="Routing"
              value={
                <DefaultAgentChip
                  triggerKind={kind}
                  triggerId={trigger.id}
                  agent={{ id: trigger.default_agent_id ?? null, name: trigger.default_agent_name ?? null }}
                  canEdit={canWriteHub}
                  onUpdate={(next) =>
                    setTrigger((current) => (current ? { ...current, ...next } as BreadthTrigger : current))
                  }
                />
              }
            />
            <Field label="Last activity" value={trigger.last_activity_at ? formatRelative(trigger.last_activity_at) : 'No activity'} />
          </div>

          {/*
            Email Gmail-scope banner (Wave 1 relocated this from a 5th KPI cell
            into this banner to keep the KPI grid 4-wide for all kinds).
          */}
          {kind === 'email' && (
            <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-100">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-full border px-2.5 py-1 text-xs ${gmailScopeClass(gmailIntegration)}`}>
                  Gmail scope: {gmailScopeLabel(gmailIntegration)}
                </span>
                <span className="text-red-100/90">{gmailScopeMessage(gmailIntegration)}</span>
              </div>
            </div>
          )}

          {/*
            Webhook circuit-breaker + rate-limit sub-pills (Wave 1 relocation
            so the standardized 4-cell KPI grid stays consistent across all
            5 trigger kinds).
          */}
          {kind === 'webhook' && (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="rounded-full border border-tsushin-border bg-black/20 px-2.5 py-1 text-tsushin-fog">
                Circuit breaker: <span className="text-white">{(trigger as WebhookIntegration).circuit_breaker_state}</span>
              </span>
              <span className="rounded-full border border-tsushin-border bg-black/20 px-2.5 py-1 text-tsushin-fog">
                Rate limit: <span className="text-white">{(trigger as WebhookIntegration).rate_limit_rpm} req/min</span>
              </span>
            </div>
          )}

          <div className={`rounded-xl border px-4 py-3 text-sm ${config.accentClass}`}>
            Created {formatDateTime(trigger.created_at)}
            {trigger.updated_at ? `; updated ${formatRelative(trigger.updated_at)}` : ''}
            {(trigger as { health_status_reason?: string | null }).health_status_reason
              ? `; health note: ${(trigger as { health_status_reason?: string | null }).health_status_reason}`
              : ''}
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
              {renderOverview()}
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
