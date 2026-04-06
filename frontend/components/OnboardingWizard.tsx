'use client'

/**
 * Onboarding Wizard Component
 * Phase 3: Frontend Onboarding Wizard
 *
 * Interactive tour that guides users through Tsushin platform features.
 * Auto-starts for new users, can be minimized, and easily dismissible.
 */

import React, { useEffect, useCallback } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { useOnboarding } from '@/contexts/OnboardingContext'
import Modal from '@/components/ui/Modal'

interface TourStep {
  title: string
  content: string
  highlightFeatures?: string[]
  targetSelector?: string | null
  actionButton?: {
    label: string
    action: () => void
  }
}

export default function OnboardingWizard() {
  const { state, nextStep, previousStep, minimize, maximize, completeTour, skipTour } = useOnboarding()
  const router = useRouter()
  const pathname = usePathname()
  const isAuthPage = pathname?.startsWith('/auth/')

  const openUserGuide = useCallback(() => {
    window.dispatchEvent(new CustomEvent('tsushin:open-user-guide'))
    minimize()
  }, [minimize])

  const tourSteps: TourStep[] = [
    {
      title: 'Welcome to Tsushin!',
      targetSelector: null,
      content: 'Tsushin is a powerful multi-agent platform that helps you build, deploy, and manage AI agents across multiple communication channels. This tour covers the mandatory setup steps to get you operational. For detailed documentation, open the User Guide anytime via the ? button in the header.',
      highlightFeatures: [
        'Multi-agent orchestration',
        'WhatsApp & Telegram integration',
        'Skill-based agent capabilities',
        'Flow automation & scheduling'
      ],
      actionButton: {
        label: 'Open User Guide',
        action: openUserGuide
      }
    },
    {
      title: 'Watcher - Real-Time Monitoring',
      targetSelector: 'nav a[href="/"]',
      content: 'The Watcher dashboard provides real-time visibility into all conversations across your agents and channels. Monitor message streams, track agent activity, and gain insights into user interactions.',
      highlightFeatures: [
        'Real-time message stream',
        'Multi-channel monitoring',
        'Agent activity tracking',
        'Search and filter capabilities'
      ]
    },
    {
      title: 'Studio - Agent Management',
      targetSelector: 'a[href="/agents"]',
      content: 'The Studio is where you create, configure, and manage your AI agents. Define agent personalities, assign skills, and control how agents interact with users.',
      highlightFeatures: [
        'Create custom agents',
        'Configure agent personalities (Personas)',
        'Assign skills and tools',
        'Set trigger conditions'
      ],
      actionButton: {
        label: 'Go to Studio',
        action: () => router.push('/agents')
      }
    },
    {
      title: 'Hub - AI Providers & System AI',
      targetSelector: 'a[href="/hub"]',
      content: 'The Hub centralizes all your external integrations. Your primary AI provider was automatically set as the System AI during setup — this powers intent classification, skill routing, and other system operations. You can add more providers or change the System AI here at any time.',
      highlightFeatures: [
        'System AI auto-configured from your setup provider',
        'Add multiple AI providers for failover',
        'Google OAuth for Gmail & Calendar (optional)',
        'Encrypted API key storage'
      ],
      actionButton: {
        label: 'Open Hub',
        action: () => router.push('/hub')
      }
    },
    {
      title: 'Communication Channels (Required)',
      targetSelector: 'a[href="/hub"]',
      content: 'To receive and respond to messages, you must connect at least one communication channel. Set up WhatsApp via QR code scanning in the Hub, connect Telegram with a bot token, or configure webhooks for other services. Without a channel, your agents can only be tested in the Playground.',
      highlightFeatures: [
        'WhatsApp: scan QR code to connect your phone',
        'Telegram: add your bot token',
        'Webhooks: connect Slack, Discord, or custom services',
        'Each channel can be independently routed to agents'
      ],
      actionButton: {
        label: 'Set Up Channels in Hub',
        action: () => router.push('/hub')
      }
    },
    {
      title: 'Flows - Automation & Scheduling',
      targetSelector: 'a[href="/flows"]',
      content: 'Flows enable you to create automated workflows, scheduled tasks, and multi-step agent orchestrations. Build complex automation without code.',
      highlightFeatures: [
        'Visual flow builder',
        'Scheduled task execution',
        'Multi-agent workflows',
        'Trigger conditions and actions'
      ],
      actionButton: {
        label: 'Explore Flows',
        action: () => router.push('/flows')
      }
    },
    {
      title: 'Playground - Safe Testing Environment',
      targetSelector: 'a[href="/playground"]',
      content: 'The Playground is your safe space to test agents, experiment with prompts, and validate configurations before connecting real channels.',
      highlightFeatures: [
        'Test agents in isolation',
        'Switch between agents',
        'Thread-based conversations',
        'Document context testing'
      ],
      actionButton: {
        label: 'Try Playground',
        action: () => router.push('/playground')
      }
    },
    {
      title: 'Security & API Access',
      targetSelector: null,
      content: 'Tsushin includes built-in AI security controls and a public API for programmatic access. Sentinel and MemGuard protect your agents from prompt injection and data leaks. The API v1 lets external systems interact with your agents.',
      highlightFeatures: [
        'Sentinel AI security and MemGuard protection',
        'Security profiles with SSRF protection',
        'API v1 for programmatic access',
        'OAuth2 client credentials for integrations'
      ],
      actionButton: {
        label: 'Go to Settings',
        action: () => router.push('/settings')
      }
    },
    {
      title: 'Setup Checklist',
      targetSelector: null,
      content: 'Here is a summary of the mandatory and recommended steps to get Tsushin fully operational. Complete these to ensure your agents can communicate across all channels.',
      highlightFeatures: [
        'AI Provider configured (done during setup)',
        'System AI auto-assigned (done during setup)',
        'Connect a channel: WhatsApp or Telegram (Hub)',
        'Test your agents in the Playground',
        'Review the User Guide for advanced features (?)'
      ],
      actionButton: {
        label: 'Finish & Go to Playground',
        action: () => {
          router.push('/playground')
          completeTour()
        }
      }
    }
  ]

  const currentStepData = tourSteps[state.currentStep - 1]

  // Handle keyboard shortcuts
  useEffect(() => {
    if (!state.isActive || state.isMinimized) return

    const handleKeyPress = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        minimize()
      } else if (e.key === 'ArrowRight' && state.currentStep < state.totalSteps) {
        nextStep()
      } else if (e.key === 'ArrowLeft' && state.currentStep > 1) {
        previousStep()
      }
    }

    window.addEventListener('keydown', handleKeyPress)
    return () => window.removeEventListener('keydown', handleKeyPress)
  }, [state.isActive, state.isMinimized, state.currentStep, state.totalSteps, nextStep, previousStep, minimize])

  // Highlight target UI elements when step changes
  useEffect(() => {
    // Clear previous highlights
    document.querySelectorAll('.tour-highlight').forEach(el => el.classList.remove('tour-highlight'))

    const step = tourSteps[state.currentStep - 1]
    if (step?.targetSelector) {
      const el = document.querySelector(step.targetSelector)
      if (el) {
        el.classList.add('tour-highlight')
        el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      }
    }

    return () => {
      document.querySelectorAll('.tour-highlight').forEach(el => el.classList.remove('tour-highlight'))
    }
  }, [state.currentStep])

  // BUG-122: Don't render tour on unauthenticated pages (placed after all hooks)
  if (isAuthPage) {
    return null
  }

  // Minimized pill UI - Always on top with very high z-index
  if (state.isActive && state.isMinimized) {
    return (
      <button
        onClick={maximize}
        className="fixed bottom-6 right-6 z-[90] bg-gradient-to-r from-teal-500 to-cyan-500 text-white px-6 py-3 rounded-full shadow-2xl hover:shadow-xl transition-all hover:scale-105 flex items-center gap-2 animate-pulse"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span className="font-semibold">
          Continue Tour ({state.currentStep}/{state.totalSteps})
        </span>
      </button>
    )
  }

  if (!state.isActive) {
    return null
  }

  return (
    <Modal
      isOpen={state.isActive && !state.isMinimized}
      onClose={minimize}
      size="xl"
      showCloseButton={true}
    >
      <div className="p-6">
        {/* Progress Indicator */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Step {state.currentStep} of {state.totalSteps}
            </span>
            <button
              onClick={skipTour}
              className="text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
            >
              Skip Tour
            </button>
          </div>
          <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
            <div
              className="bg-gradient-to-r from-teal-500 to-cyan-500 h-2 rounded-full transition-all duration-300"
              style={{ width: `${(state.currentStep / state.totalSteps) * 100}%` }}
            />
          </div>
        </div>

        {/* Step Content */}
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-4">
            {currentStepData.title}
          </h2>
          <p className="text-gray-700 dark:text-gray-300 mb-6 leading-relaxed">
            {currentStepData.content}
          </p>

          {currentStepData.highlightFeatures && (
            <div className="bg-gradient-to-br from-teal-50 to-cyan-50 dark:from-teal-900/20 dark:to-cyan-900/20 rounded-lg p-4 border border-teal-200 dark:border-teal-800">
              <h3 className="text-sm font-semibold text-teal-900 dark:text-teal-100 mb-3">
                Key Features:
              </h3>
              <ul className="space-y-2">
                {currentStepData.highlightFeatures.map((feature, idx) => (
                  <li key={idx} className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-300">
                    <svg className="w-5 h-5 text-teal-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {currentStepData.actionButton && (
            <button
              onClick={() => {
                currentStepData.actionButton!.action()
                minimize()
              }}
              className="mt-4 w-full bg-gradient-to-r from-teal-500 to-cyan-500 text-white px-4 py-2 rounded-lg hover:from-teal-600 hover:to-cyan-600 transition-all font-medium"
            >
              {currentStepData.actionButton.label}
            </button>
          )}
        </div>

        {/* Navigation Buttons */}
        <div className="flex items-center justify-between">
          <button
            onClick={previousStep}
            disabled={state.currentStep === 1}
            className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            ← Previous
          </button>

          <div className="flex gap-2">
            <button
              onClick={minimize}
              className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
              title="Minimize (ESC)"
            >
              Minimize
            </button>

            {state.currentStep === state.totalSteps ? (
              <button
                onClick={completeTour}
                className="px-6 py-2 bg-gradient-to-r from-green-500 to-emerald-500 text-white rounded-lg hover:from-green-600 hover:to-emerald-600 transition-all font-medium"
              >
                Finish Tour
              </button>
            ) : (
              <button
                onClick={nextStep}
                className="px-6 py-2 bg-gradient-to-r from-teal-500 to-cyan-500 text-white rounded-lg hover:from-teal-600 hover:to-cyan-600 transition-all font-medium"
              >
                Next →
              </button>
            )}
          </div>
        </div>

        {/* Completion Checkbox (only on last step) */}
        {state.currentStep === state.totalSteps && (
          <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
            <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 cursor-pointer">
              <input
                type="checkbox"
                defaultChecked={true}
                onChange={(e) => {
                  // If checked, mark as completed when finishing
                  // If unchecked, tour will show again next login
                }}
                className="rounded text-teal-500 focus:ring-teal-500"
              />
              <span>Don't show this tour again</span>
            </label>
          </div>
        )}
      </div>
    </Modal>
  )
}
