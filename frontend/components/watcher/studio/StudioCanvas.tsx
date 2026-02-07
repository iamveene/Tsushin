'use client'

/**
 * StudioCanvas - React Flow wrapper for Agent Studio
 */

import { useCallback, useRef, useEffect, useState, useMemo } from 'react'
import {
  ReactFlow, ReactFlowProvider, Controls, Background, BackgroundVariant,
  useReactFlow, type OnNodesChange, type Node, type Edge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { builderNodeTypes } from './nodes'
import type { BuilderNodeData, DragTransferData } from './types'

export interface StudioCanvasRef { fitView: () => void }

interface StudioCanvasProps {
  nodes: Node<BuilderNodeData>[]
  edges: Edge[]
  onNodesChange: OnNodesChange<Node<BuilderNodeData>>
  onDrop: (data: DragTransferData) => void
  onDeleteSelected: (nodeIds: string[]) => void
  onReady?: (methods: StudioCanvasRef) => void
}

function StudioCanvasInner({ nodes, edges, onNodesChange, onDrop, onDeleteSelected, onReady }: StudioCanvasProps) {
  const { fitView } = useReactFlow()
  const [isDragOver, setIsDragOver] = useState(false)

  const refMethods: StudioCanvasRef = useMemo(() => ({
    fitView: () => fitView({ padding: 0.3, duration: 300 }),
  }), [fitView])

  useEffect(() => { onReady?.(refMethods) }, [onReady, refMethods])

  const prevNodeCount = useRef(nodes.length)
  useEffect(() => {
    if (nodes.length !== prevNodeCount.current && nodes.length > 0) {
      setTimeout(() => fitView({ padding: 0.3, duration: 300 }), 100)
      prevNodeCount.current = nodes.length
    }
  }, [nodes.length, fitView])

  const handleDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; setIsDragOver(true) }, [])
  const handleDragLeave = useCallback(() => { setIsDragOver(false) }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setIsDragOver(false)
    const raw = e.dataTransfer.getData('application/studio-palette')
    if (!raw) return
    try { onDrop(JSON.parse(raw) as DragTransferData) } catch { console.error('[StudioCanvas] Failed to parse drop data') }
  }, [onDrop])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Delete' || e.key === 'Backspace') {
      const selected = nodes.filter(n => n.selected && n.data.type !== 'builder-agent').map(n => n.id)
      if (selected.length > 0) { e.preventDefault(); onDeleteSelected(selected) }
    }
  }, [nodes, onDeleteSelected])

  return (
    <div className={`studio-canvas w-full h-full ${isDragOver ? 'drag-over' : ''}`}
      onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop} onKeyDown={handleKeyDown} tabIndex={0}>
      <ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} nodeTypes={builderNodeTypes}
        fitView minZoom={0.2} maxZoom={1.5}
        defaultEdgeOptions={{ type: 'smoothstep', animated: false, style: { stroke: '#484F58', strokeWidth: 2 } }}
        proOptions={{ hideAttribution: true }} nodesDraggable nodesConnectable={false} elementsSelectable selectNodesOnDrag={false}>
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="rgba(139, 146, 158, 0.15)" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  )
}

export default function StudioCanvas(props: StudioCanvasProps) {
  return <ReactFlowProvider><StudioCanvasInner {...props} /></ReactFlowProvider>
}
