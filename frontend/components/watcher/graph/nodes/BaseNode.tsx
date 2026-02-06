'use client'

/**
 * BaseNode - Foundation node component for graph visualization
 * Provides consistent styling for all node types
 */

import { memo, ReactNode } from 'react'
import { Handle, Position, NodeProps } from '@xyflow/react'
import { GraphNodeData } from '../types'

interface BaseNodeProps extends NodeProps<GraphNodeData> {
  children?: ReactNode
  // Phase 8: Additional className for activity animations
  className?: string
}

function BaseNode({ data, selected, children, className }: BaseNodeProps) {
  const isActive = 'isActive' in data ? data.isActive : true
  // Generate accessible label based on node data
  const nodeName = 'name' in data ? data.name : ('label' in data ? data.label : 'unnamed')
  const ariaLabel = `${data.type} node: ${nodeName}${!isActive ? ' (inactive)' : ''}`

  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={`
        graph-node px-4 py-3 rounded-xl border transition-all duration-200
        ${selected
          ? 'border-tsushin-indigo shadow-glow-sm'
          : 'border-tsushin-border hover:border-tsushin-muted'
        }
        ${isActive
          ? 'bg-tsushin-surface'
          : 'bg-tsushin-surface/50 opacity-60'
        }
        ${className || ''}
      `}
    >
      {/* Source handle (right side) */}
      <Handle
        type="source"
        position={Position.Right}
        className="!bg-tsushin-indigo !border-tsushin-surface !w-3 !h-3"
      />

      {/* Target handle (left side) */}
      <Handle
        type="target"
        position={Position.Left}
        className="!bg-tsushin-accent !border-tsushin-surface !w-3 !h-3"
      />

      {children}
    </div>
  )
}

export default memo(BaseNode)
