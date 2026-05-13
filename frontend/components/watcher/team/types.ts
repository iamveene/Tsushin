import type { Node } from '@xyflow/react'
import type { Agent, TeamMemberResponse } from '@/lib/client'

export type TeamCanvasPosition = { x: number; y: number }

export const TEAM_CANVAS_AGENT_MIME = 'application/vnd.tsushin.team-agent+json'

/**
 * Drag payload for addable team agents.
 *
 * Draggable sources should call:
 *   dataTransfer.setData(TEAM_CANVAS_AGENT_MIME, JSON.stringify({ type: 'tsushin-team-agent', agentId }))
 *
 * The canvas intentionally resolves the full Agent object from the current
 * addableAgents prop so drops cannot smuggle stale agent details.
 */
export interface TeamCanvasAgentDragPayload {
  type: 'tsushin-team-agent'
  agentId: number
}

export function makeTeamCanvasAgentDragPayload(agent: Agent): string {
  return JSON.stringify({ type: 'tsushin-team-agent', agentId: agent.id } satisfies TeamCanvasAgentDragPayload)
}

export interface TeamMemberNodeData {
  [key: string]: unknown
  type: 'team-member'
  member: TeamMemberResponse
  agent?: Agent
  label: string
  topology: string
  orderLabel: string
  readOnly: boolean
  canMoveEarlier: boolean
  canMoveLater: boolean
  onRemove: (member: TeamMemberResponse) => void
  onMoveEarlier: (member: TeamMemberResponse) => void
  onMoveLater: (member: TeamMemberResponse) => void
  onToggleRequired?: (member: TeamMemberResponse) => void
}

export interface TeamCoordinatorNodeData {
  [key: string]: unknown
  type: 'team-coordinator'
  label: string
  detail: string
}

export type TeamCanvasNodeData = TeamMemberNodeData | TeamCoordinatorNodeData
export type TeamCanvasNode = Node<TeamCanvasNodeData>
