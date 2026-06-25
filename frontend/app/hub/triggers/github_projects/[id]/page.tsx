'use client'

import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'

import { useAuth } from '@/contexts/AuthContext'
import { api, type GitHubProjectsTrigger } from '@/lib/client'
import { formatRelative } from '@/lib/dateUtils'
import { AlertTriangleIcon, GitHubIcon, RefreshIcon } from '@/components/ui/icons'

export default function GitHubProjectsTriggerDetailPage() {
  const params = useParams<{ id: string }>()
  const router = useRouter()
  const { hasPermission } = useAuth()
  const canRead = hasPermission('hub.read')
  const canWrite = hasPermission('hub.write')
  const id = Number(params?.id)

  const [trigger, setTrigger] = useState<GitHubProjectsTrigger | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ tone: 'success' | 'error'; message: string } | null>(null)

  const load = useCallback(async () => {
    if (!Number.isFinite(id)) return
    setLoading(true)
    setError(null)
    try {
      setTrigger(await api.getGitHubProjectsTrigger(id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load trigger')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    if (canRead) load()
    else setLoading(false)
  }, [canRead, load])

  const onTest = async () => {
    if (!trigger) return
    setBusy(true)
    setNotice(null)
    try {
      const res = await api.testGitHubProjectsConnection({
        github_integration_id: trigger.github_integration_id,
        project_owner: trigger.project_owner,
        project_number: trigger.project_number,
      })
      setNotice(
        res.ok
          ? { tone: 'success', message: `Connected: "${res.title || 'board'}" (#${res.number ?? trigger.project_number}).` }
          : { tone: 'error', message: res.error || 'Could not read the board.' },
      )
    } catch (err) {
      setNotice({ tone: 'error', message: err instanceof Error ? err.message : 'Test failed' })
    } finally {
      setBusy(false)
    }
  }

  const onPoll = async () => {
    if (!trigger) return
    setBusy(true)
    setNotice(null)
    try {
      const res = await api.pollGitHubProjectsTriggerNow(trigger.id)
      const detail = res.status === 'ok'
        ? `Polled ${res.fetched_count} item(s) — ${res.seeded ? 'seeded snapshot (no notifications)' : `${res.dispatched_count} notification(s) dispatched`}.`
        : `Poll status: ${res.status}${res.reason ? ` (${res.reason})` : ''}.`
      setNotice({ tone: res.status === 'ok' ? 'success' : 'error', message: detail })
      await load()
    } catch (err) {
      setNotice({ tone: 'error', message: err instanceof Error ? err.message : 'Poll failed' })
    } finally {
      setBusy(false)
    }
  }

  const onToggleActive = async () => {
    if (!trigger) return
    setBusy(true)
    setNotice(null)
    try {
      const updated = await api.updateGitHubProjectsTrigger(trigger.id, { is_active: !trigger.is_active })
      setTrigger(updated)
      setNotice({ tone: 'success', message: updated.is_active ? 'Trigger resumed.' : 'Trigger paused.' })
    } catch (err) {
      setNotice({ tone: 'error', message: err instanceof Error ? err.message : 'Update failed' })
    } finally {
      setBusy(false)
    }
  }

  const onDelete = async () => {
    if (!trigger) return
    if (!window.confirm(`Delete trigger "${trigger.integration_name}"? This cannot be undone.`)) return
    setBusy(true)
    try {
      await api.deleteGitHubProjectsTrigger(trigger.id)
      router.push('/hub/triggers')
    } catch (err) {
      setNotice({ tone: 'error', message: err instanceof Error ? err.message : 'Delete failed' })
      setBusy(false)
    }
  }

  if (!canRead) {
    return (
      <div className="w-full px-4 sm:px-6 lg:px-8 py-8">
        <div className="rounded-xl border border-yellow-500/30 bg-yellow-500/10 p-8 text-center text-yellow-100">
          <AlertTriangleIcon size={28} className="mx-auto mb-3 text-yellow-300" />
          <div className="text-lg font-semibold text-white">You don&apos;t have permission to view triggers</div>
        </div>
      </div>
    )
  }

  return (
    <div className="w-full px-4 sm:px-6 lg:px-8 py-6 animate-fade-in">
      <div className="mb-5 flex items-center gap-3 text-sm text-tsushin-slate">
        <Link href="/hub" className="hover:text-white">Hub</Link>
        <span>/</span>
        <Link href="/hub/triggers" className="hover:text-white">Triggers</Link>
        <span>/</span>
        <span>GitHub Projects</span>
      </div>

      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-fuchsia-500/10">
          <GitHubIcon size={18} className="text-fuchsia-300" />
        </div>
        <div>
          <h1 className="text-2xl font-display font-semibold text-white">
            {trigger?.integration_name || 'GitHub Projects Trigger'}
          </h1>
          <p className="text-sm text-tsushin-slate">GitHub Projects v2 board watcher — notifies on new / assigned / moved cards.</p>
        </div>
      </div>

      {loading && <div className="text-sm text-tsushin-slate">Loading…</div>}
      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">{error}</div>
      )}

      {notice && (
        <div
          className={`mb-4 rounded-xl border p-3 text-sm ${
            notice.tone === 'success'
              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
              : 'border-amber-500/30 bg-amber-500/10 text-amber-200'
          }`}
        >
          {notice.message}
        </div>
      )}

      {trigger && (
        <div className="space-y-6">
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Status" value={trigger.is_active ? (trigger.status || 'active') : 'paused'} />
            <Field label="Health" value={`${trigger.health_status}${trigger.health_status_reason ? ` — ${trigger.health_status_reason}` : ''}`} />
            <Field label="Board" value={`${trigger.project_name || `${trigger.project_owner}/projects/${trigger.project_number}`}`} />
            <Field label="Owner / Number" value={`${trigger.project_owner} / #${trigger.project_number}`} />
            <Field label="Notify recipient" value={trigger.notify_recipient_raw || '—'} />
            <Field label="Notifications" value={trigger.notification_enabled ? 'enabled' : 'disabled'} />
            <Field label="Delivery agent" value={trigger.default_agent_name || (trigger.default_agent_id ? `#${trigger.default_agent_id}` : '—')} />
            <Field label="Poll interval" value={`${trigger.poll_interval_seconds}s`} />
            <Field label="GitHub connection" value={trigger.github_integration_name || `#${trigger.github_integration_id}`} />
            <Field label="Snapshot seeded" value={trigger.seeded_at ? formatRelative(trigger.seeded_at) : 'not yet'} />
            <Field label="Last poll" value={trigger.last_health_check ? formatRelative(trigger.last_health_check) : 'never'} />
            <Field label="Last activity" value={trigger.last_activity_at ? formatRelative(trigger.last_activity_at) : 'none'} />
          </div>

          {canWrite && (
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" onClick={onTest} disabled={busy} className="inline-flex items-center gap-2 rounded-lg border border-fuchsia-400/40 bg-fuchsia-500/10 px-4 py-2 text-sm text-fuchsia-100 hover:text-white disabled:opacity-50">
                Test connection
              </button>
              <button type="button" onClick={onPoll} disabled={busy} className="inline-flex items-center gap-2 rounded-lg border border-cyan-400/40 bg-cyan-500/10 px-4 py-2 text-sm text-cyan-100 hover:text-white disabled:opacity-50">
                <RefreshIcon size={16} /> Poll now
              </button>
              <button type="button" onClick={onToggleActive} disabled={busy} className="inline-flex items-center gap-2 rounded-lg border border-tsushin-border bg-tsushin-surface px-4 py-2 text-sm text-tsushin-fog hover:text-white disabled:opacity-50">
                {trigger.is_active ? 'Pause' : 'Resume'}
              </button>
              <button type="button" onClick={onDelete} disabled={busy} className="inline-flex items-center gap-2 rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm text-red-200 hover:text-white disabled:opacity-50">
                Delete
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-tsushin-border/70 bg-tsushin-slate/5 p-3">
      <div className="text-xs uppercase tracking-wide text-tsushin-slate">{label}</div>
      <div className="mt-1 text-sm text-white break-words">{value}</div>
    </div>
  )
}
