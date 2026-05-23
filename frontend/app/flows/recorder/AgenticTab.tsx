'use client'

/**
 * Agentic recording: an LLM-driven Browser-Use agent drives the same
 * Chromium session the human would. The user enters a high-level prompt,
 * watches the live stream, and can pause/resume or take over at any
 * point. The compiled output is bit-for-bit shaped like a human-driven
 * recording — same event_compiler reduces both.
 *
 * v1.1 surface: prompt input + start/pause/resume buttons. The agent
 * status is derived from `session.events` "agent.*" rows the StreamCanvas
 * caller already collects, so this component is presentational.
 */

import { useCallback, useState } from 'react'
import { api } from '@/lib/client'

interface AgenticTabProps {
  sessionId: string | null
  agentRunning: boolean
  agentPaused: boolean
  onStarted: () => void
  onPaused: (paused: boolean) => void
}

export default function AgenticTab({
  sessionId,
  agentRunning,
  agentPaused,
  onStarted,
  onPaused,
}: AgenticTabProps) {
  const [prompt, setPrompt] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleStart = useCallback(async () => {
    if (!sessionId || !prompt.trim()) return
    setBusy(true)
    setError(null)
    try {
      await api.startRecorderAgent(sessionId, { prompt: prompt.trim() })
      onStarted()
    } catch (err: any) {
      // 501 = browser-use not installed; surface a concrete hint
      const msg = err?.message || 'Failed to start agent'
      setError(
        err?.status === 501
          ? 'Agentic mode is unavailable on this backend (browser-use not installed). Manual record still works.'
          : msg
      )
    } finally {
      setBusy(false)
    }
  }, [onStarted, prompt, sessionId])

  const handlePauseToggle = useCallback(async () => {
    if (!sessionId) return
    setBusy(true)
    setError(null)
    try {
      const resp = await api.pauseRecorderAgent(sessionId)
      onPaused(resp.paused)
    } catch (err: any) {
      setError(err?.message || 'Failed to toggle pause')
    } finally {
      setBusy(false)
    }
  }, [onPaused, sessionId])

  return (
    <div className="space-y-3 p-3 bg-slate-900/60 rounded-lg border border-slate-700">
      <div>
        <label className="block text-xs font-medium uppercase text-slate-400 mb-1.5">
          Prompt
        </label>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          disabled={agentRunning}
          placeholder='e.g., "Track Correios package AD468811215BR and return the latest status"'
          rows={3}
          className="w-full px-3 py-2 bg-slate-800/50 border border-slate-600 rounded-lg text-white text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none disabled:opacity-60 resize-none"
        />
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        {!agentRunning ? (
          <button
            type="button"
            onClick={handleStart}
            disabled={!sessionId || !prompt.trim() || busy}
            className="px-3 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 disabled:bg-slate-700 disabled:text-slate-500 text-slate-900 text-xs font-semibold transition-colors"
          >
            {busy ? 'Starting…' : '▶ Start agent'}
          </button>
        ) : (
          <button
            type="button"
            onClick={handlePauseToggle}
            disabled={busy}
            className={
              'px-3 py-2 rounded-lg text-xs font-semibold transition-colors ' +
              (agentPaused
                ? 'bg-emerald-500 hover:bg-emerald-400 text-slate-900'
                : 'bg-amber-500 hover:bg-amber-400 text-slate-900')
            }
          >
            {agentPaused ? '▶ Resume' : '⏸ Pause'}
          </button>
        )}

        <span className={
          'inline-flex items-center gap-1.5 text-[10px] font-medium uppercase rounded px-2 py-0.5 border ' +
          (agentRunning
            ? (agentPaused
                ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                : 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30')
            : 'bg-slate-700/40 text-slate-400 border-slate-600')
        }>
          <span className="w-1.5 h-1.5 rounded-full bg-current" />
          {agentRunning ? (agentPaused ? 'Paused' : 'Driving') : 'Idle'}
        </span>
      </div>

      {error && (
        <p className="text-xs text-red-300">{error}</p>
      )}

      <p className="text-[11px] text-slate-500">
        While the agent drives you can still click on the stream to take over —
        the agent pauses automatically until you press Resume.
      </p>
    </div>
  )
}
