'use client'

/**
 * Ingress Override (Advanced) — v0.6.1.
 *
 * Renamed from "Public Base URL" and demoted from the default-visible primary
 * setup field to a collapsible override. The platform-managed Remote Access
 * tunnel is now the default ingress source; this card is for tenants who need
 * to route Slack/Discord/webhook callbacks through a different URL (their own
 * cloudflared, corporate reverse proxy, branded domain, etc.).
 *
 * Display logic:
 *   - Always shows the current resolver output at the top ("Currently used: X
 *     via platform tunnel / override / dev").
 *   - The override input lives inside a <details> block that auto-expands
 *     when source === 'none' (tenant has no ingress and would otherwise be
 *     stuck) or when an override is already stored.
 *   - When the override is saved but invalid (DNS / format fails), a warning
 *     is surfaced above the input so the tenant knows what's broken.
 */

import { useEffect, useState } from 'react'
import { api, type PublicIngressSource } from '@/lib/client'

interface Props {
  canEdit: boolean
}

const SOURCE_LABELS: Record<PublicIngressSource, string> = {
  override: 'tenant override',
  tunnel: 'platform tunnel',
  dev: 'dev environment',
  none: 'not configured',
}

export default function PublicBaseUrlCard({ canEdit }: Props) {
  const [value, setValue] = useState('')
  const [resolvedUrl, setResolvedUrl] = useState<string | null>(null)
  const [source, setSource] = useState<PublicIngressSource>('none')
  const [resolverWarning, setResolverWarning] = useState<string | null>(null)
  const [overrideSaved, setOverrideSaved] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)

  const loadIngress = () => {
    setLoading(true)
    return api
      .getMyPublicIngress()
      .then(info => {
        setResolvedUrl(info.url)
        setSource(info.source)
        setResolverWarning(info.warning)
        setOverrideSaved(info.override_url)
        setValue(info.override_url || '')
      })
      .catch(err => setError(err?.message || 'Failed to load ingress info'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadIngress()
  }, [])

  const trimmed = value.trim()
  const isHttpShape =
    trimmed === '' || trimmed.startsWith('https://') || trimmed.startsWith('http://')

  const handleSave = async () => {
    if (!isHttpShape) return
    setSaving(true)
    setError(null)
    setStatusMessage(null)
    try {
      const next = trimmed === '' ? null : trimmed.replace(/\/+$/, '')
      await api.updateMyTenantSettings({ public_base_url: next })
      await loadIngress()
      setStatusMessage(next ? 'Override saved' : 'Override cleared')
    } catch (err: any) {
      setError(err?.message || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const hasOverrideSaved = !!overrideSaved
  const detailsOpen = source === 'none' || hasOverrideSaved

  return (
    <div className="card p-4 border border-tsushin-border/60">
      <div className="flex flex-col gap-3">
        <div>
          <h4 className="text-sm font-semibold text-white">Ingress Override (Advanced)</h4>
          <p className="text-xs text-tsushin-slate">
            The Slack HTTP Events, Discord Interactions, and Webhook channels use the
            platform-managed Remote Access tunnel by default. Set an override here only
            when you need callbacks routed through a different public URL (e.g. your own
            cloudflared, a corporate reverse proxy, or a branded domain).
          </p>
        </div>

        <div className="rounded bg-tsushin-elevated/40 border border-tsushin-border/50 p-3 text-xs">
          {loading ? (
            <span className="text-tsushin-slate">Loading…</span>
          ) : source === 'none' ? (
            <span className="text-amber-200">
              No public ingress available. Ask a global admin to enable Remote Access for this tenant, or configure an override below.
            </span>
          ) : (
            <div className="flex flex-col gap-1">
              <span className="text-tsushin-slate">
                Currently resolved:{' '}
                <code className="px-1 bg-tsushin-elevated rounded text-emerald-300 break-all">
                  {resolvedUrl || '(invalid override, not in use)'}
                </code>{' '}
                <span className="text-tsushin-fog">via {SOURCE_LABELS[source]}</span>
              </span>
              {resolverWarning && (
                <span className="text-amber-200">Warning: {resolverWarning}</span>
              )}
            </div>
          )}
        </div>

        <details open={detailsOpen} className="group">
          <summary className="cursor-pointer text-xs font-medium text-teal-300 hover:text-teal-200 select-none">
            {hasOverrideSaved ? 'Edit override URL' : 'Configure override URL'}
          </summary>

          <div className="flex flex-col gap-2 mt-3">
            <div className="flex flex-wrap items-center gap-3">
              <input
                type="text"
                value={value}
                placeholder="https://your-tunnel.trycloudflare.com"
                onChange={(e) => { setValue(e.target.value); setStatusMessage(null) }}
                className="input flex-1 min-w-[280px] text-sm font-mono"
                disabled={!canEdit || saving || loading}
              />
              <button
                onClick={handleSave}
                className="px-4 py-2 bg-teal-600/20 text-teal-300 border border-teal-600/50 rounded text-xs disabled:opacity-50"
                disabled={!canEdit || saving || loading || !isHttpShape || trimmed === (overrideSaved || '')}
              >
                {saving ? 'Saving...' : 'Save override'}
              </button>
            </div>

            {!isHttpShape && (
              <p className="text-xs text-amber-300">
                Must start with <code className="px-1 bg-tsushin-elevated rounded">https://</code> (or{' '}
                <code className="px-1 bg-tsushin-elevated rounded">http://</code> when the dev env var is set).
              </p>
            )}

            {error && <p className="text-xs text-red-400">{error}</p>}
            {statusMessage && <p className="text-xs text-emerald-300">{statusMessage}</p>}

            {!canEdit && (
              <p className="text-xs text-amber-300">
                You need <code className="px-1 bg-tsushin-elevated rounded">org.settings.write</code> permission to edit this value.
              </p>
            )}

            {overrideSaved && (
              <p className="text-xs text-tsushin-slate">
                Override stored:{' '}
                <code className="px-1 bg-tsushin-elevated rounded text-tsushin-fog break-all">{overrideSaved}</code>
              </p>
            )}
          </div>
        </details>
      </div>
    </div>
  )
}
