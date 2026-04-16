'use client'

import { useState, useEffect, useCallback } from 'react'
import { api } from '@/lib/client'

export interface SetupProgress {
  hasAgents: boolean
  hasChannels: boolean
  hasContacts: boolean
  hasMessages: boolean
  hasFlows: boolean
  allComplete: boolean
  loading: boolean
}

export function useSetupProgress(): SetupProgress & { refresh: () => void } {
  const [progress, setProgress] = useState<SetupProgress>({
    hasAgents: false,
    hasChannels: false,
    hasContacts: false,
    hasMessages: false,
    hasFlows: false,
    allComplete: false,
    loading: true,
  })

  const fetchProgress = useCallback(async () => {
    try {
      const [agents, instances, contacts, messages, flows] = await Promise.all([
        api.getAgents().catch(() => []),
        api.getMCPInstances().catch(() => []),
        api.getContacts().catch(() => []),
        api.getMessages(1).catch(() => []),
        api.getFlows().catch(() => ({ items: [] })),
      ])

      const hasAgents = Array.isArray(agents) && agents.length > 0
      const hasChannels = Array.isArray(instances) && instances.length > 0
      const hasContacts = Array.isArray(contacts) && contacts.filter((c: any) => c.role === 'user').length > 0
      const hasMessages = Array.isArray(messages) && messages.length > 0
      const flowItems = flows && typeof flows === 'object' && 'items' in flows ? (flows as any).items : flows
      const hasFlows = Array.isArray(flowItems) && flowItems.length > 0

      setProgress({
        hasAgents,
        hasChannels,
        hasContacts,
        hasMessages,
        hasFlows,
        allComplete: hasAgents && hasChannels && hasContacts && hasMessages && hasFlows,
        loading: false,
      })
    } catch {
      setProgress(prev => ({ ...prev, loading: false }))
    }
  }, [])

  useEffect(() => {
    fetchProgress()
  }, [fetchProgress])

  return { ...progress, refresh: fetchProgress }
}
