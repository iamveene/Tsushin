'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  api,
  type ContinuousSubscription,
} from '@/lib/client'

const MANAGED_CHANNEL_TYPES = new Set(['email', 'jira', 'github', 'webhook'])

interface Props {
  agentId: number
  readOnly?: boolean
}

function getErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback
}

export function SubscriptionEditor({ agentId, readOnly = false }: Props) {
  const [subs, setSubs] = useState<ContinuousSubscription[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [togglingId, setTogglingId] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const page = await api.listContinuousSubscriptions(agentId, { limit: 100 })
      setSubs(page.items.filter((sub) => MANAGED_CHANNEL_TYPES.has(sub.channel_type)))
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load monitored trigger links'))
    } finally {
      setLoading(false)
    }
  }, [agentId])

  useEffect(() => {
    load()
  }, [load])

  async function handleToggle(sub: ContinuousSubscription) {
    if (sub.is_system_owned) return
    setTogglingId(sub.id)
    setError(null)
    try {
      const next = sub.status === 'active' ? 'paused' : 'active'
      await api.updateContinuousSubscription(agentId, sub.id, { status: next })
      await load()
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to update monitored trigger link'))
    } finally {
      setTogglingId(null)
    }
  }

  async function handleDelete(sub: ContinuousSubscription) {
    if (sub.is_system_owned) return
    if (typeof window !== 'undefined') {
      const confirmed = window.confirm(
        `Delete monitoring link #${sub.id} on ${sub.channel_type}/${sub.channel_instance_id}?`,
      )
      if (!confirmed) return
    }
    setDeletingId(sub.id)
    setError(null)
    try {
      await api.deleteContinuousSubscription(agentId, sub.id)
      await load()
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to delete monitored trigger link'))
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">Watcher Monitoring</h2>
          <p className="text-xs text-tsushin-slate">
            Trigger monitoring links that wake this Studio-created agent monitor.
          </p>
        </div>
        <a
          href="/hub/triggers"
          className="rounded-lg border border-tsushin-border px-3 py-1.5 text-sm text-tsushin-fog hover:text-white"
        >
          Configure triggers
        </a>
      </div>

      {error && (
        <div className="mb-3 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
          {error}
        </div>
      )}

      {loading ? (
        <div className="rounded-lg border border-tsushin-border/70 bg-black/20 p-6 text-center text-sm text-tsushin-slate">
          Loading monitored trigger links…
        </div>
      ) : subs.length === 0 ? (
        <div className="rounded-lg border border-dashed border-tsushin-border p-6 text-center text-sm text-tsushin-slate">
          No watcher monitoring links yet. Create or edit an Email, Jira, GitHub, or Webhook trigger and choose this monitor.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase text-tsushin-slate">
                <th className="px-3 py-2">ID</th>
                <th className="px-3 py-2">Channel</th>
                <th className="px-3 py-2">Instance</th>
                <th className="px-3 py-2">Event</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {subs.map((sub) => {
                const locked = sub.is_system_owned
                return (
                  <tr key={sub.id} className="text-tsushin-fog">
                    <td className="px-3 py-2 font-mono text-xs">#{sub.id}</td>
                    <td className="px-3 py-2 capitalize">{sub.channel_type}</td>
                    <td className="px-3 py-2 font-mono">{sub.channel_instance_id}</td>
                    <td className="px-3 py-2">{sub.event_type || <span className="text-tsushin-slate">—</span>}</td>
                    <td className="px-3 py-2">
                      <span
                        className={`rounded-full border px-2 py-0.5 text-xs ${
                          sub.status === 'active'
                            ? 'border-green-500/30 bg-green-500/10 text-green-300'
                            : sub.status === 'paused'
                              ? 'border-yellow-500/30 bg-yellow-500/10 text-yellow-300'
                              : 'border-red-500/30 bg-red-500/10 text-red-300'
                        }`}
                      >
                        {sub.status}
                      </span>
                      {locked && (
                        <span className="ml-2 rounded-full border border-tsushin-border px-2 py-0.5 text-[10px] text-tsushin-slate">
                          system
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <div className="flex justify-end gap-2">
                        <button
                          type="button"
                          disabled={locked || togglingId === sub.id || readOnly}
                          onClick={() => handleToggle(sub)}
                          className="rounded-md border border-tsushin-border px-2 py-1 text-xs text-tsushin-fog hover:text-white disabled:opacity-30"
                        >
                          {togglingId === sub.id
                            ? 'Saving…'
                            : sub.status === 'active'
                              ? 'Pause'
                              : 'Resume'}
                        </button>
                        <button
                          type="button"
                          disabled={locked || deletingId === sub.id || readOnly}
                          onClick={() => handleDelete(sub)}
                          className="rounded-md border border-red-500/30 px-2 py-1 text-xs text-red-300 hover:bg-red-500/10 disabled:opacity-30"
                        >
                          {deletingId === sub.id ? 'Deleting…' : 'Delete'}
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default SubscriptionEditor
