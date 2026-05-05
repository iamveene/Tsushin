'use client'

/**
 * Getting Started Checklist
 *
 * BUG-320: Hidden when the onboarding tour is active (tour modal and checklist competed for attention).
 * BUG-322: "Connect a Channel" item now calls forceOpenWizard() directly instead of linking to
 *          /hub?tab=channels, ensuring the guided wizard always launches (even after dismissal).
 */

import { useState } from 'react'
import Link from 'next/link'
import { useSetupProgress } from '@/hooks/useSetupProgress'
import { useOnboarding } from '@/contexts/OnboardingContext'
import { useWhatsAppWizard } from '@/contexts/WhatsAppWizardContext'

const DISMISSED_KEY = 'tsushin_getting_started_dismissed'

interface ChecklistItem {
  title: string
  subtitle: string
  href?: string
  actionLabel: string
  completedKey: keyof ReturnType<typeof useSetupProgress>
  onClick?: () => void
}

export default function GettingStartedChecklist() {
  const progress = useSetupProgress()
  const [dismissed, setDismissed] = useState(() => {
    if (typeof window === 'undefined') return true
    return localStorage.getItem(DISMISSED_KEY) === 'true'
  })
  const { state: onboardingState } = useOnboarding()
  const { forceOpenWizard } = useWhatsAppWizard()

  // BUG-320: Hide checklist while onboarding tour is active — they compete for attention
  if (onboardingState.isActive) return null

  if (dismissed || progress.loading || progress.allComplete) return null

  const items: ChecklistItem[] = [
    {
      title: 'Configure an AI Agent',
      subtitle: 'Create and customize your AI assistant',
      href: '/agents',
      actionLabel: 'Go to Studio',
      completedKey: 'hasAgents',
    },
    {
      // BUG-322: Use forceOpenWizard instead of linking directly to Hub.
      title: 'Connect a Channel',
      subtitle: 'Set up WhatsApp, Telegram, or other channels',
      actionLabel: 'Launch Setup Wizard',
      completedKey: 'hasChannels',
      onClick: forceOpenWizard,
    },
    {
      title: 'Add Contacts',
      subtitle: 'Register people your agent should recognize',
      href: '/agents/contacts',
      actionLabel: 'Add Contacts',
      completedKey: 'hasContacts',
    },
    {
      title: 'Test in Playground',
      subtitle: 'Send a test message to your agent',
      href: '/playground',
      actionLabel: 'Open Playground',
      completedKey: 'hasMessages',
    },
    {
      title: 'Create a Flow',
      subtitle: 'Automate tasks with visual workflows',
      href: '/flows',
      actionLabel: 'Create Flow',
      completedKey: 'hasFlows',
    },
  ]

  const completedCount = items.filter(item => progress[item.completedKey]).length
  const progressPercent = (completedCount / items.length) * 100

  return (
    <div className="glass-card border-l-4 border-tsushin-indigo p-5 mb-6 animate-fade-in relative">
      {/* Dismiss button */}
      <button
        onClick={() => {
          localStorage.setItem(DISMISSED_KEY, 'true')
          setDismissed(true)
        }}
        className="absolute top-3 right-3 text-tsushin-slate hover:text-white transition-colors"
        title="Dismiss"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>

      {/* Header */}
      <div className="mb-4">
        <h3 className="text-white font-semibold text-base font-display">Getting Started</h3>
        <p className="text-tsushin-slate text-xs mt-1">{completedCount} of {items.length} complete</p>
        <div className="w-full bg-tsushin-deep rounded-full h-1.5 mt-2">
          <div
            className="bg-gradient-to-r from-teal-500 to-cyan-500 h-1.5 rounded-full transition-all duration-500"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Checklist items */}
      <div className="space-y-3">
        {items.map((item) => {
          const completed = progress[item.completedKey]
          return (
            <div key={item.title} className="flex items-center gap-3">
              {/* Check circle */}
              <div className={`flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center ${
                completed
                  ? 'bg-tsushin-success'
                  : 'border-2 border-tsushin-slate/30'
              }`}>
                {completed && (
                  <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                  </svg>
                )}
              </div>

              {/* Text */}
              <div className="flex-1 min-w-0">
                <p className={`text-sm font-medium ${completed ? 'text-tsushin-slate line-through' : 'text-white'}`}>
                  {item.title}
                </p>
                <p className="text-xs text-tsushin-slate/70 truncate">{item.subtitle}</p>
              </div>

              {/* Action — either a button (onClick) or a Link (href) */}
              {!completed && (
                item.onClick ? (
                  <button
                    onClick={item.onClick}
                    className="flex-shrink-0 px-3 py-1 text-xs font-medium bg-teal-600/20 text-teal-400 hover:bg-teal-600/30 rounded-lg transition-colors"
                  >
                    {item.actionLabel}
                  </button>
                ) : (
                  <Link
                    href={item.href!}
                    className="flex-shrink-0 px-3 py-1 text-xs font-medium bg-teal-600/20 text-teal-400 hover:bg-teal-600/30 rounded-lg transition-colors"
                  >
                    {item.actionLabel}
                  </Link>
                )
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
