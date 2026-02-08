'use client'
import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { BuilderSentinelData } from '../types'

function BuilderSentinelNode({ data, selected }: NodeProps) {
  const d = data as BuilderSentinelData
  return (
    <div role="group" aria-label={`Security: ${d.name}`}
      className={`builder-node builder-node-sentinel px-4 py-3 rounded-xl border transition-all duration-200 ${selected ? 'border-red-400 shadow-glow-sm' : 'border-tsushin-border hover:border-red-400/50'} bg-tsushin-surface`}>
      <Handle type="target" position={Position.Top} className="!bg-red-400 !border-tsushin-surface !w-3 !h-3" />
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-lg bg-red-500/20 flex items-center justify-center flex-shrink-0">
          <svg className="w-4 h-4 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" /></svg>
        </div>
        <div className="min-w-0">
          <p className="text-white text-sm font-medium truncate max-w-[140px]">{d.name}</p>
          <div className="flex items-center gap-1.5">
            <span className={`text-2xs px-1.5 py-0.5 rounded ${d.mode === 'enforce' || d.mode === 'block' ? 'bg-red-500/20 text-red-300' : 'bg-yellow-500/20 text-yellow-300'}`}>{d.mode}</span>
            {d.isSystem && <span className="text-2xs text-tsushin-muted">system</span>}
          </div>
        </div>
      </div>
    </div>
  )
}
export default memo(BuilderSentinelNode)
