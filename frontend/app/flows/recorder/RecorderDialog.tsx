'use client'

/**
 * Top-level modal for the Browser Recorder. Sits over BrowserAutomationConfigPanel
 * when the user clicks the "🎬 Record" CTA — on Save, calls `onApply(config)`
 * with a Partial<FlowStepConfig> the parent merges into the existing config
 * panel via its standard onChange contract. The user always gets a final
 * review pass in the manual editor before persisting the FlowNode.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import Modal from '@/components/ui/Modal'
import { api, type FlowStepConfig } from '@/lib/client'
import StreamCanvas, { type PointerInput, type KeyInput } from './StreamCanvas'
import StepLedger from './StepLedger'
import {
  useRecorderSocket,
  type RecorderEventRow,
  type RecorderFrame,
} from './useRecorderSocket'

interface RecorderDialogProps {
  isOpen: boolean
  onClose: () => void
  onApply: (config: Partial<FlowStepConfig>) => void
  initialUrl?: string
}

export default function RecorderDialog({
  isOpen,
  onClose,
  onApply,
  initialUrl,
}: RecorderDialogProps) {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [urlInput, setUrlInput] = useState<string>(initialUrl || '')
  const [bootError, setBootError] = useState<string | null>(null)
  const [events, setEvents] = useState<RecorderEventRow[]>([])
  const [savePending, setSavePending] = useState(false)
  const [markerMode, setMarkerMode] = useState<'captcha' | 'extract' | null>(null)
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

  // Teardown the backend session when the dialog closes (without Save).
  // The deleteRecorderSession call is fire-and-forget — janitor will sweep
  // any leak.
  useEffect(() => {
    if (!isOpen && sessionId) {
      api.deleteRecorderSession(sessionId).catch(() => { /* noop */ })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen])

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
      // Strip Phase 1 fallback diagnostic so it doesn't leak into the
      // saved FlowNode.config_json. Production compiler (Phase 2) doesn't
      // emit it.
      const cfg = { ...resp.config_json }
      delete (cfg as any)._recorder_events
      onApply(cfg)
      onClose()
    } catch (err: any) {
      setBootError(err?.message || 'Compile failed')
    } finally {
      setSavePending(false)
    }
  }, [onApply, onClose, sessionId])

  const handleClear = useCallback(() => setEvents([]), [])

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
        {/* URL bar */}
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium uppercase text-slate-400 shrink-0">URL</label>
          <input
            type="text"
            value={urlInput}
            onChange={(e) => setUrlInput(e.target.value)}
            placeholder="https://www.linkcorreios.com.br/"
            className="flex-1 px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
          />
          {!sessionId ? (
            <button
              type="button"
              onClick={handleStart}
              disabled={!urlInput.trim()}
              className="px-3 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 disabled:bg-slate-700 disabled:text-slate-500 text-slate-900 text-xs font-semibold transition-colors"
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

        {bootError && (
          <div className="px-3 py-2 rounded-lg border border-red-500/30 bg-red-500/10 text-xs text-red-300">
            {bootError}
          </div>
        )}

        {/* Tool palette — Phase 4 expands these (vault picker, etc.) */}
        {sessionId && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setMarkerMode(markerMode === 'captcha' ? null : 'captcha')}
              className={
                'px-2.5 py-1 rounded-md border text-xs font-medium transition-colors ' +
                (markerMode === 'captcha'
                  ? 'border-amber-400 bg-amber-500/20 text-amber-200'
                  : 'border-slate-600 bg-slate-800/50 text-slate-300 hover:border-amber-500/50 hover:text-amber-200')
              }
            >
              ▣ Mark captcha
            </button>
            <button
              type="button"
              onClick={() => setMarkerMode(markerMode === 'extract' ? null : 'extract')}
              className={
                'px-2.5 py-1 rounded-md border text-xs font-medium transition-colors ' +
                (markerMode === 'extract'
                  ? 'border-fuchsia-400 bg-fuchsia-500/20 text-fuchsia-200'
                  : 'border-slate-600 bg-slate-800/50 text-slate-300 hover:border-fuchsia-500/50 hover:text-fuchsia-200')
              }
            >
              👁 Capture output
            </button>
            {markerMode && (
              <span className="text-xs text-slate-400 italic">
                Drag a box over the {markerMode === 'captcha' ? 'captcha image' : 'text to capture'}…
              </span>
            )}
          </div>
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
            <StepLedger events={events} onClear={handleClear} />
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between gap-2 pt-2 border-t border-slate-700">
          <p className="text-[11px] text-slate-500">
            Saved steps drop into the existing config panel for a final review pass — they don't auto-persist.
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-2 rounded-lg border border-slate-600 text-slate-300 text-xs hover:border-slate-500 hover:text-white transition-colors"
            >
              Discard
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
