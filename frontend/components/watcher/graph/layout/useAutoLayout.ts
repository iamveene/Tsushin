/**
 * Auto Layout Hook for Graph View
 * Phase 2: React hook for automatic node layout
 */

import { useCallback, useEffect, useRef } from 'react'
import { useReactFlow, useNodesInitialized } from '@xyflow/react'
import { getLayoutedElements } from './dagreLayout'
import type { LayoutOptions } from './types'
import { DEFAULT_LAYOUT_OPTIONS } from './types'

interface UseAutoLayoutReturn {
  runLayout: () => void
}

/**
 * Hook that provides auto-layout functionality for React Flow graphs
 * - Automatically runs layout once nodes are initialized (measured)
 * - Provides runLayout function for manual re-layout
 * - Fits view after layout with smooth animation
 */
export function useAutoLayout(
  options: LayoutOptions = DEFAULT_LAYOUT_OPTIONS
): UseAutoLayoutReturn {
  const { getNodes, getEdges, setNodes, fitView } = useReactFlow()
  const nodesInitialized = useNodesInitialized()
  const layoutApplied = useRef(false)
  const prevDirection = useRef(options.direction)
  const isRunning = useRef(false)

  const runLayout = useCallback(async () => {
    // Prevent concurrent layout runs
    if (isRunning.current) return
    isRunning.current = true

    try {
      const nodes = getNodes()
      const edges = getEdges()

      if (nodes.length === 0) {
        isRunning.current = false
        return
      }

      const { nodes: layoutedNodes } = await getLayoutedElements(
        nodes,
        edges,
        options
      )

      setNodes(layoutedNodes)

      // Fit view after layout with animation
      window.requestAnimationFrame(() => {
        fitView({ padding: 0.2, duration: 300 })
      })
    } finally {
      isRunning.current = false
    }
  }, [getNodes, getEdges, setNodes, fitView, options])

  // Auto-layout on initial render after nodes are measured
  useEffect(() => {
    if (nodesInitialized && !layoutApplied.current) {
      runLayout()
      layoutApplied.current = true
    }
  }, [nodesInitialized, runLayout])

  // Re-run layout when direction changes
  useEffect(() => {
    if (nodesInitialized && prevDirection.current !== options.direction) {
      runLayout()
      prevDirection.current = options.direction
    }
  }, [nodesInitialized, options.direction, runLayout])

  return { runLayout }
}
