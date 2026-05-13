'use client'

import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { UsersIcon } from '@/components/ui/icons'
import type { TeamCoordinatorNodeData } from './types'

function TeamCoordinatorNode({ data, selected }: NodeProps) {
  const d = data as TeamCoordinatorNodeData

  return (
    <div
      role="group"
      aria-label={`Team coordinator: ${d.label}`}
      className={`team-node team-coordinator-node rounded-lg border px-5 py-4 transition-all ${
        selected ? 'border-tsushin-accent shadow-glow-sm' : 'border-tsushin-accent/50 hover:border-tsushin-accent'
      }`}
    >
      <Handle type="source" position={Position.Bottom} className="team-handle team-handle-coordinator" />
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-tsushin-accent/40 bg-tsushin-accent/10 text-tsushin-accent">
          <UsersIcon size={19} />
        </div>
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-white">{d.label}</h3>
          <p className="mt-1 truncate text-xs text-tsushin-slate">{d.detail}</p>
        </div>
      </div>
    </div>
  )
}

export default memo(TeamCoordinatorNode)
