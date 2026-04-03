'use client'

import { useState, useEffect } from 'react'
import type { BuilderMemoryData } from '../types'

interface MemoryConfigFormProps {
  nodeId: string
  data: BuilderMemoryData
  onUpdate: (nodeType: string, nodeId: string, config: Record<string, unknown>) => void
}

export default function MemoryConfigForm({ nodeId, data, onUpdate }: MemoryConfigFormProps) {
  const [isolationMode, setIsolationMode] = useState(data.isolationMode)
  const [memorySize, setMemorySize] = useState(data.memorySize)
  const [semanticSearch, setSemanticSearch] = useState(data.enableSemanticSearch)
  const [decayEnabled, setDecayEnabled] = useState(data.memoryDecayEnabled ?? false)
  const [decayLambda, setDecayLambda] = useState(data.memoryDecayLambda ?? 0.01)
  const [archiveThreshold, setArchiveThreshold] = useState(data.memoryDecayArchiveThreshold ?? 0.05)
  const [mmrLambda, setMmrLambda] = useState(data.memoryDecayMmrLambda ?? 0.5)

  useEffect(() => {
    setIsolationMode(data.isolationMode)
    setMemorySize(data.memorySize)
    setSemanticSearch(data.enableSemanticSearch)
    setDecayEnabled(data.memoryDecayEnabled ?? false)
    setDecayLambda(data.memoryDecayLambda ?? 0.01)
    setArchiveThreshold(data.memoryDecayArchiveThreshold ?? 0.05)
    setMmrLambda(data.memoryDecayMmrLambda ?? 0.5)
  }, [data.isolationMode, data.memorySize, data.enableSemanticSearch, data.memoryDecayEnabled, data.memoryDecayLambda, data.memoryDecayArchiveThreshold, data.memoryDecayMmrLambda])

  const propagate = (overrides: Record<string, unknown>) => {
    onUpdate('builder-memory', nodeId, {
      memoryIsolationMode: isolationMode,
      memorySize,
      enableSemanticSearch: semanticSearch,
      memoryDecayEnabled: decayEnabled,
      memoryDecayLambda: decayLambda,
      memoryDecayArchiveThreshold: archiveThreshold,
      memoryDecayMmrLambda: mmrLambda,
      ...overrides,
    })
  }

  const handleIsolationChange = (value: string) => {
    setIsolationMode(value)
    propagate({ memoryIsolationMode: value })
  }

  const handleSizeChange = (value: number) => {
    const clamped = Math.max(1, Math.min(5000, value))
    setMemorySize(clamped)
    propagate({ memorySize: clamped })
  }

  const handleSemanticToggle = (value: boolean) => {
    setSemanticSearch(value)
    propagate({ enableSemanticSearch: value })
  }

  const handleDecayToggle = (value: boolean) => {
    setDecayEnabled(value)
    propagate({ memoryDecayEnabled: value })
  }

  const handleDecayLambdaChange = (value: number) => {
    setDecayLambda(value)
    propagate({ memoryDecayLambda: value })
  }

  const handleArchiveThresholdChange = (value: number) => {
    setArchiveThreshold(value)
    propagate({ memoryDecayArchiveThreshold: value })
  }

  const handleMmrLambdaChange = (value: number) => {
    setMmrLambda(value)
    propagate({ memoryDecayMmrLambda: value })
  }

  return (
    <div className="space-y-4">
      <div className="config-field">
        <label>Isolation Mode</label>
        <select
          className="config-select"
          value={isolationMode}
          onChange={e => handleIsolationChange(e.target.value)}
        >
          <option value="isolated">Isolated (per sender)</option>
          <option value="shared">Shared (all senders)</option>
          <option value="channel_isolated">Channel Isolated</option>
        </select>
        <p className="field-help">Controls how memory is separated between conversations</p>
      </div>

      <div className="config-field">
        <label>Memory Size (messages per sender)</label>
        <input
          type="number"
          className="config-input"
          value={memorySize}
          min={1}
          max={5000}
          onChange={e => handleSizeChange(parseInt(e.target.value) || 1)}
        />
        <p className="field-help">Number of messages kept in the ring buffer (1-5000)</p>
      </div>

      <div className="config-field">
        <label>Semantic Search</label>
        <div className="flex items-center gap-3 mt-1">
          <button
            type="button"
            onClick={() => handleSemanticToggle(!semanticSearch)}
            className={`config-toggle ${semanticSearch ? 'active' : ''}`}
            role="switch"
            aria-checked={semanticSearch}
          >
            <span className="config-toggle-thumb" />
          </button>
          <span className="text-xs text-tsushin-slate">
            {semanticSearch ? 'Enabled' : 'Disabled'}
          </span>
        </div>
        <p className="field-help">Use vector embeddings for context-aware memory retrieval</p>
      </div>

      {/* Temporal Decay Section */}
      <div className="pt-3 border-t border-white/[0.06]">
        <div className="config-field">
          <label>Temporal Decay</label>
          <div className="flex items-center gap-3 mt-1">
            <button
              type="button"
              onClick={() => handleDecayToggle(!decayEnabled)}
              className={`config-toggle ${decayEnabled ? 'active' : ''}`}
              role="switch"
              aria-checked={decayEnabled}
            >
              <span className="config-toggle-thumb" />
            </button>
            <span className="text-xs text-tsushin-slate">
              {decayEnabled ? 'Enabled' : 'Disabled'}
            </span>
          </div>
          <p className="field-help">Apply exponential decay to memory relevance over time</p>
        </div>

        {decayEnabled && (
          <div className="space-y-4 mt-3">
            <div className="config-field">
              <label className="flex items-center justify-between">
                <span>Decay Rate</span>
                <span className="text-xs text-tsushin-slate font-mono">{decayLambda.toFixed(3)}</span>
              </label>
              <input
                type="range"
                className="w-full accent-sky-500 mt-1"
                min={0.001}
                max={1.0}
                step={0.001}
                value={decayLambda}
                onChange={e => handleDecayLambdaChange(parseFloat(e.target.value))}
              />
              <p className="field-help">Lower = slower decay. 0.01 ~ 69-day half-life</p>
            </div>

            <div className="config-field">
              <label className="flex items-center justify-between">
                <span>Archive Threshold</span>
                <span className="text-xs text-tsushin-slate font-mono">{archiveThreshold.toFixed(2)}</span>
              </label>
              <input
                type="range"
                className="w-full accent-sky-500 mt-1"
                min={0}
                max={1.0}
                step={0.01}
                value={archiveThreshold}
                onChange={e => handleArchiveThresholdChange(parseFloat(e.target.value))}
              />
              <p className="field-help">Facts below this score are auto-archived</p>
            </div>

            <div className="config-field">
              <label className="flex items-center justify-between">
                <span>MMR Diversity</span>
                <span className="text-xs text-tsushin-slate font-mono">{mmrLambda.toFixed(1)}</span>
              </label>
              <input
                type="range"
                className="w-full accent-sky-500 mt-1"
                min={0}
                max={1.0}
                step={0.1}
                value={mmrLambda}
                onChange={e => handleMmrLambdaChange(parseFloat(e.target.value))}
              />
              <p className="field-help">0 = max diversity, 1 = pure relevance</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
