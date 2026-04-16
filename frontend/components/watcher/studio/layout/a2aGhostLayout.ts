/**
 * A2A Ghost Node Layout
 * Positions ghost agent nodes in a horizontal band below all existing canvas nodes.
 *
 * Layout rules:
 *   - Ghost node size: 180px wide × 70px tall
 *   - Horizontal gap: 20px between nodes
 *   - Vertical gap: 120px below the bottommost existing node
 *   - Max 4 ghosts per row, then wrap to the next row
 *   - Each row is centered relative to the horizontal center of existing nodes
 */

import type { Node } from '@xyflow/react'
import type { BuilderGhostAgentData } from '../types'

const GHOST_WIDTH = 180
const GHOST_HEIGHT = 70
const GHOST_GAP_X = 20
const GHOST_GAP_Y = 20          // vertical gap between wrapped rows
const VERTICAL_OFFSET = 120     // gap below bottommost existing node
const MAX_PER_ROW = 4

interface GhostLayoutInput {
  existingNodes: Node[]
  ghostAgents: { agentId: number; agentName: string; avatar?: string | null; permissionId?: number }[]
}

interface GhostNode {
  id: string
  type: 'builder-ghost-agent'
  position: { x: number; y: number }
  data: BuilderGhostAgentData
  draggable: true
  selectable: false
  deletable: false
}

export function computeGhostLayout(input: GhostLayoutInput): GhostNode[] {
  const { existingNodes, ghostAgents } = input

  if (ghostAgents.length === 0) return []

  // Compute bounding box of existing nodes (fall back to origin if no nodes)
  let minX = 0
  let maxX = 0
  let maxY = 0

  if (existingNodes.length > 0) {
    minX = Infinity
    maxX = -Infinity
    maxY = -Infinity

    for (const node of existingNodes) {
      const x = node.position.x
      const y = node.position.y
      // Use measured dimensions if available, otherwise fall back to 200×70
      const w = (node as any).width ?? (node as any).measured?.width ?? 200
      const h = (node as any).height ?? (node as any).measured?.height ?? 70

      if (x < minX) minX = x
      if (x + w > maxX) maxX = x + w
      if (y + h > maxY) maxY = y + h
    }
  }

  const centerX = (minX + maxX) / 2
  const baseY = maxY + VERTICAL_OFFSET

  const result: GhostNode[] = []

  ghostAgents.forEach((agent, idx) => {
    const row = Math.floor(idx / MAX_PER_ROW)
    const col = idx % MAX_PER_ROW

    // How many ghosts are in this row?
    const rowStart = row * MAX_PER_ROW
    const rowEnd = Math.min(rowStart + MAX_PER_ROW, ghostAgents.length)
    const countInRow = rowEnd - rowStart

    // Total width of this row
    const rowWidth = countInRow * GHOST_WIDTH + (countInRow - 1) * GHOST_GAP_X

    // Left edge of this row, centered around centerX
    const rowStartX = centerX - rowWidth / 2

    const x = rowStartX + col * (GHOST_WIDTH + GHOST_GAP_X)
    const y = baseY + row * (GHOST_HEIGHT + GHOST_GAP_Y)

    result.push({
      id: `ghost-${agent.agentId}`,
      type: 'builder-ghost-agent',
      position: { x, y },
      data: {
        type: 'builder-ghost-agent',
        agentId: agent.agentId,
        agentName: agent.agentName,
        avatar: agent.avatar ?? null,
        permissionId: agent.permissionId,
        isGhost: true,
      },
      draggable: true,
      selectable: false,
      deletable: false,
    })
  })

  return result
}
