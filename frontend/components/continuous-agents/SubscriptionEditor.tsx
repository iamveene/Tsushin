'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  api,
  type ContinuousSubscription,
  type ContinuousSubscriptionCreate,
} from '@/lib/client'

const CHANNEL_TYPES = ['email', 'jira', 'schedule', 'github', 'webhook', 'whatsapp'] as const
type ChannelType = (typeof CHANNEL_TYPES)[number]

interface Props {
  agentId: number
  readOnly?: boolean
}

interface NewSubForm {
  channelType: ChannelType
  channelInstanceId: string
  eventType: string
}

const EMPTY_FORM: NewSubForm = {
  channelType: 'schedule',
  channelInstanceId: '',
  eventType: '',
}

function getErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback
}

export function SubscriptionEditor({ agentId, readOnly = false }: Props) {
  const [subs, setSubs] = useState<ContinuousSubscription[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<NewSubForm>(EMPTY_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [togglingId, setTogglingId] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const page = await api.listContinuousSubscriptions(agentId, { limit: 100 })
      setSubs(page.items)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load subscriptions'))
    } finally {
      setLoading(false)
    }
  }, [agentId])

  useEffect(() => {
    load()
  }, [load])

  async function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting) return
    const instanceIdParsed = Number(form.channelInstanceId)
    if (!Number.isFinite(instanceIdParsed) || instanceIdParsed < 1) {
      setError('Channel instance ID must be a positive integer')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const payload: ContinuousSubscriptionCreate = {
        channel_type: form.channelType,
        channel_instance_id: instanceIdParsed,
        event_type: form.eventType.trim() || null,
        status: 'active',
      }
      await api.createContinuousSubscription(agentId, payload)
      setForm(EMPTY_FORM)
      setShowForm(false)
      await load()
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to create subscription'))
    } finally {
      setSubmitting(false)
    }
  }

  async function handleToggle(sub: ContinuousSubscription) {
    if (sub.is_system_owned) return
    setTogglingId(sub.id)
    setError(null)
    try {
      const next = sub.status === 'active' ? 'paused' : 'active'
      await api.updateContinuousSubscription(agentId, sub.id, { status: next })
      await load()
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to update subscription'))
    } finally {
      setTogglingId(null)
    }
  }

  async function handleDelete(sub: ContinuousSubscription) {
    if (sub.is_system_owned) return
    if (typeof window !== 'undefined') {
      const confirmed = window.confirm(
        `Delete subscription #${sub.id} on ${sub.channel_type}/${sub.channel_instance_id}?`,
      )
      if (!confirmed) return
    }
    setDeletingId(sub.id)
    setError(null)
    try {
      await api.deleteContinuousSubscription(agentId, sub.id)
      await load()
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to delete subscription'))
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">Subscriptions</h2>
          <p className="text-xs text-tsushin-slate">
            Channel instances that wake this continuous agent.
          </p>
        </div>
        {!readOnly && (
          <button
            type="button"
            onClick={() => setShowForm((value) => !value)}
            className="rounded-lg border border-tsushin-border px-3 py-1.5 text-sm text-tsushin-fog hover:text-white"
          >
            {showForm ? 'Cancel' : '+ Add subscription'}
          </button>
        )}
      </div>

      {error && (
        <div className="mb-3 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
          {error}
        </div>
      )}

      {showForm && !readOnly && (
        <form
          onSubmit={handleCreate}
          className="mb-4 grid gap-3 rounded-lg border border-tsushin-border/70 bg-black/20 p-4 sm:grid-cols-4"
        >
          <div>
            <label className="mb-1 block text-xs text-tsushin-slate">Channel</label>
            <select
              value={form.channelType}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, channelType: event.target.value as ChannelType }))
              }
              className="w-full rounded-md border border-tsushin-border bg-tsushin-ink px-2 py-1.5 text-sm text-white"
            >
              {CHANNEL_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-tsushin-slate">Instance ID</label>
            <input
              type="number"
              min={1}
              value={form.channelInstanceId}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, channelInstanceId: event.target.value }))
              }
              className="w-full rounded-md border border-tsushin-border bg-tsushin-ink px-2 py-1.5 text-sm text-white"
              placeholder="e.g. 12"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-tsushin-slate">Event type (optional)</label>
            <input
              type="text"
              value={form.eventType}
              maxLength={64}
              onChange={(event) => setForm((prev) => ({ ...prev, eventType: event.target.value }))}
              className="w-full rounded-md border border-tsushin-border bg-tsushin-ink px-2 py-1.5 text-sm text-white"
              placeholder="e.g. tick"
            />
          </div>
          <div className="flex items-end">
            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-md bg-cyan-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-cyan-400 disabled:opacity-50"
            >
              {submitting ? 'Adding…' : 'Add'}
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <div className="rounded-lg border border-tsushin-border/70 bg-black/20 p-6 text-center text-sm text-tsushin-slate">
          Loading subscriptions…
        </div>
      ) : subs.length === 0 ? (
        <div className="rounded-lg border border-dashed border-tsushin-border p-6 text-center text-sm text-tsushin-slate">
          No subscriptions yet. {!readOnly && 'Click "+ Add subscription" to wire one.'}
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
