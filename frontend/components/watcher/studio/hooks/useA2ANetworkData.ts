'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
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
  // cancelRef lives outside the async function so cleanup can cancel in-flight fetches immediately
  const cancelRef = useRef(false)

  const fetchData = useCallback(async () => {
    if (!enabled) return
    cancelRef.current = false
    setIsLoading(true)
    setError(null)
    try {
      const result = await api.getCommEnabledAgents()
      if (!cancelRef.current) {
        setCommEnabledAgents(result.agents)
        setPermissions(result.permissions)
      }
    } catch (err) {
      if (!cancelRef.current) {
        setError(err instanceof Error ? err.message : 'Failed to fetch A2A network data')
      }
    } finally {
      if (!cancelRef.current) setIsLoading(false)
    }
  }, [enabled])

  useEffect(() => {
    if (enabled) {
      fetchData()
      return () => { cancelRef.current = true }
    } else {
      setCommEnabledAgents([])
      setPermissions([])
      setError(null)
    }
  }, [enabled, fetchData])

  return { commEnabledAgents, permissions, isLoading, error, refetch: fetchData }
}
