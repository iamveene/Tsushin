'use client'

import Link from 'next/link'
import {
  BotIcon,
  PlugIcon,
  EyeIcon,
  PlayIcon,
  SettingsIcon,
} from '@/components/ui/icons'

interface Section {
  href: string
  label: string
  tagline: string
  description: string
  Icon: React.ComponentType<{ size?: number; className?: string }>
  iconClass: string
  borderClass: string
}

const SECTIONS: Section[] = [
  {
    href: '/agents',
    label: 'Studio',
    tagline: 'Where you build.',
    description:
      'Configure agents (personas, skills, channels), contacts, projects, teams, continuous agents, and custom skills. This is where you decide who your agents are and what they can do.',
    Icon: BotIcon,
    iconClass: 'text-tsushin-vermilion',
    borderClass: 'border-tsushin-vermilion/30 bg-tsushin-vermilion/5',
  },
  {
    href: '/hub',
    label: 'Hub',
    tagline: 'Where you wire external services.',
    description:
      'Connect AI providers, channels (WhatsApp / Slack / Discord / Email), triggers (Jira / GitHub / Webhook), tool APIs (1Password, GitHub credentials, etc.), and self-hosted local services (Whisper / Ollama). Anything that lives outside Tsushin and your agents need to talk to lives here.',
    Icon: PlugIcon,
    iconClass: 'text-cyan-300',
    borderClass: 'border-cyan-500/30 bg-cyan-500/5',
  },
  {
    href: '/',
    label: 'Watcher',
    tagline: 'Where you monitor.',
    description:
      'Observe agent runs, conversations, wake events, security incidents, channel health, and costs. Run history and observability across all kinds of agents (single, continuous, team) in one place.',
    Icon: EyeIcon,
    iconClass: 'text-tsushin-indigo-glow',
    borderClass: 'border-tsushin-indigo/30 bg-tsushin-indigo/5',
  },
  {
    href: '/playground',
    label: 'Playground',
    tagline: 'Where you test.',
    description:
      'Chat with your agents to verify prompts, skills, and tool calls before pointing real channels at them. Audio recording, document uploads, memory inspection, and a floating Mini-Playground bubble on every page.',
    Icon: PlayIcon,
    iconClass: 'text-emerald-300',
    borderClass: 'border-emerald-500/30 bg-emerald-500/5',
  },
  {
    href: '/settings',
    label: 'Core',
    tagline: 'Where you configure the org.',
    description:
      'Tenant-level settings: team members, plan & billing, default routing, system AI, audit logs, retention, RBAC, and Sentinel security policy. Settings here apply to the whole tenant, not a single agent.',
    Icon: SettingsIcon,
    iconClass: 'text-tsushin-slate',
    borderClass: 'border-tsushin-border bg-tsushin-surface/40',
  },
]

interface Props {
  open: boolean
  onClose: () => void
}

export default function MentalModelLegend({ open, onClose }: Props) {
  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-3xl max-h-[85vh] overflow-y-auto rounded-2xl border border-tsushin-border bg-tsushin-ink shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-tsushin-border bg-tsushin-ink px-6 py-4">
          <div>
            <h2 className="text-xl font-display font-bold text-white">What is each section?</h2>
            <p className="mt-1 text-sm text-tsushin-slate">
              Tsushin has five top-level sections. Each one has a single job — knowing which is which makes everything
              easier to find.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-tsushin-slate transition-colors hover:text-white"
            aria-label="Close"
          >
            <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="grid grid-cols-1 gap-3 p-6 md:grid-cols-2">
          {SECTIONS.map((section) => {
            const Icon = section.Icon
            return (
              <Link
                key={section.label}
                href={section.href}
                onClick={onClose}
                className={`block rounded-xl border p-4 transition-colors hover:bg-tsushin-surface/60 ${section.borderClass}`}
              >
                <div className="mb-2 flex items-center gap-3">
                  <Icon size={22} className={section.iconClass} />
                  <div>
                    <div className="text-base font-display font-semibold text-white">{section.label}</div>
                    <div className="text-xs text-tsushin-slate">{section.tagline}</div>
                  </div>
                </div>
                <p className="text-sm leading-6 text-tsushin-fog">{section.description}</p>
              </Link>
            )
          })}
        </div>

        <div className="border-t border-tsushin-border bg-tsushin-surface/30 px-6 py-4 text-xs text-tsushin-slate">
          Tip: <span className="text-tsushin-fog">Configuration lives in Studio + Hub. Observability lives in Watcher. Testing lives in Playground. Org settings live in Core.</span>
        </div>
      </div>
    </div>
  )
}
