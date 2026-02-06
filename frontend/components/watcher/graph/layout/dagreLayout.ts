/**
 * Dagre Layout Utilities for Graph View
 * Phase 2: Auto-layout algorithms using dagre
 * Phase 7: Added hierarchical layout enforcing Channels → Agents → Skills/KB
 *
 * Note: This file should only be imported client-side (inside GraphCanvas)
 * because dagre uses dynamic requires incompatible with SSR
 */

import type { Node, Edge } from '@xyflow/react'
import type { LayoutOptions } from './types'
import { DEFAULT_LAYOUT_OPTIONS } from './types'

/**
 * Get the rank (horizontal position tier) for a node based on its type
 * Phase 7: Enforces hierarchy: Channels (0) → Agents (1) → Skills/KB (2+)
 * Phase 9: Updated for skill → provider hierarchy
 *
 * Rank assignments:
 * - 0: Channels (entry points - leftmost)
 * - 1: Agents (center)
 * - 2: Skill Categories, Knowledge Summary (direct agent children)
 * - 3: Individual Skills (children of categories or direct children of agents)
 * - 4: Skill Providers (children of skills - showing available providers)
 */
function getNodeRank(node: Node): number {
  const nodeType = (node.data as { type?: string })?.type

  switch (nodeType) {
    case 'channel':
      return 0 // Leftmost - entry points
    case 'agent':
      return 1 // Center - main entities
    case 'user':
      return 1 // Users also at center tier
    case 'project':
      return 1 // Projects also at center tier
    case 'skill-category':
      return 2 // First level of expansion
    case 'knowledge-summary':
      return 2 // First level of expansion
    case 'skill':
      // Skills are children of categories (rank 3) or direct children of agents (rank 2)
      return 3
    case 'skill-provider':
      // Phase 9: Skill providers are children of skills
      return 4
    case 'knowledge':
      return 2 // Same level as skill categories
    default:
      return 1 // Default to center
  }
}

/**
 * Apply dagre layout to nodes and edges
 * Returns new node positions while preserving all other node/edge data
 *
 * Uses dynamic import for dagre to avoid SSR issues
 *
 * Phase 7: Now enforces hierarchical layout with rank constraints
 * Layout direction is always LR (Left→Right) for the hierarchy to work:
 * Channels (left) → Agents (center) → Skills/KB (right)
 */
export async function getLayoutedElements<T extends Node, E extends Edge>(
  nodes: T[],
  edges: E[],
  options: LayoutOptions = DEFAULT_LAYOUT_OPTIONS
): Promise<{ nodes: T[]; edges: E[] }> {
  if (nodes.length === 0) {
    return { nodes, edges }
  }

  // Dynamic import to avoid SSR issues
  // Using dagre 0.8.5 which bundles graphlib properly
  const dagre = await import('dagre')

  // Create new graph using dagre's bundled graphlib
  const dagreGraph = new dagre.graphlib.Graph()
  dagreGraph.setDefaultEdgeLabel(() => ({}))

  // Phase 7: Determine if we should use hierarchical layout
  // Use hierarchical layout (LR) for Agents view to enforce Channels → Agents → Skills
  // For other views or when user explicitly chooses direction, use that
  const hasChannels = nodes.some(n => (n.data as { type?: string })?.type === 'channel')
  const hasSkillsOrCategories = nodes.some(n => {
    const type = (n.data as { type?: string })?.type
    return type === 'skill' || type === 'skill-category' || type === 'knowledge-summary' || type === 'skill-provider'
  })

  // Use hierarchical LR layout if we have channels connected to agents (Agents view)
  // This enforces: Channels (left) → Agents (center) → Skills/KB (right)
  const useHierarchicalLayout = hasChannels || hasSkillsOrCategories
  const effectiveDirection = useHierarchicalLayout ? 'LR' : options.direction

  dagreGraph.setGraph({
    rankdir: effectiveDirection,
    nodesep: options.nodeSpacing,
    ranksep: options.rankSpacing,
    marginx: 20,
    marginy: 20,
  })

  // Add nodes to dagre with rank constraints for hierarchical layout
  nodes.forEach((node) => {
    const width = node.measured?.width || node.width || 180
    const height = node.measured?.height || node.height || 70

    const nodeConfig: { width: number; height: number; rank?: number } = { width, height }

    // Phase 7: Add rank constraint for hierarchical layout
    if (useHierarchicalLayout) {
      nodeConfig.rank = getNodeRank(node)
    }

    dagreGraph.setNode(node.id, nodeConfig)
  })

  // Add edges to dagre
  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target)
  })

  // Run the layout algorithm
  dagre.layout(dagreGraph)

  // Apply calculated positions back to nodes
  // Dagre gives center positions, so we offset to top-left corner
  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id)
    const width = node.measured?.width || node.width || 180
    const height = node.measured?.height || node.height || 70

    return {
      ...node,
      position: {
        x: nodeWithPosition.x - width / 2,
        y: nodeWithPosition.y - height / 2,
      },
    }
  })

  return { nodes: layoutedNodes, edges }
}
