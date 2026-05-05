'use client'

/**
 * AgentAdvancedManager — surfaces per-agent agentic-loop knobs (BUG-716).
 *
 * Two controls land in the Advanced tab:
 *   - max_agentic_rounds      (clamped to platform_min/max bounds from /api/config)
 *   - max_agentic_loop_bytes  (byte cap for the scratchpad payload)
 *
 * Backend already accepts both via PUT /api/agents/{id} after BUG-710 fix.
 */

import { useEffect, useState } from 'react'
import { api, Agent, Config } from '@/lib/client'
import { SettingsIcon, InfoIcon } from '@/components/ui/icons'

interface Props {
  agentId: number
}

const DEFAULT_MIN_ROUNDS = 1
const DEFAULT_MAX_ROUNDS = 8
const DEFAULT_LOOP_BYTES = 8192
const MIN_LOOP_BYTES = 512
const MAX_LOOP_BYTES = 131072

export default function AgentAdvancedManager({ agentId }: Props) {
  const [agent, setAgent] = useState<Agent | null>(null)
  const [config, setConfig] = useState<Config | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [maxAgenticRounds, setMaxAgenticRounds] = useState<number | null>(null)
  const [maxAgenticLoopBytes, setMaxAgenticLoopBytes] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  useEffect(() => {
    loadData()
  }, [agentId])

  const loadData = async () => {
    setLoading(true)
    setError(null)
    try {
      const [agentData, configData] = await Promise.all([
        api.getAgent(agentId),
        api.getConfig().catch(() => null),
      ])
      setAgent(agentData)
      setConfig(configData)
      setMaxAgenticRounds(agentData.max_agentic_rounds ?? null)
      setMaxAgenticLoopBytes(agentData.max_agentic_loop_bytes ?? null)
    } catch (err: any) {
      console.error('Failed to load agent advanced settings:', err)
      setError(err?.message || 'Failed to load advanced settings')
    } finally {
      setLoading(false)
    }
  }

  const platformMin = config?.platform_min_agentic_rounds ?? DEFAULT_MIN_ROUNDS
  const platformMax = config?.platform_max_agentic_rounds ?? DEFAULT_MAX_ROUNDS

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      // Clamp into platform bounds before sending so the API never has to
      // reject the payload for an out-of-range value the user set in the UI.
      let rounds: number | null = maxAgenticRounds
      if (rounds !== null && Number.isFinite(rounds)) {
        rounds = Math.max(platformMin, Math.min(platformMax, Math.round(rounds)))
      } else {
        rounds = null
      }

      let bytes: number | null = maxAgenticLoopBytes
      if (bytes !== null && Number.isFinite(bytes)) {
        bytes = Math.max(MIN_LOOP_BYTES, Math.min(MAX_LOOP_BYTES, Math.round(bytes)))
      } else {
        bytes = null
      }

      await api.updateAgent(agentId, {
        max_agentic_rounds: rounds,
        max_agentic_loop_bytes: bytes,
      })
      setSuccess('Advanced settings saved.')
      await loadData()
    } catch (err: any) {
      console.error('Failed to save advanced settings:', err)
      setError(err?.message || 'Failed to save advanced settings')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="p-8 text-center text-tsushin-slate">Loading advanced settings...</div>
  }

  if (!agent) {
    return <div className="p-8 text-center text-red-400">Failed to load agent.</div>
  }

  return (
    <div className="space-y-6">
      <div className="bg-blue-50 dark:bg-blue-900/20 border border-tsushin-border border-blue-200 dark:border-blue-700 rounded-lg p-4">
        <h3 className="text-sm font-medium text-blue-800 dark:text-blue-200 mb-2 flex items-center gap-1.5">
          <InfoIcon size={16} /> About Advanced Settings
        </h3>
        <p className="text-sm text-blue-700 dark:text-blue-300">
          Tune the bounded agentic loop for this agent. The agent may run up to
          <strong> max rounds</strong> tool calls per user turn, and the
          scratchpad payload it sees between rounds is capped at
          <strong> max bytes</strong>. Per-agent values are clamped to the
          platform-wide bounds defined under
          <em> Settings → AI Configuration → Platform AI</em>.
        </p>
      </div>

      {/* Agentic Loop */}
      <div className="bg-tsushin-surface border border-tsushin-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <SettingsIcon size={20} /> Agentic Loop
        </h3>

        <div className="space-y-6">
          <div>
            <label className="block text-sm font-medium mb-2">
              Max Agentic Rounds
              <span className="ml-2 text-xs text-tsushin-slate">
                (platform bounds: {platformMin} – {platformMax})
              </span>
            </label>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={platformMin}
                max={platformMax}
                step={1}
                value={maxAgenticRounds ?? platformMin}
                onChange={(e) => setMaxAgenticRounds(parseInt(e.target.value, 10))}
                className="flex-1"
              />
              <input
                type="number"
                min={platformMin}
                max={platformMax}
                value={maxAgenticRounds ?? ''}
                onChange={(e) => {
                  const v = e.target.value
                  if (v === '') {
                    setMaxAgenticRounds(null)
                  } else {
                    const n = parseInt(v, 10)
                    setMaxAgenticRounds(Number.isFinite(n) ? n : null)
                  }
                }}
                className="w-24 px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-ink"
                placeholder="—"
              />
              <button
                type="button"
                onClick={() => setMaxAgenticRounds(null)}
                className="text-xs text-tsushin-slate hover:text-white px-2 py-1 border border-tsushin-border rounded"
                title="Use platform default"
              >
                Reset
              </button>
            </div>
            <p className="text-xs text-tsushin-slate mt-2">
              Number of tool-using rounds the agent may take before answering. Set blank to use the platform default.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">
              Max Agentic Loop Bytes
              <span className="ml-2 text-xs text-tsushin-slate">
                ({MIN_LOOP_BYTES.toLocaleString()} – {MAX_LOOP_BYTES.toLocaleString()})
              </span>
            </label>
            <div className="flex items-center gap-3">
              <input
                type="number"
                min={MIN_LOOP_BYTES}
                max={MAX_LOOP_BYTES}
                step={512}
                value={maxAgenticLoopBytes ?? ''}
                onChange={(e) => {
                  const v = e.target.value
                  if (v === '') {
                    setMaxAgenticLoopBytes(null)
                  } else {
                    const n = parseInt(v, 10)
                    setMaxAgenticLoopBytes(Number.isFinite(n) ? n : null)
                  }
                }}
                placeholder={`${DEFAULT_LOOP_BYTES} (default)`}
                className="w-48 px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-ink"
              />
              <span className="text-xs text-tsushin-slate">bytes</span>
              <button
                type="button"
                onClick={() => setMaxAgenticLoopBytes(null)}
                className="text-xs text-tsushin-slate hover:text-white px-2 py-1 border border-tsushin-border rounded"
                title="Use default"
              >
                Reset
              </button>
            </div>
            <p className="text-xs text-tsushin-slate mt-2">
              Caps the JSON-encoded scratchpad payload fed back to the model between rounds. Lower this on small-context models.
            </p>
          </div>
        </div>
      </div>

      {(error || success) && (
        <div
          className={`p-4 rounded-lg border text-sm ${
            error
              ? 'bg-red-500/10 border-red-500/30 text-red-300'
              : 'bg-green-500/10 border-green-500/30 text-green-300'
          }`}
        >
          {error || success}
        </div>
      )}

      <div className="flex justify-end gap-3 pt-4 border-t border-tsushin-border">
        <button
          onClick={() => loadData()}
          disabled={saving}
          className="px-6 py-2 border border-tsushin-border rounded-md hover:bg-tsushin-surface disabled:opacity-50"
        >
          Reset
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="btn-primary px-6 py-2 rounded-md disabled:opacity-50 font-medium"
        >
          {saving ? 'Saving...' : 'Save Advanced Settings'}
        </button>
      </div>
    </div>
  )
}
