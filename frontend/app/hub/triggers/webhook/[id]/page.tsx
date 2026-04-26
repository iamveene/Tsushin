'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { api, type PageResponse, type PublicIngressInfo, type WakeEvent, type WebhookIntegration } from '@/lib/client'
import { useAuth } from '@/contexts/AuthContext'
import { formatDateTime, formatRelative } from '@/lib/dateUtils'
import { AlertTriangleIcon, BellIcon, ClockIcon, CopyIcon, RefreshIcon, TrashIcon, WebhookIcon } from '@/components/ui/icons'
import CriteriaBuilder, { formatCriteriaText, parseCriteriaText } from '@/components/triggers/CriteriaBuilder'
import DefaultAgentChip from '@/components/triggers/DefaultAgentChip'

type TabId = 'overview' | 'criteria' | 'events' | 'danger'

const TABS: Array<{ id: TabId; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'criteria', label: 'Criteria' },
  { id: 'events', label: 'Recent wake events' },
  { id: 'danger', label: 'Danger zone' },
]

function getErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback
}

function statusClass(trigger: WebhookIntegration): string {
  if (!trigger.is_active || trigger.status === 'paused') return 'bg-gray-500/10 text-gray-300 border-gray-500/30'
  if (trigger.circuit_breaker_state === 'open' || trigger.status === 'error') return 'bg-red-500/10 text-red-300 border-red-500/30'
  if (trigger.health_status === 'healthy') return 'bg-green-500/10 text-green-300 border-green-500/30'
  return 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30'
}

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-4">
      <div className="text-xs uppercase tracking-wide text-tsushin-slate">{label}</div>
      <div className="mt-2 text-sm text-white">{value}</div>
    </div>
  )
}

export default function WebhookTriggerDetailPage() {
  const params = useParams()
  const router = useRouter()
  const triggerId = Number(params.id)
  const hasValidId = Number.isFinite(triggerId) && triggerId > 0
  const { hasPermission } = useAuth()
  const canWriteHub = hasPermission('hub.write')
  const [trigger, setTrigger] = useState<WebhookIntegration | null>(null)
  const [publicIngress, setPublicIngress] = useState<PublicIngressInfo | null>(null)
  const [eventsPage, setEventsPage] = useState<PageResponse<WakeEvent> | null>(null)
  const [activeTab, setActiveTab] = useState<TabId>('overview')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [criteriaText, setCriteriaText] = useState('')

  const loadTrigger = useCallback(async () => {
    if (!hasValidId) return
    setLoading(true)
    setError(null)
    try {
      const [triggerData, ingressData, wakeEvents] = await Promise.all([
        api.getWebhookIntegration(triggerId),
        api.getMyPublicIngress().catch(() => null),
        api.getWakeEvents({ limit: 50, channel_type: 'webhook', channel_instance_id: triggerId }).catch(() => null),
      ])
      setTrigger(triggerData)
      setCriteriaText(formatCriteriaText(triggerData.trigger_criteria))
      setPublicIngress(ingressData)
      setEventsPage(wakeEvents)
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to load webhook trigger'))
    } finally {
      setLoading(false)
    }
  }, [hasValidId, triggerId])

  useEffect(() => {
    if (!hasValidId) {
      router.replace('/hub?tab=communication')
      return
    }
    loadTrigger()
  }, [hasValidId, loadTrigger, router])

  const absoluteInboundUrl = useMemo(() => {
    if (!trigger) return ''
    const base = publicIngress?.url || (typeof window !== 'undefined' ? window.location.origin : '')
    return `${base}${trigger.inbound_url}`
  }, [publicIngress, trigger])

  const copyInboundUrl = async () => {
    if (!absoluteInboundUrl) return
    await navigator.clipboard.writeText(absoluteInboundUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const events = useMemo(
    () => (eventsPage?.items || []).filter((event) => event.channel_instance_id === triggerId),
    [eventsPage, triggerId],
  )

  const saveCriteria = async () => {
    if (!trigger) return
    setSaving(true)
    setError(null)
    try {
      const triggerCriteria = parseCriteriaText(criteriaText)
      const updated = await api.updateWebhookIntegration(trigger.id, { trigger_criteria: triggerCriteria })
      setTrigger(updated)
      setCriteriaText(formatCriteriaText(updated.trigger_criteria))
      setSuccess('Criteria saved')
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to save criteria'))
    } finally {
      setSaving(false)
    }
  }

  const toggleActive = async () => {
    if (!trigger) return
    setSaving(true)
    setError(null)
    try {
      const updated = await api.updateWebhookIntegration(trigger.id, { is_active: !trigger.is_active })
      setTrigger(updated)
      setSuccess(updated.is_active ? 'Webhook trigger resumed' : 'Webhook trigger paused')
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to update webhook trigger'))
    } finally {
      setSaving(false)
    }
  }

  const deleteTrigger = async () => {
    if (!trigger) return
    if (!confirm(`Delete webhook trigger "${trigger.integration_name}"? This cannot be undone.`)) return
    setSaving(true)
    setError(null)
    try {
      await api.deleteWebhookIntegration(trigger.id)
      router.push('/hub?tab=communication')
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to delete webhook trigger'))
      setSaving(false)
    }
  }

  if (!hasValidId) return null

  return (
    <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8 animate-fade-in">
      <div className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-3 text-sm text-tsushin-slate">
            <Link href="/hub?tab=communication" className="hover:text-white">Hub</Link>
            <span>/</span>
            <span>Webhook Trigger</span>
          </div>
          <h1 className="text-3xl font-display font-bold text-white">
            {trigger?.integration_name || `Webhook Trigger #${triggerId}`}
          </h1>
          <p className="mt-2 max-w-3xl text-sm text-tsushin-slate">
            Signed HTTP trigger detail using the canonical v0.7.0 trigger API.
          </p>
        </div>
        <button
          type="button"
          onClick={loadTrigger}
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
          Loading webhook trigger...
        </div>
      ) : !trigger ? (
        <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/50 p-10 text-center">
          <AlertTriangleIcon size={28} className="mx-auto mb-3 text-yellow-300" />
          <div className="text-white">Webhook trigger not found</div>
        </div>
      ) : (
        <div className="space-y-6">
          {!canWriteHub && (
            <div className="rounded-xl border border-yellow-500/30 bg-yellow-500/10 p-4 text-sm text-yellow-100">
              Read-only view. Your role does not have <code className="font-mono">hub.write</code>.
            </div>
          )}

          <div className="grid gap-4 md:grid-cols-4">
            <Field label="Status" value={<span className={`rounded-full border px-2.5 py-1 text-xs ${statusClass(trigger)}`}>{trigger.is_active ? trigger.status : 'paused'}</span>} />
            <Field label="Health" value={trigger.health_status || 'unknown'} />
            <Field
              label="Routing"
              value={
                <DefaultAgentChip
                  triggerKind="webhook"
                  triggerId={trigger.id}
                  agent={{ id: trigger.default_agent_id ?? null, name: trigger.default_agent_name ?? null }}
                  canEdit={canWriteHub}
                  onUpdate={(next) =>
                    setTrigger((current) => (current ? { ...current, ...next } : current))
                  }
                />
              }
            />
            <Field label="Last activity" value={trigger.last_activity_at ? formatRelative(trigger.last_activity_at) : 'No activity'} />
          </div>

          {/*
            Circuit breaker + Rate limit used to live in the KPI strip;
            Wave 1 moves them into a secondary pill row so the standardized
            Status / Health / Routing / Last Activity layout is consistent
            across all 5 trigger kinds. Wave 3 will fold these into the
            Source section as proper sub-pills.
          */}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="rounded-full border border-tsushin-border bg-black/20 px-2.5 py-1 text-tsushin-fog">
              Circuit breaker: <span className="text-white">{trigger.circuit_breaker_state}</span>
            </span>
            <span className="rounded-full border border-tsushin-border bg-black/20 px-2.5 py-1 text-tsushin-fog">
              Rate limit: <span className="text-white">{trigger.rate_limit_rpm} req/min</span>
            </span>
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
            <>
              <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
                <h2 className="flex items-center gap-2 text-lg font-semibold text-white">
                  <WebhookIcon size={18} /> Inbound Endpoint
                </h2>
                <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center">
                  <code className="min-w-0 flex-1 break-all rounded-lg border border-tsushin-border bg-black/30 p-3 text-xs text-cyan-200">
                    {absoluteInboundUrl}
                  </code>
                  <button
                    type="button"
                    onClick={copyInboundUrl}
                    className="inline-flex items-center justify-center gap-2 rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-4 py-2 text-sm text-cyan-200 hover:text-white"
                  >
                    <CopyIcon size={16} />
                    {copied ? 'Copied' : 'Copy'}
                  </button>
                </div>
                {publicIngress?.warning && (
                  <p className="mt-2 text-xs text-yellow-200">{publicIngress.warning}</p>
                )}
              </div>

              <div className="grid gap-6 lg:grid-cols-2">
                <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
                  <h2 className="text-lg font-semibold text-white">Security</h2>
                  <div className="mt-4 space-y-4 text-sm">
                    <div>
                      <div className="text-xs text-tsushin-slate">Secret preview</div>
                      <code className="mt-1 block rounded-lg border border-tsushin-border bg-black/30 p-3 text-xs text-cyan-200">
                        {trigger.api_secret_preview}
                      </code>
                    </div>
                    <div>
                      <div className="text-xs text-tsushin-slate">IP allowlist</div>
                      <div className="mt-1 flex flex-wrap gap-2">
                        {(trigger.ip_allowlist || []).length > 0 ? trigger.ip_allowlist!.map(cidr => (
                          <span key={cidr} className="rounded-full border border-tsushin-border bg-black/20 px-2.5 py-1 text-xs text-tsushin-fog">
                            {cidr}
                          </span>
                        )) : <span className="text-tsushin-slate">Any source allowed by upstream network policy</span>}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-tsushin-slate">Max payload</div>
                      <div className="mt-1 text-white">{trigger.max_payload_bytes.toLocaleString()} bytes</div>
                    </div>
                  </div>
                </div>

                <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
                  <h2 className="flex items-center gap-2 text-lg font-semibold text-white">
                    <ClockIcon size={18} /> Callback and Health
                  </h2>
                  <div className="mt-4 space-y-4 text-sm">
                    <div>
                      <div className="text-xs text-tsushin-slate">Callback</div>
                      <div className="mt-1 text-white">{trigger.callback_enabled ? (trigger.callback_url || 'Enabled without URL') : 'Disabled'}</div>
                    </div>
                    <div>
                      <div className="text-xs text-tsushin-slate">Health</div>
                      <div className="mt-1 text-white">{trigger.health_status}</div>
                      <div className="text-xs text-tsushin-slate">{trigger.last_health_check ? `Checked ${formatRelative(trigger.last_health_check)}` : 'No health check recorded'}</div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <div className="text-xs text-tsushin-slate">Created</div>
                        <div className="mt-1 text-white">{formatDateTime(trigger.created_at)}</div>
                      </div>
                      <div>
                        <div className="text-xs text-tsushin-slate">Updated</div>
                        <div className="mt-1 text-white">{trigger.updated_at ? formatDateTime(trigger.updated_at) : '-'}</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}

          {activeTab === 'criteria' && (
            <div>
              <CriteriaBuilder
                kind="webhook"
                value={criteriaText}
                onChange={setCriteriaText}
                disabled={!canWriteHub || saving}
                readOnlyReason={!canWriteHub ? 'Read-only view. Your role can view criteria but cannot change it.' : null}
                onTest={(triggerCriteria, payload) => api.testWebhookCriteria(trigger.id, { payload, trigger_criteria: triggerCriteria })}
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
          )}

          {activeTab === 'events' && (
            <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
              <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-white">
                <BellIcon size={18} /> Recent wake events
              </h2>
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
                      </tr>
                    </thead>
                    <tbody>
                      {events.map((event) => (
                        <tr key={event.id} className="border-b border-tsushin-border/60">
                          <td className="px-3 py-2 text-white">#{event.id}<div className="text-xs text-tsushin-slate">{event.event_type}</div></td>
                          <td className="px-3 py-2 text-white">{event.status}</td>
                          <td className="px-3 py-2 text-tsushin-slate">{formatRelative(event.occurred_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {activeTab === 'danger' && (
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
          )}
        </div>
      )}
    </div>
  )
}
