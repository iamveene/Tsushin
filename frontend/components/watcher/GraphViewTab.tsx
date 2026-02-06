'use client'

/**
 * Graph View Tab - Network visualization for Watcher
 * Phase 1: Foundation with static placeholder data
 * Phase 2: Added left panel, auto-layout, drag support
 * Phase 3: Real API data integration with agents and channels
 * Phase 4: Projects view implementation
 * Phase 8: Real-time activity visualization
 */

import { useState, useRef, useCallback, useEffect, useMemo } from 'react'
import dynamic from 'next/dynamic'
import EmptyState from '@/components/EmptyState'
import { GraphNode, GraphViewType } from './graph/types'
import { LayoutOptions, DEFAULT_LAYOUT_OPTIONS } from './graph/layout'
import { useGraphData } from './graph/hooks'
import GraphLeftPanel from './graph/GraphLeftPanel'
import type { GraphCanvasRef } from './graph/GraphCanvas'
import { useWatcherActivity } from '@/hooks/useWatcherActivity'
import { getToken } from '@/contexts/AuthContext'
import './graph/graph.css'

// Dynamic import to avoid SSR issues with React Flow
// Note: Next.js dynamic() with forwardRef requires importing the component type separately
const GraphCanvasComponent = dynamic(() => import('./graph/GraphCanvas'), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-96">
      <div className="text-center">
        <div className="relative w-12 h-12 mx-auto mb-4">
          <div className="absolute inset-0 rounded-full border-4 border-tsushin-surface"></div>
          <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-tsushin-indigo animate-spin"></div>
        </div>
        <p className="text-tsushin-slate font-medium">Loading graph...</p>
      </div>
    </div>
  ),
}) as typeof import('./graph/GraphCanvas').default

// Empty state config per view type
const EMPTY_STATE_CONFIG: Record<GraphViewType, { title: string; description: string }> = {
  agents: {
    title: 'No Agents Found',
    description: 'Create an agent to visualize its channel connections in the graph view.',
  },
  projects: {
    title: 'No Projects Found',
    description: 'Create a project to visualize agent access relationships in the graph view.',
  },
  users: {
    title: 'No Users Found',
    description: 'Users will appear here once they interact with your agents.',
  },
}

export default function GraphViewTab() {
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [viewType, setViewType] = useState<GraphViewType>('agents')

  // Phase 2: Layout state
  const [autoFit, setAutoFit] = useState(true)
  const [layoutDirection, setLayoutDirection] = useState<LayoutOptions['direction']>('LR')
  const graphCanvasRef = useRef<GraphCanvasRef | null>(null)

  // Callback to receive ref methods from GraphCanvas (workaround for Next.js dynamic import ref issue)
  const handleGraphCanvasReady = useCallback((methods: GraphCanvasRef) => {
    graphCanvasRef.current = methods
  }, [])

  // Phase 3: Filter state for agents view
  const [showInactiveAgents, setShowInactiveAgents] = useState(false)

  // Phase 4: Filter state for projects view
  const [showArchivedProjects, setShowArchivedProjects] = useState(false)

  // Phase 5: Filter state for users view
  const [showInactiveUsers, setShowInactiveUsers] = useState(false)

  // Phase 10: Fullscreen mode
  const [isMaximized, setIsMaximized] = useState(false)

  // Fetch data based on view type
  const { nodes, edges, loading, error, refetch } = useGraphData({
    viewType,
    showInactiveAgents,
    showArchivedProjects,
    showInactiveUsers,
  })

  // Phase 8: Real-time activity WebSocket
  const token = typeof window !== 'undefined' ? getToken() : null
  const {
    processingAgents,
    activeChannels,
    recentSkillUse,
    recentKbUse,
    fadingAgents,
    fadingChannels,
    isConnected: isActivityConnected
  } = useWatcherActivity(token, {
    enabled: viewType === 'agents' // Only connect when viewing agents
  })

  // Phase 8: Activity state object passed directly to GraphCanvas for real-time updates
  // GraphCanvas merges this into React Flow's internal node state via useEffect
  const activityState = useMemo(() => {
    if (viewType !== 'agents') return undefined
    return { processingAgents, activeChannels, recentSkillUse, recentKbUse, fadingAgents, fadingChannels }
  }, [viewType, processingAgents, activeChannels, recentSkillUse, recentKbUse, fadingAgents, fadingChannels])

  // Global refresh integration - listen for refresh events from header button
  useEffect(() => {
    const handleRefresh = () => {
      console.log('[GraphViewTab] Refresh event received')
      refetch()
    }
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => window.removeEventListener('tsushin:refresh', handleRefresh)
  }, [refetch])

  // Phase 10: Handle Escape key to exit fullscreen
  useEffect(() => {
    if (!isMaximized) return
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsMaximized(false)
    }
    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [isMaximized])

  // Phase 10: Prevent body scroll when maximized
  useEffect(() => {
    if (isMaximized) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => { document.body.style.overflow = '' }
  }, [isMaximized])

  // Phase 10: Trigger fitView after maximize/minimize transition
  // Always fit view when maximized state changes to properly arrange content
  useEffect(() => {
    const timeoutId = setTimeout(() => {
      graphCanvasRef.current?.fitView()
    }, 350) // Wait for CSS transition
    return () => clearTimeout(timeoutId)
  }, [isMaximized])

  // Memoize layout options to prevent unnecessary re-renders and stale runLayout references
  const layoutOptions: LayoutOptions = useMemo(() => ({
    ...DEFAULT_LAYOUT_OPTIONS,
    direction: layoutDirection,
  }), [layoutDirection])

  const handleNodeClick = (node: GraphNode) => {
    setSelectedNode(node)
    console.log('[GraphViewTab] Node clicked:', node)
  }

  const handleRunLayout = useCallback(() => {
    graphCanvasRef.current?.runLayout()
  }, [])

  // Phase 7: Expand/Collapse All state and handlers
  const [isExpandingAll, setIsExpandingAll] = useState(false)
  const [expandedAgentsCount, setExpandedAgentsCount] = useState(0)

  // Compute hasExpandableNodes directly from nodes prop
  // This is more reliable than calling through the ref
  const hasExpandableNodes = useMemo(() => {
    return nodes.some(n => {
      if (n.data.type !== 'agent') return false
      const agentData = n.data as { skillsCount?: number; hasKnowledgeBase?: boolean }
      return (agentData.skillsCount && agentData.skillsCount > 0) || agentData.hasKnowledgeBase
    })
  }, [nodes])

  const hasExpandedNodes = expandedAgentsCount > 0

  const handleExpandAll = useCallback(async () => {
    if (!graphCanvasRef.current) return
    setIsExpandingAll(true)
    try {
      await graphCanvasRef.current.expandAll()
      // Count how many agents we expanded
      const expandableCount = nodes.filter(n => {
        if (n.data.type !== 'agent') return false
        const agentData = n.data as { skillsCount?: number; hasKnowledgeBase?: boolean }
        return (agentData.skillsCount && agentData.skillsCount > 0) || agentData.hasKnowledgeBase
      }).length
      setExpandedAgentsCount(expandableCount)
    } finally {
      setIsExpandingAll(false)
    }
  }, [nodes])

  const handleCollapseAll = useCallback(() => {
    if (!graphCanvasRef.current) return
    graphCanvasRef.current.collapseAll()
    setExpandedAgentsCount(0)
  }, [])

  // Handle expanded count changes from GraphCanvas (when individual nodes are expanded/collapsed)
  const handleExpandedCountChange = useCallback((count: number) => {
    setExpandedAgentsCount(count)
  }, [])

  const handleViewTypeChange = (newViewType: GraphViewType) => {
    setViewType(newViewType)
    setSelectedNode(null) // Clear selection when switching views
    setExpandedAgentsCount(0) // Reset expand state when switching views
  }

  // Check if view is enabled (Phase 5: all views enabled)
  const isViewEnabled = (type: GraphViewType) => type === 'agents' || type === 'projects' || type === 'users'

  // Loading state
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <div className="relative w-12 h-12 mx-auto mb-4">
            <div className="absolute inset-0 rounded-full border-4 border-tsushin-surface"></div>
            <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-tsushin-indigo animate-spin"></div>
          </div>
          <p className="text-tsushin-slate font-medium">Loading graph data...</p>
        </div>
      </div>
    )
  }

  // Error state
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-12 space-y-4">
        <div className="text-center">
          <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-red-500/20 flex items-center justify-center">
            <svg className="w-6 h-6 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <p className="text-red-400 font-medium mb-2">Failed to load graph data</p>
          <p className="text-sm text-tsushin-slate mb-4">{error}</p>
          <button
            onClick={refetch}
            className="btn-primary"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  // Empty state - use view-specific messaging
  if (nodes.length === 0) {
    const emptyConfig = EMPTY_STATE_CONFIG[viewType]
    return (
      <div className="space-y-4 animate-fade-in">
        {/* Keep view selector visible even in empty state */}
        <div className="flex justify-between items-center">
          <div className="glass-card rounded-lg p-1 inline-flex">
            {(['agents', 'users', 'projects'] as GraphViewType[]).map((type) => (
              <button
                key={type}
                disabled={!isViewEnabled(type)}
                onClick={() => isViewEnabled(type) && handleViewTypeChange(type)}
                className={`
                  px-4 py-2 text-sm font-medium rounded-md transition-all
                  ${viewType === type
                    ? 'bg-tsushin-surface text-white'
                    : 'text-tsushin-slate'
                  }
                  ${!isViewEnabled(type) ? 'opacity-50 cursor-not-allowed' : 'hover:text-white'}
                `}
              >
                {type.charAt(0).toUpperCase() + type.slice(1)}
              </button>
            ))}
          </div>
        </div>
        <EmptyState
          variant="no-data"
          title={emptyConfig.title}
          description={emptyConfig.description}
        />
      </div>
    )
  }

  return (
    <div className="space-y-4 animate-fade-in">
      {/* View Type Selector */}
      <div className="flex justify-between items-center">
        <div className="glass-card rounded-lg p-1 inline-flex">
          {(['agents', 'users', 'projects'] as GraphViewType[]).map((type) => (
            <button
              key={type}
              disabled={!isViewEnabled(type)}
              onClick={() => isViewEnabled(type) && handleViewTypeChange(type)}
              className={`
                px-4 py-2 text-sm font-medium rounded-md transition-all
                ${viewType === type
                  ? 'bg-tsushin-surface text-white'
                  : 'text-tsushin-slate'
                }
                ${!isViewEnabled(type) ? 'opacity-50 cursor-not-allowed' : 'hover:text-white'}
              `}
            >
              {type.charAt(0).toUpperCase() + type.slice(1)}
            </button>
          ))}
        </div>
        <div className="text-sm text-tsushin-muted">
          {nodes.length} nodes | {edges.length} connections
          {isActivityConnected && (
            <span className="ml-2 text-green-400" title="Real-time activity connected">
              <svg className="w-3 h-3 inline" fill="currentColor" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="8" />
              </svg>
            </span>
          )}
        </div>
      </div>

      {/* Phase 10: Fullscreen backdrop */}
      {isMaximized && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40"
          onClick={() => setIsMaximized(false)}
        />
      )}

      {/* Graph Canvas with Left Panel */}
      <div className={`
        ${isMaximized
          ? 'fixed inset-4 z-50 h-auto'
          : 'h-[600px] relative'
        }
        glass-card rounded-xl p-1 transition-all duration-300
      `}>
        {/* Left Panel - View Options */}
        <GraphLeftPanel
          viewType={viewType}
          autoFit={autoFit}
          onAutoFitChange={setAutoFit}
          layoutDirection={layoutDirection}
          onLayoutDirectionChange={setLayoutDirection}
          onRunLayout={handleRunLayout}
          showInactiveAgents={showInactiveAgents}
          onShowInactiveAgentsChange={setShowInactiveAgents}
          showArchivedProjects={showArchivedProjects}
          onShowArchivedProjectsChange={setShowArchivedProjects}
          showInactiveUsers={showInactiveUsers}
          onShowInactiveUsersChange={setShowInactiveUsers}
          onExpandAll={handleExpandAll}
          onCollapseAll={handleCollapseAll}
          hasExpandableNodes={hasExpandableNodes}
          hasExpandedNodes={hasExpandedNodes}
          isExpandingAll={isExpandingAll}
          isMaximized={isMaximized}
          onToggleMaximize={() => setIsMaximized(!isMaximized)}
        />

        {/* Graph Canvas */}
        <GraphCanvasComponent
          initialNodes={nodes}
          initialEdges={edges}
          onNodeClick={handleNodeClick}
          autoFit={autoFit}
          layoutOptions={layoutOptions}
          onExpandedCountChange={handleExpandedCountChange}
          onReady={handleGraphCanvasReady}
          activityState={activityState}
        />
      </div>

    </div>
  )
}
