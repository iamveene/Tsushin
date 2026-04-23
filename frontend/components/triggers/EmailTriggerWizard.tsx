'use client'

import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import GoogleAppCredentialsStep from '@/components/integrations/GoogleAppCredentialsStep'
import Wizard, { type WizardStep } from '@/components/ui/Wizard'
import { api, authenticatedFetch, type Agent, type EmailTrigger } from '@/lib/client'

interface Props {
  isOpen: boolean
  onClose: () => void
  onComplete?: (trigger: EmailTrigger) => void
  triggerId?: number | null
}

interface GmailIntegration {
  id: number
  name: string
  email_address: string
  health_status: string
  is_active: boolean
  can_send: boolean
}

const getErrorMessage = (error: unknown, fallback: string) =>
  error instanceof Error ? error.message : fallback

const STEPS: WizardStep[] = [
  {
    id: 'welcome',
    label: 'Overview',
    description: 'Understand what the email trigger will watch and how it wakes agents.',
  },
  {
    id: 'credentials',
    label: 'Credentials',
    description: 'Confirm the tenant Google OAuth app before Gmail authorization.',
  },
  {
    id: 'account',
    label: 'Account',
    description: 'Pick an existing Gmail integration or connect a new account.',
  },
  {
    id: 'settings',
    label: 'Settings',
    description: 'Choose the default agent, inbox query, and polling cadence.',
  },
  {
    id: 'review',
    label: 'Review',
    description: 'Save the trigger once the account and routing look right.',
  },
]

const POLL_INTERVAL_MS = 3000
const POLL_MAX_TICKS = 120

export default function EmailTriggerWizard({
  isOpen,
  onClose,
  onComplete,
  triggerId = null,
}: Props) {
  const isEditing = triggerId !== null
  const [step, setStep] = useState<1 | 2 | 3 | 4 | 5>(1)
  const [integrations, setIntegrations] = useState<GmailIntegration[]>([])
  const [integrationsLoading, setIntegrationsLoading] = useState(false)
  const [agents, setAgents] = useState<Agent[]>([])
  const [agentsLoaded, setAgentsLoaded] = useState(false)
  const [agentsLoading, setAgentsLoading] = useState(false)
  const [loadingTrigger, setLoadingTrigger] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [popupOpen, setPopupOpen] = useState(false)
  const [popupError, setPopupError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [selectedIntegrationId, setSelectedIntegrationId] = useState<number | null>(null)
  const [integrationName, setIntegrationName] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [pollIntervalSeconds, setPollIntervalSeconds] = useState('60')
  const [defaultAgentId, setDefaultAgentId] = useState<number | null>(null)
  const [isActive, setIsActive] = useState(true)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'success'>('idle')
  const [savedTrigger, setSavedTrigger] = useState<EmailTrigger | null>(null)

  const knownIntegrationIds = useRef<Set<number>>(new Set())
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollTicks = useRef(0)

  const clearPollTimer = useCallback(() => {
    if (pollTimer.current) {
      clearInterval(pollTimer.current)
      pollTimer.current = null
    }
  }, [])

  const fetchIntegrations = useCallback(async (seedKnownIds: boolean = false) => {
    setIntegrationsLoading(true)
    try {
      const response = await authenticatedFetch('/api/hub/google/gmail/integrations')
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const data = await response.json()
      const list: GmailIntegration[] = data.integrations || []
      setIntegrations(list)
      if (seedKnownIds || knownIntegrationIds.current.size === 0) {
        knownIntegrationIds.current = new Set(list.map((integration) => integration.id))
      }
      return list
    } catch (error: unknown) {
      setPopupError((current) => current || getErrorMessage(error, 'Failed to load Gmail accounts'))
      return []
    } finally {
      setIntegrationsLoading(false)
    }
  }, [])

  const fetchAgents = useCallback(async () => {
    if (agentsLoaded || agentsLoading) return
    setAgentsLoading(true)
    try {
      const list = await api.getAgents(true)
      setAgents(list)
    } finally {
      setAgentsLoaded(true)
      setAgentsLoading(false)
    }
  }, [agentsLoaded, agentsLoading])

  useEffect(() => {
    if (!isOpen) return

    setStep(isEditing ? 4 : 1)
    setLoadError(null)
    setPopupError(null)
    setSaveError(null)
    setSaveState('idle')
    setSavedTrigger(null)
    setPopupOpen(false)
    setSelectedIntegrationId(null)
    setIntegrationName('')
    setSearchQuery('')
    setPollIntervalSeconds('60')
    setDefaultAgentId(null)
    setIsActive(true)
    setAgents([])
    setAgentsLoaded(false)
    pollTicks.current = 0
    clearPollTimer()

    let cancelled = false

    fetchIntegrations(true).then((list) => {
      if (cancelled || isEditing || list.length !== 1) return
      setSelectedIntegrationId(list[0].id)
    })

    if (!isEditing || triggerId === null) {
      return () => {
        cancelled = true
        clearPollTimer()
      }
    }

    setLoadingTrigger(true)
    api.getEmailTrigger(triggerId)
      .then((trigger) => {
        if (cancelled) return
        setSelectedIntegrationId(trigger.gmail_integration_id ?? null)
        setIntegrationName(trigger.integration_name)
        setSearchQuery(trigger.search_query || '')
        setPollIntervalSeconds(String(trigger.poll_interval_seconds || 60))
        setDefaultAgentId(trigger.default_agent_id ?? null)
        setIsActive(trigger.is_active)
        setSavedTrigger(trigger)
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setLoadError(getErrorMessage(error, 'Failed to load email trigger'))
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingTrigger(false)
        }
      })

    return () => {
      cancelled = true
      clearPollTimer()
    }
  }, [clearPollTimer, fetchIntegrations, isEditing, isOpen, triggerId])

  useEffect(() => {
    if (!isOpen || step < 4) return
    fetchAgents()
  }, [fetchAgents, isOpen, step])

  useEffect(() => {
    if (!isOpen) return

    const handler = async (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return
      const data = event.data
      if (!data || typeof data !== 'object') return
      if (data.source !== 'tsushin-google-oauth' || data.integration !== 'gmail') return

      clearPollTimer()
      setPopupOpen(false)
      setPopupError(null)

      const list = await fetchIntegrations()
      const targetId = typeof data.integration_id === 'number' ? data.integration_id : null
      const target = (targetId && list.find((integration) => integration.id === targetId)) ||
        list.find((integration) => !knownIntegrationIds.current.has(integration.id))

      if (target) {
        setSelectedIntegrationId(target.id)
        setIntegrationName((current) => current.trim() || `Inbox: ${target.email_address}`)
      }
      knownIntegrationIds.current = new Set(list.map((integration) => integration.id))
    }

    window.addEventListener('message', handler)
    return () => window.removeEventListener('message', handler)
  }, [clearPollTimer, fetchIntegrations, isOpen])

  useEffect(() => {
    if (!isOpen || isEditing || !selectedIntegrationId) return
    const selected = integrations.find((integration) => integration.id === selectedIntegrationId)
    if (!selected) return
    setIntegrationName((current) => current.trim() || `Inbox: ${selected.email_address}`)
  }, [integrations, isEditing, isOpen, selectedIntegrationId])

  useEffect(() => {
    return () => clearPollTimer()
  }, [clearPollTimer])

  const selectedIntegration = useMemo(
    () => integrations.find((integration) => integration.id === selectedIntegrationId) || null,
    [integrations, selectedIntegrationId],
  )

  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.id === defaultAgentId) || null,
    [agents, defaultAgentId],
  )

  const trimmedName = integrationName.trim()
  const pollValue = Number(pollIntervalSeconds)
  const pollIntervalValid =
    Number.isInteger(pollValue) && pollValue >= 30 && pollValue <= 3600
  const canReview = Boolean(trimmedName && selectedIntegrationId && pollIntervalValid)

  const handleClose = () => {
    if (saveState === 'saving') return
    clearPollTimer()
    onClose()
  }

  const startNewAccountAuthorization = async () => {
    setPopupError(null)
    try {
      const response = await authenticatedFetch('/api/hub/google/gmail/oauth/authorize?include_send_scope=true', {
        method: 'POST',
      })
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw new Error(body.detail || `HTTP ${response.status}`)
      }

      const { authorization_url } = await response.json()
      const popup = window.open(
        authorization_url,
        'gmail-oauth',
        'width=520,height=640,left=200,top=100',
      )

      if (!popup) {
        window.location.href = authorization_url
        return
      }

      setPopupOpen(true)
      pollTicks.current = 0
      clearPollTimer()
      pollTimer.current = setInterval(async () => {
        pollTicks.current += 1
        if (pollTicks.current > POLL_MAX_TICKS) {
          clearPollTimer()
          setPopupOpen(false)
          setPopupError("Didn't detect a new Gmail account after 6 minutes. Did you finish the Google consent?")
          return
        }

        const list = await fetchIntegrations()
        const newIntegration = list.find((integration) => !knownIntegrationIds.current.has(integration.id))
        if (newIntegration) {
          clearPollTimer()
          setPopupOpen(false)
          setSelectedIntegrationId(newIntegration.id)
          setIntegrationName((current) => current.trim() || `Inbox: ${newIntegration.email_address}`)
          knownIntegrationIds.current = new Set(list.map((integration) => integration.id))
        }
      }, POLL_INTERVAL_MS)
    } catch (error: unknown) {
      setPopupError(getErrorMessage(error, 'Failed to start Gmail authorization'))
    }
  }

  const handleSave = async () => {
    if (!selectedIntegrationId || !trimmedName || !pollIntervalValid) {
      setSaveError('Choose a Gmail account, name the trigger, and use a 30-3600 second polling interval.')
      return
    }

    setSaveError(null)
    setSaveState('saving')

    try {
      const payload = {
        integration_name: trimmedName,
        gmail_integration_id: selectedIntegrationId,
        default_agent_id: defaultAgentId,
        search_query: searchQuery.trim() || null,
        poll_interval_seconds: pollValue,
        is_active: isActive,
      }

      const result = isEditing && triggerId !== null
        ? await api.updateEmailTrigger(triggerId, payload)
        : await api.createEmailTrigger(payload)

      setSavedTrigger(result)
      setSaveState('success')
    } catch (error: unknown) {
      setSaveState('idle')
      setSaveError(getErrorMessage(error, 'Failed to save email trigger'))
    }
  }

  const renderFooter = (content: ReactNode) => (
    <div className="flex flex-wrap items-center justify-between gap-3">
      {content}
    </div>
  )

  if (loadingTrigger) {
    return (
      <Wizard
        isOpen={isOpen}
        onClose={handleClose}
        title={isEditing ? 'Update Email Trigger' : 'Create Email Trigger'}
        steps={STEPS}
        currentStep={4}
        tone="gmail"
        status="loading"
        statusTitle="Loading email trigger"
        statusDescription="Pulling the saved Gmail account and routing settings so you can edit them."
      />
    )
  }

  if (loadError) {
    return (
      <Wizard
        isOpen={isOpen}
        onClose={handleClose}
        title={isEditing ? 'Update Email Trigger' : 'Create Email Trigger'}
        steps={STEPS}
        currentStep={4}
        tone="gmail"
        footer={renderFooter(
          <div className="ml-auto">
            <button
              type="button"
              onClick={handleClose}
              className="rounded-lg border border-tsushin-border/70 bg-transparent px-4 py-2 text-sm text-tsushin-slate transition-colors hover:border-tsushin-border hover:text-white"
            >
              Close
            </button>
          </div>,
        )}
        stepTitle="Couldn’t load this trigger"
        stepDescription="The saved trigger configuration could not be fetched. Close the wizard and try again."
      >
        <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {loadError}
        </div>
      </Wizard>
    )
  }

  if (step === 1) {
    return (
      <Wizard
        isOpen={isOpen}
        onClose={handleClose}
        title={isEditing ? 'Update Email Trigger' : 'Create Email Trigger'}
        steps={STEPS}
        currentStep={1}
        tone="gmail"
        footer={renderFooter(
          <>
            <button
              type="button"
              onClick={handleClose}
              className="rounded-lg border border-tsushin-border/70 bg-transparent px-4 py-2 text-sm text-tsushin-slate transition-colors hover:border-tsushin-border hover:text-white"
            >
              Discard
            </button>
            <button
              type="button"
              onClick={() => setStep(2)}
              className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-500"
            >
              Get Started
            </button>
          </>
        )}
        stepTitle="Wake agents from matching Gmail activity"
        stepDescription="This trigger watches one Gmail account on a polling interval, applies an optional Gmail search query, and routes matching messages to a default agent."
      >
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4">
              <div className="text-xs uppercase tracking-[0.18em] text-tsushin-slate/80">Account source</div>
              <div className="mt-2 text-sm text-white">Reuses the same Gmail OAuth accounts already connected for the tenant.</div>
            </div>
            <div className="rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4">
              <div className="text-xs uppercase tracking-[0.18em] text-tsushin-slate/80">Routing</div>
              <div className="mt-2 text-sm text-white">Optional default agent for wakeups. You can change it later if the trigger owner shifts.</div>
            </div>
            <div className="rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4">
              <div className="text-xs uppercase tracking-[0.18em] text-tsushin-slate/80">Matching</div>
              <div className="mt-2 text-sm text-white">Use any Gmail search query, or leave it blank to watch the whole inbox.</div>
            </div>
            <div className="rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4">
              <div className="text-xs uppercase tracking-[0.18em] text-tsushin-slate/80">Cadence</div>
              <div className="mt-2 text-sm text-white">Polling intervals from 30 seconds to 1 hour, with an active/paused toggle at save time.</div>
            </div>
          </div>
          <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">
            Email triggers are trigger-only. Gmail accounts stay reusable resources for automation, not communication channels.
          </div>
        </div>
      </Wizard>
    )
  }

  if (step === 2) {
    return (
      <Wizard
        isOpen={isOpen}
        onClose={handleClose}
        title={isEditing ? 'Update Email Trigger' : 'Create Email Trigger'}
        steps={STEPS}
        currentStep={2}
        tone="gmail"
        footer={renderFooter(
          <>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setStep(1)}
                className="rounded-lg border border-tsushin-border/70 bg-transparent px-4 py-2 text-sm text-tsushin-slate transition-colors hover:border-tsushin-border hover:text-white"
              >
                Back
              </button>
              <button
                type="button"
                onClick={handleClose}
                className="rounded-lg border border-tsushin-border/70 bg-transparent px-4 py-2 text-sm text-tsushin-slate transition-colors hover:border-tsushin-border hover:text-white"
              >
                Discard
              </button>
            </div>
          </>
        )}
        stepTitle="Confirm Google OAuth credentials"
        stepDescription="Email triggers reuse the tenant’s Google OAuth app. If credentials are already configured, you can continue immediately."
      >
        <GoogleAppCredentialsStep tone="gmail" onReady={() => setStep(3)} />
      </Wizard>
    )
  }

  if (step === 3) {
    return (
      <Wizard
        isOpen={isOpen}
        onClose={handleClose}
        title={isEditing ? 'Update Email Trigger' : 'Create Email Trigger'}
        steps={STEPS}
        currentStep={3}
        tone="gmail"
        footer={renderFooter(
          <>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setStep(2)}
                className="rounded-lg border border-tsushin-border/70 bg-transparent px-4 py-2 text-sm text-tsushin-slate transition-colors hover:border-tsushin-border hover:text-white"
              >
                Back
              </button>
              <button
                type="button"
                onClick={handleClose}
                className="rounded-lg border border-tsushin-border/70 bg-transparent px-4 py-2 text-sm text-tsushin-slate transition-colors hover:border-tsushin-border hover:text-white"
              >
                Discard
              </button>
            </div>
            <button
              type="button"
              onClick={() => setStep(4)}
              disabled={!selectedIntegrationId}
              className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-opacity hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Continue to Settings
            </button>
          </>
        )}
        stepTitle="Pick the Gmail account this trigger will watch"
        stepDescription="Choose an existing Gmail integration or connect a fresh account without leaving the trigger setup flow."
      >
        <div className="space-y-5">
          {popupError && (
            <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              {popupError}
            </div>
          )}

          {integrationsLoading ? (
            <div className="rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 px-4 py-8 text-center text-sm text-tsushin-slate">
              Loading Gmail accounts…
            </div>
          ) : integrations.length > 0 ? (
            <div className="space-y-3">
              <div className="text-sm font-medium text-white">Existing Gmail accounts</div>
              <div className="space-y-2">
                {integrations.map((integration) => (
                  <label
                    key={integration.id}
                    className="flex cursor-pointer items-center gap-3 rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4 hover:bg-tsushin-slate/10"
                  >
                    <input
                      type="radio"
                      name="email-trigger-gmail-account"
                      checked={selectedIntegrationId === integration.id}
                      onChange={() => setSelectedIntegrationId(integration.id)}
                      className="h-4 w-4 border-white/20 bg-[#0a0a0f] text-red-500 focus:ring-red-500"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium text-white">{integration.email_address}</div>
                      <div className="mt-1 text-xs text-tsushin-slate">
                        {integration.name} · {integration.can_send ? 'Read + send/draft' : 'Read-only'}
                      </div>
                    </div>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                        integration.health_status === 'healthy'
                          ? 'border border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                          : 'border border-yellow-500/30 bg-yellow-500/10 text-yellow-300'
                      }`}
                    >
                      {integration.health_status}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-tsushin-border/70 bg-tsushin-slate/5 px-4 py-8 text-center">
              <div className="text-sm font-medium text-white">No Gmail accounts connected yet</div>
              <p className="mt-2 text-sm text-tsushin-slate">
                Connect the first account below and it will be selected automatically for this trigger.
              </p>
            </div>
          )}

          <div className="rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-white">Connect a new Gmail account</div>
                <p className="mt-1 text-xs text-tsushin-slate">
                  Opens the same Google consent flow used by the existing Gmail setup wizard.
                </p>
              </div>
              <button
                type="button"
                onClick={startNewAccountAuthorization}
                disabled={popupOpen}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-opacity hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {popupOpen ? 'Waiting for Google consent…' : 'Connect New Account'}
              </button>
            </div>
            {popupOpen && (
              <p className="mt-3 text-xs text-tsushin-slate">
                When the Google popup finishes, this wizard will refresh the account list automatically.
              </p>
            )}
          </div>
        </div>
      </Wizard>
    )
  }

  if (step === 4) {
    return (
      <Wizard
        isOpen={isOpen}
        onClose={handleClose}
        title={isEditing ? 'Update Email Trigger' : 'Create Email Trigger'}
        steps={STEPS}
        currentStep={4}
        tone="gmail"
        footer={renderFooter(
          <>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setStep(3)}
                className="rounded-lg border border-tsushin-border/70 bg-transparent px-4 py-2 text-sm text-tsushin-slate transition-colors hover:border-tsushin-border hover:text-white"
              >
                Back
              </button>
              <button
                type="button"
                onClick={handleClose}
                className="rounded-lg border border-tsushin-border/70 bg-transparent px-4 py-2 text-sm text-tsushin-slate transition-colors hover:border-tsushin-border hover:text-white"
              >
                Discard
              </button>
            </div>
            <button
              type="button"
              onClick={() => {
                setSaveError(null)
                setStep(5)
              }}
              disabled={!canReview}
              className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-opacity hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Review Trigger
            </button>
          </>
        )}
        stepTitle="Set the trigger name, routing, and inbox filter"
        stepDescription="You can pause the trigger at save time, leave the Gmail query blank for whole-inbox monitoring, or set a default agent for wakeups."
      >
        <div className="space-y-5">
          {saveError && (
            <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              {saveError}
            </div>
          )}

          <div className="grid gap-5 md:grid-cols-2">
            <div className="space-y-2">
              <label className="block text-sm font-medium text-white">
                Trigger Name <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={integrationName}
                onChange={(event) => setIntegrationName(event.target.value)}
                placeholder="Inbox: ops@example.com"
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-500/30"
              />
              <p className="text-xs text-tsushin-slate">Human label shown in the Communication → Triggers section.</p>
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium text-white">
                Gmail Account <span className="text-red-400">*</span>
              </label>
              <button
                type="button"
                onClick={() => setStep(3)}
                className="flex w-full items-center justify-between rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-left text-sm text-white hover:bg-tsushin-slate/15"
              >
                <span>{selectedIntegration?.email_address || 'Choose a Gmail account'}</span>
                <span className="text-xs text-tsushin-slate">Change</span>
              </button>
              <p className="text-xs text-tsushin-slate">Email triggers reuse existing Gmail integrations rather than creating a channel.</p>
            </div>

            <div className="space-y-2 md:col-span-2">
              <label className="block text-sm font-medium text-white">Gmail Search Query</label>
              <textarea
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                rows={3}
                placeholder="label:inbox is:unread newer_than:2d"
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-500/30"
              />
              <p className="text-xs text-tsushin-slate">Leave blank to watch all new inbox activity. Any valid Gmail search query works here.</p>
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium text-white">
                Poll Interval (seconds) <span className="text-red-400">*</span>
              </label>
              <input
                type="number"
                min={30}
                max={3600}
                step={30}
                value={pollIntervalSeconds}
                onChange={(event) => setPollIntervalSeconds(event.target.value)}
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-500/30"
              />
              <p className={`text-xs ${pollIntervalValid ? 'text-tsushin-slate' : 'text-amber-300'}`}>
                Use a value between 30 and 3600 seconds.
              </p>
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium text-white">Default Agent</label>
              <select
                value={defaultAgentId ?? ''}
                onChange={(event) => setDefaultAgentId(event.target.value ? Number(event.target.value) : null)}
                className="w-full rounded-xl border border-tsushin-border bg-tsushin-slate/10 px-3 py-2 text-sm text-white focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-500/30"
              >
                <option value="">No default agent</option>
                {agents.map((agent) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.contact_name}
                  </option>
                ))}
              </select>
              <p className="text-xs text-tsushin-slate">
                {agentsLoading ? 'Loading active agents…' : 'Optional agent to wake when a message matches this trigger.'}
              </p>
            </div>
          </div>

          <label className="flex items-start gap-3 rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4">
            <input
              type="checkbox"
              checked={isActive}
              onChange={(event) => setIsActive(event.target.checked)}
              className="mt-1 h-4 w-4 rounded border-white/20 bg-[#0a0a0f] text-red-500 focus:ring-red-500"
            />
            <div>
              <div className="text-sm font-medium text-white">{isActive ? 'Enable this trigger immediately' : 'Create it paused'}</div>
              <p className="mt-1 text-xs text-tsushin-slate">
                Paused triggers keep their configuration but stop polling Gmail until you reactivate them.
              </p>
            </div>
          </label>
        </div>
      </Wizard>
    )
  }

  if (saveState === 'success' && savedTrigger) {
    return (
      <Wizard
        isOpen={isOpen}
        onClose={handleClose}
        title={isEditing ? 'Update Email Trigger' : 'Create Email Trigger'}
        steps={STEPS}
        currentStep={5}
        tone="gmail"
        status="success"
        statusTitle={isEditing ? 'Email trigger updated' : 'Email trigger created'}
        statusDescription={`"${savedTrigger.integration_name}" is now ${savedTrigger.is_active ? 'active' : 'paused'} and watching ${savedTrigger.gmail_account_email || 'the selected Gmail account'}.`}
        statusBody={(
          <div className="mx-auto max-w-md rounded-xl border border-tsushin-border/70 bg-tsushin-slate/5 px-4 py-3 text-left">
            <div className="space-y-2 text-sm text-tsushin-slate">
              <div>
                <span className="text-white">Account:</span> {savedTrigger.gmail_account_email || '—'}
              </div>
              <div>
                <span className="text-white">Query:</span> {savedTrigger.search_query || 'Whole inbox'}
              </div>
              <div>
                <span className="text-white">Poll interval:</span> {savedTrigger.poll_interval_seconds}s
              </div>
              <div>
                <span className="text-white">Default agent:</span> {savedTrigger.default_agent_name || 'None'}
              </div>
            </div>
          </div>
        )}
        footer={renderFooter(
          <div className="ml-auto">
            <button
              type="button"
              onClick={() => {
                onComplete?.(savedTrigger)
                handleClose()
              }}
              className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-500"
            >
              Done
            </button>
          </div>,
        )}
      />
    )
  }

  return (
    <Wizard
      isOpen={isOpen}
      onClose={handleClose}
      title={isEditing ? 'Update Email Trigger' : 'Create Email Trigger'}
      steps={STEPS}
      currentStep={5}
      tone="gmail"
      status={saveState === 'saving' ? 'loading' : 'idle'}
      statusTitle="Saving email trigger"
      statusDescription="Persisting the Gmail trigger configuration and refreshing the trigger list."
      footer={saveState === 'saving'
        ? renderFooter(
            <div className="ml-auto rounded-lg border border-tsushin-border/70 bg-tsushin-slate/10 px-4 py-2 text-sm text-tsushin-slate">
              Saving…
            </div>,
          )
        : renderFooter(
            <>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setStep(4)}
                  className="rounded-lg border border-tsushin-border/70 bg-transparent px-4 py-2 text-sm text-tsushin-slate transition-colors hover:border-tsushin-border hover:text-white"
                >
                  Back
                </button>
                <button
                  type="button"
                  onClick={handleClose}
                  className="rounded-lg border border-tsushin-border/70 bg-transparent px-4 py-2 text-sm text-tsushin-slate transition-colors hover:border-tsushin-border hover:text-white"
                >
                  Discard
                </button>
              </div>
              <button
                type="button"
                onClick={handleSave}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-500"
              >
                {isEditing ? 'Save Changes' : 'Create Trigger'}
              </button>
            </>
          )}
      stepTitle="Review the trigger before saving"
      stepDescription="Double-check the account, query, and default agent. You can come back later to edit the trigger without reconnecting Gmail."
    >
      <div className="space-y-5">
        {saveError && (
          <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {saveError}
          </div>
        )}

        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-tsushin-slate/80">Trigger name</div>
            <div className="mt-2 text-sm text-white">{trimmedName || '—'}</div>
          </div>
          <div className="rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-tsushin-slate/80">Gmail account</div>
            <div className="mt-2 text-sm text-white">{selectedIntegration?.email_address || '—'}</div>
          </div>
          <div className="rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-tsushin-slate/80">Search query</div>
            <div className="mt-2 text-sm text-white">{searchQuery.trim() || 'Whole inbox'}</div>
          </div>
          <div className="rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-tsushin-slate/80">Polling</div>
            <div className="mt-2 text-sm text-white">{pollValue}s</div>
          </div>
          <div className="rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-tsushin-slate/80">Default agent</div>
            <div className="mt-2 text-sm text-white">{selectedAgent?.contact_name || 'No default agent'}</div>
          </div>
          <div className="rounded-2xl border border-tsushin-border/70 bg-tsushin-slate/5 p-4">
            <div className="text-xs uppercase tracking-[0.18em] text-tsushin-slate/80">Status on save</div>
            <div className="mt-2 text-sm text-white">{isActive ? 'Active' : 'Paused'}</div>
          </div>
        </div>
      </div>
    </Wizard>
  )
}
