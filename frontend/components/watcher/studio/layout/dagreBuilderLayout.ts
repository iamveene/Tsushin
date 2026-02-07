/**
 * Dagre Layout for Agent Studio Builder
 * Phase G2: Hierarchical auto-arrange layout using dagre
 *
 * Activated when any group node is expanded.
 * Produces: Agent (left) -> Groups + Directs (middle) -> Children (right)
 *
 * Note: Uses dynamic import for dagre to avoid SSR issues.
 */

import type { Node, Edge } from '@xyflow/react'
import type { BuilderNodeData } from '../types'
import type { RadialLayoutResult, GroupedCategoryInput } from './radialLayout'

const EDGE_STYLE = { stroke: '#484F58', strokeWidth: 2 }
const CHILD_EDGE_STYLE = { stroke: '#484F58', strokeWidth: 1.5, strokeDasharray: '6 3' }

/** Rank assignment for hierarchical positioning */
function getBuilderRank(nodeType: string): number {
  switch (nodeType) {
    case 'builder-agent': return 0
    case 'builder-group':
    case 'builder-persona':
    case 'builder-sentinel':
    case 'builder-memory': return 1
    case 'builder-channel':
    case 'builder-skill':
    case 'builder-tool':
    case 'builder-knowledge': return 2
    default: return 1
  }
}

/** Approximate node dimensions for dagre spacing */
function getBuilderNodeDimensions(nodeType: string): { width: number; height: number } {
  switch (nodeType) {
    case 'builder-agent': return { width: 220, height: 100 }
    case 'builder-group': return { width: 180, height: 60 }
    default: return { width: 200, height: 70 }
  }
}

/**
 * Calculate dagre-based hierarchical layout for the builder.
 * Agent -> Groups/Directs -> Expanded Children (LR direction)
 */
export async function calculateDagreBuilderLayout(
  agentNode: Node<BuilderNodeData>,
  groupedCategories: GroupedCategoryInput[],
  directNodes: Node<BuilderNodeData>[]
): Promise<RadialLayoutResult> {
  const dagre = await import('dagre')

  const dagreGraph = new dagre.graphlib.Graph()
  dagreGraph.setDefaultEdgeLabel(() => ({}))

  dagreGraph.setGraph({
    rankdir: 'LR',
    nodesep: 60,
    ranksep: 180,
    marginx: 40,
    marginy: 40,
  })

  const allNodes: Node<BuilderNodeData>[] = [agentNode]
  const edges: Edge[] = []

  // Add group nodes + expanded children
  for (const { groupNode, childNodes, isExpanded } of groupedCategories) {
    allNodes.push(groupNode)
    edges.push({
      id: `edge-${agentNode.id}-${groupNode.id}`,
      source: agentNode.id,
      target: groupNode.id,
      type: 'smoothstep',
      style: EDGE_STYLE,
    })

    if (isExpanded && childNodes.length > 0) {
      for (const child of childNodes) {
        allNodes.push(child)
        edges.push({
          id: `edge-${groupNode.id}-${child.id}`,
          source: groupNode.id,
          target: child.id,
          type: 'smoothstep',
          style: CHILD_EDGE_STYLE,
        })
      }
    }
  }

  // Add direct nodes (persona, security, memory)
  for (const node of directNodes) {
    allNodes.push(node)
    edges.push({
      id: `edge-${agentNode.id}-${node.id}`,
      source: agentNode.id,
      target: node.id,
      type: 'smoothstep',
      style: EDGE_STYLE,
    })
  }

  // Register nodes in dagre with dimensions and rank hints
  for (const node of allNodes) {
    const dims = getBuilderNodeDimensions(node.type || '')
    dagreGraph.setNode(node.id, {
      width: dims.width,
      height: dims.height,
      rank: getBuilderRank(node.type || ''),
    })
  }

  // Register edges in dagre
  for (const edge of edges) {
    dagreGraph.setEdge(edge.source, edge.target)
  }

  dagre.layout(dagreGraph)

  // Map dagre center positions to React Flow top-left positions
  const positionedNodes = allNodes.map(node => {
    const pos = dagreGraph.node(node.id)
    const dims = getBuilderNodeDimensions(node.type || '')
    return {
      ...node,
      position: {
        x: pos.x - dims.width / 2,
        y: pos.y - dims.height / 2,
      },
      draggable: node.type !== 'builder-agent' && node.type !== 'builder-group',
    }
  })

  return { nodes: positionedNodes, edges }
}
