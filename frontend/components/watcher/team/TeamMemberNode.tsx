'use client'

import { memo, useState } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { ArrowDownIcon, ArrowUpIcon, BotIcon, ChevronDownIcon, TrashIcon } from '@/components/ui/icons'
import type { TeamMemberNodeData } from './types'

function TeamMemberNode({ data, selected }: NodeProps) {
  const d = data as TeamMemberNodeData
  const isReadOnly = d.readOnly
  const [expanded, setExpanded] = useState(false)

  return (
    <div
      role="group"
      aria-label={`Team member: ${d.label}`}
      className={`team-node team-member-node rounded-lg border bg-tsushin-surface px-4 py-3 transition-all ${
        selected ? 'border-tsushin-indigo shadow-glow-sm' : 'border-tsushin-border hover:border-tsushin-muted'
      }`}
    >
      <Handle type="target" position={Position.Left} className="team-handle" />
      <Handle type="target" position={Position.Top} className="team-handle" />
      <Handle type="source" position={Position.Right} className="team-handle" />
      <Handle type="source" position={Position.Bottom} className="team-handle" />

      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-tsushin-border bg-tsushin-deep text-tsushin-accent">
          <BotIcon size={18} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="truncate text-sm font-semibold text-white">{d.label}</h3>
              <p className="mt-1 text-xs text-tsushin-slate">{d.orderLabel}</p>
            </div>
            {!isReadOnly && (
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation()
                  d.onRemove(d.member)
                }}
                className="nodrag nopan rounded-md p-1 text-tsushin-muted transition-colors hover:bg-tsushin-vermilion/10 hover:text-tsushin-vermilion"
                title="Remove member"
                aria-label={`Remove ${d.label}`}
              >
                <TrashIcon size={15} />
              </button>
            )}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className={`badge ${d.member.is_required ? 'badge-success' : 'badge-neutral'}`}>
              {d.member.is_required ? 'Required' : 'Optional'}
            </span>
            <span className="badge badge-neutral">{d.member.role || 'member'}</span>
            {d.agent?.skills_count !== undefined && <span className="badge badge-neutral">{d.agent.skills_count} skills</span>}
          </div>

          <div className="nodrag nopan mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation()
                setExpanded((value) => !value)
              }}
              className="team-toggle-btn inline-flex items-center gap-1"
              aria-expanded={expanded}
            >
              <ChevronDownIcon size={13} className={`transition-transform ${expanded ? 'rotate-180' : ''}`} />
              Details
            </button>
            {!isReadOnly && (
              <>
              <button
                type="button"
                disabled={!d.canMoveEarlier}
                onClick={(event) => {
                  event.stopPropagation()
                  d.onMoveEarlier(d.member)
                }}
                className="team-icon-btn"
                title="Move earlier"
                aria-label={`Move ${d.label} earlier`}
              >
                <ArrowUpIcon size={14} />
              </button>
              <button
                type="button"
                disabled={!d.canMoveLater}
                onClick={(event) => {
                  event.stopPropagation()
                  d.onMoveLater(d.member)
                }}
                className="team-icon-btn"
                title="Move later"
                aria-label={`Move ${d.label} later`}
              >
                <ArrowDownIcon size={14} />
              </button>
              {d.onToggleRequired && (
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation()
                    d.onToggleRequired?.(d.member)
                  }}
                  className="team-toggle-btn"
                >
                  {d.member.is_required ? 'Make optional' : 'Require'}
                </button>
              )}
              </>
            )}
          </div>

          {expanded && (
            <div className="nodrag nopan mt-3 rounded-lg border border-tsushin-border bg-tsushin-deep/70 p-3 text-xs text-tsushin-slate">
              <div className="grid gap-2">
                <DetailRow label="Model" value={d.agent ? `${d.agent.model_provider}/${d.agent.model_name}` : 'Unavailable'} />
                <DetailRow label="Skills" value={d.agent?.skills_count !== undefined ? String(d.agent.skills_count) : 'Unknown'} />
                <DetailRow label="Channels" value={d.agent?.enabled_channels?.length ? d.agent.enabled_channels.join(', ') : 'Default'} />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-tsushin-muted">{label}</span>
      <span className="truncate text-right text-white">{value}</span>
    </div>
  )
}

export default memo(TeamMemberNode)
