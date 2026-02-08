'use client'
import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { BuilderToolData } from '../types'

function BuilderToolNode({ data, selected }: NodeProps) {
  const d = data as BuilderToolData
  return (
    <div role="group" aria-label={`Tool: ${d.name}`}
      className={`builder-node builder-node-tool px-4 py-3 rounded-xl border transition-all duration-200 ${selected ? 'border-orange-400 shadow-glow-sm' : 'border-tsushin-border hover:border-orange-400/50'} bg-tsushin-surface`}>
      <Handle type="target" position={Position.Top} className="!bg-orange-400 !border-tsushin-surface !w-3 !h-3" />
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-lg bg-orange-500/20 flex items-center justify-center flex-shrink-0">
          <svg className="w-4 h-4 text-orange-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 7.5l-2.25-1.313M21 7.5v2.25m0-2.25l-2.25 1.313M3 7.5l2.25-1.313M3 7.5l2.25 1.313M3 7.5v2.25m9 3l2.25-1.313M12 12.75l-2.25-1.313M12 12.75V15m0 6.75l2.25-1.313M12 21.75V19.5m0 2.25l-2.25-1.313m0-16.875L12 2.25l2.25 1.313M21 14.25v2.25l-2.25 1.313m-13.5 0L3 16.5v-2.25" /></svg>
        </div>
        <div className="min-w-0">
          <p className="text-white text-sm font-medium truncate max-w-[140px]">{d.name}</p>
          <p className="text-orange-300/70 text-xs">{d.toolType}</p>
          <span className={`text-2xs ${d.isEnabled ? 'text-green-400' : 'text-gray-500'}`}>{d.isEnabled ? 'Enabled' : 'Disabled'}</span>
        </div>
      </div>
    </div>
  )
}
export default memo(BuilderToolNode)
