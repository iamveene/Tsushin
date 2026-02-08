'use client'
import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { BuilderSkillData } from '../types'

function BuilderSkillNode({ data, selected }: NodeProps) {
  const d = data as BuilderSkillData
  return (
    <div role="group" aria-label={`Skill: ${d.skillName}`}
      className={`builder-node builder-node-skill px-4 py-3 rounded-xl border transition-all duration-200 ${selected ? 'border-teal-400 shadow-glow-sm' : 'border-tsushin-border hover:border-teal-400/50'} bg-tsushin-surface`}>
      <Handle type="target" position={Position.Top} className="!bg-teal-400 !border-tsushin-surface !w-3 !h-3" />
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-lg bg-teal-500/20 flex items-center justify-center flex-shrink-0">
          <svg className="w-4 h-4 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.42 15.17l-5.1-3.06a1 1 0 01-.42-.83V7.06a1 1 0 01.42-.83l5.1-3.06a1 1 0 011.16 0l5.1 3.06a1 1 0 01.42.83v4.22a1 1 0 01-.42.83l-5.1 3.06a1 1 0 01-1.16 0z" /></svg>
        </div>
        <div className="min-w-0">
          <p className="text-white text-sm font-medium truncate max-w-[140px]">{d.skillName}</p>
          {d.category && <p className="text-teal-300/70 text-xs">{d.category}</p>}
          {d.providerName && <p className="text-tsushin-muted text-2xs truncate max-w-[140px]">{d.providerName}</p>}
        </div>
      </div>
    </div>
  )
}
export default memo(BuilderSkillNode)
