'use client'

/**
 * Remote Access (Cloudflare Tunnel) Page — Global Admin Only
 * v0.6.0
 *
 * Lets the global admin configure the system-wide Cloudflare tunnel, monitor
 * its lifecycle, toggle per-tenant entitlement, and surface the Google OAuth
 * callback URIs that must be whitelisted in Google Cloud Console.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { useRequireGlobalAdmin } from '@/contexts/AuthContext'
import {
  api,
  RemoteAccessCallbacks,
  RemoteAccessConfig,
  RemoteAccessConfigUpdate,
  RemoteAccessMode,
  RemoteAccessProtocol,
  RemoteAccessState,
  RemoteAccessStatus,
  RemoteAccessTenantRow,
} from '@/lib/client'
import { GlobeIcon } from '@/components/ui/icons'

const STATUS_POLL_INTERVAL_MS = 5000
const STATUS_REFRESH_DELAY_MS = 1500

const HOSTNAME_REGEX =
  /^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$/

const STATE_LABEL: Record<RemoteAccessState, string> = {
  stopped: 'Stopped',
  starting: 'Starting',
  running: 'Running',
  stopping: 'Stopping',
  crashed: 'Crashed',
  error: 'Error',
  unavailable: 'Unavailable',
}

const STATE_COLOR_CLASSES: Record<RemoteAccessState, string> = {
  stopped: 'bg-tsushin-ink text-tsushin-slate border border-tsushin-border',
  starting: 'bg-yellow-500/20 text-yellow-300 border border-yellow-500/40 animate-pulse',
  running: 'bg-green-500/20 text-green-300 border border-green-500/40',
  stopping: 'bg-yellow-500/20 text-yellow-300 border border-yellow-500/40 animate-pulse',
  crashed: 'bg-red-500/20 text-red-300 border border-red-500/40',
  error: 'bg-red-500/20 text-red-300 border border-red-500/40',
  unavailable: 'bg-orange-500/20 text-orange-300 border border-orange-500/40',
}

type FormDraft = {
  mode: RemoteAccessMode
  enabled: boolean
  autostart: boolean
  protocol: RemoteAccessProtocol
  tunnel_hostname: string
  tunnel_dns_target: string
  target_url: string
  tunnel_token: string
  clear_token: boolean
}

function buildDraftFromConfig(cfg: RemoteAccessConfig | null): FormDraft {
  return {
    mode: cfg?.mode ?? 'quick',
    enabled: cfg?.enabled ?? false,
    autostart: cfg?.autostart ?? false,
    protocol: cfg?.protocol ?? 'auto',
    tunnel_hostname: cfg?.tunnel_hostname ?? '',
    tunnel_dns_target: cfg?.tunnel_dns_target ?? '',
    target_url: cfg?.target_url ?? 'http://frontend:3030',
    tunnel_token: '',
    clear_token: false,
  }
}

function formatRelative(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    const date = new Date(iso)
    const now = Date.now()
    const diff = Math.round((now - date.getTime()) / 1000)
    if (diff < 60) return `${diff}s ago`
    if (diff < 3600) return `${Math.round(diff / 60)}m ago`
    if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
    return date.toLocaleDateString()
  } catch {
    return iso
  }
}

function getErrorDetail(err: unknown): string {
  if (err instanceof Error) return err.message
  if (typeof err === 'string') return err
  return 'Unexpected error'
}

export default function RemoteAccessPage() {
  const { user, loading: authLoading } = useRequireGlobalAdmin()

  const [status, setStatus] = useState<RemoteAccessStatus | null>(null)
  const [config, setConfig] = useState<RemoteAccessConfig | null>(null)
  const [tenants, setTenants] = useState<RemoteAccessTenantRow[]>([])
  const [callbacks, setCallbacks] = useState<RemoteAccessCallbacks | null>(null)

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [acting, setActing] = useState<null | 'start' | 'stop' | 'restart'>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [startMode, setStartMode] = useState<RemoteAccessMode>('quick')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [hostnameError, setHostnameError] = useState<string | null>(null)
  const [togglingTenants, setTogglingTenants] = useState<Set<string>>(new Set())
  const [copiedKey, setCopiedKey] = useState<string | null>(null)

  const [formDraft, setFormDraft] = useState<FormDraft>(buildDraftFromConfig(null))

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const cancelledRef = useRef(false)

  const hostnameInvalid = useMemo(() => {
    if (formDraft.mode !== 'named') return false
    if (!formDraft.tunnel_hostname) return false
    return !HOSTNAME_REGEX.test(formDraft.tunnel_hostname.trim().toLowerCase())
  }, [formDraft.mode, formDraft.tunnel_hostname])

  const transitioning = status?.state === 'starting' || status?.state === 'stopping'

  // --------------------------------------------------------------------------
  // Data loading
  // --------------------------------------------------------------------------
  const loadAll = useCallback(async () => {
    try {
      const [s, c, t, cb] = await Promise.all([
        api.getRemoteAccessStatus(),
        api.getRemoteAccessConfig(),
        api.listRemoteAccessTenants(),
        api.getRemoteAccessCallbacks(),
      ])
      if (cancelledRef.current) return
      setStatus(s)
      setConfig(c)
      setFormDraft(buildDraftFromConfig(c))
      setStartMode(c.mode)
      setTenants(t)
      setCallbacks(cb)
    } catch (err) {
      if (cancelledRef.current) return
      setError(getErrorDetail(err))
    } finally {
      if (!cancelledRef.current) setLoading(false)
    }
  }, [])

  const refreshStatusOnly = useCallback(async () => {
    try {
      const s = await api.getRemoteAccessStatus()
      if (!cancelledRef.current) setStatus(s)
    } catch {
      // Silent — don't blank the UI on transient poll failure
    }
  }, [])

  useEffect(() => {
    cancelledRef.current = false
    if (!authLoading && user) {
      loadAll()
    }
    return () => {
      cancelledRef.current = true
    }
  }, [authLoading, user, loadAll])

  // Status poll every 5s while visible
  useEffect(() => {
    if (authLoading || !user) return
    const startPoll = () => {
      if (pollRef.current) return
      pollRef.current = setInterval(() => {
        if (document.visibilityState !== 'visible') return
        refreshStatusOnly()
      }, STATUS_POLL_INTERVAL_MS)
    }
    const stopPoll = () => {
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
    const onVisibility = () => {
      if (document.visibilityState === 'visible') {
        refreshStatusOnly()
        startPoll()
      } else {
        stopPoll()
      }
    }
    startPoll()
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      stopPoll()
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [authLoading, user, refreshStatusOnly])

  // --------------------------------------------------------------------------
  // Handlers
  // --------------------------------------------------------------------------
  const showSuccess = (msg: string) => {
    setSuccess(msg)
    setError(null)
    setTimeout(() => setSuccess(null), 3000)
  }

  const handleCopy = async (text: string, key: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedKey(key)
      setTimeout(() => setCopiedKey(null), 2000)
    } catch {
      setError('Clipboard access denied')
    }
  }

  const handleStart = async () => {
    setError(null)
    setActing('start')
    try {
      const s = await api.startRemoteAccess(startMode)
      setStatus(s)
      showSuccess(`Tunnel starting (${startMode})`)
      setTimeout(refreshStatusOnly, STATUS_REFRESH_DELAY_MS)
    } catch (err) {
      setError(getErrorDetail(err))
    } finally {
      setActing(null)
    }
  }

  const handleStop = async () => {
    setError(null)
    setActing('stop')
    try {
      const s = await api.stopRemoteAccess()
      setStatus(s)
      showSuccess('Tunnel stopped')
      setTimeout(refreshStatusOnly, STATUS_REFRESH_DELAY_MS)
    } catch (err) {
      setError(getErrorDetail(err))
    } finally {
      setActing(null)
    }
  }

  const handleRestart = async () => {
    setError(null)
    setActing('restart')
    try {
      await api.stopRemoteAccess()
      const s = await api.startRemoteAccess(status?.mode ?? startMode)
      setStatus(s)
      showSuccess('Tunnel restarted')
      setTimeout(refreshStatusOnly, STATUS_REFRESH_DELAY_MS)
    } catch (err) {
      setError(getErrorDetail(err))
    } finally {
      setActing(null)
    }
  }

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setHostnameError(null)

    if (formDraft.mode === 'named') {
      const host = formDraft.tunnel_hostname.trim().toLowerCase()
      if (!host) {
        setHostnameError('Hostname is required in named mode')
        return
      }
      if (!HOSTNAME_REGEX.test(host)) {
        setHostnameError('Must be a fully qualified domain (e.g. tsushin.archsec.io)')
        return
      }
    }

    setSaving(true)
    try {
      const payload: RemoteAccessConfigUpdate = {
        enabled: formDraft.enabled,
        mode: formDraft.mode,
        autostart: formDraft.autostart,
        protocol: formDraft.protocol,
        tunnel_hostname: formDraft.tunnel_hostname.trim() || null,
        tunnel_dns_target: formDraft.tunnel_dns_target.trim() || null,
        target_url: formDraft.target_url.trim() || 'http://frontend:3030',
        expected_updated_at: config?.updated_at ?? null,
      }
      if (formDraft.clear_token) {
        payload.clear_tunnel_token = true
      } else if (formDraft.tunnel_token) {
        payload.tunnel_token = formDraft.tunnel_token
      }

      const next = await api.updateRemoteAccessConfig(payload)
      setConfig(next)
      setFormDraft(buildDraftFromConfig(next))
      const cb = await api.getRemoteAccessCallbacks()
      setCallbacks(cb)
      showSuccess('Configuration saved')
      refreshStatusOnly()
    } catch (err) {
      setError(getErrorDetail(err))
    } finally {
      setSaving(false)
    }
  }

  const handleToggleTenant = async (tenant: RemoteAccessTenantRow) => {
    const next = !tenant.remote_access_enabled
    const snapshot = tenants
    setTogglingTenants((prev) => {
      const copy = new Set(prev)
      copy.add(tenant.id)
      return copy
    })
    // Optimistic update
    setTenants((cur) =>
      cur.map((t) =>
        t.id === tenant.id
          ? {
              ...t,
              remote_access_enabled: next,
              last_changed_at: new Date().toISOString(),
              last_changed_by_email: user?.email ?? t.last_changed_by_email,
            }
          : t
      )
    )
    try {
      const updated = await api.setTenantRemoteAccess(tenant.id, next)
      setTenants((cur) => cur.map((t) => (t.id === tenant.id ? updated : t)))
      showSuccess(
        `Remote access ${next ? 'enabled' : 'disabled'} for ${tenant.name}`
      )
    } catch (err) {
      setTenants(snapshot)
      setError(`Failed to update ${tenant.name}: ${getErrorDetail(err)}`)
    } finally {
      setTogglingTenants((prev) => {
        const copy = new Set(prev)
        copy.delete(tenant.id)
        return copy
      })
    }
  }

  // --------------------------------------------------------------------------
  // Render
  // --------------------------------------------------------------------------
  if (authLoading || loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-tsushin-slate">Loading...</div>
      </div>
    )
  }
  if (!user) return null

  const currentState: RemoteAccessState = status?.state ?? 'unavailable'
  const namedReady =
    (config?.tunnel_token_configured ?? false) && !!config?.tunnel_hostname

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="flex items-start justify-between mb-8">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-3xl font-bold text-white">Remote Access</h1>
              <span className="px-3 py-1 bg-purple-100 dark:bg-purple-900/30 text-purple-900 dark:text-purple-200 text-sm font-semibold rounded-full inline-flex items-center gap-1">
                <GlobeIcon size={14} /> Global Admin
              </span>
            </div>
            <p className="text-tsushin-slate">
              Expose Tsushin through a Cloudflare Tunnel and control per-tenant access.
            </p>
          </div>
          <Link
            href="/system/tenants"
            className="text-sm text-teal-400 hover:underline"
          >
            ← Tenants
          </Link>
        </div>

        {/* Global feedback */}
        {error && (
          <div
            role="alert"
            className="mb-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 flex items-start justify-between gap-4"
          >
            <p className="text-sm text-red-700 dark:text-red-300 whitespace-pre-wrap break-words">
              {error}
            </p>
            <button
              onClick={() => setError(null)}
              className="text-red-600 dark:text-red-400 hover:underline text-sm"
              aria-label="Dismiss error"
            >
              ✕
            </button>
          </div>
        )}
        {success && (
          <div
            role="status"
            className="mb-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4"
          >
            <p className="text-sm text-green-700 dark:text-green-300">{success}</p>
          </div>
        )}

        {/* Card A — Status */}
        <div className="bg-tsushin-surface rounded-xl border border-tsushin-border p-6 mb-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h2 className="text-lg font-semibold text-white mb-1">Tunnel Status</h2>
              <p className="text-sm text-tsushin-slate">
                Live state of the cloudflared subprocess in this backend container.
              </p>
            </div>
            <div aria-live="polite">
              <span
                className={`px-3 py-1 rounded-full text-xs font-semibold ${STATE_COLOR_CLASSES[currentState]}`}
              >
                {STATE_LABEL[currentState]}
              </span>
            </div>
          </div>

          {status?.message && (
            <p className="text-xs text-tsushin-slate italic mb-4">{status.message}</p>
          )}

          <dl className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm mb-4">
            <div>
              <dt className="text-tsushin-slate text-xs uppercase">Public URL</dt>
              <dd className="flex items-center gap-2">
                {status?.public_url ? (
                  <>
                    <code className="text-teal-300 break-all">{status.public_url}</code>
                    <button
                      onClick={() => handleCopy(status.public_url!, 'public_url')}
                      className="text-xs text-tsushin-slate hover:text-teal-400"
                      aria-label="Copy public URL"
                    >
                      {copiedKey === 'public_url' ? 'Copied' : 'Copy'}
                    </button>
                  </>
                ) : (
                  <span className="text-tsushin-slate">—</span>
                )}
              </dd>
            </div>
            <div>
              <dt className="text-tsushin-slate text-xs uppercase">Mode</dt>
              <dd className="text-white">{status?.mode ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-tsushin-slate text-xs uppercase">PID</dt>
              <dd className="text-white">{status?.pid ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-tsushin-slate text-xs uppercase">Started</dt>
              <dd className="text-white" title={status?.started_at ?? ''}>
                {formatRelative(status?.started_at)}
              </dd>
            </div>
            <div>
              <dt className="text-tsushin-slate text-xs uppercase">Restart attempts</dt>
              <dd className="text-white">{status?.restart_attempts ?? 0}</dd>
            </div>
            <div>
              <dt className="text-tsushin-slate text-xs uppercase">Binary</dt>
              <dd className="text-white">
                {status?.binary_available ? (
                  <code className="text-green-300 text-xs">{status?.cloudflared_path}</code>
                ) : (
                  <span className="text-red-400">Not found</span>
                )}
              </dd>
            </div>
          </dl>

          {status?.last_error && (
            <div className="mb-4 p-3 rounded bg-red-500/10 border border-red-500/30 text-xs text-red-300">
              <strong>Last error:</strong> {status.last_error}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <select
                value={startMode}
                onChange={(e) => setStartMode(e.target.value as RemoteAccessMode)}
                className="px-3 py-2 bg-tsushin-ink border border-tsushin-border rounded-md text-white text-sm"
                disabled={transitioning || !status?.binary_available}
                aria-label="Tunnel mode for start"
              >
                <option value="quick">Quick</option>
                <option value="named" disabled={!namedReady}>
                  Named {namedReady ? '' : '(configure below)'}
                </option>
              </select>
              <button
                onClick={handleStart}
                disabled={
                  acting !== null ||
                  !status?.binary_available ||
                  status?.state === 'running' ||
                  status?.state === 'starting'
                }
                className="btn-primary px-4 py-2 rounded-md text-sm disabled:opacity-50"
              >
                {acting === 'start' ? 'Starting…' : 'Start'}
              </button>
            </div>
            <button
              onClick={handleStop}
              disabled={
                acting !== null ||
                !(
                  status?.state === 'running' ||
                  status?.state === 'starting' ||
                  status?.state === 'crashed' ||
                  status?.state === 'error'
                )
              }
              className="px-4 py-2 bg-tsushin-ink border border-red-500/40 text-red-300 hover:bg-red-500/10 rounded-md text-sm disabled:opacity-50"
            >
              {acting === 'stop' ? 'Stopping…' : 'Stop'}
            </button>
            <button
              onClick={handleRestart}
              disabled={acting !== null || status?.state !== 'running'}
              className="px-4 py-2 bg-tsushin-ink border border-tsushin-border text-white rounded-md text-sm disabled:opacity-50"
            >
              {acting === 'restart' ? 'Restarting…' : 'Restart'}
            </button>
          </div>
        </div>

        {/* Card B — Config */}
        <form
          onSubmit={handleSaveConfig}
          className="bg-tsushin-surface rounded-xl border border-tsushin-border p-6 mb-6"
        >
          <h2 className="text-lg font-semibold text-white mb-1">Tunnel Configuration</h2>
          <p className="text-sm text-tsushin-slate mb-6">
            Credentials are encrypted at rest. The tunnel token is write-only.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {/* Enabled */}
            <div className="flex items-center gap-3">
              <input
                id="cfg-enabled"
                type="checkbox"
                checked={formDraft.enabled}
                onChange={(e) =>
                  setFormDraft({ ...formDraft, enabled: e.target.checked })
                }
                className="h-4 w-4"
              />
              <label htmlFor="cfg-enabled" className="text-sm text-white">
                Feature enabled globally
              </label>
            </div>

            {/* Autostart */}
            <div className="flex items-center gap-3">
              <input
                id="cfg-autostart"
                type="checkbox"
                checked={formDraft.autostart}
                onChange={(e) =>
                  setFormDraft({ ...formDraft, autostart: e.target.checked })
                }
                className="h-4 w-4"
                disabled={!formDraft.enabled}
              />
              <label htmlFor="cfg-autostart" className="text-sm text-white">
                Auto-start on boot (with supervisor)
              </label>
            </div>

            {/* Mode */}
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-white mb-2">Mode</label>
              <div className="flex gap-4">
                {(['quick', 'named'] as RemoteAccessMode[]).map((m) => (
                  <label key={m} className="flex items-center gap-2 text-sm text-white">
                    <input
                      type="radio"
                      name="mode"
                      value={m}
                      checked={formDraft.mode === m}
                      onChange={() => setFormDraft({ ...formDraft, mode: m })}
                    />
                    <span className="capitalize">{m}</span>
                    {m === 'quick' && (
                      <span className="text-xs text-tsushin-slate">(trycloudflare.com)</span>
                    )}
                  </label>
                ))}
              </div>
            </div>

            {formDraft.mode === 'named' && (
              <>
                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-white mb-2">
                    Tunnel hostname
                  </label>
                  <input
                    type="text"
                    value={formDraft.tunnel_hostname}
                    onChange={(e) =>
                      setFormDraft({ ...formDraft, tunnel_hostname: e.target.value })
                    }
                    onBlur={() => {
                      if (
                        formDraft.tunnel_hostname &&
                        !HOSTNAME_REGEX.test(formDraft.tunnel_hostname.trim().toLowerCase())
                      ) {
                        setHostnameError('Must be a fully qualified domain (e.g. tsushin.archsec.io)')
                      } else {
                        setHostnameError(null)
                      }
                    }}
                    placeholder="tsushin.archsec.io"
                    className={`w-full px-3 py-2 bg-tsushin-ink border rounded-md text-white focus:ring-2 focus:ring-teal-500 ${
                      hostnameError || hostnameInvalid
                        ? 'border-red-500/60'
                        : 'border-tsushin-border'
                    }`}
                    aria-invalid={hostnameError || hostnameInvalid ? 'true' : 'false'}
                    aria-describedby="hostname-err"
                  />
                  {(hostnameError || hostnameInvalid) && (
                    <p id="hostname-err" className="mt-1 text-xs text-red-400">
                      {hostnameError ??
                        'Must be a fully qualified domain (e.g. tsushin.archsec.io)'}
                    </p>
                  )}
                </div>

                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-white mb-2">
                    DNS target <span className="text-tsushin-slate">(optional, informational)</span>
                  </label>
                  <input
                    type="text"
                    value={formDraft.tunnel_dns_target}
                    onChange={(e) =>
                      setFormDraft({ ...formDraft, tunnel_dns_target: e.target.value })
                    }
                    placeholder="e.g. abcd1234.cfargotunnel.com"
                    className="w-full px-3 py-2 bg-tsushin-ink border border-tsushin-border rounded-md text-white focus:ring-2 focus:ring-teal-500"
                  />
                </div>

                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-white mb-2">
                    Tunnel token
                  </label>
                  <input
                    type="password"
                    autoComplete="off"
                    value={formDraft.tunnel_token}
                    onChange={(e) =>
                      setFormDraft({
                        ...formDraft,
                        tunnel_token: e.target.value,
                        clear_token: false,
                      })
                    }
                    placeholder={
                      config?.tunnel_token_configured
                        ? '●●●●●● (configured — leave blank to keep existing)'
                        : 'Paste Cloudflare tunnel token'
                    }
                    className="w-full px-3 py-2 bg-tsushin-ink border border-tsushin-border rounded-md text-white focus:ring-2 focus:ring-teal-500 font-mono text-xs"
                  />
                  {config?.tunnel_token_configured && (
                    <button
                      type="button"
                      onClick={() =>
                        setFormDraft({
                          ...formDraft,
                          tunnel_token: '',
                          clear_token: true,
                        })
                      }
                      className="mt-1 text-xs text-red-400 hover:underline"
                    >
                      Clear existing token
                    </button>
                  )}
                  {formDraft.clear_token && (
                    <p className="mt-1 text-xs text-yellow-300">
                      Token will be cleared on save.
                    </p>
                  )}
                </div>
              </>
            )}

            {/* Protocol */}
            <div>
              <label className="block text-sm font-medium text-white mb-2">Protocol</label>
              <select
                value={formDraft.protocol}
                onChange={(e) =>
                  setFormDraft({
                    ...formDraft,
                    protocol: e.target.value as RemoteAccessProtocol,
                  })
                }
                className="w-full px-3 py-2 bg-tsushin-ink border border-tsushin-border rounded-md text-white"
              >
                <option value="auto">auto</option>
                <option value="http2">http2</option>
                <option value="quic">quic</option>
              </select>
            </div>

            {/* Advanced */}
            <div className="md:col-span-2">
              <button
                type="button"
                onClick={() => setShowAdvanced((s) => !s)}
                className="text-sm text-teal-400 hover:underline"
              >
                {showAdvanced ? '▾' : '▸'} Advanced
              </button>
              {showAdvanced && (
                <div className="mt-3">
                  <label className="block text-sm font-medium text-white mb-2">
                    Target URL
                  </label>
                  <input
                    type="text"
                    value={formDraft.target_url}
                    onChange={(e) =>
                      setFormDraft({ ...formDraft, target_url: e.target.value })
                    }
                    placeholder="http://frontend:3030"
                    className="w-full px-3 py-2 bg-tsushin-ink border border-tsushin-border rounded-md text-white font-mono text-xs"
                  />
                  <p className="mt-1 text-xs text-tsushin-slate">
                    Only change for non-standard deployments.
                  </p>
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center justify-end gap-3 mt-6 pt-4 border-t border-tsushin-border">
            {config?.updated_by_email && (
              <p className="text-xs text-tsushin-slate mr-auto">
                Last updated {formatRelative(config.updated_at)} by {config.updated_by_email}
              </p>
            )}
            <button
              type="submit"
              disabled={saving || transitioning || hostnameInvalid}
              className="btn-primary px-4 py-2 rounded-md text-sm disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save configuration'}
            </button>
          </div>
        </form>

        {/* Card D — Callbacks (placed above Tenants because it's a prerequisite) */}
        <div className="bg-tsushin-surface rounded-xl border border-tsushin-border p-6 mb-6">
          <h2 className="text-lg font-semibold text-white mb-1">
            Google OAuth callback URIs
          </h2>
          <p className="text-sm text-tsushin-slate mb-4">
            Add these to your Google Cloud Console OAuth client <strong>before</strong> enabling the tunnel, or Google SSO will break for users arriving via the public hostname.
          </p>
          {callbacks?.hostname ? (
            <div className="space-y-2">
              {callbacks.callbacks.map((cb) => (
                <div
                  key={cb.uri}
                  className="flex items-center justify-between gap-3 p-3 rounded bg-tsushin-ink border border-tsushin-border"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs text-tsushin-slate">{cb.label}</span>
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded-full ${
                          cb.purpose === 'google_sso'
                            ? 'bg-blue-500/20 text-blue-300 border border-blue-500/40'
                            : 'bg-purple-500/20 text-purple-300 border border-purple-500/40'
                        }`}
                      >
                        {cb.purpose}
                      </span>
                    </div>
                    <code className="text-xs text-teal-300 break-all">{cb.uri}</code>
                  </div>
                  <button
                    onClick={() => handleCopy(cb.uri, cb.uri)}
                    className="text-xs text-tsushin-slate hover:text-teal-400"
                    aria-label={`Copy ${cb.label}`}
                  >
                    {copiedKey === cb.uri ? 'Copied' : 'Copy'}
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-tsushin-slate italic">
              Configure a named-tunnel hostname above to see the callback URIs you need to whitelist.
            </p>
          )}
        </div>

        {/* Card C — Tenants */}
        <div className="bg-tsushin-surface rounded-xl border border-tsushin-border p-6 mb-6">
          <h2 className="text-lg font-semibold text-white mb-1">
            Per-tenant entitlement
          </h2>
          <p className="text-sm text-tsushin-slate mb-4">
            Toggle which tenants are permitted to log in via the public tunnel hostname. Disabled tenants receive a 403 at login with an audit event.
          </p>
          {tenants.length === 0 ? (
            <p className="text-sm text-tsushin-slate italic">No tenants yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-tsushin-slate uppercase border-b border-tsushin-border">
                    <th className="py-2 pr-4">Tenant</th>
                    <th className="py-2 pr-4">Slug</th>
                    <th className="py-2 pr-4">Users</th>
                    <th className="py-2 pr-4">Remote access</th>
                    <th className="py-2 pr-4">Last changed</th>
                  </tr>
                </thead>
                <tbody>
                  {tenants.map((t) => {
                    const isToggling = togglingTenants.has(t.id)
                    return (
                      <tr
                        key={t.id}
                        className="border-b border-tsushin-border/50"
                        aria-busy={isToggling || undefined}
                      >
                        <td className="py-3 pr-4 text-white">{t.name}</td>
                        <td className="py-3 pr-4 text-tsushin-slate font-mono text-xs">{t.slug}</td>
                        <td className="py-3 pr-4 text-tsushin-slate">{t.user_count}</td>
                        <td className="py-3 pr-4">
                          <button
                            type="button"
                            role="switch"
                            aria-checked={t.remote_access_enabled}
                            onClick={() => handleToggleTenant(t)}
                            disabled={isToggling}
                            className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors ${
                              t.remote_access_enabled ? 'bg-teal-500' : 'bg-tsushin-ink border border-tsushin-border'
                            } ${isToggling ? 'opacity-60' : ''}`}
                            aria-label={`Toggle remote access for ${t.name}`}
                          >
                            <span
                              className={`inline-block h-3 w-3 rounded-full bg-white transform transition-transform ${
                                t.remote_access_enabled ? 'translate-x-5' : 'translate-x-1'
                              }`}
                            />
                          </button>
                        </td>
                        <td className="py-3 pr-4 text-xs text-tsushin-slate">
                          {t.last_changed_at
                            ? `${formatRelative(t.last_changed_at)}${
                                t.last_changed_by_email ? ` by ${t.last_changed_by_email}` : ''
                              }`
                            : '—'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
