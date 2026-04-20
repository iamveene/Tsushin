'use client'

import { useCallback, useEffect, useRef } from 'react'
import { api } from '@/lib/client'

export interface KokoroPollCallbacks {
  onReady: () => void
  onError: (message: string) => void
  onProgress?: (message: string) => void
}

/**
 * Polls a Kokoro TTS container until it reports `running`, `error`, or times out.
 * Shared between AudioAgentsWizard and the AgentWizard audio step so the two
 * flows stay consistent when Kokoro auto-provisioning is involved.
 */
export function useKokoroPolling() {
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  const cancel = useCallback(() => {
    if (timer.current) {
      clearInterval(timer.current)
      timer.current = null
    }
  }, [])

  useEffect(() => cancel, [cancel])

  const poll = useCallback(
    (instanceId: number, cb: KokoroPollCallbacks) => {
      cancel()
      let ticks = 0
      timer.current = setInterval(async () => {
        ticks++
        try {
          const status = await api.getTTSContainerStatus(instanceId)
          const state = (status?.status || '').toLowerCase()
          if (state === 'running') {
            cancel()
            cb.onReady()
            return
          }
          if (state === 'error') {
            cancel()
            cb.onError('Container failed to start. Check Hub → Voice for details.')
            return
          }
          if (state === 'creating' || state === 'provisioning') {
            cb.onProgress?.('Pulling image and starting container (30–90s)...')
          }
        } catch {
          /* transient — keep polling */
        }
        if (ticks > 120) {
          cancel()
          cb.onError('Provisioning timed out after 6 minutes. Check Hub → Voice.')
        }
      }, 3000)
    },
    [cancel],
  )

  return { poll, cancel }
}
