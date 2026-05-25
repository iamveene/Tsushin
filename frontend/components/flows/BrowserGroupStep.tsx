'use client'

/**
 * BrowserGroupStep — collapsible card that bundles the consecutive
 * `browser_automation` steps compiled from one recorder session.
 *
 * Used in two surfaces:
 *   - mode="edit": flow editor step list, lets the user expand to see
 *     per-action thumbnails recorded at capture time, and ungroup if
 *     they want flat editing.
 *   - mode="run":  watcher run-detail modal, additionally shows each
 *     child's runtime screenshot from FlowNodeRun.output_json side-by-side
 *     with the recorded thumbnail for visual auditing.
 *
 * Both modes share the same header layout (host, child count, human/agent
 * badge, recorded-at) and the same expand chevron, modelled after
 * components/watcher/studio/nodes/BuilderGroupNode but adapted for the
 * vertical step list rather than a node-graph canvas.
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { GlobeIcon } from '@/components/ui/icons'
import { formatRelative as formatRelativeUtil } from '@/lib/dateUtils'
import type { RecordedDriverLabel } from '@/lib/client'

export interface BrowserGroupChild {
  // Display label for the row (e.g. "navigate", "fill q", "solve_captcha").
  label: string
  // tool_action from config_json — drives the small action chip color.
  toolAction?: string
  // Recorded JPEG (base64), captured at the moment of the source event.
  recordedScreenshotB64?: string | null
  // Runtime screenshot path or base64 (mode="run" only) — pulled from
  // FlowNodeRun.output_json. Optional; not all runs persist one.
  runtimeScreenshot?: string | null
  // run-mode status: lets the row chip show pass/fail without re-deriving.
  status?: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  // run-mode error blurb if status==='failed'.
  errorText?: string | null
}

export interface BrowserGroupStepProps {
  mode: 'edit' | 'run'
  targetHost: string
  driver: RecordedDriverLabel
  recordedAt?: string | null
  childCount: number
  children: BrowserGroupChild[]
  // Optional banner shown above the children when the group was
  // synthesized from legacy flat steps (no real browser_group parent).
  // Click "Save flow" to persist the grouping.
  syntheticHint?: boolean
  // Optional callbacks — edit mode only. mode="run" ignores these.
  onUngroup?: () => void
  // Whether the group should start expanded. Defaults to collapsed.
  defaultExpanded?: boolean
  // v0.7.x inline child editing (edit mode only):
  //   - `editingChildIdx`: index of the child currently being edited;
  //     -1 / null means none.
  //   - `onChildClick`: invoked when the user clicks a child row's header.
  //     Parent toggles `editingChildIdx` to expand/collapse the editor.
  //   - `renderChildEditor`: render the existing EditableStepConfigForm
  //     (or any other config UI) for the open child. Returning null
  //     keeps the row collapsed.
  // Same callbacks apply to both human and agentic recordings — once
  // compiled, the children are plain browser_automation steps.
  editingChildIdx?: number | null
  onChildClick?: (childIdx: number) => void
  renderChildEditor?: (childIdx: number, child: BrowserGroupChild) => ReactNode
}

const DRIVER_BADGE: Record<RecordedDriverLabel, { label: string; cls: string }> = {
  human: {
    label: 'Human',
    cls: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30',
  },
  agent: {
    label: 'Agent',
    cls: 'bg-violet-500/10 text-violet-300 border-violet-500/30',
  },
  mixed: {
    label: 'Mixed',
    cls: 'bg-amber-500/10 text-amber-300 border-amber-500/30',
  },
}

function actionChipClass(action: string | undefined): string {
  switch (action) {
    case 'navigate':
      return 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/30'
    case 'fill':
      return 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/30'
    case 'click':
      return 'bg-sky-500/10 text-sky-300 border border-sky-500/30'
    case 'solve_captcha':
      return 'bg-amber-500/10 text-amber-300 border border-amber-500/30'
    case 'extract':
      return 'bg-fuchsia-500/10 text-fuchsia-300 border border-fuchsia-500/30'
    case 'wait_for_url':
      return 'bg-slate-500/10 text-slate-300 border border-slate-500/30'
    default:
      return 'bg-slate-500/10 text-slate-300 border border-slate-500/30'
  }
}

function statusChipClass(status: BrowserGroupChild['status']): string {
  switch (status) {
    case 'completed':
      return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
    case 'failed':
      return 'bg-rose-500/15 text-rose-300 border-rose-500/30'
    case 'running':
      return 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30 animate-pulse'
    case 'cancelled':
      return 'bg-slate-500/15 text-slate-300 border-slate-500/30'
    default:
      return 'bg-slate-500/15 text-slate-400 border-slate-500/30'
  }
}

function Thumb({ src, alt, label }: { src?: string | null; alt: string; label: string }) {
  if (!src) {
    return (
      <div
        className="w-32 h-20 rounded-md border border-slate-700 bg-slate-800/60 flex items-center justify-center text-[10px] text-slate-500 italic"
        title={`${label}: not captured`}
      >
        {label}: —
      </div>
    )
  }
  const href = src.startsWith('data:') || src.startsWith('http') || src.startsWith('/')
    ? src
    : `data:image/jpeg;base64,${src}`
  return (
    <div className="flex flex-col gap-1">
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="block w-32 h-20 rounded-md border border-slate-700 overflow-hidden hover:border-cyan-500 transition-colors"
        title={`${label} (open full size)`}
      >
        <img src={href} alt={alt} className="w-full h-full object-cover object-top" />
      </a>
      <span className="text-[10px] text-slate-500 text-center">{label}</span>
    </div>
  )
}

export default function BrowserGroupStep({
  mode,
  targetHost,
  driver,
  recordedAt,
  childCount,
  children,
  syntheticHint,
  onUngroup,
  defaultExpanded,
  editingChildIdx,
  onChildClick,
  renderChildEditor,
}: BrowserGroupStepProps) {
  const [expanded, setExpanded] = useState<boolean>(Boolean(defaultExpanded))

  const driverBadge = DRIVER_BADGE[driver] ?? DRIVER_BADGE.human
  const relativeRecordedAt = useMemo(() => {
    if (!recordedAt) return null
    try {
      return formatRelativeUtil(recordedAt)
    } catch {
      return null
    }
  }, [recordedAt])

  // v0.7.x UX polish: when a child opens its inline editor, scroll the
  // editing row into view so the form is never off-screen below the fold.
  // `editingChildIdx` is the auth source; the effect targets the row's
  // ref by index.
  const childRowRefs = useRef<Array<HTMLDivElement | null>>([])
  useEffect(() => {
    if (mode !== 'edit') return
    if (editingChildIdx == null || editingChildIdx < 0) return
    const el = childRowRefs.current[editingChildIdx]
    if (!el) return
    // Smooth scroll so the editor lands centered in the viewport.
    // requestAnimationFrame waits one tick for the editor to mount + lay out.
    requestAnimationFrame(() => {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    })
  }, [editingChildIdx, mode])

  return (
    <div
      data-testid="browser-group-step"
      className={`rounded-xl border transition-all ${
        expanded
          ? 'border-cyan-500/60 bg-gradient-to-br from-slate-700/50 to-slate-800/60 shadow-glow-sm'
          : 'border-slate-700 bg-slate-700/30 hover:border-cyan-500/40'
      }`}
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full p-4 flex items-center gap-4 text-left"
      >
        <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-cyan-500/30 to-sky-500/30 border border-cyan-500/40 flex items-center justify-center text-cyan-300">
          <GlobeIcon size={20} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="font-medium text-white flex items-center gap-2 flex-wrap">
            <span className="truncate">
              {targetHost && targetHost !== 'browser session'
                ? `Browser session · ${targetHost}`
                : 'Browser session'}
            </span>
            <span
              className={`text-xs px-2 py-0.5 rounded-full border ${driverBadge.cls}`}
              title={`Recording driver: ${driverBadge.label}`}
            >
              {driverBadge.label}
            </span>
            <span className="text-xs px-2 py-0.5 rounded-full border border-slate-600 bg-slate-700/40 text-slate-300">
              {childCount} step{childCount !== 1 ? 's' : ''}
            </span>
            {syntheticHint ? (
              <span
                className="text-xs px-2 py-0.5 rounded-full border border-amber-500/30 bg-amber-500/10 text-amber-300"
                title="Auto-grouped from legacy flat browser steps. Save the flow to persist this grouping."
              >
                Auto-grouped — save to persist
              </span>
            ) : null}
          </div>
          {relativeRecordedAt ? (
            <div className="text-sm text-slate-400">Recorded {relativeRecordedAt}</div>
          ) : (
            <div className="text-sm text-slate-400">Recorded browser flow</div>
          )}
        </div>

        {mode === 'edit' && onUngroup ? (
          <span
            role="button"
            tabIndex={0}
            onClick={(e) => {
              e.stopPropagation()
              onUngroup()
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.stopPropagation()
                onUngroup()
              }
            }}
            className="text-xs px-3 py-1.5 rounded-md border border-slate-600 text-slate-300 hover:border-cyan-500/50 hover:text-white transition-colors cursor-pointer"
            title="Flatten back to individual browser_automation steps for granular editing — children stay, only the group wrapper is removed"
          >
            Flatten
          </span>
        ) : null}

        <svg
          className={`w-5 h-5 text-slate-400 transition-transform ${expanded ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded ? (
        <div className="border-t border-slate-700/70 px-4 py-3 space-y-2 bg-slate-900/40 rounded-b-xl">
          {children.length === 0 ? (
            <div className="text-sm text-slate-500 italic p-4 text-center">
              This group has no child steps yet.
            </div>
          ) : (
            children.map((child, idx) => {
              const isEditable = mode === 'edit' && !!onChildClick
              const isEditing = mode === 'edit' && editingChildIdx === idx
              const editor = isEditing && renderChildEditor ? renderChildEditor(idx, child) : null
              return (
                <div
                  key={idx}
                  ref={(el) => { childRowRefs.current[idx] = el }}
                  className={`rounded-lg border bg-slate-800/40 transition-colors ${
                    isEditing
                      ? 'border-cyan-500/60'
                      : 'border-slate-700/50 hover:border-slate-600/70'
                  }`}
                >
                  <div
                    className={`flex items-start gap-3 p-3 ${isEditable ? 'cursor-pointer' : ''}`}
                    role={isEditable ? 'button' : undefined}
                    tabIndex={isEditable ? 0 : undefined}
                    onClick={(e) => {
                      if (!isEditable) return
                      e.stopPropagation()
                      onChildClick!(idx)
                    }}
                    onKeyDown={(e) => {
                      if (!isEditable) return
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        e.stopPropagation()
                        onChildClick!(idx)
                      }
                    }}
                    title={isEditable ? (isEditing ? 'Click to collapse' : 'Click to edit this step') : undefined}
                  >
                    <div className="flex flex-col items-center gap-1 pt-1 w-8">
                      <span className="text-xs font-mono text-slate-500">{idx + 1}</span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-2">
                        {child.toolAction ? (
                          <span className={`text-xs font-mono px-2 py-0.5 rounded-md ${actionChipClass(child.toolAction)}`}>
                            {child.toolAction}
                          </span>
                        ) : null}
                        <span className="text-sm text-slate-200 truncate">{child.label}</span>
                        {mode === 'run' && child.status ? (
                          <span
                            className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-md border ${statusChipClass(child.status)}`}
                          >
                            {child.status}
                          </span>
                        ) : null}
                        {isEditable ? (
                          <span className="ml-auto text-[10px] uppercase tracking-wide text-cyan-400">
                            {isEditing ? '▾ editing' : 'edit'}
                          </span>
                        ) : null}
                      </div>
                      {mode === 'run' && child.errorText ? (
                        <div className="text-xs text-rose-300 bg-rose-500/5 border border-rose-500/20 rounded-md px-2 py-1 mb-2 break-words">
                          {child.errorText}
                        </div>
                      ) : null}
                      <div className="flex flex-wrap gap-3">
                        <Thumb
                          src={child.recordedScreenshotB64}
                          alt={`Recorded screenshot for step ${idx + 1}`}
                          label="recorded"
                        />
                        {mode === 'run' ? (
                          <Thumb
                            src={child.runtimeScreenshot}
                            alt={`Runtime screenshot for step ${idx + 1}`}
                            label="runtime"
                          />
                        ) : null}
                      </div>
                    </div>
                  </div>
                  {editor ? (
                    <div className="border-t border-cyan-500/30 px-4 py-3 bg-slate-900/40 rounded-b-lg">
                      {editor}
                    </div>
                  ) : null}
                </div>
              )
            })
          )}
        </div>
      ) : null}
    </div>
  )
}
