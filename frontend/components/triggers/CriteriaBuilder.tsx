'use client'

import { useState } from 'react'
import type { TriggerCriteria } from '@/lib/client'
import { CheckCircleIcon, FilterIcon, PlayIcon, XCircleIcon } from '@/components/ui/icons'

export interface CriteriaTestResult {
  matched: boolean
  reason?: string | null
}

interface Props {
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  onTest?: (criteria: TriggerCriteria | null, payload: Record<string, unknown>) => Promise<CriteriaTestResult>
}

const DEFAULT_CRITERIA = {
  criteria_version: 1,
  filters: {
    jsonpath_matchers: [
      {
        path: '$.type',
        operator: 'equals',
        value: 'incident',
      },
    ],
  },
  window: {
    mode: 'since_cursor',
  },
  ordering: 'oldest_first',
  dedupe_scope: 'instance',
}

const DEFAULT_PAYLOAD = {
  type: 'incident',
  source: 'preview',
}

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2)
}

export function formatCriteriaText(value?: TriggerCriteria | null): string {
  return value ? pretty(value) : ''
}

export function parseCriteriaText(text: string): TriggerCriteria | null {
  const trimmed = text.trim()
  if (!trimmed) return null
  const parsed = JSON.parse(trimmed)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Criteria must be a JSON object')
  }
  return parsed as TriggerCriteria
}

function parsePayloadText(text: string): Record<string, unknown> {
  const parsed = JSON.parse(text)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Payload must be a JSON object')
  }
  return parsed as Record<string, unknown>
}

export default function CriteriaBuilder({ value, onChange, disabled = false, onTest }: Props) {
  const [payloadText, setPayloadText] = useState(pretty(DEFAULT_PAYLOAD))
  const [testing, setTesting] = useState(false)
  const [message, setMessage] = useState<{ tone: 'success' | 'error' | 'info'; text: string } | null>(null)

  const applyTemplate = () => {
    onChange(pretty(DEFAULT_CRITERIA))
    setMessage({ tone: 'info', text: 'JSONPath template inserted.' })
  }

  const clearCriteria = () => {
    onChange('')
    setMessage(null)
  }

  const testCriteria = async () => {
    if (!onTest || testing) return
    setTesting(true)
    setMessage(null)
    try {
      const criteria = parseCriteriaText(value)
      const payload = parsePayloadText(payloadText)
      const result = await onTest(criteria, payload)
      setMessage({
        tone: result.matched ? 'success' : 'error',
        text: result.matched ? 'Criteria matched the payload.' : `No match${result.reason ? `: ${result.reason}` : ''}.`,
      })
    } catch (error: unknown) {
      setMessage({ tone: 'error', text: error instanceof Error ? error.message : 'Criteria test failed' })
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
          <FilterIcon size={16} /> Criteria
        </h3>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={applyTemplate}
            disabled={disabled}
            className="rounded border border-cyan-500/40 bg-cyan-500/10 px-3 py-1.5 text-xs text-cyan-200 hover:text-white disabled:opacity-50"
          >
            JSONPath Template
          </button>
          <button
            type="button"
            onClick={clearCriteria}
            disabled={disabled}
            className="rounded border border-tsushin-border bg-transparent px-3 py-1.5 text-xs text-tsushin-slate hover:text-white disabled:opacity-50"
          >
            Clear
          </button>
        </div>
      </div>

      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={7}
        disabled={disabled}
        placeholder={pretty(DEFAULT_CRITERIA)}
        className="w-full rounded-xl border border-tsushin-border bg-black/25 px-3 py-2 font-mono text-xs text-white placeholder:text-tsushin-slate focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/30 disabled:opacity-60"
      />

      {onTest && (
        <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
          <div>
            <label className="mb-2 block text-xs font-medium text-tsushin-slate">Test payload</label>
            <textarea
              value={payloadText}
              onChange={(event) => setPayloadText(event.target.value)}
              rows={5}
              disabled={disabled}
              className="w-full rounded-xl border border-tsushin-border bg-black/25 px-3 py-2 font-mono text-xs text-white focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/30 disabled:opacity-60"
            />
          </div>
          <button
            type="button"
            onClick={testCriteria}
            disabled={disabled || testing}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-tsushin-border bg-tsushin-surface px-4 py-2 text-sm text-tsushin-fog hover:text-white disabled:opacity-50"
          >
            <PlayIcon size={14} />
            {testing ? 'Testing...' : 'Test Criteria'}
          </button>
        </div>
      )}

      {message && (
        <div className={`mt-3 flex items-start gap-2 rounded-lg border px-3 py-2 text-xs ${
          message.tone === 'success'
            ? 'border-green-500/30 bg-green-500/10 text-green-200'
            : message.tone === 'error'
            ? 'border-red-500/30 bg-red-500/10 text-red-200'
            : 'border-cyan-500/30 bg-cyan-500/10 text-cyan-200'
        }`}>
          {message.tone === 'success' ? <CheckCircleIcon size={14} className="mt-0.5 shrink-0" /> : <XCircleIcon size={14} className="mt-0.5 shrink-0" />}
          <span>{message.text}</span>
        </div>
      )}
    </div>
  )
}
