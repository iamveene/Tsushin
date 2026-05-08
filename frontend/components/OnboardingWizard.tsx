'use client'

/**
 * Onboarding Wizard Component
 * Phase 3: Frontend Onboarding Wizard
 *
 * Interactive tour that guides users through Tsushin platform features.
 * Auto-starts for new users, can be minimized, and easily dismissible.
 *
 * BUG-319: Removed step 9 (Setup Checklist) — it duplicated GettingStartedChecklist.
 *           Replaced with a "You're all set" message pointing to the checklist.
 * BUG-321: Channels step action button launches WhatsApp wizard directly (not just /hub nav).
 * BUG-323: Channels step navigates to the Hub Channels tab, not /hub.
 * BUG-325: "Open User Guide" action button disabled when User Guide is already open.
 * BUG-334: Escape and Close button call dismissTour() which persists to localStorage immediately.
 * v0.7.0 getting-started path: Tour now covers providers,
 * agents, channels, flows, voice, Sentinel, triggers, and final next steps.
 */

import React, { useEffect, useCallback, useMemo, useState } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { useOnboarding } from '@/contexts/OnboardingContext'
import Modal from '@/components/ui/Modal'
import { api } from '@/lib/client'

interface TourStep {
  sectionLabel: string
  title: string
  content: string
  highlightFeatures?: string[]
  targetSelector?: string | null
  actionButton?: {
    label: string
    action: () => void
    disabled?: boolean
    disabledReason?: string
  }
  customBody?: React.ReactNode
}

export default function OnboardingWizard() {
  const { state, nextStep, previousStep, minimize, maximize, completeTour, dismissTour, skipTour } = useOnboarding()
  const router = useRouter()
  const pathname = usePathname()
  const isAuthPage = pathname?.startsWith('/auth/')

  // BUG-325: "Open User Guide" should be disabled when guide is already open
  const isUserGuideOpen = state.isUserGuideOpen

  const openUserGuide = useCallback(() => {
    window.dispatchEvent(new CustomEvent('tsushin:open-user-guide'))
    minimize()
  }, [minimize])

  // Keep the tour's provider / skill bullets in sync with the internal wizards
  // by fetching the same catalogs the wizards use. Avoids drift between the
  // onboarding tour copy and what the user actually sees inside the wizards.
  const [ttsProviderSummaries, setTtsProviderSummaries] = useState<
    Array<{ id: string; name: string; is_free: boolean; voice_count: number; status: string }>
  >([])
  useEffect(() => {
    // BUG-683: skip the authenticated /api/tts-providers fetch on public
    // surfaces (/setup, /auth/*). The tour isn't visible there anyway (see
    // early-return below), and firing the request emits a 401 in the network
    // tab before the user even has a session.
    if (isAuthPage || pathname?.startsWith('/setup')) {
      return
    }
    let cancelled = false
    api.getTTSProviders()
      .then(providers => {
        if (cancelled) return
        setTtsProviderSummaries(
          providers
            .filter(p => p.status !== 'coming_soon')
            .map(p => ({
              id: p.id,
              name: p.name,
              is_free: p.is_free,
              voice_count: p.voice_count,
              status: p.status,
            }))
        )
      })
      .catch(() => { /* leave empty; bullets fall back to static hints below */ })
    return () => { cancelled = true }
  }, [isAuthPage, pathname])

  // Derived bullet list for the Voice Capabilities tour step. Built from the
  // live /api/tts-providers catalog so a new backend provider auto-appears in
  // the tour without manual edits. Falls back to a single generic line if the
  // fetch failed.
  const voiceProviderBullets: string[] = useMemo(() => (
    ttsProviderSummaries.length > 0
      ? ttsProviderSummaries.map(p => {
          const label = p.name
          const voiceCount = p.voice_count > 0 ? ` — ${p.voice_count} voice${p.voice_count === 1 ? '' : 's'}` : ''
          const cost = p.is_free ? ' (free)' : p.status === 'preview' ? ' (preview)' : ''
          return `${label}${voiceCount}${cost}`
        })
      : ['Multiple TTS providers: Kokoro (free/local), OpenAI, ElevenLabs, and Google Gemini TTS (preview)']
  ), [ttsProviderSummaries])

  const tourSteps: TourStep[] = useMemo(() => [
    {
      // Step 1
      sectionLabel: 'Overview',
      title: 'Welcome to Tsushin!',
      targetSelector: null,
      content: 'Tsushin helps you build AI agents, connect them to channels, and monitor what they do. Quick walkthrough of the essentials. For detailed documentation, open the User Guide anytime via the ? button in the header.',
      highlightFeatures: [
        'Multiple agents working together',
        'WhatsApp & Telegram integration',
        'Skill-based agent capabilities',
        'Flow automation & scheduling'
      ],
      actionButton: {
        label: isUserGuideOpen ? 'User Guide is already open' : 'Open User Guide',
        action: openUserGuide,
        disabled: isUserGuideOpen,
      }
    },
    {
      // Step 2 — v0.7.0 getting-started path: AI providers
      sectionLabel: 'Providers',
      title: 'Set Up AI Providers',
      targetSelector: null,
      content: 'Start in Hub with the provider your agents will use for chat, tools, images, voice, or embeddings. Tsushin can keep separate providers for system tasks, agent replies, and specialized skills, so you can begin with one and add more later.',
      highlightFeatures: [
        'Language models: OpenAI, Anthropic, Gemini, Vertex AI, Groq, Grok, DeepSeek, OpenRouter, or local Ollama',
        `Voice providers: ${voiceProviderBullets.slice(0, 3).join('; ')}`,
        'Image and embedding providers are configured in the same Hub area when you need them',
        'Use Test Connection before assigning a provider to agents',
        'Keep the System AI separate if you want lightweight routing and classification'
      ],
      actionButton: {
        label: 'Open Hub → AI Providers',
        action: () => router.push('/hub?tab=ai-providers')
      }
    },
    {
      // Step 3 — v0.7.0 getting-started path: channels vs triggers
      sectionLabel: 'Channels & triggers',
      title: 'Understand Channels and Triggers',
      targetSelector: null,
      content: 'Channels are for conversations. Triggers are for events that wake an agent or flow. Keeping those two paths separate makes setup easier: connect chat apps in Hub → Channels, and configure event sources in Hub → Triggers.',
      highlightFeatures: [
        'Channels: WhatsApp, Telegram, Slack, Discord, and Playground testing',
        'Triggers: Gmail, Jira, GitHub, and signed webhooks',
        'Inbound services may need a public HTTPS URL through Remote Access or an ingress override',
        'Route each connected channel or trigger to the agent that should handle it'
      ],
      actionButton: {
        label: 'Open Hub → Channels',
        action: () => router.push('/hub?tab=channels')
      }
    },
    {
      // Step 4 — v0.7.0 getting-started path: agents and skills
      sectionLabel: 'Agents & skills',
      title: 'Build Agents and Add Skills',
      targetSelector: null,
      content: 'Studio is where you create agents, choose their personality, and give them the skills they need for real work. Start with one capable agent, then add more specialized agents when responsibilities become clear.',
      highlightFeatures: [
        'Agents: choose persona, channel routing, memory, and security defaults',
        'Instruction skills: reusable guidance and response patterns',
        'Script skills: Python, Bash, or Node actions in the toolbox environment',
        'MCP servers: connect existing tool APIs to selected agents'
      ],
      actionButton: {
        label: 'Open Studio → Agents',
        action: () => router.push('/agents')
      }
    },
    {
      // Step 5 — v0.7.0 getting-started path: memory
      sectionLabel: 'Memory & knowledge',
      title: 'Prepare Memory and Knowledge',
      targetSelector: null,
      content: 'Use Knowledge Base and Vector Stores when agents need durable context from documents, prior cases, or shared memory. In v0.7.0, embedding providers and vector indexes are explicit choices, so pick them before loading important data.',
      highlightFeatures: [
        'Upload documents to Knowledge Base for agent-ready context',
        'Choose embedding provider, model, and dimensions before indexing',
        'Use separate vector indexes for different data shapes or sensitivity levels',
        'Assign memory intentionally: per-agent, shared, or channel-aware'
      ],
      actionButton: {
        label: 'Open Vector Stores',
        action: () => router.push('/hub?tab=vector-stores')
      }
    },
    {
      // Step 6 — v0.7.0 getting-started path: flows and continuous agents
      sectionLabel: 'Automation',
      title: 'Automate Work with Flows and Continuous Agents',
      targetSelector: 'a[href="/flows"]',
      content: 'Use Flows for repeatable workflows and Continuous Agents for always-on work that reacts to events over time. Triggers can wake either path, and each run stays visible for review.',
      highlightFeatures: [
        'Flows: multi-step automations with schedules, triggers, and run history',
        'Continuous Agents: long-running agents configured from Studio',
        'Wake Events: inspect what woke an agent or flow',
        'Use dry-runs and poll-now actions before depending on live automation'
      ],
      actionButton: {
        label: 'Explore Flows',
        action: () => router.push('/flows')
      }
    },
    {
      // Step 7 — v0.7.0 getting-started path: monitoring and safety
      sectionLabel: 'Monitoring & safety',
      title: 'Watch Activity and Keep Sentinel On',
      targetSelector: 'nav a[href="/"]',
      content: "Watcher shows what agents, channels, flows, and security checks are doing. Sentinel is Tsushin's built-in safety layer, and starting with it on in block mode is the safest default.",
      highlightFeatures: [
        'Dashboard: message and run activity across channels',
        'Graph: how agents, contacts, projects, and security events relate',
        'Sentinel: prompt, tool, and command checks before agents act',
        'Billing: AI usage and cost by agent or provider'
      ],
      actionButton: {
        label: 'Open Watcher',
        action: () => router.push('/')
      }
    },
    {
      // Step 8 — v0.7.0 getting-started path: test and finish
      sectionLabel: 'Test & finish',
      title: 'Test Safely in Playground',
      targetSelector: 'a[href="/playground"]',
      content: 'Use Playground before connecting agents to real channels or triggers. It lets you test behavior, confirm memory and skills, then expand into a full conversation when you need more room.',
      highlightFeatures: [
        'Test agents without sending messages to real users',
        'Switch agents, projects, and threads',
        'Inspect memory, skills, and tool behavior',
        'Relaunch this tour anytime from the ? button'
      ],
      actionButton: {
        label: 'Finish & Go to Playground',
        action: () => {
          router.push('/playground')
          completeTour()
        }
      }
    }
  ], [
    completeTour,
    isUserGuideOpen,
    minimize,
    openUserGuide,
    router,
    voiceProviderBullets,
  ])

  const currentStepData = tourSteps[state.currentStep - 1]

  // BUG-334: Escape key calls dismissTour() which persists to localStorage immediately
  useEffect(() => {
    if (!state.isActive || state.isMinimized) return

    const handleKeyPress = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        // BUG-334: Permanently dismiss — localStorage is set in dismissTour() before state update
        dismissTour()
      } else if (e.key === 'ArrowRight' && state.currentStep < state.totalSteps) {
        nextStep()
      } else if (e.key === 'ArrowLeft' && state.currentStep > 1) {
        previousStep()
      }
    }

    window.addEventListener('keydown', handleKeyPress)
    return () => window.removeEventListener('keydown', handleKeyPress)
  }, [state.isActive, state.isMinimized, state.currentStep, state.totalSteps, nextStep, previousStep, dismissTour])

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
  }, [state.currentStep, tourSteps])

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

  // BUG-595: Belt-and-suspenders — if the user has already completed or
  // dismissed the tour, never render the wizard Modal again, even if some
  // stray state flip set `isActive=true`. `hasCompletedOnboarding` is pinned
  // to `true` by both `completeTour` and `dismissTour` and mirrors the
  // per-user localStorage flag, so this guard is authoritative.
  if (state.hasCompletedOnboarding) {
    return null
  }

  // BUG-603: Don't show the onboarding overlay on auth or setup routes — the
  // route-level flows (login, signup, /setup) have their own UX and the tour
  // Modal can stack on top of them and trap the page.
  if (isAuthPage || pathname?.startsWith('/setup')) {
    return null
  }

  return (
    <Modal
      isOpen={state.isActive && !state.isMinimized}
      onClose={dismissTour}
      size="xl"
      showCloseButton={true}
    >
      <div className="p-6">
        {/* Progress Indicator */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Step {state.currentStep} of {state.totalSteps} — {currentStepData.sectionLabel}
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

          {currentStepData.customBody}

          {currentStepData.actionButton && (
            <button
              onClick={() => {
                if (!currentStepData.actionButton!.disabled) {
                  currentStepData.actionButton!.action()
                  // Only minimize (not dismiss) when using action buttons mid-tour
                  if (state.currentStep < state.totalSteps) {
                    minimize()
                  }
                }
              }}
              disabled={currentStepData.actionButton.disabled}
              className={`mt-4 w-full px-4 py-2 rounded-lg transition-all font-medium ${
                currentStepData.actionButton.disabled
                  ? 'bg-gray-300 dark:bg-gray-600 text-gray-500 dark:text-gray-400 cursor-not-allowed'
                  : 'bg-gradient-to-r from-teal-500 to-cyan-500 text-white hover:from-teal-600 hover:to-cyan-600'
              }`}
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
              title="Minimize (use × to permanently dismiss)"
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

        {/* Completion hint on last step */}
        {state.currentStep === state.totalSteps && (
          <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
            <p className="text-xs text-gray-500 dark:text-gray-400 text-center">
              The Getting Started checklist on the dashboard will track your remaining setup steps.
            </p>
          </div>
        )}
      </div>
    </Modal>
  )
}
