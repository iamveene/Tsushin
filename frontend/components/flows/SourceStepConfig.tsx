'use client'

/**
 * SourceStepConfig
 *
 * Wave 4 of the Triggers ↔ Flows unification.
 *
 * Replaces the Wave 2 placeholder that read "Source step config — wired
 * in Wave 4." Renders a read-only summary of the bound trigger plus a
 * "last sample payload" expander so flow authors can write
 * `{{source.payload.field}}` references with confidence.
 *
 * Source step config_json shape (set by Wave 2 SourceStepHandler):
 *   { trigger_kind: 'jira'|'email'|'github'|'schedule'|'webhook',
 *     trigger_instance_id: number }
 *
 * Sample payload sourcing:
 *   - webhook: Wave 5 ships `getWebhookPayloadCaptures(integration_id)`.
 *     Until then this component falls back to "Send a test event…".
 *   - jira / email / github / schedule: most recent WakeEvent for the
 *     bound trigger via `getWakeEvents` + `getWakeEventPayload`.
 *
 * The component degrades quietly if the backend hasn't merged the
 * binding endpoints yet — empty state copy stays informative.
 */

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import {
  api,
  type TriggerDetail,
  type TriggerKind,
  type WakeEvent,
} from '@/lib/client'
import {
  ExternalLinkIcon,
  LightningIcon,
  WebhookIcon,
  WrenchIcon,
  CalendarIcon,
  EnvelopeIcon,
  GlobeIcon,
} from '@/components/ui/icons'

interface Props {
  config: Record<string, any>
}

const KIND_LABELS: Record<TriggerKind, string> = {
  jira: 'Jira',
  email: 'Email',
  github: 'GitHub',
  schedule: 'Schedule',
  webhook: 'Webhook',
}

function KindIcon({ kind, size = 16 }: { kind: TriggerKind; size?: number }) {
  if (kind === 'webhook') return <WebhookIcon size={size} />
  if (kind === 'jira') return <WrenchIcon size={size} />
  if (kind === 'github') return <GlobeIcon size={size} />
  if (kind === 'schedule') return <CalendarIcon size={size} />
  if (kind === 'email') return <EnvelopeIcon size={size} />
  return <LightningIcon size={size} />
}

function getTriggerName(detail: TriggerDetail | null, kind: TriggerKind): string {
  if (!detail) return ''
  if ('integration_name' in detail && detail.integration_name) return detail.integration_name as string
  return `${KIND_LABELS[kind]} #${(detail as { id: number }).id}`
}

export default function SourceStepConfig({ config }: Props) {
  const triggerKind = (config?.trigger_kind || '') as TriggerKind | ''
  const triggerInstanceId = Number(config?.trigger_instance_id) || 0

  const [trigger, setTrigger] = useState<TriggerDetail | null>(null)
  const [loadingTrigger, setLoadingTrigger] = useState(false)

  const [showSample, setShowSample] = useState(false)
  const [sampleLoading, setSampleLoading] = useState(false)
  const [sampleEvent, setSampleEvent] = useState<WakeEvent | null>(null)
  const [samplePayload, setSamplePayload] = useState<unknown>(null)
  const [sampleError, setSampleError] = useState<string | null>(null)

  const isValid = useMemo(
    () => Boolean(triggerKind && triggerInstanceId > 0),
    [triggerKind, triggerInstanceId],
  )

  useEffect(() => {
    let cancelled = false
    if (!isValid) {
      setTrigger(null)
      return
    }
    setLoadingTrigger(true)
    api.getTriggerDetail(triggerKind as TriggerKind, triggerInstanceId)
      .then((d) => { if (!cancelled) setTrigger(d) })
      .catch(() => { if (!cancelled) setTrigger(null) })
      .finally(() => { if (!cancelled) setLoadingTrigger(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [triggerKind, triggerInstanceId, isValid])

  async function loadSamplePayload() {
    if (!isValid || !triggerKind) return
    setSampleLoading(true)
    setSampleError(null)
    setSampleEvent(null)
    setSamplePayload(null)
    try {
      // Webhook captures arrive in Wave 5 via api.getWebhookPayloadCaptures —
      // fall back to the WakeEvent path for everything for now.
      const events = await api.getWakeEvents({
        limit: 1,
        channel_type: triggerKind,
        channel_instance_id: triggerInstanceId,
      })
      const item = events.items?.[0] || null
      setSampleEvent(item)
      if (item) {
        try {
          const payload = await api.getWakeEventPayload(item.id)
          setSamplePayload(payload.payload)
        } catch {
          setSamplePayload(null)
        }
      }
    } catch (err: unknown) {
      setSampleError(err instanceof Error ? err.message : 'Failed to load sample payload')
    } finally {
      setSampleLoading(false)
    }
  }

  function handleToggleSample() {
    const next = !showSample
    setShowSample(next)
    if (next && !sampleEvent && !sampleLoading) {
      loadSamplePayload()
    }
  }

  if (!isValid) {
    return (
      <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4">
        <div className="text-sm font-medium text-white">Source step</div>
        <p className="mt-1 text-sm text-amber-100">
          This source step is missing a trigger binding (no <code>trigger_kind</code> or <code>trigger_instance_id</code>).
          Re-create the flow from the trigger page (<em>Hub → Triggers → choose a trigger → Create flow from this trigger</em>)
          to ensure the source step is wired correctly.
        </p>
      </div>
    )
  }

  const triggerName = getTriggerName(trigger, triggerKind as TriggerKind)
  const triggerHref = `/hub/triggers/${triggerKind}/${triggerInstanceId}`

  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-cyan-500/30 bg-cyan-500/5 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm font-medium text-white">
              <KindIcon kind={triggerKind as TriggerKind} size={16} />
              <span>Source: {KIND_LABELS[triggerKind as TriggerKind]}</span>
            </div>
            <div className="mt-1 truncate text-sm text-tsushin-fog">
              {loadingTrigger ? 'Loading trigger…' : (triggerName || `${KIND_LABELS[triggerKind as TriggerKind]} #${triggerInstanceId}`)}
            </div>
          </div>
          <Link
            href={triggerHref}
            className="inline-flex items-center gap-1 rounded-md border border-cyan-400/40 bg-cyan-500/10 px-2 py-1 text-xs text-cyan-100 hover:text-white"
          >
            Edit trigger <ExternalLinkIcon size={12} />
          </Link>
        </div>
      </div>

      <div className="rounded-lg border border-slate-700 bg-slate-800/40 p-3">
        <button
          type="button"
          onClick={handleToggleSample}
          className="flex w-full items-center justify-between text-left text-sm text-slate-200 hover:text-white"
        >
          <span className="font-medium">Last sample payload</span>
          <span className="text-xs text-tsushin-slate">{showSample ? 'Hide' : 'Show'}</span>
        </button>
        {showSample && (
          <div className="mt-2 space-y-2 text-xs">
            {sampleLoading && <div className="text-tsushin-slate">Loading sample…</div>}
            {!sampleLoading && sampleError && (
              <div className="text-rose-300">{sampleError}</div>
            )}
            {!sampleLoading && !sampleError && !sampleEvent && triggerKind === 'webhook' && (
              <div className="text-tsushin-slate">
                Send a test event to populate samples. Tsushin will store the latest webhook payloads here.
              </div>
            )}
            {!sampleLoading && !sampleError && !sampleEvent && triggerKind !== 'webhook' && (
              <div className="text-tsushin-slate">
                No recent events yet. Once this trigger fires for the first time, the latest payload will appear here.
              </div>
            )}
            {!sampleLoading && sampleEvent && (
              <div>
                <div className="mb-1 text-tsushin-slate">
                  WakeEvent #{sampleEvent.id} · {sampleEvent.event_type} ·{' '}
                  {new Date(sampleEvent.occurred_at).toLocaleString()}
                </div>
                {samplePayload !== null && samplePayload !== undefined ? (
                  <pre className="max-h-64 overflow-auto rounded-md border border-slate-700 bg-black/40 p-2 font-mono text-[11px] leading-snug text-slate-200">
                    {JSON.stringify(samplePayload, null, 2)}
                  </pre>
                ) : (
                  <div className="text-tsushin-slate">Payload body unavailable.</div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="rounded-lg border border-slate-700 bg-slate-800/30 p-3 text-xs text-slate-300">
        <div className="font-medium text-slate-200">Variable hint</div>
        <p className="mt-1 leading-snug text-slate-400">
          Reference fields downstream as{' '}
          <code className="rounded bg-slate-900/60 px-1 py-0.5 text-slate-200">{'{{source.payload.your_field}}'}</code>,{' '}
          <code className="rounded bg-slate-900/60 px-1 py-0.5 text-slate-200">{'{{source.trigger_kind}}'}</code>,{' '}
          <code className="rounded bg-slate-900/60 px-1 py-0.5 text-slate-200">{'{{source.event_type}}'}</code>,{' '}
          <code className="rounded bg-slate-900/60 px-1 py-0.5 text-slate-200">{'{{source.dedupe_key}}'}</code>,{' '}
          <code className="rounded bg-slate-900/60 px-1 py-0.5 text-slate-200">{'{{source.occurred_at}}'}</code>.
        </p>
      </div>
    </div>
  )
}
