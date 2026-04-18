'use client'

/**
 * MiniHeader — header row for the Playground Mini panel.
 * Row 1: agent + project selects.
 * Row 2: thread title • new thread • expand (handover) • close.
 */

import React from 'react'
import { useRouter } from 'next/navigation'
import { PlaygroundAgentInfo, PlaygroundThread, Project } from '@/lib/client'
import { ExternalLinkIcon, PlusIcon, XIcon, SparklesIcon } from '@/components/ui/icons'

interface MiniHeaderProps {
  agents: PlaygroundAgentInfo[]
  projects: Project[]
  threads: PlaygroundThread[]

  selectedAgentId: number | null
  selectedProjectId: number | null
  activeThreadId: number | null
  activeThread: PlaygroundThread | null

  onSelectAgent: (id: number) => void
  onSelectProject: (id: number | null) => void
  onSelectThread: (id: number) => void
  onNewThread: () => void
  onClose: () => void
  titleId: string
}

export default function MiniHeader({
  agents,
  projects,
  threads,
  selectedAgentId,
  selectedProjectId,
  activeThreadId,
  activeThread,
  onSelectAgent,
  onSelectProject,
  onSelectThread,
  onNewThread,
  onClose,
  titleId,
}: MiniHeaderProps) {
  const router = useRouter()

  const threadTitle =
    activeThread?.title ||
    threads.find(t => t.id === activeThreadId)?.title ||
    (activeThreadId ? `Thread #${activeThreadId}` : 'New conversation')

  const handleExpand = () => {
    const params = new URLSearchParams()
    if (activeThreadId) params.set('thread', String(activeThreadId))
    if (selectedAgentId) params.set('agent', String(selectedAgentId))
    if (selectedProjectId) params.set('project', String(selectedProjectId))
    onClose()
    router.push(`/playground${params.toString() ? `?${params.toString()}` : ''}`)
  }

  return (
    <div className="px-3 pt-3 pb-2 border-b border-tsushin-border bg-tsushin-surface flex flex-col gap-2">
      {/* Row 1 — title + actions */}
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1.5 flex-shrink-0 text-tsushin-accent">
          <SparklesIcon size={14} />
          <h2 id={titleId} className="text-xs font-semibold uppercase tracking-wide text-gray-200">
            Playground Mini
          </h2>
        </div>
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onClick={onNewThread}
            disabled={!selectedAgentId}
            title="New thread"
            aria-label="New thread"
            className="w-7 h-7 rounded-md text-tsushin-slate hover:text-white hover:bg-tsushin-elevated disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tsushin-accent"
          >
            <PlusIcon size={15} />
          </button>
          <button
            type="button"
            onClick={handleExpand}
            title="Expand to full Playground"
            aria-label="Expand to full Playground"
            className="w-7 h-7 rounded-md text-tsushin-slate hover:text-white hover:bg-tsushin-elevated flex items-center justify-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tsushin-accent"
          >
            <ExternalLinkIcon size={15} />
          </button>
          <button
            type="button"
            onClick={onClose}
            title="Close (Esc)"
            aria-label="Close Playground Mini"
            className="w-7 h-7 rounded-md text-tsushin-slate hover:text-white hover:bg-tsushin-elevated flex items-center justify-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tsushin-accent"
          >
            <XIcon size={15} />
          </button>
        </div>
      </div>

      {/* Row 2 — agent + project selectors */}
      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-0.5 min-w-0">
          <span className="text-[10px] uppercase tracking-wide text-tsushin-slate">Agent</span>
          <select
            value={selectedAgentId ?? ''}
            onChange={e => onSelectAgent(Number(e.target.value))}
            disabled={agents.length === 0}
            aria-label="Select agent"
            className="bg-tsushin-elevated border border-tsushin-border rounded-md px-2 py-1 text-xs text-gray-100 focus:outline-none focus:ring-1 focus:ring-tsushin-accent focus:border-tsushin-accent disabled:opacity-50 truncate"
          >
            {agents.length === 0 && <option value="">No agents</option>}
            {agents.map(a => (
              <option key={a.id} value={a.id}>
                {a.name}
                {a.is_default ? ' ★' : ''}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-0.5 min-w-0">
          <span className="text-[10px] uppercase tracking-wide text-tsushin-slate">Project</span>
          <select
            value={selectedProjectId ?? ''}
            onChange={e => {
              const v = e.target.value
              onSelectProject(v === '' ? null : Number(v))
            }}
            aria-label="Select project"
            className="bg-tsushin-elevated border border-tsushin-border rounded-md px-2 py-1 text-xs text-gray-100 focus:outline-none focus:ring-1 focus:ring-tsushin-accent focus:border-tsushin-accent truncate"
          >
            <option value="">(No project)</option>
            {projects.map(p => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {/* Row 3 — thread picker + title */}
      <div className="flex items-center gap-2">
        <select
          value={activeThreadId ?? ''}
          onChange={e => {
            const v = e.target.value
            if (v) onSelectThread(Number(v))
          }}
          aria-label="Select thread"
          className="flex-1 min-w-0 bg-tsushin-elevated border border-tsushin-border rounded-md px-2 py-1 text-xs text-gray-100 focus:outline-none focus:ring-1 focus:ring-tsushin-accent focus:border-tsushin-accent truncate"
        >
          <option value="">{threadTitle}</option>
          {threads.map(t => (
            <option key={t.id} value={t.id}>
              {t.title || `Thread #${t.id}`}
            </option>
          ))}
        </select>
      </div>
    </div>
  )
}
