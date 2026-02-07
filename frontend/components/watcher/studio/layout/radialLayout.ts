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

export interface RadialLayoutResult { nodes: Node<BuilderNodeData>[]; edges: Edge[] }

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
      edges.push({ id: `edge-${agentNode.id}-${firstRing[i].id}`, source: agentNode.id, target: firstRing[i].id, type: 'smoothstep', style: { stroke: '#484F58', strokeWidth: 2 } })
    }
    if (overflowRing.length > 0) {
      const overflowPositions = positionNodesInSector(overflowRing.length, sector.start, sector.end, RADIUS_OVERFLOW)
      for (let i = 0; i < overflowRing.length; i++) {
        positionedNodes.push({ ...overflowRing[i], position: overflowPositions[i] })
        edges.push({ id: `edge-${agentNode.id}-${overflowRing[i].id}`, source: agentNode.id, target: overflowRing[i].id, type: 'smoothstep', style: { stroke: '#484F58', strokeWidth: 2 } })
      }
    }
  }
  return { nodes: positionedNodes, edges }
}
