/**
 * Radial Layout for Agent Studio
 */
import type { Node, Edge } from '@xyflow/react'
import type { BuilderNodeData, ProfileCategoryId } from '../types'
import { SECTOR_ANGLES } from '../types'

const RADIUS_FIRST = 300
const RADIUS_OVERFLOW = 480
const AGENT_POSITION = { x: 0, y: 0 }
const MAX_PER_RING = 6
const SUB_RADIAL_RADIUS = 140

const EDGE_STYLE = { stroke: '#484F58', strokeWidth: 2 }
const CHILD_EDGE_STYLE = { stroke: '#484F58', strokeWidth: 1.5, strokeDasharray: '6 3' }

function getCategory(nodeType: string): ProfileCategoryId | null {
  const map: Record<string, ProfileCategoryId> = {
    'builder-persona': 'persona', 'builder-channel': 'channels', 'builder-skill': 'skills',
    'builder-tool': 'tools', 'builder-sentinel': 'security', 'builder-knowledge': 'knowledge', 'builder-memory': 'memory',
  }
  return map[nodeType] || null
}

function degToRad(deg: number): number { return (deg * Math.PI) / 180 }

function getSectorSpan(start: number, end: number): { normalizedStart: number; span: number } {
  return end < start ? { normalizedStart: start, span: (360 - start) + end } : { normalizedStart: start, span: end - start }
}

function positionNodesInSector(count: number, sectorStart: number, sectorEnd: number, radius: number): Array<{ x: number; y: number }> {
  if (count === 0) return []
  const { normalizedStart, span } = getSectorSpan(sectorStart, sectorEnd)
  if (count === 1) {
    const angle = normalizedStart + span / 2
    return [{ x: AGENT_POSITION.x + radius * Math.cos(degToRad(angle - 90)), y: AGENT_POSITION.y + radius * Math.sin(degToRad(angle - 90)) }]
  }
  const padding = span * 0.1
  const usableSpan = span - padding * 2
  const step = usableSpan / (count - 1)
  return Array.from({ length: count }, (_, i) => {
    const angle = normalizedStart + padding + step * i
    return { x: AGENT_POSITION.x + radius * Math.cos(degToRad(angle - 90)), y: AGENT_POSITION.y + radius * Math.sin(degToRad(angle - 90)) }
  })
}

/** Position child nodes in a sub-radial around a parent position */
function positionSubRadial(count: number, center: { x: number; y: number }, radius: number): Array<{ x: number; y: number }> {
  if (count === 0) return []
  if (count === 1) return [{ x: center.x + radius, y: center.y }]
  const angleStep = (2 * Math.PI) / count
  const startOffset = -Math.PI / 2 // Start from top
  return Array.from({ length: count }, (_, i) => {
    const angle = startOffset + i * angleStep
    return { x: center.x + radius * Math.cos(angle), y: center.y + radius * Math.sin(angle) }
  })
}

/** Get the center position for a sector (single point at radius) */
function getSectorCenter(sector: { start: number; end: number }, radius: number): { x: number; y: number } {
  const { normalizedStart, span } = getSectorSpan(sector.start, sector.end)
  const angle = normalizedStart + span / 2
  return {
    x: AGENT_POSITION.x + radius * Math.cos(degToRad(angle - 90)),
    y: AGENT_POSITION.y + radius * Math.sin(degToRad(angle - 90)),
  }
}

export interface RadialLayoutResult { nodes: Node<BuilderNodeData>[]; edges: Edge[] }

/** Original flat layout (kept for backwards compatibility) */
export function calculateRadialLayout(agentNode: Node<BuilderNodeData>, attachedNodes: Node<BuilderNodeData>[]): RadialLayoutResult {
  const byCategory = new Map<ProfileCategoryId, Node<BuilderNodeData>[]>()
  for (const node of attachedNodes) {
    const cat = getCategory(node.type || '')
    if (cat) { if (!byCategory.has(cat)) byCategory.set(cat, []); byCategory.get(cat)!.push(node) }
  }

  const positionedNodes: Node<BuilderNodeData>[] = [{ ...agentNode, position: AGENT_POSITION }]
  const edges: Edge[] = []

  for (const [category, nodes] of byCategory) {
    const sector = SECTOR_ANGLES[category]
    if (!sector) continue
    const firstRing = nodes.slice(0, MAX_PER_RING)
    const overflowRing = nodes.slice(MAX_PER_RING)
    const firstPositions = positionNodesInSector(firstRing.length, sector.start, sector.end, RADIUS_FIRST)
    for (let i = 0; i < firstRing.length; i++) {
      positionedNodes.push({ ...firstRing[i], position: firstPositions[i] })
      edges.push({ id: `edge-${agentNode.id}-${firstRing[i].id}`, source: agentNode.id, target: firstRing[i].id, type: 'smoothstep', style: EDGE_STYLE })
    }
    if (overflowRing.length > 0) {
      const overflowPositions = positionNodesInSector(overflowRing.length, sector.start, sector.end, RADIUS_OVERFLOW)
      for (let i = 0; i < overflowRing.length; i++) {
        positionedNodes.push({ ...overflowRing[i], position: overflowPositions[i] })
        edges.push({ id: `edge-${agentNode.id}-${overflowRing[i].id}`, source: agentNode.id, target: overflowRing[i].id, type: 'smoothstep', style: EDGE_STYLE })
      }
    }
  }
  return { nodes: positionedNodes, edges }
}

/** Grouped category entry for layout */
export interface GroupedCategoryInput {
  category: ProfileCategoryId
  groupNode: Node<BuilderNodeData>
  childNodes: Node<BuilderNodeData>[]
  isExpanded: boolean
}

/** Grouped radial layout: group nodes + direct nodes around agent, with sub-radial children when expanded */
export function calculateGroupedRadialLayout(
  agentNode: Node<BuilderNodeData>,
  groupedCategories: GroupedCategoryInput[],
  directNodes: Node<BuilderNodeData>[]
): RadialLayoutResult {
  const positionedNodes: Node<BuilderNodeData>[] = [{ ...agentNode, position: AGENT_POSITION }]
  const edges: Edge[] = []

  // Position group nodes at sector centers
  for (const { category, groupNode, childNodes, isExpanded } of groupedCategories) {
    const sector = SECTOR_ANGLES[category]
    if (!sector) continue

    const groupPos = getSectorCenter(sector, RADIUS_FIRST)
    positionedNodes.push({ ...groupNode, position: groupPos, draggable: false })
    edges.push({ id: `edge-${agentNode.id}-${groupNode.id}`, source: agentNode.id, target: groupNode.id, type: 'smoothstep', style: EDGE_STYLE })

    // When expanded, add children in sub-radial around the group node
    if (isExpanded && childNodes.length > 0) {
      const childPositions = positionSubRadial(childNodes.length, groupPos, SUB_RADIAL_RADIUS)
      for (let i = 0; i < childNodes.length; i++) {
        positionedNodes.push({ ...childNodes[i], position: childPositions[i] })
        edges.push({ id: `edge-${groupNode.id}-${childNodes[i].id}`, source: groupNode.id, target: childNodes[i].id, type: 'smoothstep', style: CHILD_EDGE_STYLE })
      }
    }
  }

  // Position direct nodes (persona, security, memory) at their sector centers
  const directByCategory = new Map<ProfileCategoryId, Node<BuilderNodeData>[]>()
  for (const node of directNodes) {
    const cat = getCategory(node.type || '')
    if (cat) {
      if (!directByCategory.has(cat)) directByCategory.set(cat, [])
      directByCategory.get(cat)!.push(node)
    }
  }

  for (const [category, nodes] of directByCategory) {
    const sector = SECTOR_ANGLES[category]
    if (!sector) continue
    const positions = positionNodesInSector(nodes.length, sector.start, sector.end, RADIUS_FIRST)
    for (let i = 0; i < nodes.length; i++) {
      positionedNodes.push({ ...nodes[i], position: positions[i] })
      edges.push({ id: `edge-${agentNode.id}-${nodes[i].id}`, source: agentNode.id, target: nodes[i].id, type: 'smoothstep', style: EDGE_STYLE })
    }
  }

  return { nodes: positionedNodes, edges }
}
