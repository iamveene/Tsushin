'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { api, authenticatedFetch, type EmailTrigger, type PageResponse, type WakeEvent } from '@/lib/client'
import { useAuth } from '@/contexts/AuthContext'
import { formatDateTime, formatRelative } from '@/lib/dateUtils'
import { AlertTriangleIcon, BellIcon, ClockIcon, EnvelopeIcon, RefreshIcon, SparklesIcon, TrashIcon } from '@/components/ui/icons'
import CriteriaBuilder, {
  buildEmailSearchQuery,
  buildCriteriaTemplate,
  emailSourceFromSearchQuery,
  formatCriteriaText,
  parseCriteriaText,
  type CriteriaSourceValues,
} from '@/components/triggers/CriteriaBuilder'

type TabId = 'overview' | 'criteria' | 'events' | 'danger'

interface GmailIntegrationSummary {
  id: number
  name: string
  email_address: string
  health_status: string
  health_status_reason?: string | null
  is_active: boolean
  can_send: boolean
  can_draft?: boolean
}

const TABS: Array<{ id: TabId; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'criteria', label: 'Criteria' },
  { id: 'events', label: 'Recent wake events' },
  { id: 'danger', label: 'Danger zone' },
]

function getErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback
}

async function fetchGmailIntegrations(): Promise<GmailIntegrationSummary[]> {
  const response = await authenticatedFetch('/api/hub/google/gmail/integrations')
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  const data = await response.json()
  return Array.isArray(data.integrations) ? data.integrations : []
}

function statusClass(trigger: EmailTrigger): string {
  if (!trigger.is_active || trigger.status === 'paused') return 'bg-gray-500/10 text-gray-300 border-gray-500/30'
  if (trigger.status === 'error' || trigger.health_status === 'unhealthy') return 'bg-red-500/10 text-red-300 border-red-500/30'
  if (trigger.health_status === 'healthy') return 'bg-green-500/10 text-green-300 border-green-500/30'
  return 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30'
}

function statusLabel(trigger: EmailTrigger): string {
  if (!trigger.is_active || trigger.status === 'paused') return 'paused'
  return trigger.status || 'unknown'
}

function gmailScopeLabel(integration?: GmailIntegrationSummary | null): string {
  if (!integration) return 'Scope unknown'
  if (integration.can_send && integration.can_draft) return 'Read + send/draft'
  if (integration.can_send) return 'Read + send/reply'
  return 'Read-only'
}

function gmailScopeClass(integration?: GmailIntegrationSummary | null): string {
  if (!integration) return 'bg-gray-500/10 text-gray-300 border-gray-500/30'
  if (integration.can_send && integration.can_draft) return 'bg-green-500/10 text-green-300 border-green-500/30'
  if (integration.can_send) return 'bg-yellow-500/10 text-yellow-200 border-yellow-500/30'
  return 'bg-gray-500/10 text-gray-300 border-gray-500/30'
}

function gmailScopeMessage(integration?: GmailIntegrationSummary | null): string {
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

function healthClass(healthStatus?: string | null): string {
  if (healthStatus === 'healthy') return 'bg-green-500/10 text-green-300 border-green-500/30'
  if (healthStatus === 'unhealthy') return 'bg-red-500/10 text-red-300 border-red-500/30'
  if (healthStatus === 'disconnected') return 'bg-gray-500/10 text-gray-300 border-gray-500/30'
  return 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30'
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

export default function EmailTriggerDetailPage() {
  const params = useParams()
  const router = useRouter()
  const triggerId = Number(params.id)
  const hasValidId = Number.isFinite(triggerId) && triggerId > 0
  const { hasPermission } = useAuth()
  const canWriteHub = hasPermission('hub.write')
  const [trigger, setTrigger] = useState<EmailTrigger | null>(null)
  const [eventsPage, setEventsPage] = useState<PageResponse<WakeEvent> | null>(null)
  const [gmailIntegrations, setGmailIntegrations] = useState<GmailIntegrationSummary[]>([])
  const [activeTab, setActiveTab] = useState<TabId>('overview')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [triageLoading, setTriageLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [criteriaText, setCriteriaText] = useState('')
  const [criteriaSource, setCriteriaSource] = useState<CriteriaSourceValues>({})

  const loadData = useCallback(async () => {
    if (!hasValidId) return
    setLoading(true)
    setError(null)
    try {
      const [triggerData, wakeEvents, integrations] = await Promise.all([
        api.getEmailTrigger(triggerId),
        api.getWakeEvents({ limit: 50, channel_type: 'email', channel_instance_id: triggerId }).catch(() => null),
        fetchGmailIntegrations().catch(() => []),
      ])
      const source = emailSourceFromSearchQuery(triggerData.search_query)
      setTrigger(triggerData)
      setEventsPage(wakeEvents)
      setGmailIntegrations(integrations)
      setCriteriaSource(source)
      setCriteriaText(formatCriteriaText(buildCriteriaTemplate('email', source)))
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to load email trigger'))
    } finally {
      setLoading(false)
    }
  }, [hasValidId, triggerId])

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
    if (!trigger) return null
    return gmailIntegrations.find((integration) => integration.id === trigger.gmail_integration_id) ||
      gmailIntegrations.find((integration) => integration.email_address === trigger.gmail_account_email) ||
      null
  }, [gmailIntegrations, trigger])

  const toggleActive = async () => {
    if (!trigger) return
    setSaving(true)
    setError(null)
    try {
      const updated = await api.updateEmailTrigger(trigger.id, { is_active: !trigger.is_active })
      setTrigger(updated)
      setSuccess(updated.is_active ? 'Email trigger resumed' : 'Email trigger paused')
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to update email trigger'))
    } finally {
      setSaving(false)
    }
  }

  const deleteTrigger = async () => {
    if (!trigger) return
    if (!confirm(`Delete email trigger "${trigger.integration_name}"? This cannot be undone.`)) return
    setSaving(true)
    setError(null)
    try {
      await api.deleteEmailTrigger(trigger.id)
      router.push('/hub?tab=communication')
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to delete email trigger'))
      setSaving(false)
    }
  }

  const enableTriage = async () => {
    if (!trigger) return
    setTriageLoading(true)
    setError(null)
    try {
      const result = await api.createEmailTriageSubscription(trigger.id)
      setSuccess(result.created_subscription ? 'Email triage flow enabled' : 'Email triage flow is already active')
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to enable email triage'))
    } finally {
      setTriageLoading(false)
    }
  }

  const saveCriteria = async () => {
    if (!trigger) return
    setSaving(true)
    setError(null)
    try {
      parseCriteriaText(criteriaText)
      const nextSearchQuery = buildEmailSearchQuery(criteriaSource) || null
      const updated = await api.updateEmailTrigger(trigger.id, { search_query: nextSearchQuery })
      const source = emailSourceFromSearchQuery(updated.search_query)
      setTrigger(updated)
      setCriteriaSource(source)
      setCriteriaText(formatCriteriaText(buildCriteriaTemplate('email', source)))
      setSuccess('Criteria saved')
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to save criteria'))
    } finally {
      setSaving(false)
    }
  }

  const renderEventsTab = () => (
    <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-white">
          <BellIcon size={18} /> Recent wake events
        </h2>
        <Link href="/hub/wake-events?channel_type=email" className="text-sm text-cyan-200 hover:text-white">
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
              Pausing preserves configuration but stops new wake events from this Gmail account.
            </p>
            {canWriteHub && (
              <button
                type="button"
                onClick={toggleActive}
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
              Delete this trigger and remove the saved Gmail source binding.
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
            <span>Email Trigger</span>
          </div>
          <h1 className="text-3xl font-display font-bold text-white">
            {trigger?.integration_name || `Email Trigger #${triggerId}`}
          </h1>
          <p className="mt-2 max-w-3xl text-sm text-tsushin-slate">
            Gmail-backed trigger detail using the v0.7.0 trigger namespace.
          </p>
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
          Loading email trigger...
        </div>
      ) : !trigger ? (
        <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/50 p-10 text-center">
          <AlertTriangleIcon size={28} className="mx-auto mb-3 text-yellow-300" />
          <div className="text-white">Email trigger not found</div>
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
            <Field label="Gmail scope" value={<span className={`rounded-full border px-2.5 py-1 text-xs ${gmailScopeClass(gmailIntegration)}`}>{gmailScopeLabel(gmailIntegration)}</span>} />
            <Field label="Last activity" value={trigger.last_activity_at ? formatRelative(trigger.last_activity_at) : 'No activity'} />
          </div>

          <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-100">
            {gmailScopeMessage(gmailIntegration)}
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
            <div className="grid gap-6 lg:grid-cols-2">
              <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
                <h2 className="flex items-center gap-2 text-lg font-semibold text-white">
                  <EnvelopeIcon size={18} /> Inbox Binding
                </h2>
                <div className="mt-4 space-y-4 text-sm">
                  <DetailRow label="Gmail account">{trigger.gmail_account_email || 'Not reported'}</DetailRow>
                  <DetailRow label="Gmail integration">{trigger.gmail_integration_name || trigger.gmail_integration_id || '-'}</DetailRow>
                  <DetailRow label="Provider">{trigger.provider}</DetailRow>
                  <DetailRow label="Integration health">
                    <span className={`rounded-full border px-2.5 py-1 text-xs ${healthClass(gmailIntegration?.health_status)}`}>
                      {gmailIntegration?.health_status || 'unknown'}
                    </span>
                    {gmailIntegration?.health_status_reason && (
                      <p className="mt-2 text-xs text-yellow-200">{gmailIntegration.health_status_reason}</p>
                    )}
                  </DetailRow>
                </div>
              </div>

              <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
                <h2 className="flex items-center gap-2 text-lg font-semibold text-white">
                  <ClockIcon size={18} /> Routing Detail
                </h2>
                <div className="mt-4 space-y-4 text-sm">
                  <DetailRow label="Default agent">
                    {trigger.default_agent_name || (trigger.default_agent_id ? `Agent #${trigger.default_agent_id}` : 'None')}
                  </DetailRow>
                  <DetailRow label="Poll interval">{`${trigger.poll_interval_seconds}s`}</DetailRow>
                  <DetailRow label="Trigger health">
                    {trigger.health_status}
                    {trigger.health_status_reason && (
                      <p className="mt-1 text-xs text-yellow-200">{trigger.health_status_reason}</p>
                    )}
                  </DetailRow>
                  <div className="grid grid-cols-2 gap-3">
                    <DetailRow label="Created">{formatDateTime(trigger.created_at)}</DetailRow>
                    <DetailRow label="Updated">{trigger.updated_at ? formatDateTime(trigger.updated_at) : '-'}</DetailRow>
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5 lg:col-span-2">
                <h2 className="flex items-center gap-2 text-lg font-semibold text-white">
                  <SparklesIcon size={18} /> Managed Email Triage
                </h2>
                <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_auto] lg:items-center">
                  <div className="space-y-2 text-sm text-tsushin-slate">
                    <p>
                      Link this Gmail trigger to the default agent and create system-owned continuous-agent routing for draft-based triage.
                    </p>
                    {!trigger.default_agent_id && (
                      <p className="text-yellow-200">Choose a default agent before enabling managed triage.</p>
                    )}
                    {gmailIntegration && !gmailIntegration.can_draft && (
                      <p className="text-yellow-200">
                        Re-authorize this Gmail account with <code className="font-mono">gmail.compose</code> before draft creation can run.
                      </p>
                    )}
                  </div>
                  {canWriteHub && (
                    <button
                      type="button"
                      onClick={enableTriage}
                      disabled={triageLoading || !trigger.default_agent_id || Boolean(gmailIntegration && !gmailIntegration.can_draft)}
                      className="inline-flex items-center justify-center gap-2 rounded-lg border border-cyan-400/40 bg-cyan-500/10 px-4 py-2 text-sm text-cyan-100 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <SparklesIcon size={16} />
                      {triageLoading ? 'Enabling...' : 'Enable Triage'}
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'criteria' && (
            <div className="space-y-3">
              <CriteriaBuilder
                kind="email"
                value={criteriaText}
                onChange={setCriteriaText}
                disabled={!canWriteHub || saving}
                source={criteriaSource}
                onSourceChange={(patch) => setCriteriaSource((current) => ({ ...current, ...patch }))}
                readOnlyReason={!canWriteHub ? 'Read-only view. Your role can view criteria but cannot change it.' : null}
              />
              {canWriteHub && (
                <button
                  type="button"
                  onClick={saveCriteria}
                  disabled={saving}
                  className="rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-4 py-2 text-sm text-cyan-200 hover:text-white disabled:opacity-50"
                >
                  {saving ? 'Saving...' : 'Save Criteria'}
                </button>
              )}
            </div>
          )}

          {activeTab === 'events' && renderEventsTab()}
          {activeTab === 'danger' && renderDangerTab()}
        </div>
      )}
    </div>
  )
}
