'use client'

/**
 * MemoryRecapCard
 *
 * v0.7.x Wave 2-D — trigger-detail surface for managing per-trigger Memory
 * Recap config. Renders inside the Overview tab of `TriggerDetailShell`,
 * after the Outputs section, for all four trigger kinds (jira / email /
 * github / webhook).
 *
 * States:
 *   - loading: spinner-text while the GET resolves
 *   - empty:   no row exists → "Memory Recap is not configured" + Enable CTA
 *   - summary: row exists → read-only chip view + Edit / Disable / Test
 *   - editor:  inline `MemoryRecapStep` + Save / Cancel
 *
 * "Disable" PUTs `enabled=false` instead of DELETE so re-enabling restores
 * the previously-saved values.
 */

import { useCallback, useEffect, useState } from 'react'
import { api, type TriggerRecapConfig, type TriggerRecapTestResult } from '@/lib/client'
import MemoryRecapStep, {
  DEFAULT_RECAP_CONFIG,
  type RecapTriggerKind,
} from '@/components/triggers/MemoryRecapStep'

interface Props {
  kind: RecapTriggerKind
  triggerId: number
  canWriteHub: boolean
}

const cardClass = 'rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5'
const chipClass =
  'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs'
const labelClass = 'text-xs uppercase tracking-wide text-tsushin-slate'

function getErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback
}

function scopeLabel(scope: TriggerRecapConfig['scope']): string {
  switch (scope) {
    case 'agent':
      return 'agent'
    case 'trigger_kind':
      return 'trigger_kind'
    case 'trigger_instance':
    default:
      return 'trigger_instance'
  }
}

function injectPositionLabel(pos: TriggerRecapConfig['inject_position']): string {
  return pos === 'system_addendum' ? 'system addendum' : 'prepend user msg'
}

export default function MemoryRecapCard({ kind, triggerId, canWriteHub }: Props) {
  const [loading, setLoading] = useState(true)
  const [config, setConfig] = useState<TriggerRecapConfig | null>(null)
  const [draft, setDraft] = useState<TriggerRecapConfig>(DEFAULT_RECAP_CONFIG)
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<TriggerRecapTestResult | null>(null)
  const [testError, setTestError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await api.getTriggerRecapConfig(kind, triggerId)
      setConfig(result)
      setDraft(result ?? DEFAULT_RECAP_CONFIG)
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to load memory recap config'))
    } finally {
      setLoading(false)
    }
  }, [kind, triggerId])

  useEffect(() => {
    refresh()
  }, [refresh])

  const flashSuccess = useCallback((message: string) => {
    setSuccess(message)
    setTimeout(() => setSuccess(null), 3000)
  }, [])

  const handleEnable = useCallback(() => {
    setDraft({ ...DEFAULT_RECAP_CONFIG, enabled: true })
    setEditing(true)
    setError(null)
  }, [])

  const handleEdit = useCallback(() => {
    setDraft(config ?? DEFAULT_RECAP_CONFIG)
    setEditing(true)
    setError(null)
  }, [config])

  const handleCancel = useCallback(() => {
    setDraft(config ?? DEFAULT_RECAP_CONFIG)
    setEditing(false)
    setError(null)
  }, [config])

  const handleSave = useCallback(async () => {
    setSaving(true)
    setError(null)
    try {
      const saved = await api.putTriggerRecapConfig(kind, triggerId, draft)
      setConfig(saved)
      setDraft(saved)
      setEditing(false)
      flashSuccess('Memory recap saved')
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to save memory recap config'))
    } finally {
      setSaving(false)
    }
  }, [draft, flashSuccess, kind, triggerId])

  const handleDisable = useCallback(async () => {
    if (!config) return
    setSaving(true)
    setError(null)
    try {
      // Preserve the saved config — only flip the enabled flag — so the
      // operator can re-enable later without re-keying every field.
      const next: TriggerRecapConfig = { ...config, enabled: false }
      const saved = await api.putTriggerRecapConfig(kind, triggerId, next)
      setConfig(saved)
      setDraft(saved)
      flashSuccess('Memory recap disabled')
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to disable memory recap'))
    } finally {
      setSaving(false)
    }
  }, [config, flashSuccess, kind, triggerId])

  const handleTest = useCallback(async () => {
    setTesting(true)
    setTestError(null)
    setTestResult(null)
    try {
      const result = await api.testTriggerRecap(kind, triggerId, {})
      setTestResult(result)
    } catch (err: unknown) {
      setTestError(getErrorMessage(err, 'Failed to run test recap'))
    } finally {
      setTesting(false)
    }
  }, [kind, triggerId])

  if (loading) {
    return (
      <div className={cardClass}>
        <h3 className="text-base font-semibold text-white">Memory Recap</h3>
        <p className="mt-2 text-sm text-tsushin-slate">Loading recap configuration…</p>
      </div>
    )
  }

  // Editor mode (inline MemoryRecapStep). Used both for first-time enable and
  // for editing an existing row.
  if (editing) {
    return (
      <div className={cardClass}>
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold text-white">Memory Recap</h3>
            <p className="mt-1 text-sm text-tsushin-slate">
              Configure recall of past similar cases for this trigger.
            </p>
          </div>
        </div>
        {error && (
          <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
            {error}
          </div>
        )}
        {success && (
          <div className="mb-4 rounded-lg border border-green-500/30 bg-green-500/10 px-3 py-2 text-sm text-green-200">
            {success}
          </div>
        )}
        <MemoryRecapStep
          triggerKind={kind}
          initialConfig={draft}
          onChange={setDraft}
          triggerInstanceId={triggerId}
          caseMemoryEnabled={true}
        />
        {canWriteHub && (
          <div className="mt-5 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-4 py-2 text-sm text-cyan-200 hover:text-white disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save Memory Recap'}
            </button>
            <button
              type="button"
              onClick={handleCancel}
              disabled={saving}
              className="rounded-lg border border-tsushin-border bg-tsushin-surface px-4 py-2 text-sm text-tsushin-fog hover:text-white disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    )
  }

  // Empty state — no recap row exists for this trigger.
  if (!config) {
    return (
      <div className={cardClass}>
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h3 className="text-base font-semibold text-white">Memory Recap</h3>
            <p className="mt-1 text-sm text-tsushin-slate">
              Memory Recap is not configured for this trigger.
            </p>
          </div>
          {canWriteHub && (
            <button
              type="button"
              onClick={handleEnable}
              className="shrink-0 rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-4 py-2 text-sm text-cyan-200 hover:text-white"
            >
              Enable
            </button>
          )}
        </div>
        {error && (
          <div className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
            {error}
          </div>
        )}
      </div>
    )
  }

  // Summary view — read-only badges + edit/disable/test controls.
  const enabled = config.enabled
  return (
    <div className={cardClass}>
      <div className="flex flex-col gap-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h3 className="text-base font-semibold text-white">Memory Recap</h3>
            <p className="mt-1 text-sm text-tsushin-slate">
              Recalls past similar cases when this trigger fires and injects them into the agent prompt.
            </p>
          </div>
          <span
            className={`${chipClass} ${
              enabled
                ? 'border-green-500/40 bg-green-500/10 text-green-200'
                : 'border-tsushin-border bg-black/30 text-tsushin-slate'
            }`}
          >
            {enabled ? 'enabled' : 'disabled'}
          </span>
        </div>

        {success && (
          <div className="rounded-lg border border-green-500/30 bg-green-500/10 px-3 py-2 text-sm text-green-200">
            {success}
          </div>
        )}
        {error && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
            {error}
          </div>
        )}

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <div className={labelClass}>Scope</div>
            <div className="mt-1 text-sm text-white">{scopeLabel(config.scope)}</div>
          </div>
          <div>
            <div className={labelClass}>Max cases (k)</div>
            <div className="mt-1 text-sm text-white">{config.k}</div>
          </div>
          <div>
            <div className={labelClass}>Min similarity</div>
            <div className="mt-1 text-sm text-white">{config.min_similarity.toFixed(2)}</div>
          </div>
          <div>
            <div className={labelClass}>Vector kind</div>
            <div className="mt-1 text-sm text-white">{config.vector_kind}</div>
          </div>
          <div>
            <div className={labelClass}>Inject position</div>
            <div className="mt-1 text-sm text-white">{injectPositionLabel(config.inject_position)}</div>
          </div>
          <div>
            <div className={labelClass}>Include failed cases</div>
            <div className="mt-1 text-sm text-white">{config.include_failed ? 'yes' : 'no'}</div>
          </div>
          <div>
            <div className={labelClass}>Max recap chars</div>
            <div className="mt-1 text-sm text-white">{config.max_recap_chars}</div>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {canWriteHub && (
            <button
              type="button"
              onClick={handleEdit}
              disabled={saving}
              className="rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-4 py-2 text-sm text-cyan-200 hover:text-white disabled:opacity-50"
            >
              Edit
            </button>
          )}
          {canWriteHub && enabled && (
            <button
              type="button"
              onClick={handleDisable}
              disabled={saving}
              className="rounded-lg border border-tsushin-border bg-tsushin-surface px-4 py-2 text-sm text-tsushin-fog hover:text-white disabled:opacity-50"
            >
              {saving ? 'Working…' : 'Disable'}
            </button>
          )}
          <button
            type="button"
            onClick={handleTest}
            disabled={testing}
            className="rounded-lg border border-tsushin-border bg-tsushin-surface px-4 py-2 text-sm text-tsushin-fog hover:text-white disabled:opacity-50"
          >
            {testing ? 'Testing…' : 'Test Recap'}
          </button>
        </div>

        {testError && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
            {testError}
          </div>
        )}
        {testResult && (
          <div className="space-y-2">
            <div className="text-xs text-tsushin-slate">
              Cases used: <span className="text-white">{testResult.cases_used}</span>
              <span className="mx-2">·</span>
              Elapsed: <span className="text-white">{testResult.elapsed_ms}ms</span>
              <span className="mx-2">·</span>
              Used sample: <span className="text-white">{testResult.used_sample ? 'yes' : 'no'}</span>
            </div>
            <pre className="max-h-64 overflow-auto rounded-lg border border-tsushin-border bg-black/40 p-3 text-xs text-tsushin-slate">
              {testResult.rendered_text || '(empty recap — no cases matched)'}
            </pre>
          </div>
        )}
      </div>
    </div>
  )
}
