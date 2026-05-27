'use client'

/**
 * Compact, scrollable list of captured RecordedEvent rows. Each row shows
 * the action type, key payload fields, and a remove control so the user
 * can prune noise before saving.
 *
 * Display-only: actually deleting/editing rows in the *backend* event
 * list isn't supported in v1.0 (the user can edit the compiled selectors
 * in BrowserAutomationConfigPanel after Save). v1.x can add inline edit
 * once we have a Redux-style action log.
 */

import type { RecorderEventRow } from './useRecorderSocket'

interface StepLedgerProps {
  events: RecorderEventRow[]
  onClear?: () => void
  /** Invoked when the user clicks the "🔑 Vault?" chip on a fill row that
   * still holds plaintext. The parent opens PasswordVaultReferencePicker
   * targeting this row's selector. */
  onVaultRequest?: (row: RecorderEventRow, index: number) => void
}

const KIND_LABELS: Record<string, { label: string; tone: string }> = {
  navigate: { label: 'Navigate', tone: 'bg-blue-500/15 text-blue-300 border-blue-500/30' },
  click: { label: 'Click', tone: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' },
  fill: { label: 'Fill', tone: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30' },
  load: { label: 'Page load', tone: 'bg-slate-600/30 text-slate-300 border-slate-500/40' },
  'marker.captcha': { label: 'Captcha', tone: 'bg-amber-500/15 text-amber-300 border-amber-500/30' },
  'marker.extract': { label: 'Capture', tone: 'bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-500/30' },
  'marker.vault': { label: 'Vault', tone: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30' },
}

function summarize(row: RecorderEventRow): string {
  const p = row.payload || {}
  switch (row.kind) {
    case 'navigate':
      return p.url || '(no url)'
    case 'click':
      return p.selector || `(${p.x},${p.y})`
    case 'fill':
      if (typeof p.value === 'string' && p.value.startsWith('pvh_')) {
        return `${p.selector || 'input'} ← vault (${p.value.slice(0, 12)}…)`
      }
      return `${p.selector || 'input'} ← "${String(p.value || '').slice(0, 32)}"`
    case 'load':
      return p.url || ''
    case 'marker.captcha':
      return p.selector || `[${p.rect?.join?.(', ')}]`
    case 'marker.extract':
      return `${p.selector || ''} → ${p.as || 'captured_value'}`
    case 'marker.vault':
      return `${p.selector || ''} ← ${(p.reference || '').slice(0, 16)}…`
    default:
      return JSON.stringify(p).slice(0, 80)
  }
}

/**
 * BUG-769: the WebSocket stream emits one `fill` event per typed character
 * (Input.insertText fires per keystroke). Showing 13 rows for `AD468811215BR`
 * is unreadable and made it hard to spot when the selector resolution
 * actually worked. Coalesce sequential fills on the same selector into a
 * single ledger row carrying the cumulative value — matches what the
 * backend compiler already does in `_coalesce_fills` so what you see here
 * is what gets compiled.
 */
function coalesceForDisplay(events: RecorderEventRow[]): RecorderEventRow[] {
  const out: RecorderEventRow[] = []
  for (const row of events) {
    const prev = out[out.length - 1]
    if (
      prev &&
      row.kind === 'fill' &&
      prev.kind === 'fill' &&
      (row.payload?.selector || null) === (prev.payload?.selector || null)
    ) {
      const merged = {
        ...prev,
        payload: {
          ...prev.payload,
          value: String(prev.payload?.value || '') + String(row.payload?.value || ''),
          field_meta: row.payload?.field_meta || prev.payload?.field_meta,
        },
        ts: row.ts || prev.ts,
      }
      out[out.length - 1] = merged
      continue
    }
    out.push(row)
  }
  return out
}

export default function StepLedger({ events, onClear, onVaultRequest }: StepLedgerProps) {
  const visibleEvents = coalesceForDisplay(events)
  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          Captured steps ({visibleEvents.length})
        </h3>
        {onClear && events.length > 0 && (
          <button
            type="button"
            onClick={onClear}
            className="text-xs text-slate-400 hover:text-red-300 transition-colors"
          >
            Clear
          </button>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1 min-h-0">
        {visibleEvents.length === 0 ? (
          <p className="text-xs text-slate-500 px-2 py-4">
            Nothing recorded yet. Type a URL above and start clicking — actions appear here.
          </p>
        ) : (
          visibleEvents.map((row, index) => {
            const meta = KIND_LABELS[row.kind] || {
              label: row.kind,
              tone: 'bg-slate-700/30 text-slate-300 border-slate-600',
            }
            const isPassword =
              row.kind === 'fill' &&
              !String(row.payload?.value || '').startsWith('pvh_') &&
              ((row.payload?.field_meta?.type as string) === 'password')
            return (
              <div
                key={`${row.ts || index}-${index}`}
                className="flex items-start gap-2 px-2 py-1.5 rounded-md hover:bg-slate-800/60 transition-colors"
              >
                <span className="shrink-0 w-5 text-[10px] text-slate-500 font-mono pt-0.5">{index + 1}.</span>
                <span className={`shrink-0 inline-block text-[10px] font-medium uppercase rounded border px-1.5 py-0.5 ${meta.tone}`}>
                  {meta.label}
                </span>
                <span className="text-xs text-slate-300 break-all flex-1 min-w-0">
                  {summarize(row)}
                </span>
                {isPassword && (
                  onVaultRequest ? (
                    <button
                      type="button"
                      onClick={() => onVaultRequest(row, index)}
                      className="shrink-0 inline-block text-[10px] font-semibold rounded border border-yellow-500/40 bg-yellow-500/10 text-yellow-300 px-1.5 py-0.5 hover:bg-yellow-500/20 hover:border-yellow-400 transition-colors"
                      title="Click to pick a vault entry — the plaintext value gets swapped for a secret reference before save."
                    >
                      🔑 Vault?
                    </button>
                  ) : (
                    <span
                      className="shrink-0 inline-block text-[10px] font-semibold rounded border border-yellow-500/40 bg-yellow-500/10 text-yellow-300 px-1.5 py-0.5"
                      title="This looks like a credential field. Use the Vault tile to replace the plaintext value before saving."
                    >
                      🔑 Vault?
                    </span>
                  )
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
