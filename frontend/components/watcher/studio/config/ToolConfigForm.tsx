'use client'

import { useState, useEffect } from 'react'
import type { BuilderToolData } from '../types'

interface ToolConfigFormProps {
  nodeId: string
  data: BuilderToolData
  onUpdate: (nodeType: string, nodeId: string, config: Record<string, unknown>) => void
}

export default function ToolConfigForm({ nodeId, data, onUpdate }: ToolConfigFormProps) {
  const [isEnabled, setIsEnabled] = useState(data.isEnabled)

  useEffect(() => {
    setIsEnabled(data.isEnabled)
  }, [data.isEnabled])

  const handleToggle = () => {
    const next = !isEnabled
    setIsEnabled(next)
    onUpdate('builder-tool', nodeId, { toolId: data.toolId, isEnabled: next })
  }

  return (
    <div className="space-y-4">
      <div className="config-field">
        <label>Tool Name</label>
        <p className="text-sm text-white">{data.name}</p>
      </div>

      <div className="config-field">
        <label>Type</label>
        <p className="text-sm text-tsushin-slate">{data.toolType}</p>
      </div>

      <div className="config-field">
        <label>Enabled</label>
        <div className="flex items-center gap-3 mt-1">
          <button
            type="button"
            onClick={handleToggle}
            className={`config-toggle ${isEnabled ? 'active' : ''}`}
            role="switch"
            aria-checked={isEnabled}
          >
            <span className="config-toggle-thumb" />
          </button>
          <span className="text-xs text-tsushin-slate">
            {isEnabled ? 'Active' : 'Inactive'}
          </span>
        </div>
        <p className="field-help">Toggle this tool on or off for the agent</p>
      </div>
    </div>
  )
}
