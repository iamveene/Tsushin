'use client'

import { useState } from 'react'
import { api } from '@/lib/client'
import type { AgentCommPermission } from '@/lib/client'

interface A2APermissionConfigFormProps {
  sourceAgentId: number
  targetAgentId: number
  permission: AgentCommPermission | null
  onClose: () => void
  onSaved: (updated: AgentCommPermission) => void
}

export default function A2APermissionConfigForm({
  sourceAgentId,
  targetAgentId,
  permission,
  onClose,
  onSaved,
}: A2APermissionConfigFormProps) {
  const [isEnabled, setIsEnabled] = useState(permission?.is_enabled ?? true)
  const [maxDepth, setMaxDepth] = useState(permission?.max_depth ?? 3)
  const [rateLimitRpm, setRateLimitRpm] = useState(permission?.rate_limit_rpm ?? 60)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSave = async () => {
    setIsSaving(true)
    setError(null)
    try {
      let result: AgentCommPermission
      if (permission) {
        result = await api.updateAgentCommPermission(permission.id, {
          is_enabled: isEnabled,
          max_depth: maxDepth,
          rate_limit_rpm: rateLimitRpm,
        })
      } else {
        result = await api.createAgentCommPermission({
          source_agent_id: sourceAgentId,
          target_agent_id: targetAgentId,
          max_depth: maxDepth,
          rate_limit_rpm: rateLimitRpm,
        })
      }
      onSaved(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save permission')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 pb-2 border-b border-tsushin-border">
        <button onClick={onClose} className="p-1 rounded hover:bg-tsushin-surface text-tsushin-slate hover:text-white transition-colors">
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
          </svg>
        </button>
        <span className="text-xs font-medium text-amber-400">A2A Permission</span>
      </div>

      {/* Enable toggle */}
      <div className="config-field">
        <label>Enabled</label>
        <button
          onClick={() => setIsEnabled(!isEnabled)}
          className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${isEnabled ? 'bg-amber-500' : 'bg-tsushin-surface border border-tsushin-border'}`}
        >
          <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow transform transition-transform ${isEnabled ? 'translate-x-4' : 'translate-x-0.5'}`} />
        </button>
      </div>

      {/* Max depth slider */}
      <div className="config-field">
        <label>Max Depth <span className="text-amber-400 font-semibold">{maxDepth}</span></label>
        <input
          type="range"
          min={1}
          max={5}
          value={maxDepth}
          onChange={e => setMaxDepth(Number(e.target.value))}
          className="w-full accent-amber-500"
        />
        <div className="flex justify-between text-[10px] text-tsushin-muted">
          <span>1</span><span>2</span><span>3</span><span>4</span><span>5</span>
        </div>
      </div>

      {/* Rate limit */}
      <div className="config-field">
        <label>Rate Limit (req/min)</label>
        <input
          type="number"
          min={1}
          max={1000}
          value={rateLimitRpm}
          onChange={e => setRateLimitRpm(Math.max(1, Number(e.target.value)))}
          className="config-input w-full"
        />
      </div>

      {error && (
        <p className="text-xs text-red-400">{error}</p>
      )}

      <button
        onClick={handleSave}
        disabled={isSaving}
        className={`w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${isSaving ? 'opacity-60 cursor-wait' : 'bg-amber-500/20 text-amber-300 hover:bg-amber-500/30'}`}
      >
        {isSaving ? 'Saving...' : permission ? 'Save Changes' : 'Create Permission'}
      </button>
    </div>
  )
}
