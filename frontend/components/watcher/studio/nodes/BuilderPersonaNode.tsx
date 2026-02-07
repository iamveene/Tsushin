'use client'
import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { BuilderPersonaData } from '../types'

function BuilderPersonaNode({ data, selected }: NodeProps) {
  const d = data as BuilderPersonaData
  return (
    <div role="group" aria-label={`Persona: ${d.name}`}
      className={`builder-node builder-node-persona px-4 py-3 rounded-xl border transition-all duration-200 ${selected ? 'border-purple-400 shadow-glow-sm' : 'border-tsushin-border hover:border-purple-400/50'} bg-tsushin-surface`}>
      <Handle type="source" position={Position.Right} className="!bg-purple-400 !border-tsushin-surface !w-3 !h-3" />
      <Handle type="target" position={Position.Left} className="!bg-purple-400 !border-tsushin-surface !w-3 !h-3" />
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-lg bg-purple-500/20 flex items-center justify-center flex-shrink-0">
          <svg className="w-4 h-4 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" /></svg>
        </div>
        <div className="min-w-0">
          <p className="text-white text-sm font-medium truncate max-w-[140px]">{d.name}</p>
          {d.role && <p className="text-purple-300/70 text-xs truncate max-w-[140px]">{d.role}</p>}
          {d.personalityTraits && <p className="text-tsushin-muted text-2xs truncate max-w-[140px] mt-0.5">{d.personalityTraits}</p>}
        </div>
      </div>
    </div>
  )
}
export default memo(BuilderPersonaNode)
