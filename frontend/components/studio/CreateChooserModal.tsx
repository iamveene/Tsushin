'use client'

/**
 * CreateChooserModal
 *
 * v0.7.1 IA — surfaces the three creation surfaces under Studio (Agent /
 * Continuous Agent / Team) side-by-side with one-paragraph orientation
 * for each. Pre-fix the SplitButton on the Studio Agents page only
 * exposed Agent + Team and gave operators no way to discover that
 * Continuous Agents existed at all (they were hidden in Watcher). This
 * modal closes that discovery gap and lets the user pick the right
 * surface up front instead of guessing or navigating to Watcher to find
 * it.
 *
 * The component is a presentation-only chooser — it dispatches via the
 * onSelect prop and does NOT mount any of the underlying create modals
 * itself. That keeps the routing concerns where they already live (the
 * agent wizard for Agent, the SplitButton route for Continuous Agent,
 * `/studio/teams` for Team).
 */

import type { ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { BotIcon, LightningIcon, UsersIcon } from '@/components/ui/icons'

export type ChosenKind = 'agent' | 'continuous-agent' | 'team'

interface Props {
  open: boolean
  onClose: () => void
  /**
   * Called with the picked kind. The Studio Agents page wires this to
   * its existing agent-wizard launcher (kind='agent'), to the
   * `/studio/continuous-agents?new=1` deep link (kind='continuous-agent'),
   * and to `/studio/teams?new=1` (kind='team'). Callers in other Studio
   * pages can override the routing by handling the kind themselves.
   */
  onSelect: (kind: ChosenKind) => void
}

interface OptionCardProps {
  Icon: React.FC<{ size?: number; className?: string }>
  iconColorClass: string
  title: string
  badge: string
  tagline: string
  bullets: string[]
  example: string
  onClick: () => void
  ctaLabel: string
}

function OptionCard({ Icon, iconColorClass, title, badge, tagline, bullets, example, onClick, ctaLabel }: OptionCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex flex-col rounded-xl border border-tsushin-border bg-tsushin-ink/40 p-4 text-left transition hover:border-cyan-500/40 hover:bg-cyan-500/5"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`flex h-9 w-9 items-center justify-center rounded-lg bg-tsushin-surface ${iconColorClass}`}>
            <Icon size={20} />
          </span>
          <h3 className="text-base font-semibold text-white">{title}</h3>
        </div>
        <span className="rounded-full border border-tsushin-border/60 bg-tsushin-surface/40 px-2 py-0.5 text-[10px] uppercase tracking-wide text-tsushin-slate">
          {badge}
        </span>
      </div>
      <p className="mt-2 text-sm text-tsushin-fog">{tagline}</p>
      <ul className="mt-3 space-y-1 text-xs text-tsushin-slate">
        {bullets.map((b) => (
          <li key={b} className="flex gap-1.5">
            <span className="text-cyan-400">•</span>
            <span>{b}</span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-[11px] italic text-tsushin-muted">e.g. {example}</p>
      <div className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-cyan-300 group-hover:text-cyan-200">
        {ctaLabel} →
      </div>
    </button>
  )
}

export default function CreateChooserModal({ open, onClose, onSelect }: Props) {
  const router = useRouter()
  if (!open) return null

  function pick(kind: ChosenKind) {
    onSelect(kind)
    onClose()
  }

  function pickContinuousAgent() {
    // Default routing for Continuous Agent — Studio's CA page picks up
    // `?new=1` and opens the setup modal. Callers can override via the
    // onSelect dispatch above; this is the fallback so the modal stays
    // useful even when wired into pages that don't handle the kind
    // themselves.
    onSelect('continuous-agent')
    onClose()
    router.push('/studio/continuous-agents?new=1')
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-5xl rounded-2xl border border-tsushin-border bg-tsushin-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-tsushin-border px-6 py-4">
          <div>
            <h2 className="text-xl font-display font-bold text-white">What do you want to build?</h2>
            <p className="mt-0.5 text-sm text-tsushin-slate">
              Pick the surface that matches the job. You can always create more later.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-tsushin-slate hover:text-white"
            aria-label="Close"
          >
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="grid gap-4 p-6 md:grid-cols-3">
          <OptionCard
            Icon={BotIcon as React.FC<{ size?: number; className?: string }>}
            iconColorClass="text-teal-300"
            title="Agent"
            badge="On-demand"
            tagline="Configurable persona + skills + model. Replies when you message it; the foundation for the other two."
            bullets={[
              'Conversational replies (WhatsApp, Telegram, Playground).',
              'Skills, custom tools, persona, model.',
              'No always-on runtime — runs only when invoked.',
            ]}
            example='"Customer-support bot that answers WhatsApp DMs."'
            onClick={() => pick('agent')}
            ctaLabel="Create agent"
          />

          <OptionCard
            Icon={LightningIcon as React.FC<{ size?: number; className?: string }>}
            iconColorClass="text-emerald-300"
            title="Continuous Agent"
            badge="Always-on"
            tagline="Wraps an existing Agent so it wakes on a trigger event with daily budget caps."
            bullets={[
              'Reacts to inbound events (email, Jira, GitHub, webhook).',
              'Daily budget enforcement (runs/tokens/tool-calls).',
              'Optional notify-only mode — record wakes without running the agent.',
              'Persistent run history per wake event.',
            ]}
            example='"When a Jira P0 ticket lands, page the on-call agent."'
            onClick={pickContinuousAgent}
            ctaLabel="Create continuous agent"
          />

          <OptionCard
            Icon={UsersIcon as React.FC<{ size?: number; className?: string }>}
            iconColorClass="text-indigo-300"
            title="Team"
            badge="Multi-agent"
            tagline="Coordinate multiple agents on one task — sequential (line) or collaborative (mesh)."
            bullets={[
              'Multiple agents executing one goal together.',
              'Topology: LINE (each runs in order) or MESH (coordinator dispatches).',
              'Bind to a trigger to run automatically on inbound events.',
              'Per-team budget + run history.',
            ]}
            example='"Triage → Investigate → Respond. Three agents, one Jira ticket."'
            onClick={() => pick('team')}
            ctaLabel="Create team"
          />
        </div>

        <div className="border-t border-tsushin-border bg-tsushin-ink/40 px-6 py-3 text-xs text-tsushin-slate">
          Not sure? Start with an <span className="text-white">Agent</span> — every Continuous Agent and Team is built on top of one.
        </div>
      </div>
    </div>
  )
}
