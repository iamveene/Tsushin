'use client'

import { memo, useCallback } from 'react'
import { type NodeProps } from '@xyflow/react'
import type { BuilderGhostAgentData } from '../types'

function BuilderGhostAgentNode({ data }: NodeProps) {
  const d = data as BuilderGhostAgentData

  const handleDoubleClick = useCallback(() => {
    d.onGhostDoubleClick?.(d.agentId)
  }, [d])

  return (
    <div
      role="group"
      aria-label={`Ghost Agent: ${d.agentName}`}
      className="builder-ghost-agent-node rounded-xl px-4 py-3"
      onDoubleClick={handleDoubleClick}
    >
      <div className="flex items-center gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-amber-200 font-medium text-xs truncate max-w-[130px]">{d.agentName}</p>
        </div>
        <span className="a2a-badge flex-shrink-0">A2A</span>
      </div>
    </div>
  )
}

export default memo(BuilderGhostAgentNode)
