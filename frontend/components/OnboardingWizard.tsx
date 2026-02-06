'use client'

/**
 * Onboarding Wizard Component
 * Phase 3: Frontend Onboarding Wizard
 *
 * Interactive tour that guides users through Tsushin platform features.
 * Auto-starts for new users, can be minimized, and easily dismissible.
 */

import React, { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useOnboarding } from '@/contexts/OnboardingContext'
import Modal from '@/components/ui/Modal'

interface TourStep {
  title: string
  content: string
  highlightFeatures?: string[]
  actionButton?: {
    label: string
    action: () => void
  }
}

export default function OnboardingWizard() {
  const { state, nextStep, previousStep, minimize, maximize, completeTour, skipTour } = useOnboarding()
  const router = useRouter()

  const tourSteps: TourStep[] = [
    {
      title: 'Welcome to Tsushin!',
      content: 'Tsushin is a powerful multi-agent platform that helps you build, deploy, and manage AI agents across multiple communication channels.',
      highlightFeatures: [
        'Multi-agent orchestration',
        'WhatsApp & Telegram integration',
        'Skill-based agent capabilities',
        'Flow automation & scheduling'
      ],
      actionButton: {
        label: 'Configure Google OAuth',
        action: () => router.push('/settings/integrations')
      }
    },
    {
      title: 'Watcher - Real-Time Monitoring',
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
      title: 'Hub - Integrations & API Keys',
      content: 'The Hub centralizes all your external service integrations. Configure API keys for AI providers, connect OAuth services like Gmail and Calendar, and manage integration settings.',
      highlightFeatures: [
        'AI Provider API keys (Gemini, OpenAI, Anthropic)',
        'Google OAuth (Gmail, Calendar)',
        'Asana integration',
        'System AI configuration'
      ],
      actionButton: {
        label: 'Open Hub',
        action: () => router.push('/hub')
      }
    },
    {
      title: 'Flows - Automation & Scheduling',
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
      content: 'The Playground is your safe space to test agents, experiment with prompts, and validate configurations without consuming production message credits or affecting real users.',
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
      title: 'Communication Channels',
      content: 'Tsushin supports multiple communication channels for different use cases:',
      highlightFeatures: [
        'Playground - Internal testing and development',
        'WhatsApp - Production messaging via MCP integration',
        'Telegram - Alternative production channel',
        'Each channel can be independently enabled per agent'
      ]
    },
    {
      title: 'Contact Management',
      content: 'Contacts allow you to map real users (phone numbers, IDs) to agents, enabling personalized context and agent-specific handling. Configure which agents respond to which contacts.',
      highlightFeatures: [
        'Map phone numbers to agents',
        'Personalized agent responses',
        'Contact-specific context',
        'Role-based access (user, agent, system)'
      ],
      actionButton: {
        label: 'View Contacts',
        action: () => router.push('/contacts')
      }
    },
    {
      title: "You're All Set!",
      content: 'You now have a comprehensive understanding of the Tsushin platform. Start by creating your first agent in the Studio, or test the default agents in the Playground.',
      highlightFeatures: [
        'Default agents are already configured',
        'Google OAuth setup is optional',
        'All features are ready to use',
        'Access this tour anytime via the ? button'
      ],
      actionButton: {
        label: 'Go to Playground',
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

  // Minimized pill UI - Always on top with very high z-index
  if (state.isActive && state.isMinimized) {
    return (
      <button
        onClick={maximize}
        className="fixed bottom-6 right-6 z-[9999] bg-gradient-to-r from-teal-500 to-cyan-500 text-white px-6 py-3 rounded-full shadow-2xl hover:shadow-xl transition-all hover:scale-105 flex items-center gap-2 animate-pulse"
        style={{ zIndex: 9999 }}
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
