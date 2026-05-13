'use client'

/**
 * SourceStepConfig
 *
 * Wave 4-5 of the Triggers ↔ Flows unification.
 *
 * Replaces the Wave 2 placeholder that read "Source step config — wired
 * in Wave 4." Renders a read-only summary of the bound trigger plus a
 * "last sample payload" expander so flow authors can write
 * `{{source.payload.field}}` references with confidence.
 *
 * Source step config_json shape (set by Wave 2 SourceStepHandler):
 *   { trigger_kind: 'jira'|'email'|'github'|'webhook',
 *     trigger_instance_id: number }
 *
 * Sample payload sourcing:
 *   - webhook (Wave 5): `getWebhookPayloadCaptures(integration_id)` returns
 *     the last 5 inbound payloads. The component renders an expandable
 *     list of captures and walks the most-recent capture (recursive
 *     descent, max depth 4, max 50 paths) to render clickable JSON-path
 *     chips. Clicking a chip copies `{{source.payload.<path>}}` to the
 *     clipboard. Empty state shows curl + "How to test" expander.
 *   - jira / email / github: most recent WakeEvent for the
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
  type WebhookIntegration,
  type WebhookPayloadCapture,
} from '@/lib/client'
import {
  ExternalLinkIcon,
  LightningIcon,
  WebhookIcon,
  WrenchIcon,
  EnvelopeIcon,
  GlobeIcon,
  CopyIcon,
} from '@/components/ui/icons'
import { copyToClipboard } from '@/lib/clipboard'
import { useToast } from '@/contexts/ToastContext'
import { formatRelative } from '@/lib/dateUtils'

interface Props {
  config: Record<string, unknown>
}

const KIND_LABELS: Record<TriggerKind, string> = {
  jira: 'Jira',
  email: 'Email',
  github: 'GitHub',
  webhook: 'Webhook',
}

function KindIcon({ kind, size = 16 }: { kind: TriggerKind; size?: number }) {
  if (kind === 'webhook') return <WebhookIcon size={size} />
  if (kind === 'jira') return <WrenchIcon size={size} />
  if (kind === 'github') return <GlobeIcon size={size} />
  if (kind === 'email') return <EnvelopeIcon size={size} />
  return <LightningIcon size={size} />
}

function getTriggerName(detail: TriggerDetail | null, kind: TriggerKind): string {
  if (!detail) return ''
  if ('integration_name' in detail && detail.integration_name) return detail.integration_name as string
  return `${KIND_LABELS[kind]} #${(detail as { id: number }).id}`
}

/**
 * Walks an arbitrary JSON-decoded object and yields field paths (dot-
 * notation, with array indices skipped — `items[0].name` becomes
 * `items.name`). Caps at depth 4 and 50 paths so a pathological payload
 * doesn't wedge the editor. Object keys are sorted for stable rendering.
 */
function inferJsonPaths(value: unknown, maxDepth = 4, maxPaths = 50): string[] {
  const out: string[] = []
  const seen = new Set<string>()

  function walk(node: unknown, prefix: string, depth: number) {
    if (out.length >= maxPaths) return
    if (depth > maxDepth) return
    if (node === null || node === undefined) return
    if (Array.isArray(node)) {
      // For arrays, descend into the first element to surface its keys
      // without polluting the path with indices.
      if (node.length > 0) walk(node[0], prefix, depth + 1)
      return
    }
    if (typeof node !== 'object') return
    const obj = node as Record<string, unknown>
    const keys = Object.keys(obj).sort()
    for (const k of keys) {
      if (out.length >= maxPaths) return
      const path = prefix ? `${prefix}.${k}` : k
      if (!seen.has(path)) {
        seen.add(path)
        out.push(path)
      }
      walk(obj[k], path, depth + 1)
    }
  }

  walk(value, '', 0)
  return out
}

function safeParseJson(text: string | null | undefined): unknown {
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

export default function SourceStepConfig({ config }: Props) {
  const triggerKind = (config?.trigger_kind || '') as TriggerKind | ''
  const triggerInstanceId = Number(config?.trigger_instance_id) || 0
  const toast = useToast()

  const [trigger, setTrigger] = useState<TriggerDetail | null>(null)
  const [loadingTrigger, setLoadingTrigger] = useState(false)

  const [showSample, setShowSample] = useState(false)
  const [sampleLoading, setSampleLoading] = useState(false)
  const [sampleEvent, setSampleEvent] = useState<WakeEvent | null>(null)
  const [samplePayload, setSamplePayload] = useState<unknown>(null)
  const [sampleError, setSampleError] = useState<string | null>(null)

  // Wave 5: webhook-only state — list of last 5 captures + which row is
  // expanded. Inferred chips are derived from the most-recent capture.
  const [captures, setCaptures] = useState<WebhookPayloadCapture[] | null>(null)
  const [capturesLoading, setCapturesLoading] = useState(false)
  const [capturesError, setCapturesError] = useState<string | null>(null)
  const [expandedCaptureId, setExpandedCaptureId] = useState<number | null>(null)
  const [showHowToTest, setShowHowToTest] = useState(false)

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
  }, [triggerKind, triggerInstanceId, isValid])

  async function loadSamplePayload() {
    if (!isValid || !triggerKind) return
    setSampleLoading(true)
    setSampleError(null)
    setSampleEvent(null)
    setSamplePayload(null)
    try {
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

  async function loadWebhookCaptures() {
    if (triggerKind !== 'webhook' || triggerInstanceId <= 0) return
    setCapturesLoading(true)
    setCapturesError(null)
    try {
      const items = await api.getWebhookPayloadCaptures(triggerInstanceId)
      setCaptures(items)
      // Auto-expand the most recent capture for instant context.
      if (items.length > 0) {
        setExpandedCaptureId(items[0].id)
      }
    } catch (err: unknown) {
      setCapturesError(err instanceof Error ? err.message : 'Failed to load payload captures')
      setCaptures([])
    } finally {
      setCapturesLoading(false)
    }
  }

  function handleToggleSample() {
    const next = !showSample
    setShowSample(next)
    if (next) {
      if (triggerKind === 'webhook') {
        if (captures === null && !capturesLoading) loadWebhookCaptures()
      } else if (!sampleEvent && !sampleLoading) {
        loadSamplePayload()
      }
    }
  }

  async function handleCopyPath(path: string) {
    const ref = `{{source.payload.${path}}}`
    try {
      await copyToClipboard(ref)
      toast.success(`Copied ${ref}`)
    } catch {
      toast.error('Failed to copy', 'Clipboard access was blocked.')
    }
  }

  // Derive inferred JSON paths from the most-recent capture so the chip
  // panel is immediately visible without having to expand a row first.
  const inferredPaths = useMemo<string[]>(() => {
    if (triggerKind !== 'webhook' || !captures || captures.length === 0) return []
    const parsed = safeParseJson(captures[0].payload_json)
    return inferJsonPaths(parsed)
  }, [triggerKind, captures])

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

  // Webhook integrations carry an inbound URL we can show in the curl
  // example so authors can copy/paste a working `curl` command without
  // chasing it from another tab.
  const webhookTrigger =
    triggerKind === 'webhook' && trigger && 'inbound_url' in trigger
      ? (trigger as WebhookIntegration)
      : null
  const inboundUrl = webhookTrigger?.inbound_url || ''
  const secretPreview = webhookTrigger?.api_secret_preview || ''
  const curlExample = inboundUrl
    ? `curl -X POST '${inboundUrl}' \\\n  -H 'X-Webhook-Secret: <your-secret>' \\\n  -H 'Content-Type: application/json' \\\n  -d '{"event":"test","data":{"id":42}}'`
    : ''

  // Read-only trigger configuration summary.
  //
  // Pre-fix the source step exposed only the trigger NAME plus a sample-payload
  // expander, which forced flow authors to leave the editor and chase the
  // filter parameters from Hub → Triggers. Surfacing the kind-specific
  // filter inputs (JQL/search_query/repo/etc.) plus a criteria.filters
  // preview right next to the agent-summary card closes that gap and
  // gives operators a direct anchor for "what is this flow ingesting?".
  const triggerCriteria = (trigger && 'trigger_criteria' in trigger
    ? (trigger as { trigger_criteria?: Record<string, unknown> | null }).trigger_criteria
    : null) || null
  const criteriaFiltersRaw = triggerCriteria && typeof triggerCriteria === 'object'
    ? (triggerCriteria as Record<string, unknown>).filters
    : null
  const criteriaFilters = criteriaFiltersRaw && typeof criteriaFiltersRaw === 'object'
    ? (criteriaFiltersRaw as Record<string, unknown>)
    : null
  const criteriaJsonpathMatchers = (() => {
    if (!criteriaFilters) return []
    const cands = ['jsonpath_matchers', 'jsonpath', 'matchers']
    for (const k of cands) {
      const v = criteriaFilters[k]
      if (Array.isArray(v)) return v
    }
    return []
  })()
  const criteriaFiltersHasContent = (() => {
    if (criteriaJsonpathMatchers.length > 0) return true
    if (!criteriaFilters) return false
    return Object.keys(criteriaFilters).some((k) => {
      const v = criteriaFilters[k]
      if (v === null || v === undefined || v === '' || v === false) return false
      if (Array.isArray(v) && v.length === 0) return false
      if (typeof v === 'object' && v !== null && Object.keys(v as Record<string, unknown>).length === 0) return false
      return true
    })
  })()

  type ConfigEntry = { label: string; value: string; mono?: boolean }
  const configEntries: ConfigEntry[] = (() => {
    if (!trigger) return []
    if (triggerKind === 'jira') {
      const t = trigger as { project_key?: string | null; jql?: string }
      return [
        ...(t.project_key ? [{ label: 'Project', value: t.project_key, mono: true } as ConfigEntry] : []),
        ...(t.jql ? [{ label: 'JQL', value: t.jql, mono: true } as ConfigEntry] : []),
      ]
    }
    if (triggerKind === 'email') {
      const t = trigger as { search_query?: string | null; gmail_account_email?: string | null }
      return [
        ...(t.gmail_account_email ? [{ label: 'Inbox', value: t.gmail_account_email } as ConfigEntry] : []),
        ...(t.search_query ? [{ label: 'Search query', value: t.search_query, mono: true } as ConfigEntry] : []),
      ]
    }
    if (triggerKind === 'github') {
      const t = trigger as {
        repo_owner?: string
        repo_name?: string
        events?: string[] | null
        branch_filter?: string | null
        path_filters?: string[] | null
        author_filter?: string | null
      }
      return [
        ...(t.repo_owner && t.repo_name
          ? [{ label: 'Repository', value: `${t.repo_owner}/${t.repo_name}`, mono: true } as ConfigEntry]
          : []),
        ...(t.events && t.events.length > 0
          ? [{ label: 'Events', value: t.events.join(', '), mono: true } as ConfigEntry]
          : []),
        ...(t.branch_filter ? [{ label: 'Branch filter', value: t.branch_filter, mono: true } as ConfigEntry] : []),
        ...(t.path_filters && t.path_filters.length > 0
          ? [{ label: 'Path filters', value: t.path_filters.join(', '), mono: true } as ConfigEntry]
          : []),
        ...(t.author_filter ? [{ label: 'Author filter', value: t.author_filter, mono: true } as ConfigEntry] : []),
      ]
    }
    return []
  })()

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

      {(configEntries.length > 0 || criteriaFiltersHasContent) && (
        <div className="rounded-lg border border-slate-700 bg-slate-800/40 p-4">
          <div className="flex items-center justify-between">
            <div className="text-xs font-medium uppercase tracking-wide text-slate-400">
              Trigger configuration
            </div>
            <Link
              href={`${triggerHref}?tab=criteria`}
              className="inline-flex items-center gap-1 text-xs text-cyan-300 hover:text-cyan-200"
            >
              Edit in Hub <ExternalLinkIcon size={11} />
            </Link>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Filters that gate which events fire this flow. Edited on the trigger detail page.
          </p>
          {configEntries.length > 0 && (
            <dl className="mt-3 grid gap-2 sm:grid-cols-[120px_1fr] text-xs">
              {configEntries.map((entry) => (
                <div key={entry.label} className="contents">
                  <dt className="text-slate-400">{entry.label}</dt>
                  <dd
                    className={`break-words text-slate-100 ${entry.mono ? 'font-mono' : ''}`}
                  >
                    {entry.value}
                  </dd>
                </div>
              ))}
            </dl>
          )}
          {criteriaFiltersHasContent && (
            <div className="mt-3">
              <div className="text-xs text-slate-400 mb-1">
                Payload filters
                {criteriaJsonpathMatchers.length > 0 && (
                  <span className="ml-1 text-slate-500">
                    ({criteriaJsonpathMatchers.length} JSONPath matcher
                    {criteriaJsonpathMatchers.length === 1 ? '' : 's'})
                  </span>
                )}
              </div>
              <pre className="rounded bg-slate-900/60 border border-slate-700 p-2 text-[11px] text-slate-300 overflow-x-auto">
                {JSON.stringify(criteriaFilters, null, 2)}
              </pre>
            </div>
          )}
          {!criteriaFiltersHasContent && (
            <div className="mt-3 text-xs text-slate-500">
              No payload filters set on the trigger — every event fanned out by the source
              configuration above reaches this flow.
            </div>
          )}
        </div>
      )}

      <div className="rounded-lg border border-slate-700 bg-slate-800/40 p-3">
        <button
          type="button"
          onClick={handleToggleSample}
          className="flex w-full items-center justify-between text-left text-sm text-slate-200 hover:text-white"
        >
          <span className="font-medium">
            {triggerKind === 'webhook' ? 'Recent payloads' : 'Last sample payload'}
          </span>
          <span className="text-xs text-tsushin-slate">{showSample ? 'Hide' : 'Show'}</span>
        </button>

        {showSample && triggerKind === 'webhook' && (
          <div className="mt-2 space-y-3 text-xs">
            {capturesLoading && <div className="text-tsushin-slate">Loading captures…</div>}
            {!capturesLoading && capturesError && (
              <div className="text-rose-300">{capturesError}</div>
            )}

            {!capturesLoading && !capturesError && captures !== null && captures.length === 0 && (
              <div className="space-y-2">
                <div className="text-tsushin-slate">
                  Send a test event to populate samples. Tsushin will store the latest webhook payloads here.
                </div>
                <button
                  type="button"
                  onClick={() => setShowHowToTest((v) => !v)}
                  className="text-cyan-300 hover:text-white"
                >
                  {showHowToTest ? 'Hide how-to-test' : 'How to test'}
                </button>
                {showHowToTest && (
                  <div className="space-y-2 rounded-md border border-slate-700 bg-black/30 p-2">
                    {inboundUrl ? (
                      <>
                        <div>
                          <div className="text-tsushin-slate">Inbound URL</div>
                          <code className="mt-1 block break-all rounded border border-slate-700 bg-black/40 px-2 py-1 font-mono text-[11px] text-cyan-200">
                            {inboundUrl}
                          </code>
                        </div>
                        {secretPreview && (
                          <div className="text-tsushin-slate">
                            Secret preview: <code className="text-cyan-200">{secretPreview}</code>
                          </div>
                        )}
                        <div>
                          <div className="text-tsushin-slate">curl</div>
                          <pre className="mt-1 overflow-auto rounded border border-slate-700 bg-black/40 p-2 font-mono text-[11px] leading-snug text-slate-200">
                            {curlExample}
                          </pre>
                        </div>
                      </>
                    ) : (
                      <div className="text-tsushin-slate">
                        Open the trigger detail page to copy the inbound URL and secret, then POST a JSON
                        body to that URL with <code>X-Webhook-Secret</code>.
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {!capturesLoading && !capturesError && captures !== null && captures.length > 0 && (
              <div className="space-y-3">
                {/* JSON-path inference panel */}
                {inferredPaths.length > 0 && (
                  <div className="rounded-md border border-slate-700 bg-black/30 p-2">
                    <div className="mb-1 text-tsushin-slate">
                      Inferred fields (click to copy{' '}
                      <code className="text-slate-300">{'{{source.payload.<path>}}'}</code>)
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {inferredPaths.map((path) => (
                        <button
                          key={path}
                          type="button"
                          onClick={() => handleCopyPath(path)}
                          className="inline-flex items-center gap-1 rounded-full border border-cyan-400/40 bg-cyan-500/10 px-2 py-0.5 font-mono text-[11px] text-cyan-100 hover:text-white"
                          title={`Copy {{source.payload.${path}}}`}
                        >
                          <CopyIcon size={10} />
                          {path}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* List of captures, most recent first */}
                <ul className="space-y-2">
                  {captures.map((cap) => {
                    const isOpen = expandedCaptureId === cap.id
                    const parsed = safeParseJson(cap.payload_json)
                    return (
                      <li key={cap.id} className="rounded-md border border-slate-700 bg-black/20">
                        <button
                          type="button"
                          onClick={() => setExpandedCaptureId(isOpen ? null : cap.id)}
                          className="flex w-full items-center justify-between gap-2 px-2 py-1 text-left text-slate-200 hover:text-white"
                        >
                          <span className="truncate">
                            #{cap.id} · {formatRelative(cap.captured_at)}
                            {cap.dedupe_key ? (
                              <span className="ml-2 text-tsushin-slate">
                                dedupe: <code className="text-slate-400">{cap.dedupe_key}</code>
                              </span>
                            ) : null}
                          </span>
                          <span className="text-tsushin-slate">{isOpen ? '−' : '+'}</span>
                        </button>
                        {isOpen && (
                          <pre className="max-h-64 overflow-auto rounded-b-md border-t border-slate-700 bg-black/40 p-2 font-mono text-[11px] leading-snug text-slate-200">
                            {parsed !== null
                              ? JSON.stringify(parsed, null, 2)
                              : cap.payload_json}
                          </pre>
                        )}
                      </li>
                    )
                  })}
                </ul>
              </div>
            )}
          </div>
        )}

        {showSample && triggerKind !== 'webhook' && (
          <div className="mt-2 space-y-2 text-xs">
            {sampleLoading && <div className="text-tsushin-slate">Loading sample…</div>}
            {!sampleLoading && sampleError && (
              <div className="text-rose-300">{sampleError}</div>
            )}
            {!sampleLoading && !sampleError && !sampleEvent && (
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
