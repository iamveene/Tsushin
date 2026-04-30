'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { authenticatedFetch } from '@/lib/client'

export interface GmailIntegration {
  id: number
  name: string
  email_address: string
  health_status: string
  is_active: boolean
  can_send: boolean
  can_draft?: boolean
}

export interface UseGmailOAuthPollerOptions {
  /** Only run effects (fetch, listen) when the host wizard is visible. */
  enabled: boolean
  /** Optional callback fired when a freshly-authorized integration appears. */
  onNewIntegration?: (integration: GmailIntegration) => void
}

export interface UseGmailOAuthPollerResult {
  integrations: GmailIntegration[]
  integrationsLoading: boolean
  popupOpen: boolean
  popupError: string | null
  startAuthorization: () => Promise<void>
  fetchIntegrations: (seedKnownIds?: boolean) => Promise<GmailIntegration[]>
  resetError: () => void
}

const POLL_INTERVAL_MS = 3000
const POLL_MAX_TICKS = 120

const getErrorMessage = (error: unknown, fallback: string) =>
  error instanceof Error ? error.message : fallback

/**
 * Encapsulates the Gmail OAuth popup-and-poll flow used by the trigger
 * creation wizard so email-source behavior stays shared without duplicating state.
 */
export default function useGmailOAuthPoller({
  enabled,
  onNewIntegration,
}: UseGmailOAuthPollerOptions): UseGmailOAuthPollerResult {
  const [integrations, setIntegrations] = useState<GmailIntegration[]>([])
  const [integrationsLoading, setIntegrationsLoading] = useState(false)
  const [popupOpen, setPopupOpen] = useState(false)
  const [popupError, setPopupError] = useState<string | null>(null)

  const knownIntegrationIds = useRef<Set<number>>(new Set())
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollTicks = useRef(0)
  const onNewIntegrationRef = useRef(onNewIntegration)

  useEffect(() => {
    onNewIntegrationRef.current = onNewIntegration
  }, [onNewIntegration])

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

  // Seed the integration list when the host wizard opens.
  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    fetchIntegrations(true).then((list) => {
      if (cancelled || list.length !== 1) return
      // Auto-pick path is left to the consumer; just expose the single account.
      onNewIntegrationRef.current?.(list[0])
    })
    return () => {
      cancelled = true
      clearPollTimer()
    }
  }, [clearPollTimer, enabled, fetchIntegrations])

  // Listen for the popup's postMessage handshake.
  useEffect(() => {
    if (!enabled) return

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
        onNewIntegrationRef.current?.(target)
      }
      knownIntegrationIds.current = new Set(list.map((integration) => integration.id))
    }

    window.addEventListener('message', handler)
    return () => window.removeEventListener('message', handler)
  }, [clearPollTimer, enabled, fetchIntegrations])

  // Always release the timer on unmount.
  useEffect(() => () => clearPollTimer(), [clearPollTimer])

  const startAuthorization = useCallback(async () => {
    setPopupError(null)
    try {
      const response = await authenticatedFetch(
        '/api/hub/google/gmail/oauth/authorize?include_send_scope=true',
        { method: 'POST' },
      )
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
          onNewIntegrationRef.current?.(newIntegration)
          knownIntegrationIds.current = new Set(list.map((integration) => integration.id))
        }
      }, POLL_INTERVAL_MS)
    } catch (error: unknown) {
      setPopupError(getErrorMessage(error, 'Failed to start Gmail authorization'))
    }
  }, [clearPollTimer, fetchIntegrations])

  const resetError = useCallback(() => setPopupError(null), [])

  return {
    integrations,
    integrationsLoading,
    popupOpen,
    popupError,
    startAuthorization,
    fetchIntegrations,
    resetError,
  }
}

export { POLL_INTERVAL_MS, POLL_MAX_TICKS }
