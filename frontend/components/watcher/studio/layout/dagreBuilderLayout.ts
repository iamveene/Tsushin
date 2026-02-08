/**
 * Tree Layout for Agent Studio Builder
 * Phase G2: Hierarchical top-down tree layout
 * Phase A: User position persistence (dragged nodes keep their position)
 * Phase B: Improved spacing and visual hierarchy
 * Phase D: Tier-3 provider nodes under expanded skills
 *
 * Produces a clean 4-tier top-down tree:
 *   Tier 0 (top):    Agent node, centered
 *   Tier 1 (middle): Group nodes + direct nodes (persona, sentinel, memory)
 *   Tier 2:          Expanded children (skills, channels, tools, knowledge docs)
 *   Tier 3 (bottom): Provider sub-nodes under expanded skills
 *
 * Uses a manual layout algorithm for deterministic, balanced results
 * that always keep the agent at the top center.
 */

import type { Node, Edge } from '@xyflow/react'
import type { BuilderNodeData } from '../types'
import type { RadialLayoutResult, GroupedCategoryInput } from './radialLayout'

const EDGE_STYLE = { stroke: '#484F58', strokeWidth: 2 }
const CHILD_EDGE_STYLE = { stroke: '#484F58', strokeWidth: 1.5, strokeDasharray: '6 3' }

/** Spacing constants (Phase B: improved breathing room) */
const TIER_GAP_Y = 160        // Vertical gap between tiers
const TIER_3_GAP_Y = 100      // Smaller gap for provider sub-nodes
const NODE_GAP_X = 50         // Horizontal gap between nodes in the same tier
const CHILD_GAP_X = 30        // Horizontal gap between child nodes
const GROUP_SECTION_GAP = 80  // Extra horizontal gap between different group sections in tier 2
const PROVIDER_GAP_X = 20     // Gap between provider sub-nodes

/** Approximate node dimensions (Phase B: improved sizing) */
function getNodeWidth(nodeType: string): number {
  switch (nodeType) {
    case 'builder-agent': return 260
    case 'builder-group': return 180
    case 'builder-skill': return 210
    case 'builder-knowledge': return 210
    case 'builder-skill-provider': return 150
    default: return 200
  }
}

function getNodeHeight(nodeType: string): number {
  switch (nodeType) {
    case 'builder-agent': return 120
    case 'builder-group': return 52
    case 'builder-skill': return 72
    case 'builder-knowledge': return 80
    case 'builder-skill-provider': return 48
    default: return 68
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
 * 6. Position tier-3 provider nodes under expanded skill nodes
 * 7. Overlay user-dragged positions for nodes that have been manually positioned
 */
export async function calculateDagreBuilderLayout(
  agentNode: Node<BuilderNodeData>,
  groupedCategories: GroupedCategoryInput[],
  directNodes: Node<BuilderNodeData>[],
  userPositions?: Map<string, { x: number; y: number }>,
  providerNodes?: Node<BuilderNodeData>[],
  providerEdges?: Edge[],
): Promise<RadialLayoutResult> {

  const allNodes: Node<BuilderNodeData>[] = []
  const edges: Edge[] = []

  // Build tier-1 entries: direct nodes on left, groups in center, memory on right
  // This creates a balanced, organized layout
  const groupEntries: Tier1Entry[] = []
  const leftDirectEntries: Tier1Entry[] = []  // persona, sentinel
  const rightDirectEntries: Tier1Entry[] = [] // memory

  for (const { groupNode, childNodes, isExpanded } of groupedCategories) {
    const visibleChildren = isExpanded ? childNodes : []
    groupEntries.push({ node: groupNode, children: visibleChildren, isGroup: true })

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
    const entry: Tier1Entry = { node, children: [], isGroup: false }
    // Memory goes to the right, persona/sentinel go to the left
    if (node.type === 'builder-memory') {
      rightDirectEntries.push(entry)
    } else {
      leftDirectEntries.push(entry)
    }
    edges.push({
      id: `edge-${agentNode.id}-${node.id}`,
      source: agentNode.id,
      target: node.id,
      type: 'smoothstep',
      style: EDGE_STYLE,
    })
  }

  // Final order: [left directs] [groups] [right directs]
  const tier1Entries: Tier1Entry[] = [...leftDirectEntries, ...groupEntries, ...rightDirectEntries]

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

  // Total width of tier 1 (Phase B: use GROUP_SECTION_GAP between groups)
  const totalTier1Width = entryWidths.reduce((sum, w, i) => {
    if (i === 0) return w
    // Use larger gap between groups with expanded children and other entries
    const prevEntry = tier1Entries[i - 1]
    const curEntry = tier1Entries[i]
    const gap = (prevEntry.children.length > 0 || curEntry.children.length > 0) ? GROUP_SECTION_GAP : NODE_GAP_X
    return sum + w + gap
  }, 0)

  // --- Step 2: Position tier-1 nodes and their children ---
  const tier1Y = TIER_GAP_Y  // Y position for tier-1 nodes
  const tier2Y = tier1Y + getNodeHeight('builder-group') + TIER_GAP_Y * 0.75 // Consistent gap below groups
  const tier3Y = tier2Y + getNodeHeight('builder-skill') + TIER_3_GAP_Y // Y position for tier-3 providers

  // Track skill node positions for provider placement
  const skillPositions = new Map<string, { x: number; y: number; width: number }>()

  let cursorX = -totalTier1Width / 2  // Start from left edge, centered at 0

  for (let i = 0; i < tier1Entries.length; i++) {
    const entry = tier1Entries[i]
    const entryW = entryWidths[i]
    const nodeW = getNodeWidth(entry.node.type || '')

    // Center this tier-1 node within its allocated width
    const nodeCenterX = cursorX + entryW / 2
    const nodeX = nodeCenterX - nodeW / 2
    const nodeY = tier1Y

    // Use user position if available, otherwise use calculated position
    const userPos = userPositions?.get(entry.node.id)
    allNodes.push({
      ...entry.node,
      position: userPos || { x: nodeX, y: nodeY },
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
        const childUserPos = userPositions?.get(child.id)
        const childPos = childUserPos || { x: childCursorX, y: tier2Y }
        allNodes.push({
          ...child,
          position: childPos,
          draggable: true,
        })

        // Track skill positions for provider placement
        if (child.type === 'builder-skill') {
          const skillData = child.data as any
          if (skillData.skillType) {
            skillPositions.set(skillData.skillType, { x: childPos.x, y: childPos.y, width: childW })
          }
        }

        childCursorX += childW + CHILD_GAP_X
      }
    }

    // Advance cursor (Phase B: dynamic gap sizing)
    if (i < tier1Entries.length - 1) {
      const nextEntry = tier1Entries[i + 1]
      const gap = (entry.children.length > 0 || nextEntry.children.length > 0) ? GROUP_SECTION_GAP : NODE_GAP_X
      cursorX += entryW + gap
    }
  }

  // --- Step 3: Position agent node centered at top ---
  const agentW = getNodeWidth('builder-agent')
  allNodes.unshift({
    ...agentNode,
    position: { x: -agentW / 2, y: 0 },
    draggable: false,
  })

  // --- Step 4: Position tier-3 provider nodes under their parent skill ---
  if (providerNodes && providerNodes.length > 0) {
    // Group providers by parent skill
    const providersBySkill = new Map<string, Node<BuilderNodeData>[]>()
    for (const pn of providerNodes) {
      const d = pn.data as any
      const key = d.parentSkillType
      if (!providersBySkill.has(key)) providersBySkill.set(key, [])
      providersBySkill.get(key)!.push(pn)
    }

    for (const [skillType, providers] of providersBySkill) {
      const skillPos = skillPositions.get(skillType)
      if (!skillPos) continue

      const providerW = getNodeWidth('builder-skill-provider')
      const totalProvidersW = providers.length * providerW + (providers.length - 1) * PROVIDER_GAP_X
      const startX = skillPos.x + skillPos.width / 2 - totalProvidersW / 2

      providers.forEach((pn, idx) => {
        const px = startX + idx * (providerW + PROVIDER_GAP_X)
        const userPos = userPositions?.get(pn.id)
        allNodes.push({
          ...pn,
          position: userPos || { x: px, y: tier3Y },
          draggable: true,
        })
      })
    }
  }

  // Add provider edges
  if (providerEdges) {
    edges.push(...providerEdges)
  }

  return { nodes: allNodes, edges }
}
