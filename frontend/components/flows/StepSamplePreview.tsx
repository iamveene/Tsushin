'use client'

/**
 * StepSamplePreview
 *
 * Per-step "what data does this step receive?" expander for the flow
 * editor. Pre-fix, a flow author had to leave the editor (or scroll back
 * up to the Source step's sample-payload viewer) to see the structure
 * of the trigger event their templates were referencing. This component
 * surfaces the most-recent wake event payload right inside each step's
 * edit panel so operators can author `{{source.payload.X}}` references
 * with confidence and inspect the JSON paths the step's current config
 * already references.
 *
 * Requires the parent flow to be system-managed (auto-generated from a
 * trigger). For user-authored flows there's no canonical wake event to
 * preview, so the parent should not render this panel.
 *
 * v1 only shows the raw payload + a count of `{{source.payload.X}}`
 * references in the step's config. A future iteration can resolve those
 * references against the sample and render the expected step input
 * end-to-end (the dry-run feature on the roadmap).
 */

import { useEffect, useMemo, useState } from 'react'
import { api, type WakeEvent } from '@/lib/client'
import { LightningIcon } from '@/components/ui/icons'

interface Props {
  triggerKind: string
  triggerInstanceId: number
  /** Resolved step config_json — used to count template references. */
  stepConfig?: Record<string, unknown> | null
}

const TEMPLATE_RE = /\{\{\s*source\.payload\.([^}\s]+)\s*\}\}/g

function findSourceRefs(config: unknown, acc: Set<string>): Set<string> {
  if (config === null || config === undefined) return acc
  if (typeof config === 'string') {
    let m: RegExpExecArray | null
    while ((m = TEMPLATE_RE.exec(config)) !== null) {
      acc.add(m[1])
    }
    return acc
  }
  if (Array.isArray(config)) {
    for (const item of config) findSourceRefs(item, acc)
    return acc
  }
  if (typeof config === 'object') {
    for (const v of Object.values(config as Record<string, unknown>)) findSourceRefs(v, acc)
  }
  return acc
}

export default function StepSamplePreview({ triggerKind, triggerInstanceId, stepConfig }: Props) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [event, setEvent] = useState<WakeEvent | null>(null)
  const [payload, setPayload] = useState<unknown>(null)
  const [error, setError] = useState<string | null>(null)

  const referencedPaths = useMemo(() => {
    return Array.from(findSourceRefs(stepConfig, new Set<string>())).sort()
  }, [stepConfig])

  useEffect(() => {
    if (!open || event !== null || loading) return
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const events = await api.getWakeEvents({
          limit: 1,
          channel_type: triggerKind,
          channel_instance_id: triggerInstanceId,
        })
        const item = events.items?.[0] || null
        if (cancelled) return
        setEvent(item)
        if (item) {
          try {
            const detail = await api.getWakeEventPayload(item.id)
            if (!cancelled) setPayload(detail.payload)
          } catch {
            if (!cancelled) setPayload(null)
          }
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load sample payload')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, triggerKind, triggerInstanceId])

  if (!triggerKind || !triggerInstanceId) return null

  return (
    <div className="rounded-lg border border-tsushin-border bg-tsushin-ink/40">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2 text-left text-xs"
      >
        <span className="flex items-center gap-2 font-medium text-slate-200">
          <LightningIcon size={12} className="text-amber-300" />
          Sample data this step receives
          {referencedPaths.length > 0 && (
            <span className="rounded-full border border-cyan-400/40 bg-cyan-500/10 px-1.5 py-0.5 text-[10px] text-cyan-200">
              {referencedPaths.length} ref{referencedPaths.length === 1 ? '' : 's'}
            </span>
          )}
        </span>
        <span className="text-tsushin-slate">{open ? 'Hide' : 'Show'}</span>
      </button>

      {open && (
        <div className="space-y-2 border-t border-tsushin-border px-3 py-2 text-xs">
          {loading && <div className="text-tsushin-slate">Loading latest wake event…</div>}
          {error && <div className="text-amber-300">{error}</div>}
          {!loading && !error && !event && (
            <div className="text-tsushin-slate">
              No wake events yet for this trigger. Once it fires once, the most recent payload will be visible here.
            </div>
          )}
          {!loading && event && (
            <>
              <div className="flex flex-wrap items-center gap-2 text-[11px] text-tsushin-slate">
                <span className="rounded border border-tsushin-border bg-tsushin-surface/40 px-1.5 py-0.5 font-mono text-cyan-200">
                  #{event.id}
                </span>
                <span>{event.event_type}</span>
                <span>·</span>
                <span>{new Date(event.occurred_at).toLocaleString()}</span>
                <span>·</span>
                <span className="rounded-full border border-tsushin-border bg-tsushin-surface/40 px-1.5 py-0.5 uppercase tracking-wide">
                  {event.status}
                </span>
              </div>

              {referencedPaths.length > 0 && (
                <div>
                  <div className="mb-1 text-[10px] uppercase tracking-wide text-tsushin-slate">
                    This step references
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {referencedPaths.map((path) => (
                      <code
                        key={path}
                        className="rounded border border-cyan-400/30 bg-cyan-500/10 px-1.5 py-0.5 text-[10px] text-cyan-200"
                      >
                        {`{{source.payload.${path}}}`}
                      </code>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <div className="mb-1 text-[10px] uppercase tracking-wide text-tsushin-slate">
                  Wake event payload
                </div>
                <pre className="max-h-64 overflow-auto rounded bg-slate-900/60 border border-tsushin-border p-2 text-[11px] text-slate-200">
                  {JSON.stringify(payload, null, 2)}
                </pre>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
