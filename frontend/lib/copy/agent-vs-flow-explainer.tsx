/**
 * AgentVsFlowExplainer
 *
 * v0.7.0-fix Phase 7 — single source of truth for the "when do I use a
 * Continuous Agent vs a Flow?" copy. The user complained that operators
 * had to guess which one solves their problem when configuring; this
 * panel renders identically at the top of both creation surfaces so the
 * comparison is unmistakable.
 *
 * Render via either <AgentVsFlowExplainer kind="agent" /> or
 * kind="flow" — only the highlight changes; the copy stays in lock-step.
 */

import type { ReactNode } from 'react'

interface Props {
  /** Which surface is rendering this — controls which side is highlighted. */
  kind: 'agent' | 'flow'
  /** Optional inline class overrides (e.g. for spacing in the parent). */
  className?: string
}

interface SideProps {
  active: boolean
  title: string
  tagline: string
  bullets: string[]
  example: string
  badge: ReactNode
}

function Side({ active, title, tagline, bullets, example, badge }: SideProps) {
  const baseBorder = active ? 'border-cyan-500/60 bg-cyan-500/5' : 'border-tsushin-border bg-tsushin-ink/40'
  const activeBadge = active ? 'bg-cyan-500/20 text-cyan-200 border-cyan-500/40' : 'bg-tsushin-border/40 text-tsushin-slate border-tsushin-border'
  return (
    <div className={`rounded-xl border ${baseBorder} p-3`}>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">{title}</h3>
        <span className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${activeBadge}`}>
          {badge}
        </span>
      </div>
      <p className="mt-1 text-xs text-tsushin-slate">{tagline}</p>
      <ul className="mt-2 space-y-1 text-xs text-tsushin-fog">
        {bullets.map((b) => (
          <li key={b} className="flex gap-1">
            <span className="text-cyan-400">•</span>
            <span>{b}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[11px] italic text-tsushin-slate">e.g. {example}</p>
    </div>
  )
}

export default function AgentVsFlowExplainer({ kind, className }: Props) {
  return (
    <div className={`rounded-xl border border-tsushin-border bg-tsushin-ink/30 p-3 ${className ?? ''}`}>
      <div className="mb-2 text-xs uppercase tracking-wide text-tsushin-slate">
        Continuous Agent vs Flow — pick the right surface
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <Side
          active={kind === 'agent'}
          title="Continuous Agent"
          tagline="Always-on wrapper around an existing agent that wakes on external events."
          bullets={[
            'Reacts to inbound events (email, Jira, GitHub, webhook).',
            'Runs the same agent each time — stateful budget + run history.',
            'Lives under Watcher → Continuous Agents.',
          ]}
          example='"When a Jira P0 ticket arrives, page on-call."'
          badge={kind === 'agent' ? 'You are here' : 'Reactive'}
        />
        <Side
          active={kind === 'flow'}
          title="Flow"
          tagline="Multi-step workflow with branches, fired immediately, on a schedule, by keyword, or by a trigger binding."
          bullets={[
            'Declarative steps (notification, tool, conversation).',
            'Best for branching logic and explicit ordering.',
            'Lives under Flows.',
          ]}
          example='"Daily 9am: collect overnight build failures, summarize, post to Slack."'
          badge={kind === 'flow' ? 'You are here' : 'Declarative'}
        />
      </div>
    </div>
  )
}
