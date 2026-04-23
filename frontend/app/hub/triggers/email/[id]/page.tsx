'use client'

import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { api, type EmailTrigger } from '@/lib/client'
import { useAuth } from '@/contexts/AuthContext'
import { formatDateTime, formatRelative } from '@/lib/dateUtils'
import { AlertTriangleIcon, ClockIcon, EnvelopeIcon, RefreshIcon, TrashIcon } from '@/components/ui/icons'

function getErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback
}

function statusClass(active: boolean, status: string): string {
  if (!active || status === 'paused') return 'bg-gray-500/10 text-gray-300 border-gray-500/30'
  if (status === 'error') return 'bg-red-500/10 text-red-300 border-red-500/30'
  return 'bg-green-500/10 text-green-300 border-green-500/30'
}

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-4">
      <div className="text-xs uppercase tracking-wide text-tsushin-slate">{label}</div>
      <div className="mt-2 text-sm text-white">{value}</div>
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
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const loadTrigger = useCallback(async () => {
    if (!hasValidId) return
    setLoading(true)
    setError(null)
    try {
      const data = await api.getEmailTrigger(triggerId)
      setTrigger(data)
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
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadTrigger()
  }, [hasValidId, loadTrigger, router])

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
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={loadTrigger}
            disabled={loading || saving}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-tsushin-border bg-tsushin-surface px-4 py-2 text-sm text-tsushin-fog hover:text-white disabled:opacity-50"
          >
            <RefreshIcon size={16} />
            Refresh
          </button>
          {trigger && canWriteHub && (
            <>
              <button
                type="button"
                onClick={toggleActive}
                disabled={saving}
                className="rounded-lg border border-tsushin-border bg-tsushin-surface px-4 py-2 text-sm text-tsushin-fog hover:text-white disabled:opacity-50"
              >
                {trigger.is_active ? 'Pause' : 'Resume'}
              </button>
              <button
                type="button"
                onClick={deleteTrigger}
                disabled={saving}
                className="inline-flex items-center justify-center gap-2 rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm text-red-200 hover:text-white disabled:opacity-50"
              >
                <TrashIcon size={16} />
                Delete
              </button>
            </>
          )}
        </div>
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
            <Field label="Status" value={<span className={`rounded-full border px-2.5 py-1 text-xs ${statusClass(trigger.is_active, trigger.status)}`}>{trigger.is_active ? trigger.status : 'paused'}</span>} />
            <Field label="Provider" value={trigger.provider} />
            <Field label="Poll interval" value={`${trigger.poll_interval_seconds}s`} />
            <Field label="Last activity" value={trigger.last_activity_at ? formatRelative(trigger.last_activity_at) : 'No activity'} />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
              <h2 className="flex items-center gap-2 text-lg font-semibold text-white">
                <EnvelopeIcon size={18} /> Inbox Binding
              </h2>
              <div className="mt-4 space-y-4 text-sm">
                <div>
                  <div className="text-xs text-tsushin-slate">Gmail account</div>
                  <div className="mt-1 text-white">{trigger.gmail_account_email || 'Not reported'}</div>
                </div>
                <div>
                  <div className="text-xs text-tsushin-slate">Gmail integration</div>
                  <div className="mt-1 text-white">{trigger.gmail_integration_name || trigger.gmail_integration_id || '-'}</div>
                </div>
                <div>
                  <div className="text-xs text-tsushin-slate">Search query</div>
                  <code className="mt-1 block rounded-lg border border-tsushin-border bg-black/30 p-3 text-xs text-cyan-200">
                    {trigger.search_query || 'Inbox default'}
                  </code>
                </div>
              </div>
            </div>

            <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
              <h2 className="flex items-center gap-2 text-lg font-semibold text-white">
                <ClockIcon size={18} /> Routing Detail
              </h2>
              <div className="mt-4 space-y-4 text-sm">
                <div>
                  <div className="text-xs text-tsushin-slate">Default agent</div>
                  <div className="mt-1 text-white">{trigger.default_agent_name || (trigger.default_agent_id ? `Agent #${trigger.default_agent_id}` : 'None')}</div>
                </div>
                <div>
                  <div className="text-xs text-tsushin-slate">Health</div>
                  <div className="mt-1 text-white">{trigger.health_status}</div>
                  {trigger.health_status_reason && (
                    <p className="mt-1 text-xs text-yellow-200">{trigger.health_status_reason}</p>
                  )}
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
