'use client'

import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { BuilderAgentData } from '../types'

function BuilderAgentNode({ data, selected }: NodeProps) {
  const d = data as BuilderAgentData
  return (
    <div role="group" aria-label={`Agent: ${d.name}`}
      className={`builder-node builder-node-agent px-6 py-4 rounded-xl border-2 transition-all duration-200 ${selected ? 'border-tsushin-indigo shadow-glow-sm' : 'border-tsushin-indigo/40 hover:border-tsushin-indigo/70'} bg-tsushin-surface`}>
      <Handle type="source" position={Position.Right} className="!bg-tsushin-indigo !border-tsushin-surface !w-3 !h-3" />
      <Handle type="target" position={Position.Left} className="!bg-tsushin-accent !border-tsushin-surface !w-3 !h-3" />
      <div className="flex items-center gap-3 mb-3">
        <div className="w-10 h-10 rounded-lg bg-tsushin-indigo/20 flex items-center justify-center flex-shrink-0">
          <svg className="w-5 h-5 text-tsushin-indigo" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
          </svg>
        </div>
        <div className="min-w-0">
          <h3 className="text-white font-medium text-sm truncate max-w-[160px]">{d.name}</h3>
          <p className="text-tsushin-muted text-xs truncate max-w-[160px]">{d.modelProvider}/{d.modelName}</p>
        </div>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-2xs font-medium ${d.isActive ? 'bg-green-500/20 text-green-300' : 'bg-gray-500/20 text-gray-400'}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${d.isActive ? 'bg-green-400' : 'bg-gray-500'}`} />
          {d.isActive ? 'Active' : 'Inactive'}
        </span>
        {d.isDefault && <span className="inline-flex items-center px-2 py-0.5 rounded-full text-2xs font-medium bg-tsushin-indigo/20 text-tsushin-indigo">Default</span>}
        {d.enabledChannels.length > 0 && <span className="inline-flex items-center px-2 py-0.5 rounded-full text-2xs font-medium bg-cyan-500/20 text-cyan-300">{d.enabledChannels.length} ch</span>}
        {d.personaName && <span className="inline-flex items-center px-2 py-0.5 rounded-full text-2xs font-medium bg-purple-500/20 text-purple-300 truncate max-w-[100px]">{d.personaName}</span>}
      </div>
    </div>
  )
}

export default memo(BuilderAgentNode)
