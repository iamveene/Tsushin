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
 * v0.7.0 getting-started path: Total steps is now 16, covering providers,
 * agents, channels, flows, voice, Sentinel, triggers, and final next steps.
 */

import React, { useEffect, useCallback, useMemo, useState } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { useOnboarding } from '@/contexts/OnboardingContext'
import { useWhatsAppWizard } from '@/contexts/WhatsAppWizardContext'
import { useAudioWizard } from '@/contexts/AudioWizardContext'
import Modal from '@/components/ui/Modal'
import { api } from '@/lib/client'

function getErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback
}

function SentinelTourPanel({ onAdvanced }: { onAdvanced: () => void }) {
  const [isBlock, setIsBlock] = useState<boolean | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false
    api.getSentinelConfig().then((cfg) => {
      if (cancelled) return
      const enabled = cfg.is_enabled !== false
      const mode = cfg.detection_mode
      setIsBlock(enabled && mode === 'block')
      setLoaded(true)
    }).catch(() => { if (!cancelled) setLoaded(true) })
    return () => { cancelled = true }
  }, [])

  const toggle = async (next: boolean) => {
    setSaving(true)
    setError(null)
    try {
      if (next) {
        await api.updateSentinelConfig({
          is_enabled: true,
          detection_mode: 'block',
          block_on_detection: true,
          enable_prompt_analysis: true,
          enable_tool_analysis: true,
          enable_shell_analysis: true,
        })
      } else {
        await api.updateSentinelConfig({
          detection_mode: 'detect_only',
          block_on_detection: false,
        })
      }
      setIsBlock(next)
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to save Sentinel setting'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mt-4 p-4 rounded-lg border border-emerald-500/30 bg-emerald-500/5 space-y-3">
      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="text-sm font-medium text-white">Sentinel detection mode</div>
          <div className="text-xs text-gray-400 mt-0.5">
            {!loaded ? 'Loading…' : isBlock
              ? 'Block (recommended) — Sentinel blocks detections in real time.'
              : 'Detect only — Sentinel logs detections but agents still run.'}
          </div>
        </div>
        <button
          type="button"
          disabled={!loaded || saving}
          onClick={() => toggle(!isBlock)}
          className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
            isBlock ? 'bg-emerald-500' : 'bg-gray-600'
          } disabled:opacity-50`}
        >
          <span
            className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition ${
              isBlock ? 'translate-x-5' : 'translate-x-0'
            }`}
          />
        </button>
      </div>
      <p className="text-[11px] text-gray-400">
        This is a tenant-wide setting. Per-agent overrides live in{' '}
        <a href="/settings/sentinel" onClick={onAdvanced} className="text-emerald-400 underline">
          Sentinel Settings
        </a>
        .
      </p>
      {error && <div className="text-xs text-red-400">{error}</div>}
    </div>
  )
}

interface TourStep {
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
  const { openWizard: openWhatsAppWizard } = useWhatsAppWizard()
  const { openWizard: openAudioWizard } = useAudioWizard()
  const router = useRouter()
  const pathname = usePathname()
  const isAuthPage = pathname?.startsWith('/auth/')

  // BUG-325: "Open User Guide" should be disabled when guide is already open
  const isUserGuideOpen = state.isUserGuideOpen

  const openUserGuide = useCallback(() => {
    window.dispatchEvent(new CustomEvent('tsushin:open-user-guide'))
    minimize()
  }, [minimize])

  // v0.7.0: Voice Capabilities step launches the AudioAgentsWizard and advances tour when closed
  const openVoiceWizard = useCallback(() => {
    openAudioWizard()
    minimize()
    const handleWizardClose = () => {
      window.removeEventListener('tsushin:audio-wizard-closed', handleWizardClose)
      setTimeout(() => {
        window.dispatchEvent(new CustomEvent('tsushin:advance-tour-step'))
      }, 300)
    }
    window.addEventListener('tsushin:audio-wizard-closed', handleWizardClose)
  }, [openAudioWizard, minimize])

  // BUG-321: Step 5 launches WhatsApp wizard directly AND advances tour when wizard closes
  const openChannelsWizard = useCallback(() => {
    openWhatsAppWizard()
    minimize()
    // Listen for wizard close to advance tour to next step (step 6)
    const handleWizardClose = () => {
      // Advance to step 6 (Flows) when wizard is dismissed
      window.removeEventListener('tsushin:whatsapp-wizard-closed', handleWizardClose)
      // Use a small delay to allow wizard close animation to complete
      setTimeout(() => {
        // Only advance if tour is still minimized (user didn't manually reopen it)
        // We signal to advance the step
        window.dispatchEvent(new CustomEvent('tsushin:advance-tour-step'))
      }, 300)
    }
    window.addEventListener('tsushin:whatsapp-wizard-closed', handleWizardClose)
  }, [openWhatsAppWizard, minimize])

  // Listen for advance-tour-step event (triggered after WhatsApp wizard closes)
  useEffect(() => {
    const handleAdvance = () => {
      // Only advance if we're on step 5 or the wizard just closed
      nextStep()
    }
    window.addEventListener('tsushin:advance-tour-step', handleAdvance)
    return () => window.removeEventListener('tsushin:advance-tour-step', handleAdvance)
  }, [nextStep])

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
        label: isUserGuideOpen ? 'User Guide is already open' : 'Open User Guide',
        action: openUserGuide,
        disabled: isUserGuideOpen,
      }
    },
    {
      // Step 2 — v0.7.0 getting-started path: AI providers
      title: 'Set Up AI Providers',
      targetSelector: null,
      content: 'Start in Hub with the provider your agents will use for chat, tools, images, voice, or embeddings. Tsushin can keep separate providers for system tasks, agent replies, and specialized skills, so you can begin with one and add more later.',
      highlightFeatures: [
        'Language models: OpenAI, Anthropic, Gemini, Vertex AI, Groq, Grok, DeepSeek, OpenRouter, or local Ollama',
        'Voice and image providers are configured in the same Hub area when you need them',
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
      // Step 4 — v0.7.0 getting-started path: skills
      title: 'Add Skills When Agents Need Tools',
      targetSelector: null,
      content: 'Skills give agents specific capabilities beyond normal chat. Start with instruction skills for behavior, script skills for controlled actions, or MCP servers when you already have an external tool surface to expose.',
      highlightFeatures: [
        'Instruction skills: reusable guidance and response patterns',
        'Script skills: Python, Bash, or Node actions in the toolbox environment',
        'MCP servers: connect existing tool APIs to selected agents',
        'Sentinel scans skills before they become available'
      ],
      actionButton: {
        label: 'Open Custom Skills',
        action: () => router.push('/agents/custom-skills')
      }
    },
    {
      // Step 5 — v0.7.0 getting-started path: memory
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
      // Step 6
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
      // Step 7
      title: 'Studio - Agent Management',
      targetSelector: 'a[href="/agents"]',
      content: 'The Studio is where you create, configure, and manage your AI agents. Define agent personalities, assign skills, and control how agents interact with users.',
      highlightFeatures: [
        'Create custom agents',
        'Configure agent personalities (Personas)',
        'Assign skills and tools, including provider-backed skills such as Password Vault',
        'Set trigger conditions'
      ],
      actionButton: {
        label: 'Go to Studio',
        action: () => router.push('/agents')
      }
    },
    {
      // Step 8
      title: 'Hub - AI Providers & System AI',
      targetSelector: 'a[href="/hub"]',
      content: 'The Hub centralizes all your external integrations. Your primary AI provider was automatically set as the System AI during setup — this powers intent classification, skill routing, and other system operations. You can add more providers or change the System AI here at any time.',
      highlightFeatures: [
        'System AI auto-configured from your setup provider',
        'Add multiple AI providers for failover',
        'Tool APIs for Jira, GitHub, and Password Vault providers such as 1Password',
        'Google OAuth for Gmail & Calendar (optional)',
        'Encrypted API key storage'
      ],
      actionButton: {
        label: 'Open Hub',
        action: () => router.push('/hub')
      }
    },
    {
      // Step 9 — BUG-321, BUG-323: Open WhatsApp wizard directly; navigate to the Hub Channels tab.
      title: 'Communication Channels (Required)',
      targetSelector: 'a[href="/hub"]',
      content: 'To receive and respond to conversations, connect at least one communication channel. Click "Set Up Channels" below to launch the guided WhatsApp setup wizard, or navigate to Hub → Channels. Custom HTTP events are configured later as Triggers, not conversational channels.',
      highlightFeatures: [
        'WhatsApp: scan QR code to connect your phone',
        'Telegram: add your bot token',
        'Slack and Discord: connect workspace and community conversations',
        'Each channel can be independently routed to agents'
      ],
      actionButton: {
        label: 'Set Up Channels (guided wizard)',
        action: openChannelsWizard
      }
    },
    {
      // Step 10
      title: 'Flows - Automation & Scheduling',
      targetSelector: 'a[href="/flows"]',
      content: 'Flows enable you to create automated workflows, scheduled tasks, and multi-step agent orchestrations. Build complex automation without code — mix LLM-powered (agentic) steps with deterministic (programmatic) steps and conditional gates (hybrid).',
      highlightFeatures: [
        'Visual flow builder with agentic, programmatic, and hybrid step families, including conversation, skill, notification, tool, password vault, browser automation, transform, storage, gate, source, and subflow nodes',
        'Password Vault, browser automation, transform, storage/dedupe, gate, and notification nodes can be edited from scratch for UI-first financial workflows',
        'Five built-in templates ready to instantiate: Daily Email Digest, Weekly Calendar Summary, New Contact Welcome, Jira Weekly Triage, GitHub Release Notes',
        'Build flows from agent, tool, notification, transform, storage, gate, source, and subflow steps',
        'Use templates for common work such as email digests, calendar summaries, and release notes',
        'Attach flows to schedules, keywords, manual runs, or triggers',
        'Trigger-bound flows start from a locked source step so incoming event data is available downstream',
        'Review run history for retries, latency, and token usage'
      ],
      actionButton: {
        label: 'Explore Flows',
        action: () => router.push('/flows')
      }
    },
    {
      // Step 11
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
      // Step 12 — v0.7.0: Voice Capabilities (optional)
      title: 'Voice Capabilities (optional)',
      targetSelector: null,
      content: 'Want your agents to reply with audio or transcribe incoming voice messages? Launch the Audio Agents wizard — it walks you through picking a TTS provider, configuring a voice, and either scaffolding a brand-new Voice Assistant agent or attaching audio capabilities to an existing one. This step is entirely optional; skip if you do not need audio.',
      // NOTE: The TTS-provider bullets are derived from the live /api/tts-providers
      // catalog so adding a provider to backend/hub/providers/tts_registry.py
      // auto-propagates here without touching this file. See voiceProviderBullets above.
      highlightFeatures: [
        ...voiceProviderBullets,
        'Create a new Voice Assistant OR attach audio_tts/audio_transcript to an existing agent',
        'Pick "Hybrid" to both transcribe incoming voice AND reply with synthesized audio',
        'NEW in v0.7.0: two ASR (speech-to-text) engines now ship out of the box — self-hosted OpenAI Whisper (official package, runs in your Docker stack with no API key) and self-hosted Speaches (faster-whisper). Cloud OpenAI Whisper still works as a third option.',
        'Per-agent ASR assignment with cascade-aware delete (removing an ASR provider unbinds the agents using it instead of orphaning them)'
      ],
      actionButton: {
        label: 'Set up voice agent (guided wizard)',
        action: openVoiceWizard
      }
    },
    {
      // Step 13 — Playground Mini floating bubble
      title: 'New: Playground Mini',
      targetSelector: '[data-testid="playground-mini"]',
      content: 'Test any agent from any page without leaving. Pick an agent, project, or thread, fire a quick message — then hit Expand if you want to continue in the full Playground. The conversation carries over intact.',
      highlightFeatures: [
        'Available on every authenticated page (hidden only inside the full Playground)',
        'Quick agent + project + thread switcher',
        'Expand-to-Playground handover preserves your conversation',
        'Toggle anywhere with Ctrl/Cmd + Shift + L'
      ],
      actionButton: {
        label: 'Open Playground Mini',
        action: () => {
          // If we're on the full Playground, bounce to home so the Mini renders.
          if (typeof window !== 'undefined' && window.location.pathname.startsWith('/playground')) {
            router.push('/')
          }
          window.dispatchEvent(new CustomEvent('tsushin:playground-mini:open'))
        }
      }
    },
    {
      // Step 14 — v0.7.0-preview: Sentinel / MemGuard block-mode nudge before the finale.
      title: 'Sentinel — Security Layer',
      targetSelector: null,
      content: "Sentinel is Tsushin's built-in security layer. It reviews prompts, tool calls, and shell commands before agents act on them, and can block prompt injection, agent takeover attempts, and memory poisoning. Start with it ON in block mode; you can relax it later for development.",
      highlightFeatures: [
        'Prompt injection + agent takeover detection on every message',
        'Tool / shell / slash-command analysis before execution',
        'Detect-only or warn-only modes for dev work',
        'Full audit log of every decision',
      ],
      customBody: <SentinelTourPanel onAdvanced={minimize} />,
    },
    {
      // Step 15 — v0.7.0: Trigger/continuous-agent readiness before the finale.
      title: 'New in v0.7.0 - Triggers & Continuous Agents',
      targetSelector: '[data-testid="hub-triggers-section"]',
      content: 'Triggers are separate from conversational channels. Use Hub → Triggers when Gmail, Jira, GitHub, or an external webhook should wake an agent or flow. Continuous Agents and Wake Events live under Watcher for monitoring always-on work.',
      highlightFeatures: [
        'Email: watch Gmail using saved OAuth accounts and search criteria',
        'Jira: poll issues with JQL and route matching work',
        'GitHub: receive repository events through a configured webhook',
        'Webhook: receive signed events from external systems',
        'Use dry-runs and poll-now actions before depending on live automation',
        'Generated flows can be reviewed and adjusted after save'
      ],
      actionButton: {
        label: 'Open Hub Triggers',
        action: () => router.push('/hub/triggers')
      }
    },
    {
      // Step 16 — BUG-319: Replaced old "Setup Checklist" (step 9) with a brief completion message.
      // Points users to the Getting Started Checklist on the dashboard instead of duplicating it.
      title: "You're All Set!",
      targetSelector: null,
      content: "You've completed the Tsushin onboarding tour. Check the Getting Started checklist on the dashboard for your setup progress — it tracks channel setup, contacts, playground testing, and more. You can relaunch this tour anytime via the ? button in the header.",
      highlightFeatures: [
        'Default agents are already configured',
        'Getting Started checklist tracks your progress on the dashboard',
        'Connect a channel via the checklist or Hub → Channels tab',
        'Access this tour anytime via the ? button'
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
    openChannelsWizard,
    openUserGuide,
    openVoiceWizard,
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
