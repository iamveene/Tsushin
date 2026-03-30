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
    setIsLoading(true)
    setError(null)
    try {
      const result = await api.getCommEnabledAgents()
      setCommEnabledAgents(result.agents)
      setPermissions(result.permissions)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch A2A network data')
    } finally {
      setIsLoading(false)
    }
  }, [enabled])

  useEffect(() => {
    if (enabled) {
      fetchData()
    } else {
      setCommEnabledAgents([])
      setPermissions([])
      setError(null)
    }
  }, [enabled, fetchData])

  return { commEnabledAgents, permissions, isLoading, error, refetch: fetchData }
}
