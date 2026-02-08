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
  onNodeDoubleClick?: (nodeId: string, nodeType: string, nodeData: BuilderNodeData) => void
  onReady?: (methods: StudioCanvasRef) => void
  onExpandAll?: () => void
  onCollapseAll?: () => void
  hasAnyExpanded?: boolean
}

function StudioCanvasInner({ nodes, edges, onNodesChange, onDrop, onDeleteSelected, onNodeDoubleClick, onReady, onExpandAll, onCollapseAll, hasAnyExpanded }: StudioCanvasProps) {
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

  const handleAutoArrange = useCallback(() => {
    fitView({ padding: 0.3, duration: 300 })
  }, [fitView])

  const handleDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; setIsDragOver(true) }, [])
  const handleDragLeave = useCallback(() => { setIsDragOver(false) }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setIsDragOver(false)
    const raw = e.dataTransfer.getData('application/studio-palette')
    if (!raw) return
    try { onDrop(JSON.parse(raw) as DragTransferData) } catch { console.error('[StudioCanvas] Failed to parse drop data') }
  }, [onDrop])

  const handleNodeDblClick = useCallback((_event: React.MouseEvent, node: Node<BuilderNodeData>) => {
    if (node.data.type === 'builder-agent' || node.data.type === 'builder-group') return
    onNodeDoubleClick?.(node.id, node.data.type as string, node.data as BuilderNodeData)
  }, [onNodeDoubleClick])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Delete' || e.key === 'Backspace') {
      const selected = nodes.filter(n => n.selected && n.data.type !== 'builder-agent' && n.data.type !== 'builder-group').map(n => n.id)
      if (selected.length > 0) { e.preventDefault(); onDeleteSelected(selected) }
    }
  }, [nodes, onDeleteSelected])

  const hasGroupNodes = nodes.some(n => n.data.type === 'builder-group')

  return (
    <div className={`studio-canvas w-full h-full ${isDragOver ? 'drag-over' : ''}`}
      onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop} onKeyDown={handleKeyDown} tabIndex={0}>
      {/* Layout Controls Toolbar */}
      {hasGroupNodes && (
        <div className="studio-layout-toolbar">
          <button onClick={handleAutoArrange} className="studio-layout-btn" title="Re-center and fit all nodes">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" />
            </svg>
            Fit View
          </button>
          <button
            onClick={() => hasAnyExpanded ? onCollapseAll?.() : onExpandAll?.()}
            className="studio-layout-btn"
            title={hasAnyExpanded ? 'Collapse all groups' : 'Expand all groups'}
          >
            {hasAnyExpanded ? (
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5l5.25 5.25" />
              </svg>
            ) : (
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" />
              </svg>
            )}
            {hasAnyExpanded ? 'Collapse All' : 'Expand All'}
          </button>
        </div>
      )}
      <ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} nodeTypes={builderNodeTypes}
        onNodeDoubleClick={handleNodeDblClick} fitView minZoom={0.2} maxZoom={1.5}
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
