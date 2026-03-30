'use client'

import { useState, useEffect, useCallback } from 'react'
import { api } from '@/lib/client'
import type { CommEnabledAgent, CommPermissionSummary } from '@/lib/client'

interface A2ANetworkData {
  commEnabledAgents: CommEnabledAgent[]
  permissions: CommPermissionSummary[]
  isLoading: boolean
  error: string | null
  refetch: () => void
}

export function useA2ANetworkData(enabled: boolean): A2ANetworkData {
  const [commEnabledAgents, setCommEnabledAgents] = useState<CommEnabledAgent[]>([])
  const [permissions, setPermissions] = useState<CommPermissionSummary[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    if (!enabled) return
    let cancelled = false
    setIsLoading(true)
    setError(null)
    try {
      const result = await api.getCommEnabledAgents()
      if (!cancelled) {
        setCommEnabledAgents(result.agents)
        setPermissions(result.permissions)
      }
    } catch (err) {
      if (!cancelled) {
        setError(err instanceof Error ? err.message : 'Failed to fetch A2A network data')
      }
    } finally {
      if (!cancelled) setIsLoading(false)
    }
    // Return cancellation — used by useEffect cleanup
    return () => { cancelled = true }
  }, [enabled])

  useEffect(() => {
    if (enabled) {
      let cancel: (() => void) | undefined
      fetchData().then(cleanup => { cancel = cleanup })
      return () => { cancel?.() }
    } else {
      setCommEnabledAgents([])
      setPermissions([])
      setError(null)
    }
  }, [enabled, fetchData])

  return { commEnabledAgents, permissions, isLoading, error, refetch: fetchData }
}
