/**
 * Tree Layout for Agent Studio Builder
 * Phase G2: Hierarchical top-down tree layout
 *
 * Activated when any group node is expanded.
 * Produces a clean 3-tier top-down tree:
 *   Tier 0 (top):    Agent node, centered
 *   Tier 1 (middle): Group nodes + direct nodes (persona, sentinel, memory)
 *   Tier 2 (bottom): Expanded children (skills, channels, tools, knowledge docs)
 *
 * Uses a manual layout algorithm (not dagre) for deterministic,
 * balanced results that always keep the agent at the top center.
 */

import type { Node, Edge } from '@xyflow/react'
import type { BuilderNodeData } from '../types'
import type { RadialLayoutResult, GroupedCategoryInput } from './radialLayout'

const EDGE_STYLE = { stroke: '#484F58', strokeWidth: 2 }
const CHILD_EDGE_STYLE = { stroke: '#484F58', strokeWidth: 1.5, strokeDasharray: '6 3' }

/** Spacing constants */
const TIER_GAP_Y = 120        // Vertical gap between tiers
const NODE_GAP_X = 30         // Horizontal gap between nodes in the same tier
const CHILD_GAP_X = 20        // Horizontal gap between child nodes
const GROUP_SECTION_GAP = 60  // Extra horizontal gap between different group sections in tier 2

/** Approximate node dimensions */
function getNodeWidth(nodeType: string): number {
  switch (nodeType) {
    case 'builder-agent': return 220
    case 'builder-group': return 180
    default: return 200
  }
}

function getNodeHeight(nodeType: string): number {
  switch (nodeType) {
    case 'builder-agent': return 100
    case 'builder-group': return 60
    default: return 70
  }
}

interface Tier1Entry {
  node: Node<BuilderNodeData>
  children: Node<BuilderNodeData>[]  // empty for direct nodes, populated for expanded groups
  isGroup: boolean
}

/**
 * Calculate a manual top-down tree layout for the builder.
 *
 * Algorithm:
 * 1. Compute the total width each tier-1 node needs (including its children)
 * 2. Lay out tier-2 children in horizontal rows under their parent
 * 3. Center each tier-1 node above its children
 * 4. Arrange all tier-1 entries side by side
 * 5. Center the agent node above the entire tier-1 row
 */
export async function calculateDagreBuilderLayout(
  agentNode: Node<BuilderNodeData>,
  groupedCategories: GroupedCategoryInput[],
  directNodes: Node<BuilderNodeData>[]
): Promise<RadialLayoutResult> {

  const allNodes: Node<BuilderNodeData>[] = []
  const edges: Edge[] = []

  // Build tier-1 entries: groups first, then direct nodes
  const tier1Entries: Tier1Entry[] = []

  for (const { groupNode, childNodes, isExpanded } of groupedCategories) {
    const visibleChildren = isExpanded ? childNodes : []
    tier1Entries.push({ node: groupNode, children: visibleChildren, isGroup: true })

    edges.push({
      id: `edge-${agentNode.id}-${groupNode.id}`,
      source: agentNode.id,
      target: groupNode.id,
      type: 'smoothstep',
      style: EDGE_STYLE,
    })

    if (isExpanded) {
      for (const child of childNodes) {
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

  for (const node of directNodes) {
    tier1Entries.push({ node, children: [], isGroup: false })
    edges.push({
      id: `edge-${agentNode.id}-${node.id}`,
      source: agentNode.id,
      target: node.id,
      type: 'smoothstep',
      style: EDGE_STYLE,
    })
  }

  // --- Step 1: Calculate the width each tier-1 entry occupies ---
  // Width = max(node width, total children width)
  const entryWidths: number[] = tier1Entries.map(entry => {
    const nodeW = getNodeWidth(entry.node.type || '')
    if (entry.children.length === 0) return nodeW

    const childrenTotalW = entry.children.reduce((sum, c, i) => {
      return sum + getNodeWidth(c.type || '') + (i > 0 ? CHILD_GAP_X : 0)
    }, 0)

    return Math.max(nodeW, childrenTotalW)
  })

  // Total width of tier 1
  const totalTier1Width = entryWidths.reduce((sum, w, i) => {
    return sum + w + (i > 0 ? NODE_GAP_X : 0)
  }, 0)

  // --- Step 2: Position tier-1 nodes and their children ---
  const tier1Y = TIER_GAP_Y  // Y position for tier-1 nodes
  const tier2Y = TIER_GAP_Y * 2 + getNodeHeight('builder-group') // Y position for tier-2 children

  let cursorX = -totalTier1Width / 2  // Start from left edge, centered at 0

  for (let i = 0; i < tier1Entries.length; i++) {
    const entry = tier1Entries[i]
    const entryW = entryWidths[i]
    const nodeW = getNodeWidth(entry.node.type || '')
    const nodeH = getNodeHeight(entry.node.type || '')

    // Center this tier-1 node within its allocated width
    const nodeCenterX = cursorX + entryW / 2
    const nodeX = nodeCenterX - nodeW / 2
    const nodeY = tier1Y

    allNodes.push({
      ...entry.node,
      position: { x: nodeX, y: nodeY },
      draggable: !entry.isGroup,
    })

    // Position children below
    if (entry.children.length > 0) {
      const childrenTotalW = entry.children.reduce((sum, c, idx) => {
        return sum + getNodeWidth(c.type || '') + (idx > 0 ? CHILD_GAP_X : 0)
      }, 0)

      let childCursorX = nodeCenterX - childrenTotalW / 2

      for (const child of entry.children) {
        const childW = getNodeWidth(child.type || '')
        const childH = getNodeHeight(child.type || '')
        allNodes.push({
          ...child,
          position: { x: childCursorX, y: tier2Y },
          draggable: true,
        })
        childCursorX += childW + CHILD_GAP_X
      }
    }

    cursorX += entryW + NODE_GAP_X
  }

  // --- Step 3: Position agent node centered at top ---
  const agentW = getNodeWidth('builder-agent')
  const agentH = getNodeHeight('builder-agent')
  allNodes.unshift({
    ...agentNode,
    position: { x: -agentW / 2, y: 0 },
    draggable: false,
  })

  return { nodes: allNodes, edges }
}
