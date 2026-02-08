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

  useEffect(() => {
    setIsolationMode(data.isolationMode)
    setMemorySize(data.memorySize)
    setSemanticSearch(data.enableSemanticSearch)
  }, [data.isolationMode, data.memorySize, data.enableSemanticSearch])

  const handleIsolationChange = (value: string) => {
    setIsolationMode(value)
    onUpdate('builder-memory', nodeId, { memoryIsolationMode: value, memorySize, enableSemanticSearch: semanticSearch })
  }

  const handleSizeChange = (value: number) => {
    const clamped = Math.max(1, Math.min(5000, value))
    setMemorySize(clamped)
    onUpdate('builder-memory', nodeId, { memoryIsolationMode: isolationMode, memorySize: clamped, enableSemanticSearch: semanticSearch })
  }

  const handleSemanticToggle = (value: boolean) => {
    setSemanticSearch(value)
    onUpdate('builder-memory', nodeId, { memoryIsolationMode: isolationMode, memorySize, enableSemanticSearch: value })
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
    </div>
  )
}
