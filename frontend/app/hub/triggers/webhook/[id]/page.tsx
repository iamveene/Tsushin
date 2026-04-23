'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { api, type PublicIngressInfo, type WebhookIntegration } from '@/lib/client'
import { formatDateTime, formatRelative } from '@/lib/dateUtils'
import { AlertTriangleIcon, ClockIcon, CopyIcon, RefreshIcon, WebhookIcon } from '@/components/ui/icons'

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
  const [trigger, setTrigger] = useState<WebhookIntegration | null>(null)
  const [publicIngress, setPublicIngress] = useState<PublicIngressInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const loadTrigger = useCallback(async () => {
    if (!hasValidId) return
    setLoading(true)
    setError(null)
    try {
      const [triggerData, ingressData] = await Promise.all([
        api.getWebhookIntegration(triggerId),
        api.getMyPublicIngress().catch(() => null),
      ])
      setTrigger(triggerData)
      setPublicIngress(ingressData)
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
    // eslint-disable-next-line react-hooks/set-state-in-effect
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
          disabled={loading}
          className="inline-flex items-center justify-center gap-2 rounded-lg border border-tsushin-border bg-tsushin-surface px-4 py-2 text-sm text-tsushin-fog hover:text-white disabled:opacity-50"
        >
          <RefreshIcon size={16} />
          Refresh
        </button>
      </div>

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
          <div className="grid gap-4 md:grid-cols-4">
            <Field label="Status" value={<span className={`rounded-full border px-2.5 py-1 text-xs ${statusClass(trigger)}`}>{trigger.is_active ? trigger.status : 'paused'}</span>} />
            <Field label="Circuit breaker" value={trigger.circuit_breaker_state} />
            <Field label="Rate limit" value={`${trigger.rate_limit_rpm} req/min`} />
            <Field label="Last activity" value={trigger.last_activity_at ? formatRelative(trigger.last_activity_at) : 'No activity'} />
          </div>

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
        </div>
      )}
    </div>
  )
}
