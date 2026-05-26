'use client'

/**
 * Top-level modal for the Browser Recorder. Sits over BrowserAutomationConfigPanel
 * when the user clicks the "🎬 Record" CTA — on Save, calls `onApply(config)`
 * with a Partial<FlowStepConfig> the parent merges into the existing config
 * panel via its standard onChange contract. The user always gets a final
 * review pass in the manual editor before persisting the FlowNode.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Modal from '@/components/ui/Modal'
import PasswordVaultReferencePicker, {
  type PasswordVaultReferenceValue,
} from '@/components/password-vault/PasswordVaultReferencePicker'
import { api, type FlowStepConfig, type BrowserGroupCompiled } from '@/lib/client'
import AgenticTab from './AgenticTab'
import StreamCanvas, { type PointerInput, type KeyInput } from './StreamCanvas'
import StepLedger from './StepLedger'
import ToolPalette, { type MarkerMode } from './ToolPalette'
import {
  useRecorderSocket,
  type RecorderEventRow,
  type RecorderFrame,
} from './useRecorderSocket'

interface RecorderDialogProps {
  isOpen: boolean
  onClose: () => void
  // Legacy single-step merge — used by BrowserAutomationConfigPanel to
  // drop a compiled config_json into the existing single browser_automation
  // step's config form. Optional when onInsertGroup is provided.
  onApply?: (config: Partial<FlowStepConfig>) => void
  // v0.7.x Recorder UX: flow-level group insertion. When provided, the
  // Save button consumes the new `flow_group` compile shape (parent
  // browser_group + annotated children) and asks the parent to insert
  // them as new flow steps. This is the production-ready path; the
  // legacy onApply remains for the in-panel record-into-one-step flow.
  onInsertGroup?: (compiled: BrowserGroupCompiled) => void | Promise<void>
  // Deprecated: prefer url + onUrlChange for two-way binding. Kept for
  // legacy callers that seed the URL once and discard ownership.
  initialUrl?: string
  // Controlled URL mode. When `url` is provided, the dialog reflects
  // and reports changes to the parent — letting the wizard collect the
  // URL once and reuse it here without re-typing.
  url?: string
  onUrlChange?: (url: string) => void
  // When true, the in-dialog URL bar is hidden (the parent already
  // collected the URL upstream). Start/Go still work, driven by `url`.
  hideUrlBar?: boolean
}

export default function RecorderDialog({
  isOpen,
  onClose,
  onApply,
  onInsertGroup,
  initialUrl,
  url,
  onUrlChange,
  hideUrlBar,
}: RecorderDialogProps) {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [isClosing, setIsClosing] = useState(false)
  // Controlled when `url` is defined; otherwise we own the value locally
  // (legacy uncontrolled callers). `initialUrl` is treated as a one-shot
  // seed for the local state and ignored in controlled mode.
  const [localUrl, setLocalUrl] = useState<string>(initialUrl || '')
  const isControlled = url !== undefined
  const urlInput = isControlled ? (url as string) : localUrl
  const setUrlInput = useCallback((next: string) => {
    if (onUrlChange) onUrlChange(next)
    if (!isControlled) setLocalUrl(next)
  }, [isControlled, onUrlChange])
  const [bootError, setBootError] = useState<string | null>(null)
  const [events, setEvents] = useState<RecorderEventRow[]>([])
  const [savePending, setSavePending] = useState(false)
  const [markerMode, setMarkerMode] = useState<MarkerMode>(null)
  // Vault picker state — opened from a StepLedger "🔑 Vault?" chip.
  // Holds the selector of the row we're wiring so the marker.vault event
  // dispatched on accept targets the correct fill row.
  const [vaultTarget, setVaultTarget] = useState<{ selector: string; rowIndex: number } | null>(null)
  const [vaultDraft, setVaultDraft] = useState<PasswordVaultReferenceValue>({})
  const [agenticExpanded, setAgenticExpanded] = useState(false)
  const [agentPaused, setAgentPaused] = useState(false)
  // Derive agent-running from the event stream — the backend dispatches
  // "agent.start" / "agent.complete" / "agent.error" rows which the WS
  // relay surfaces. Keeps the state synced even if the UI reloads.
  const agentRunning = useMemo(() => {
    let running = false
    for (const ev of events) {
      if (ev.kind === 'agent.start') running = true
      else if (ev.kind === 'agent.complete' || ev.kind === 'agent.error' || ev.kind === 'agent.cancelled') running = false
    }
    return running
  }, [events])
  // Hold the latest frame outside React state to avoid re-rendering the whole
  // dialog at 10 fps — StreamCanvas reads through this ref via the `framePort`.
  const framePortRef = useRef<{ latestFrame: RecorderFrame | null }>({ latestFrame: null })

  const handleFrame = useCallback((frame: RecorderFrame) => {
    framePortRef.current.latestFrame = frame
  }, [])

  const handleSocketEvent = useCallback((event: RecorderEventRow) => {
    setEvents((prev) => [...prev, event])
  }, [])

  const handleSocketError = useCallback((message: string) => {
    setBootError(message)
  }, [])

  const { status, viewport, send, close } = useRecorderSocket({
    sessionId: sessionId || '',
    enabled: isOpen && !!sessionId,
    onFrame: handleFrame,
    onEvent: handleSocketEvent,
    onError: handleSocketError,
  })

  // Reset all state when the dialog is closed externally.
  useEffect(() => {
    if (!isOpen) {
      setSessionId(null)
      setEvents([])
      setBootError(null)
      setMarkerMode(null)
      framePortRef.current.latestFrame = null
    }
  }, [isOpen])

  // Safety net: if the dialog is closed without going through
  // handleDiscard (e.g. parent unmounts), fire a best-effort DELETE so the
  // tenant doesn't lose a recording slot. Awaited DELETE for explicit
  // Discard happens in handleDiscard below.
  useEffect(() => {
    if (!isOpen && sessionId) {
      api.deleteRecorderSession(sessionId).catch(() => { /* noop */ })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen])

  // Explicit Discard: await DELETE so the user can immediately start
  // another recording without hitting the per-tenant cap. Without this
  // wait, two quick "Discard → Start" cycles used to surface a 409.
  const handleDiscard = useCallback(async () => {
    if (isClosing) return
    if (sessionId) {
      setIsClosing(true)
      try {
        await api.deleteRecorderSession(sessionId)
      } catch {
        // Janitor reaps anything we leak.
      } finally {
        setSessionId(null)
        setIsClosing(false)
      }
    }
    onClose()
  }, [isClosing, onClose, sessionId])

  const handleStart = useCallback(async () => {
    setBootError(null)
    try {
      const resp = await api.startRecorderSession({
        initial_url: urlInput.trim() || undefined,
      })
      setSessionId(resp.session_id)
    } catch (err: any) {
      setBootError(err?.message || 'Failed to start session')
    }
  }, [urlInput])

  const handlePointer = useCallback((evt: PointerInput) => {
    send({
      type: 'input.mouse',
      action: evt.action,
      x: evt.x,
      y: evt.y,
      button: evt.button,
      deltaX: evt.deltaX,
      deltaY: evt.deltaY,
      modifiers: evt.modifiers,
    })
  }, [send])

  const handleKey = useCallback((evt: KeyInput) => {
    send({
      type: 'input.key',
      action: evt.action,
      key: evt.key,
      code: evt.code,
      modifiers: evt.modifiers,
    })
  }, [send])

  const handleText = useCallback((text: string) => {
    send({ type: 'input.text', text })
  }, [send])

  const handleRectMark = useCallback((rect: {
    x: number; y: number; width: number; height: number; kind: 'captcha' | 'extract'
  }) => {
    if (rect.kind === 'captcha') {
      send({ type: 'marker.captcha', x: rect.x, y: rect.y, width: rect.width, height: rect.height })
    } else {
      const asName = window.prompt('Variable name for this captured value:', 'captured_value') || 'captured_value'
      send({
        type: 'marker.extract',
        x: rect.x, y: rect.y, width: rect.width, height: rect.height,
        as: asName,
      })
    }
    setMarkerMode(null)
  }, [send])

  const handleNavigate = useCallback(() => {
    const trimmed = urlInput.trim()
    if (!trimmed) return
    send({ type: 'navigate', url: trimmed })
  }, [send, urlInput])

  const handleSave = useCallback(async () => {
    if (!sessionId) return
    setSavePending(true)
    try {
      const resp = await api.compileRecorderSession(sessionId)
      // When the parent has opted into group insertion AND the recorder
      // produced any compilable actions, insert the parent + children at
      // the flow level. Falls back to the legacy single-step merge if
      // the parent only provided onApply (BrowserAutomationConfigPanel),
      // or if the recording was empty enough that flow_group is null.
      if (onInsertGroup && resp.flow_group) {
        await onInsertGroup(resp.flow_group)
        onClose()
        return
      }
      if (onApply) {
        // Strip Phase 1 fallback diagnostic so it doesn't leak into the
        // saved FlowNode.config_json. Production compiler (Phase 2) doesn't
        // emit it.
        const cfg = { ...resp.config_json }
        delete (cfg as any)._recorder_events
        onApply(cfg)
        onClose()
        return
      }
      setBootError('Nothing to do — neither onInsertGroup nor onApply was wired.')
    } catch (err: any) {
      setBootError(err?.message || 'Compile failed')
    } finally {
      setSavePending(false)
    }
  }, [onApply, onClose, onInsertGroup, sessionId])

  const handleClear = useCallback(() => setEvents([]), [])

  const handleVaultRequest = useCallback((row: RecorderEventRow, index: number) => {
    const sel = String(row.payload?.selector || '').trim()
    if (!sel) return
    setVaultDraft({})
    setVaultTarget({ selector: sel, rowIndex: index })
  }, [])

  const handleVaultConfirm = useCallback(() => {
    if (!vaultTarget) return
    const ref = (vaultDraft.password_vault_reference || '').trim()
    if (!ref) {
      setBootError('Pick a vault entry before confirming.')
      return
    }
    send({
      type: 'marker.vault',
      selector: vaultTarget.selector,
      reference: ref,
    })
    setVaultTarget(null)
    setVaultDraft({})
  }, [send, vaultDraft.password_vault_reference, vaultTarget])

  const handleVaultCancel = useCallback(() => {
    setVaultTarget(null)
    setVaultDraft({})
  }, [])

  const statusBadge = (
    <span className={
      'inline-flex items-center gap-1.5 text-[10px] font-medium uppercase rounded px-2 py-0.5 ' +
      (status === 'open' ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30' :
       status === 'connecting' || status === 'authenticating' ? 'bg-amber-500/15 text-amber-300 border border-amber-500/30' :
       status === 'error' ? 'bg-red-500/15 text-red-300 border border-red-500/30' :
       'bg-slate-700/40 text-slate-400 border border-slate-600')
    }>
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {status}
    </span>
  )

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Record browser session" size="2xl" autoHeight>
      <div className="flex flex-col gap-3 h-[70vh] min-h-0">
        {/* URL bar — hidden when the parent already collected the URL */}
        {!hideUrlBar ? (
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium uppercase text-slate-400 shrink-0">URL</label>
            <input
              type="text"
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              placeholder="https://example.com/"
              className="flex-1 px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
            />
            {!sessionId ? (
              <button
                type="button"
                onClick={handleStart}
                disabled={!urlInput.trim() || isClosing}
                title={urlInput.trim() ? 'Spawn a live Chromium and begin capturing actions' : 'Enter a starting URL above to enable recording'}
                className="px-3 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 disabled:bg-slate-700 disabled:text-slate-500 disabled:cursor-not-allowed text-slate-900 text-xs font-semibold transition-colors"
              >
                Start recording
              </button>
            ) : (
              <button
                type="button"
                onClick={handleNavigate}
                className="px-3 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-white text-xs font-semibold transition-colors"
              >
                Go
              </button>
            )}
            {statusBadge}
          </div>
        ) : (
          <div className="flex items-center justify-between gap-2">
            <div className="text-[11px] text-slate-500">
              Recording <span className="text-slate-300 font-mono">{urlInput || '(no URL)'}</span>
            </div>
            <div className="flex items-center gap-2">
              {!sessionId && (
                <button
                  type="button"
                  onClick={handleStart}
                  disabled={!urlInput.trim() || isClosing}
                  className="px-3 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 disabled:bg-slate-700 disabled:text-slate-500 disabled:cursor-not-allowed text-slate-900 text-xs font-semibold transition-colors"
                >
                  Start recording
                </button>
              )}
              {statusBadge}
            </div>
          </div>
        )}

        {bootError && (
          <div className="px-3 py-2 rounded-lg border border-red-500/30 bg-red-500/10 text-xs text-red-300">
            {bootError}
          </div>
        )}

        {sessionId && (
          <>
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <ToolPalette markerMode={markerMode} onModeChange={setMarkerMode} />
              <button
                type="button"
                onClick={() => setAgenticExpanded((v) => !v)}
                className="text-[11px] text-slate-400 hover:text-cyan-300 inline-flex items-center gap-1 transition-colors"
                title="Have an LLM-driven Browser-Use agent drive the session instead of clicking yourself"
              >
                {agenticExpanded ? '▾' : '▸'} Agentic mode
              </button>
            </div>
            {agenticExpanded && (
              <AgenticTab
                sessionId={sessionId}
                agentRunning={agentRunning}
                agentPaused={agentPaused}
                onStarted={() => setAgentPaused(false)}
                onPaused={setAgentPaused}
              />
            )}
          </>
        )}

        {/* Two-pane layout: stream | step ledger */}
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-3 min-h-0">
          <div className="bg-slate-900 rounded-lg border border-slate-700 overflow-hidden p-2 flex items-center justify-center min-h-0">
            {sessionId ? (
              <StreamCanvas
                viewport={viewport}
                framePort={framePortRef.current}
                onPointer={handlePointer}
                onKey={handleKey}
                onText={handleText}
                onRectMark={handleRectMark}
                markerMode={markerMode}
              />
            ) : (
              <div className="text-center text-xs text-slate-500">
                <p className="mb-1">Enter a URL above and click <span className="text-slate-300">Start recording</span>.</p>
                <p>A live Chromium session opens here and every action is captured into the step list.</p>
              </div>
            )}
          </div>
          <div className="bg-slate-900 rounded-lg border border-slate-700 overflow-hidden min-h-0">
            <StepLedger events={events} onClear={handleClear} onVaultRequest={handleVaultRequest} />
          </div>
        </div>

        {/* Vault picker — opened from the 🔑 chip on a fill row that still
            holds plaintext. On confirm we dispatch marker.vault with the
            picker's op://-style reference and the targeted selector. */}
        <Modal
          isOpen={!!vaultTarget}
          onClose={handleVaultCancel}
          title="Wire a password vault entry"
          size="lg"
          autoHeight
          footer={
            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={handleVaultCancel}
                className="px-3 py-2 rounded-lg border border-slate-600 text-slate-300 text-xs hover:border-slate-500 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleVaultConfirm}
                disabled={!vaultDraft.password_vault_reference}
                className="px-3 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 disabled:bg-slate-700 disabled:text-slate-500 text-slate-900 text-xs font-semibold transition-colors"
              >
                Apply to step
              </button>
            </div>
          }
        >
          <div className="space-y-3">
            {vaultTarget && (
              <p className="text-xs text-slate-400">
                Targeting <code className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-200 font-mono text-[11px]">{vaultTarget.selector}</code>{' '}
                — the recorded plaintext value will be replaced with this vault reference at save.
              </p>
            )}
            <PasswordVaultReferencePicker value={vaultDraft} onChange={setVaultDraft} />
          </div>
        </Modal>

        {/* Footer */}
        <div className="flex items-center justify-between gap-2 pt-2 border-t border-slate-700">
          <p className="text-[11px] text-slate-500">
            Saved steps drop into the existing config panel for a final review pass — they don't auto-persist.
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleDiscard}
              disabled={isClosing}
              className="px-3 py-2 rounded-lg border border-slate-600 text-slate-300 text-xs hover:border-slate-500 hover:text-white disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
            >
              {isClosing ? 'Discarding…' : 'Discard'}
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={!sessionId || events.length === 0 || savePending}
              className="px-3 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 disabled:bg-slate-700 disabled:text-slate-500 text-slate-900 text-xs font-semibold transition-colors"
            >
              {savePending ? 'Saving…' : 'Save as flow step'}
            </button>
          </div>
        </div>
      </div>
    </Modal>
  )
}
