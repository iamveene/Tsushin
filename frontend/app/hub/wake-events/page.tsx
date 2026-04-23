'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { api, type PageResponse, type WakeEvent } from '@/lib/client'
import { formatDateTime, formatRelative } from '@/lib/dateUtils'
import { BellIcon, ClockIcon, EyeIcon, FilterIcon, RefreshIcon, ZapIcon } from '@/components/ui/icons'

const STATUS_OPTIONS = ['all', 'queued', 'claimed', 'processed', 'failed', 'filtered_out']
const CHANNEL_OPTIONS = ['all', 'email', 'webhook', 'whatsapp', 'telegram', 'slack', 'discord']

function getErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback
}

function statusClass(status: string): string {
  const normalized = status.toLowerCase()
  if (['processed', 'success', 'completed'].includes(normalized)) return 'bg-green-500/10 text-green-300 border-green-500/30'
  if (['queued', 'claimed', 'pending'].includes(normalized)) return 'bg-yellow-500/10 text-yellow-300 border-yellow-500/30'
  if (['failed', 'error'].includes(normalized)) return 'bg-red-500/10 text-red-300 border-red-500/30'
  if (['filtered_out', 'duplicate'].includes(normalized)) return 'bg-gray-500/10 text-gray-300 border-gray-500/30'
  return 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30'
}

function importanceClass(importance: string): string {
  const normalized = importance.toLowerCase()
  if (['high', 'critical', 'urgent'].includes(normalized)) return 'text-red-300'
  if (['medium', 'normal'].includes(normalized)) return 'text-yellow-300'
  return 'text-tsushin-slate'
}

export default function WakeEventsPage() {
  const searchParams = useSearchParams()
  const highlightId = Number(searchParams.get('highlight'))
  const [eventsPage, setEventsPage] = useState<PageResponse<WakeEvent> | null>(null)
  const [statusFilter, setStatusFilter] = useState('all')
  const [channelFilter, setChannelFilter] = useState('all')
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const pageSize = 50

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getWakeEvents({
        limit: pageSize,
        offset,
        status: statusFilter === 'all' ? undefined : statusFilter,
        channel_type: channelFilter === 'all' ? undefined : channelFilter,
      })
      setEventsPage(data)
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to load wake events'))
    } finally {
      setLoading(false)
    }
  }, [channelFilter, offset, statusFilter])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData()
  }, [loadData])

  const events = useMemo(() => eventsPage?.items ?? [], [eventsPage])
  const selectedEvent = useMemo(() => {
    if (Number.isFinite(highlightId) && highlightId > 0) {
      return events.find(event => event.id === highlightId) || events[0] || null
    }
    return events[0] || null
  }, [events, highlightId])
  const total = eventsPage?.total || 0
  const canGoBack = offset > 0
  const canGoNext = offset + pageSize < total
  const visiblePayloadRefs = events.filter(event => event.payload_ref).length

  return (
    <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8 animate-fade-in">
      <div className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-3 text-sm text-tsushin-slate">
            <Link href="/hub" className="hover:text-white">Hub</Link>
            <span>/</span>
            <span>Wake Events</span>
          </div>
          <h1 className="text-3xl font-display font-bold text-white">Wake Events</h1>
          <p className="mt-2 max-w-3xl text-sm text-tsushin-slate">
            Trigger-origin event browser for continuous agents. Payloads are represented by payload references only.
          </p>
        </div>
        <button
          type="button"
          onClick={loadData}
          disabled={loading}
          className="inline-flex items-center justify-center gap-2 rounded-lg border border-tsushin-border bg-tsushin-surface px-4 py-2 text-sm text-tsushin-fog hover:text-white disabled:opacity-50"
        >
          <RefreshIcon size={16} />
          Refresh
        </button>
      </div>

      <div className="mb-6 grid gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-4">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-tsushin-slate">
            <BellIcon size={14} /> Matching events
          </div>
          <div className="mt-2 text-2xl font-semibold text-white">{total}</div>
        </div>
        <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-4">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-tsushin-slate">
            <ZapIcon size={14} /> Visible page
          </div>
          <div className="mt-2 text-2xl font-semibold text-white">{events.length}</div>
        </div>
        <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-4">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-tsushin-slate">
            <EyeIcon size={14} /> Payload refs
          </div>
          <div className="mt-2 text-2xl font-semibold text-white">{visiblePayloadRefs}</div>
        </div>
      </div>

      <div className="mb-5 rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
          <FilterIcon size={16} /> Filters
        </div>
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {STATUS_OPTIONS.map(option => (
              <button
                key={option}
                type="button"
                onClick={() => {
                  setStatusFilter(option)
                  setOffset(0)
                }}
                className={`rounded-lg border px-3 py-1.5 text-xs capitalize transition-colors ${
                  statusFilter === option
                    ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-200'
                    : 'border-tsushin-border text-tsushin-slate hover:text-white'
                }`}
              >
                {option.replace('_', ' ')}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            {CHANNEL_OPTIONS.map(option => (
              <button
                key={option}
                type="button"
                onClick={() => {
                  setChannelFilter(option)
                  setOffset(0)
                }}
                className={`rounded-lg border px-3 py-1.5 text-xs capitalize transition-colors ${
                  channelFilter === option
                    ? 'border-teal-500/50 bg-teal-500/10 text-teal-200'
                    : 'border-tsushin-border text-tsushin-slate hover:text-white'
                }`}
              >
                {option}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && (
        <div className="mb-5 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
          {error}
        </div>
      )}

      {loading ? (
        <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/50 p-10 text-center text-tsushin-slate">
          Loading wake events...
        </div>
      ) : events.length === 0 ? (
        <div className="rounded-xl border border-dashed border-tsushin-border p-10 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-cyan-500/10 text-cyan-300">
            <BellIcon size={24} />
          </div>
          <h2 className="text-lg font-semibold text-white">No wake events</h2>
          <p className="mx-auto mt-2 max-w-xl text-sm text-tsushin-slate">
            No events match the selected filters yet.
          </p>
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(320px,420px)]">
          <div className="overflow-hidden rounded-xl border border-tsushin-border bg-tsushin-surface/60">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase tracking-wide text-tsushin-slate">
                  <tr className="border-b border-tsushin-border">
                    <th className="px-4 py-3">Event</th>
                    <th className="px-4 py-3">Channel</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Importance</th>
                    <th className="px-4 py-3">Occurred</th>
                    <th className="px-4 py-3">Payload ref</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map(event => (
                    <tr
                      key={event.id}
                      className={`border-b border-tsushin-border/60 ${
                        event.id === highlightId ? 'bg-cyan-500/10' : ''
                      }`}
                    >
                      <td className="px-4 py-3">
                        <div className="font-mono text-cyan-200">#{event.id}</div>
                        <div className="text-xs text-tsushin-slate">{event.event_type}</div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="text-white">{event.channel_type}</div>
                        <div className="text-xs text-tsushin-slate">Instance #{event.channel_instance_id}</div>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`rounded-full border px-2 py-0.5 text-xs ${statusClass(event.status)}`}>{event.status}</span>
                      </td>
                      <td className={`px-4 py-3 capitalize ${importanceClass(event.importance)}`}>{event.importance}</td>
                      <td className="px-4 py-3 text-tsushin-slate">
                        <div className="flex items-center gap-1.5">
                          <ClockIcon size={13} />
                          {formatRelative(event.occurred_at)}
                        </div>
                      </td>
                      <td className="px-4 py-3">
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
          </div>

          <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
            <h2 className="text-lg font-semibold text-white">Selected Event</h2>
            {selectedEvent ? (
              <div className="mt-4 space-y-4 text-sm">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <div className="text-xs text-tsushin-slate">Event ID</div>
                    <div className="font-mono text-white">#{selectedEvent.id}</div>
                  </div>
                  <div>
                    <div className="text-xs text-tsushin-slate">Status</div>
                    <span className={`mt-1 inline-flex rounded-full border px-2 py-0.5 text-xs ${statusClass(selectedEvent.status)}`}>{selectedEvent.status}</span>
                  </div>
                  <div>
                    <div className="text-xs text-tsushin-slate">Continuous agent</div>
                    {selectedEvent.continuous_agent_id ? (
                      <Link href={`/continuous-agents/${selectedEvent.continuous_agent_id}`} className="font-mono text-cyan-200 hover:text-white">
                        #{selectedEvent.continuous_agent_id}
                      </Link>
                    ) : (
                      <div className="text-white">Unassigned</div>
                    )}
                  </div>
                  <div>
                    <div className="text-xs text-tsushin-slate">Subscription</div>
                    <div className="font-mono text-white">{selectedEvent.continuous_subscription_id ?? '-'}</div>
                  </div>
                </div>
                <div>
                  <div className="text-xs text-tsushin-slate">Dedupe key</div>
                  <code className="mt-1 block break-all rounded-lg border border-tsushin-border bg-black/30 p-2 text-xs text-tsushin-fog">
                    {selectedEvent.dedupe_key}
                  </code>
                </div>
                <div>
                  <div className="text-xs text-tsushin-slate">Payload reference</div>
                  <code className="mt-1 block break-all rounded-lg border border-tsushin-border bg-black/30 p-2 text-xs text-cyan-200">
                    {selectedEvent.payload_ref || 'None'}
                  </code>
                  <p className="mt-2 text-xs text-tsushin-slate">
                    Raw payload JSON is not displayed in this UI; the A2 contract exposes only payload_ref.
                  </p>
                </div>
                <div>
                  <div className="text-xs text-tsushin-slate">Timestamps</div>
                  <div className="mt-1 text-white">Occurred {formatDateTime(selectedEvent.occurred_at)}</div>
                  <div className="text-tsushin-slate">Created {formatDateTime(selectedEvent.created_at)}</div>
                </div>
              </div>
            ) : (
              <div className="mt-4 rounded-lg border border-dashed border-tsushin-border p-8 text-center text-sm text-tsushin-slate">
                Select a wake event row.
              </div>
            )}
          </div>
        </div>
      )}

      <div className="mt-6 flex items-center justify-between">
        <button
          type="button"
          disabled={!canGoBack || loading}
          onClick={() => setOffset(Math.max(0, offset - pageSize))}
          className="rounded-lg border border-tsushin-border px-4 py-2 text-sm text-tsushin-fog hover:text-white disabled:opacity-40"
        >
          Previous
        </button>
        <span className="text-sm text-tsushin-slate">Offset {offset}</span>
        <button
          type="button"
          disabled={!canGoNext || loading}
          onClick={() => setOffset(offset + pageSize)}
          className="rounded-lg border border-tsushin-border px-4 py-2 text-sm text-tsushin-fog hover:text-white disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </div>
  )
}
