'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Background,
  BackgroundVariant,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  applyNodeChanges,
  useReactFlow,
  type Edge,
  type NodeChange,
  type NodeDragHandler,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { BotIcon, PlusIcon, UsersIcon } from '@/components/ui/icons'
import type { Agent, TeamDetail, TeamMemberResponse } from '@/lib/client'
import { teamNodeTypes } from './nodes'
import {
  TEAM_CANVAS_AGENT_MIME,
  makeTeamCanvasAgentDragPayload,
  type TeamCanvasAgentDragPayload,
  type TeamCanvasNode,
  type TeamCanvasPosition,
} from './types'
import './team.css'

export interface TeamCanvasProps {
  team: TeamDetail
  agents?: Agent[]
  addableAgents: Agent[]
  readOnly: boolean
  onAddMember: (agent: Agent, position: { x: number; y: number }) => void | Promise<void>
  onRemoveMember: (member: TeamMemberResponse) => void | Promise<void>
  onReorderMembers: (orderedMembers: TeamMemberResponse[]) => void | Promise<void>
  onUpdateMemberPosition: (member: TeamMemberResponse, position: { x: number; y: number }) => void | Promise<void>
  onToggleRequired?: (member: TeamMemberResponse) => void | Promise<void>
  onResetLayout?: () => void | Promise<void>
}

const MEMBER_WIDTH = 260
const MEMBER_GAP = 90
const LINE_Y = 160
const COORDINATOR_X = 0
const COORDINATOR_Y = -180
const MESH_MEMBER_Y = 160
const MESH_ROW_GAP = 320

function orderedMembers(team: TeamDetail) {
  return [...team.members]
    .filter((member) => member.role !== 'coordinator')
    .sort((left, right) => {
      const leftOrder = left.execution_order ?? Number.MAX_SAFE_INTEGER
      const rightOrder = right.execution_order ?? Number.MAX_SAFE_INTEGER
      if (leftOrder !== rightOrder) return leftOrder - rightOrder
      return left.id - right.id
    })
}

function memberLabel(member: TeamMemberResponse) {
  return member.agent_name || `Agent #${member.agent_id}`
}

function persistedPosition(member: TeamMemberResponse): TeamCanvasPosition | null {
  if (typeof member.position_x !== 'number' || typeof member.position_y !== 'number') return null
  return { x: member.position_x, y: member.position_y }
}

function defaultLinePosition(index: number, total: number): TeamCanvasPosition {
  const step = MEMBER_WIDTH + MEMBER_GAP
  return { x: (index - (total - 1) / 2) * step, y: LINE_Y }
}

function defaultMeshPosition(index: number, total: number): TeamCanvasPosition {
  if (total <= 1) return { x: 0, y: MESH_MEMBER_Y }
  const perRow = Math.min(total, 4)
  const row = Math.floor(index / perRow)
  const col = index % perRow
  const rowCount = Math.ceil(total / perRow)
  const lastRowSize = total - (rowCount - 1) * perRow
  const colsThisRow = row === rowCount - 1 ? lastRowSize : perRow
  const step = MEMBER_WIDTH + MEMBER_GAP
  return {
    x: (col - (colsThisRow - 1) / 2) * step,
    y: MESH_MEMBER_Y + row * MESH_ROW_GAP,
  }
}

function parseAgentDrop(raw: string): TeamCanvasAgentDragPayload | null {
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<TeamCanvasAgentDragPayload>
    if (parsed.type !== 'tsushin-team-agent' || typeof parsed.agentId !== 'number') return null
    return { type: 'tsushin-team-agent', agentId: parsed.agentId }
  } catch {
    return null
  }
}

function makeOrderedEdge(source: string, target: string, index: number): Edge {
  return {
    id: `team-line-${source}-${target}-${index}`,
    source,
    target,
  }
}

function makeMeshEdge(target: string, index: number): Edge {
  return {
    id: `team-mesh-coordinator-${target}-${index}`,
    source: 'team-coordinator',
    target,
  }
}

function TeamCanvasInner({
  team,
  agents = [],
  addableAgents,
  readOnly,
  onAddMember,
  onRemoveMember,
  onReorderMembers,
  onUpdateMemberPosition,
  onToggleRequired,
  onResetLayout,
}: TeamCanvasProps) {
  const { fitView, screenToFlowPosition } = useReactFlow()
  const [isDragOver, setIsDragOver] = useState(false)
  const members = useMemo(() => orderedMembers(team), [team])
  const agentById = useMemo(() => new Map(agents.map((agent) => [agent.id, agent])), [agents])
  const addableAgentById = useMemo(() => new Map(addableAgents.map((agent) => [agent.id, agent])), [addableAgents])

  const reorderMember = useCallback((member: TeamMemberResponse, direction: 'up' | 'down') => {
    if (readOnly) return
    const currentIndex = members.findIndex((item) => item.id === member.id)
    if (currentIndex < 0) return
    const targetIndex = direction === 'up' ? currentIndex - 1 : currentIndex + 1
    if (targetIndex < 0 || targetIndex >= members.length) return

    const nextMembers = [...members]
    const current = nextMembers[currentIndex]
    nextMembers[currentIndex] = nextMembers[targetIndex]
    nextMembers[targetIndex] = current
    onReorderMembers(nextMembers.map((item, index) => ({ ...item, execution_order: index + 1 })))
  }, [members, onReorderMembers, readOnly])

  const baseNodes = useMemo<TeamCanvasNode[]>(() => {
    const topology = team.topology === 'mesh' ? 'mesh' : 'line'
    const memberNodes: TeamCanvasNode[] = members.map((member, index) => {
      const position = persistedPosition(member) ?? (topology === 'mesh'
        ? defaultMeshPosition(index, members.length)
        : defaultLinePosition(index, members.length))

      return {
        id: `team-member-${member.id}`,
        type: 'team-member',
        position,
        data: {
          type: 'team-member',
          member,
          agent: agentById.get(member.agent_id),
          label: memberLabel(member),
          topology,
          orderLabel: topology === 'line' ? `Step ${index + 1}` : `Member ${index + 1}`,
          readOnly,
          canMoveEarlier: topology === 'line' && index > 0,
          canMoveLater: topology === 'line' && index < members.length - 1,
          onRemove: onRemoveMember,
          onMoveEarlier: (target) => reorderMember(target, 'up'),
          onMoveLater: (target) => reorderMember(target, 'down'),
          onToggleRequired,
        },
      }
    })

    if (topology !== 'mesh') return memberNodes

    const coordinatorMember = team.members.find((member) => member.role === 'coordinator' || member.agent_id === team.coordinator_agent_id)
    const coordinatorLabel = coordinatorMember ? memberLabel(coordinatorMember) : 'Team coordinator'

    return [
      {
        id: 'team-coordinator',
        type: 'team-coordinator',
        position: { x: COORDINATOR_X, y: COORDINATOR_Y },
        draggable: false,
        data: {
          type: 'team-coordinator',
          label: coordinatorLabel,
          detail: team.coordinator_agent_id ? `Agent #${team.coordinator_agent_id}` : 'Managed mesh coordinator',
        },
      },
      ...memberNodes,
    ]
  }, [agentById, members, onRemoveMember, onToggleRequired, readOnly, reorderMember, team])

  const edges = useMemo<Edge[]>(() => {
    if (team.topology === 'mesh') {
      return members.map((member, index) => makeMeshEdge(`team-member-${member.id}`, index))
    }
    return members.slice(0, -1).map((member, index) => makeOrderedEdge(`team-member-${member.id}`, `team-member-${members[index + 1].id}`, index))
  }, [members, team.topology])

  const [nodes, setNodes] = useState<TeamCanvasNode[]>(baseNodes)
  const nodeKeyRef = useRef('')

  useEffect(() => {
    const nextKey = baseNodes.map((node) => `${node.id}:${node.position.x}:${node.position.y}`).join('|')
    if (nextKey === nodeKeyRef.current) return
    nodeKeyRef.current = nextKey
    setNodes(baseNodes)
    window.setTimeout(() => fitView({ padding: 0.24, duration: 220 }), 80)
  }, [baseNodes, fitView])

  const handleNodesChange = useCallback((changes: NodeChange<TeamCanvasNode>[]) => {
    setNodes((current) => applyNodeChanges(changes, current) as TeamCanvasNode[])
  }, [])

  const handleNodeDragStop = useCallback<NodeDragHandler>((_event, node) => {
    if (readOnly || node.data.type !== 'team-member') return
    onUpdateMemberPosition(node.data.member, { x: node.position.x, y: node.position.y })
  }, [onUpdateMemberPosition, readOnly])

  const handleDragStart = useCallback((event: React.DragEvent, agent: Agent) => {
    if (readOnly) {
      event.preventDefault()
      return
    }
    event.dataTransfer.effectAllowed = 'copy'
    event.dataTransfer.setData(TEAM_CANVAS_AGENT_MIME, makeTeamCanvasAgentDragPayload(agent))
  }, [readOnly])

  const handleDragOver = useCallback((event: React.DragEvent) => {
    if (readOnly) return
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
    setIsDragOver(true)
  }, [readOnly])

  const handleDragLeave = useCallback(() => {
    setIsDragOver(false)
  }, [])

  const handleDrop = useCallback((event: React.DragEvent) => {
    if (readOnly) return
    event.preventDefault()
    setIsDragOver(false)
    const payload = parseAgentDrop(event.dataTransfer.getData(TEAM_CANVAS_AGENT_MIME))
    if (!payload) return
    const agent = addableAgentById.get(payload.agentId)
    if (!agent) return
    const position = screenToFlowPosition({ x: event.clientX, y: event.clientY })
    onAddMember(agent, position)
  }, [addableAgentById, onAddMember, readOnly, screenToFlowPosition])

  const topologyLabel = team.topology === 'mesh' ? 'Mesh topology' : 'Line topology'
  const topologyDescription = team.topology === 'mesh'
    ? 'Coordinator spokes connect to every member.'
    : 'Members run in order with sequential handoffs.'

  return (
    <div className="team-canvas-shell grid gap-4 lg:grid-cols-[260px_1fr]">
      <aside className="rounded-xl border border-tsushin-border bg-tsushin-surface/70 p-4">
        <div className="mb-4 flex items-center gap-2">
          <PlusIcon size={17} className="text-tsushin-accent" />
          <div>
            <h3 className="text-sm font-semibold text-white">Add members</h3>
            <p className="text-xs text-tsushin-slate">{readOnly ? 'Read-only team' : 'Drag agents onto the canvas'}</p>
          </div>
        </div>

        <div className="space-y-2">
          {addableAgents.length === 0 ? (
            <div className="rounded-lg border border-dashed border-tsushin-border px-3 py-8 text-center text-sm text-tsushin-slate">
              No addable agents.
            </div>
          ) : addableAgents.map((agent) => (
            <div
              key={agent.id}
              draggable={!readOnly}
              onDragStart={(event) => handleDragStart(event, agent)}
              className={`team-addable-agent rounded-lg border border-tsushin-border bg-tsushin-surface/50 px-3 py-2 transition-colors hover:border-tsushin-muted ${readOnly ? 'disabled' : ''}`}
            >
              <div className="flex items-center gap-2">
                <BotIcon size={16} className="shrink-0 text-tsushin-accent" />
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-white">{agent.contact_name}</div>
                  <div className="truncate text-xs text-tsushin-slate">{agent.model_provider}/{agent.model_name}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </aside>

      <section className="overflow-hidden rounded-xl border border-tsushin-border bg-tsushin-surface">
        <div className="flex items-center justify-between gap-4 border-b border-tsushin-border px-4 py-3">
          <div className="flex items-center gap-2">
            <UsersIcon size={18} className="text-tsushin-accent" />
            <div>
              <h3 className="text-sm font-semibold text-white">{topologyLabel}</h3>
              <p className="text-xs text-tsushin-slate">{topologyDescription}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {!readOnly && onResetLayout && members.length > 0 && (
              <button
                type="button"
                onClick={() => onResetLayout()}
                className="team-toggle-btn"
                title="Reset all member positions to the default layout"
              >
                Auto arrange
              </button>
            )}
            <span className="badge badge-neutral">{members.length} members</span>
          </div>
        </div>

        <div
          className={`team-canvas h-[520px] w-full ${isDragOver ? 'drag-over' : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={handleNodesChange}
            onNodeDragStop={handleNodeDragStop}
            nodeTypes={teamNodeTypes}
            fitView
            minZoom={0.25}
            maxZoom={1.4}
            nodesDraggable={!readOnly}
            nodesConnectable={false}
            elementsSelectable
            selectNodesOnDrag={false}
            defaultEdgeOptions={{ type: 'straight', animated: false, style: { stroke: '#484F58', strokeWidth: 2 } }}
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="rgba(139, 146, 158, 0.16)" />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
      </section>
    </div>
  )
}

export default function TeamCanvas(props: TeamCanvasProps) {
  return (
    <ReactFlowProvider>
      <TeamCanvasInner {...props} />
    </ReactFlowProvider>
  )
}
