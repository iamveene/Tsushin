'use client'

/**
 * StudioCanvas - React Flow wrapper for Agent Studio
 */

import { useCallback, useRef, useEffect, useState, useMemo } from 'react'
import {
  ReactFlow, ReactFlowProvider, Controls, Background, BackgroundVariant,
  useReactFlow, applyNodeChanges, type OnNodesChange, type Node, type Edge, type NodeChange,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { builderNodeTypes } from './nodes'
import type { BuilderNodeData, BuilderGhostAgentData, DragTransferData } from './types'

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
  onResetLayout?: () => void
  hasAnyExpanded?: boolean
  // A2A ghost nodes (managed locally for dragging)
  ghostNodes?: Node<BuilderNodeData>[]
  a2aEdges?: Edge[]
  onGhostDoubleClick?: (agentId: number) => void
}

function StudioCanvasInner({
  nodes, edges, onNodesChange, onDrop, onDeleteSelected, onNodeDoubleClick,
  onReady, onExpandAll, onCollapseAll, onResetLayout, hasAnyExpanded,
  ghostNodes = [], a2aEdges = [], onGhostDoubleClick,
}: StudioCanvasProps) {
  const { fitView, screenToFlowPosition } = useReactFlow()
  const [isDragOver, setIsDragOver] = useState(false)

  // Local state for ghost node positions (dragging is managed here, not in parent)
  const [localGhostNodes, setLocalGhostNodes] = useState<Node<BuilderNodeData>[]>(ghostNodes)
  const ghostKeyRef = useRef<string>('')
  useEffect(() => {
    const newKey = ghostNodes.map(n => n.id).sort().join(',')
    if (newKey !== ghostKeyRef.current) {
      ghostKeyRef.current = newKey
      setLocalGhostNodes(ghostNodes)
    }
  }, [ghostNodes])

  // Merged nodes/edges for React Flow (ghost nodes visible but not dirty-tracked)
  const allNodes = useMemo(() => [...nodes, ...localGhostNodes], [nodes, localGhostNodes])
  const allEdges = useMemo(() => [...edges, ...a2aEdges], [edges, a2aEdges])

  // Combined onNodesChange: route ghost position changes locally, rest to parent
  const handleNodesChange = useCallback((changes: NodeChange<Node<BuilderNodeData>>[]) => {
    const ghostChanges = changes.filter(c => 'id' in c && (c.id as string).startsWith('ghost-'))
    const regularChanges = changes.filter(c => !('id' in c) || !(c.id as string).startsWith('ghost-'))
    if (ghostChanges.length > 0) {
      setLocalGhostNodes(prev => applyNodeChanges(ghostChanges, prev) as Node<BuilderNodeData>[])
    }
    if (regularChanges.length > 0) {
      onNodesChange(regularChanges as NodeChange<Node<BuilderNodeData>>[])
    }
  }, [onNodesChange])

  const refMethods: StudioCanvasRef = useMemo(() => ({
    fitView: () => fitView({ padding: 0.3, duration: 300 }),
  }), [fitView])

  useEffect(() => { onReady?.(refMethods) }, [onReady, refMethods])

  // Fit view once when nodes first appear (initial load only, resets on agent switch)
  const hasInitialFit = useRef(false)
  useEffect(() => {
    if (nodes.length === 0) {
      hasInitialFit.current = false  // Reset on agent switch (nodes cleared)
    } else if (!hasInitialFit.current) {
      hasInitialFit.current = true
      setTimeout(() => fitView({ padding: 0.3, duration: 300 }), 150)
    }
  }, [nodes.length, fitView])

  const handleAutoArrange = useCallback(() => {
    fitView({ padding: 0.3, duration: 300 })
  }, [fitView])

  const handleResetLayout = useCallback(() => {
    onResetLayout?.()
    setTimeout(() => fitView({ padding: 0.3, duration: 300 }), 150)
  }, [onResetLayout, fitView])

  const handleDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; setIsDragOver(true) }, [])
  const handleDragLeave = useCallback(() => { setIsDragOver(false) }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setIsDragOver(false)
    const raw = e.dataTransfer.getData('application/studio-palette')
    if (!raw) return
    try {
      const parsed = JSON.parse(raw) as DragTransferData
      const flowPos = screenToFlowPosition({ x: e.clientX, y: e.clientY })
      onDrop({ ...parsed, dropPosition: flowPos })
    } catch { console.error('[StudioCanvas] Failed to parse drop data') }
  }, [onDrop, screenToFlowPosition])

  const handleNodeDblClick = useCallback((_event: React.MouseEvent, node: Node<BuilderNodeData>) => {
    if (node.data.type === 'builder-agent' || node.data.type === 'builder-group') return
    if (node.data.type === 'builder-ghost-agent') {
      onGhostDoubleClick?.((node.data as BuilderGhostAgentData).agentId)
      return
    }
    onNodeDoubleClick?.(node.id, node.data.type as string, node.data as BuilderNodeData)
  }, [onNodeDoubleClick, onGhostDoubleClick])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Delete' || e.key === 'Backspace') {
      // Guard: never delete agent, group, or ghost nodes
      const selected = nodes.filter(n =>
        n.selected &&
        n.data.type !== 'builder-agent' &&
        n.data.type !== 'builder-group' &&
        n.data.type !== 'builder-ghost-agent'
      ).map(n => n.id)
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
          <button onClick={handleResetLayout} className="studio-layout-btn" title="Reset all nodes to auto-calculated positions">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.992 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" />
            </svg>
            Reset Layout
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
      <ReactFlow nodes={allNodes} edges={allEdges} onNodesChange={handleNodesChange} nodeTypes={builderNodeTypes}
        onNodeDoubleClick={handleNodeDblClick} fitView minZoom={0.2} maxZoom={1.5}
        defaultEdgeOptions={{ type: 'straight', animated: false, style: { stroke: '#484F58', strokeWidth: 2 } }}
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
