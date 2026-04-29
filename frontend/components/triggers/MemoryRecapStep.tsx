'use client'

/**
 * MemoryRecapStep
 *
 * v0.7.x Wave 2-D — frontend wizard step for configuring per-trigger Memory
 * Recap (case-memory recall). Renders inside `TriggerCreationWizard` between
 * the Criteria and Confirm steps. Pure presentational component: parent owns
 * the state and persists via `apiClient.putTriggerRecapConfig` after the
 * trigger row exists.
 *
 * Test Recap requires a saved trigger id, so the button stays disabled until
 * the trigger is persisted (parent passes `triggerInstanceId` once available).
 */

import { useCallback, useState } from 'react'
import { api, type TriggerRecapConfig, type TriggerRecapTestResult } from '@/lib/client'

export type RecapTriggerKind = 'jira' | 'email' | 'github' | 'webhook'

interface MemoryRecapStepProps {
  triggerKind: RecapTriggerKind
  initialConfig: TriggerRecapConfig
  onChange: (config: TriggerRecapConfig) => void
  triggerInstanceId?: number | null
  caseMemoryEnabled: boolean
}

export const DEFAULT_RECAP_CONFIG: TriggerRecapConfig = {
  enabled: false,
  query_template: '',
  scope: 'trigger_instance',
  k: 3,
  min_similarity: 0.35,
  vector_kind: 'problem',
  include_failed: true,
  format_template: '',
  inject_position: 'prepend_user_msg',
  max_recap_chars: 1500,
}

const KIND_DEFAULT_QUERY: Record<RecapTriggerKind, string> = {
  jira: '{{ summary }} {{ description }}',
  email: '{{ subject }} {{ body_preview }}',
  github: '{{ pull_request.title }} {{ pull_request.body }}',
  webhook: '',
}

const labelClass = 'text-xs uppercase tracking-wide text-tsushin-slate'
const inputClass =
  'w-full rounded-lg border border-tsushin-border bg-tsushin-surface/60 px-3 py-2 text-sm text-white outline-none transition-colors focus:border-tsushin-accent/60'
const textareaClass = `${inputClass} font-mono`
const cardClass = 'rounded-xl border border-tsushin-border bg-tsushin-surface/40 p-4'

export default function MemoryRecapStep({
  triggerKind,
  initialConfig,
  onChange,
  triggerInstanceId,
  caseMemoryEnabled,
}: MemoryRecapStepProps) {
  const [testResult, setTestResult] = useState<TriggerRecapTestResult | null>(null)
  const [testError, setTestError] = useState<string | null>(null)
  const [testing, setTesting] = useState(false)

  const config = initialConfig

  const update = useCallback(
    (patch: Partial<TriggerRecapConfig>) => {
      onChange({ ...config, ...patch })
    },
    [config, onChange],
  )

  const handleToggleEnabled = useCallback(
    (next: boolean) => {
      // Auto-fill the kind-specific query template the first time the user
      // turns recap on if they haven't customized the query yet — saves a
      // round trip to the docs for the common case.
      if (next && !config.query_template.trim()) {
        onChange({
          ...config,
          enabled: true,
          query_template: KIND_DEFAULT_QUERY[triggerKind] ?? '',
        })
      } else {
        onChange({ ...config, enabled: next })
      }
    },
    [config, onChange, triggerKind],
  )

  const handleTestRecap = useCallback(async () => {
    if (triggerInstanceId == null) return
    setTesting(true)
    setTestError(null)
    setTestResult(null)
    try {
      const body = {
        query: config.query_template.trim() || 'sample test query',
      }
      const result = await api.testTriggerRecap(triggerKind, triggerInstanceId, body)
      setTestResult(result)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Test recap failed'
      setTestError(message)
    } finally {
      setTesting(false)
    }
  }, [config.query_template, triggerInstanceId, triggerKind])

  if (!caseMemoryEnabled) {
    return (
      <div className="space-y-4">
        <div>
          <h3 className="text-base font-semibold text-white">Memory Recap</h3>
          <p className="mt-1 text-sm text-tsushin-slate">
            Recall snippets from past similar cases when this trigger fires.
          </p>
        </div>
        <div className={`${cardClass} border-yellow-500/30 bg-yellow-500/5`}>
          <p className="text-sm text-yellow-200">
            Case Memory is disabled for this tenant. Enable the
            <code className="mx-1 rounded bg-black/30 px-1 py-0.5 text-xs">case_memory_enabled</code>
            feature flag in tenant settings to configure per-trigger memory recap.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-base font-semibold text-white">Memory Recap</h3>
        <p className="mt-1 text-sm text-tsushin-slate">
          When this trigger fires, recall snippets from past similar cases and inject them into the agent prompt.
        </p>
      </div>

      <div className={`${cardClass} flex items-center justify-between gap-4`}>
        <div className="min-w-0">
          <div className="text-sm font-medium text-white">Enable memory recap for this trigger</div>
          <p className="mt-0.5 text-xs text-tsushin-slate">
            Off by default. When on, similar past cases will be injected into the agent's prompt at trigger time.
          </p>
        </div>
        <label className="inline-flex shrink-0 cursor-pointer items-center gap-2">
          <input
            type="checkbox"
            role="switch"
            checked={config.enabled}
            onChange={(event) => handleToggleEnabled(event.target.checked)}
            className="peer sr-only"
          />
          <span className="relative inline-block h-6 w-11 rounded-full bg-tsushin-border transition-colors peer-checked:bg-tsushin-accent">
            <span className="absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white transition-transform peer-checked:translate-x-5" />
          </span>
        </label>
      </div>

      {config.enabled && (
        <div className="space-y-4">
          <div className={cardClass}>
            <label htmlFor="recap-query-template" className={labelClass}>
              Query template
            </label>
            <p className="mt-1 text-xs text-tsushin-slate">
              Jinja-style template rendered against the inbound payload. The result becomes the recall query.
            </p>
            <textarea
              id="recap-query-template"
              rows={4}
              value={config.query_template}
              onChange={(event) => update({ query_template: event.target.value })}
              className={`mt-2 ${textareaClass}`}
              placeholder={KIND_DEFAULT_QUERY[triggerKind] || 'e.g. {{ field }} {{ other_field }}'}
              spellCheck={false}
            />
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className={cardClass}>
              <label htmlFor="recap-scope" className={labelClass}>
                Scope
              </label>
              <select
                id="recap-scope"
                value={config.scope}
                onChange={(event) =>
                  update({ scope: event.target.value as TriggerRecapConfig['scope'] })
                }
                className={`mt-2 ${inputClass}`}
              >
                <option value="trigger_instance">Trigger instance (this trigger only)</option>
                <option value="trigger_kind">Trigger kind (all triggers of this kind)</option>
                <option value="agent">Agent (all of this agent's cases)</option>
              </select>
            </div>

            <div className={cardClass}>
              <label htmlFor="recap-k" className={labelClass}>
                Max cases (k)
              </label>
              <input
                id="recap-k"
                type="number"
                min={1}
                max={10}
                value={config.k}
                onChange={(event) => {
                  const parsed = Number(event.target.value)
                  update({ k: Number.isFinite(parsed) ? parsed : config.k })
                }}
                className={`mt-2 ${inputClass}`}
              />
            </div>

            <div className={cardClass}>
              <label htmlFor="recap-min-sim" className={labelClass}>
                Min similarity
                <span className="ml-2 font-mono text-tsushin-accent">
                  {config.min_similarity.toFixed(2)}
                </span>
              </label>
              <input
                id="recap-min-sim"
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={config.min_similarity}
                onChange={(event) => update({ min_similarity: Number(event.target.value) })}
                className="mt-3 w-full"
              />
            </div>

            <div className={cardClass}>
              <label htmlFor="recap-vector-kind" className={labelClass}>
                Vector kind
              </label>
              <select
                id="recap-vector-kind"
                value={config.vector_kind}
                onChange={(event) =>
                  update({ vector_kind: event.target.value as TriggerRecapConfig['vector_kind'] })
                }
                className={`mt-2 ${inputClass}`}
              >
                <option value="problem">problem</option>
                <option value="action">action</option>
                <option value="outcome">outcome</option>
                <option value="any">any</option>
              </select>
            </div>
          </div>

          <div className={`${cardClass} flex items-center justify-between gap-4`}>
            <div className="min-w-0">
              <div className="text-sm font-medium text-white">Include failed cases</div>
              <p className="mt-0.5 text-xs text-tsushin-slate">
                When off, only cases marked as successful will be considered for recall.
              </p>
            </div>
            <label className="inline-flex shrink-0 cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                role="switch"
                checked={config.include_failed}
                onChange={(event) => update({ include_failed: event.target.checked })}
                className="peer sr-only"
              />
              <span className="relative inline-block h-6 w-11 rounded-full bg-tsushin-border transition-colors peer-checked:bg-tsushin-accent">
                <span className="absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white transition-transform peer-checked:translate-x-5" />
              </span>
            </label>
          </div>

          <div className={cardClass}>
            <span className={labelClass}>Inject position</span>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <label className="flex cursor-pointer items-start gap-2 rounded-lg border border-tsushin-border bg-tsushin-surface/60 p-3 hover:border-tsushin-accent/40">
                <input
                  type="radio"
                  name="recap-inject-position"
                  value="prepend_user_msg"
                  checked={config.inject_position === 'prepend_user_msg'}
                  onChange={() => update({ inject_position: 'prepend_user_msg' })}
                  className="mt-1"
                />
                <span>
                  <span className="block text-sm text-white">Prepend to user message</span>
                  <span className="block text-xs text-tsushin-slate">
                    Recap inserted before the rendered trigger payload.
                  </span>
                </span>
              </label>
              <label className="flex cursor-pointer items-start gap-2 rounded-lg border border-tsushin-border bg-tsushin-surface/60 p-3 hover:border-tsushin-accent/40">
                <input
                  type="radio"
                  name="recap-inject-position"
                  value="system_addendum"
                  checked={config.inject_position === 'system_addendum'}
                  onChange={() => update({ inject_position: 'system_addendum' })}
                  className="mt-1"
                />
                <span>
                  <span className="block text-sm text-white">System addendum</span>
                  <span className="block text-xs text-tsushin-slate">
                    Recap appended to the system prompt instead of the user message.
                  </span>
                </span>
              </label>
            </div>
          </div>

          <div className={cardClass}>
            <label htmlFor="recap-max-chars" className={labelClass}>
              Max recap chars
            </label>
            <input
              id="recap-max-chars"
              type="number"
              min={200}
              max={8192}
              value={config.max_recap_chars}
              onChange={(event) => {
                const parsed = Number(event.target.value)
                update({ max_recap_chars: Number.isFinite(parsed) ? parsed : config.max_recap_chars })
              }}
              className={`mt-2 ${inputClass}`}
            />
          </div>

          <div className={cardClass}>
            <label htmlFor="recap-format-template" className={labelClass}>
              Format template (advanced, optional)
            </label>
            <p className="mt-1 text-xs text-tsushin-slate">
              Optional Jinja template used to format each recalled case. Leave empty to use the platform default.
            </p>
            <textarea
              id="recap-format-template"
              rows={3}
              value={config.format_template}
              onChange={(event) => update({ format_template: event.target.value })}
              className={`mt-2 ${textareaClass}`}
              placeholder="{{ case.problem }} → {{ case.action }} → {{ case.outcome }}"
              spellCheck={false}
            />
          </div>

          <div className={`${cardClass} space-y-3`}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-white">Test recap</div>
                <p className="mt-0.5 text-xs text-tsushin-slate">
                  {triggerInstanceId == null
                    ? 'Save the trigger first to enable a live recap test.'
                    : 'Runs the rendered query against the configured vector store.'}
                </p>
              </div>
              <button
                type="button"
                onClick={handleTestRecap}
                disabled={triggerInstanceId == null || testing}
                className="rounded-lg border border-tsushin-border/70 bg-tsushin-surface/60 px-3 py-2 text-sm text-white transition-colors hover:border-tsushin-accent/50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {testing ? 'Testing…' : 'Test Recap'}
              </button>
            </div>
            {testError && (
              <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-300">
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
      )}
    </div>
  )
}
