'use client'

/**
 * usePlaygroundMini — the data hook behind Playground Mini.
 *
 * Owns agent / project / thread selection, message list, send state, and
 * persistence via `playgroundMiniSessionStore`. Reuses existing `api.*`
 * methods — no new endpoints, no WebSocket.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  api,
  PlaygroundAgentInfo,
  PlaygroundMessage,
  PlaygroundThread,
  Project,
} from '@/lib/client'
import * as store from '@/lib/playgroundMiniSessionStore'

export interface UsePlaygroundMiniOptions {
  userId: number | null
  onExpand?: () => void
}

export interface UsePlaygroundMiniResult {
  hydrated: boolean
  isOpen: boolean
  setOpen: (open: boolean) => void
  toggleOpen: () => void

  agents: PlaygroundAgentInfo[]
  projects: Project[]
  threads: PlaygroundThread[]

  selectedAgentId: number | null
  selectedProjectId: number | null
  activeThreadId: number | null
  activeThread: PlaygroundThread | null

  messages: PlaygroundMessage[]
  isSending: boolean
  isLoadingAgents: boolean
  isLoadingThreads: boolean
  isLoadingMessages: boolean
  sendError: string | null

  selectAgent: (agentId: number) => void
  selectProject: (projectId: number | null) => void
  selectThread: (threadId: number) => Promise<void>
  newThread: () => Promise<void>
  sendMessage: (text: string) => Promise<void>
  refresh: () => Promise<void>
}

export function usePlaygroundMini(options: UsePlaygroundMiniOptions): UsePlaygroundMiniResult {
  const { userId } = options

  const [hydrated, setHydrated] = useState(false)
  const [isOpen, setIsOpenState] = useState(false)

  const [agents, setAgents] = useState<PlaygroundAgentInfo[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [threads, setThreads] = useState<PlaygroundThread[]>([])
  const [selectedAgentId, setSelectedAgentId] = useState<number | null>(null)
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null)
  const [activeThreadId, setActiveThreadId] = useState<number | null>(null)
  const [activeThread, setActiveThread] = useState<PlaygroundThread | null>(null)
  const [messages, setMessages] = useState<PlaygroundMessage[]>([])

  const [isSending, setIsSending] = useState(false)
  const [isLoadingAgents, setIsLoadingAgents] = useState(false)
  const [isLoadingThreads, setIsLoadingThreads] = useState(false)
  const [isLoadingMessages, setIsLoadingMessages] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)

  const threadAbortRef = useRef<AbortController | null>(null)
  // Synchronous in-flight guard so `sendMessage` doesn't need to list
  // `isSending` in its `useCallback` deps — otherwise the callback identity
  // flips on every in-flight transition and ripples through to every consumer.
  const sendingRef = useRef(false)

  // --- Hydrate from sessionStorage on mount (client-only) ---------------------
  useEffect(() => {
    if (!userId) {
      setHydrated(true)
      return
    }
    const persisted = store.load(userId)
    setIsOpenState(persisted.isOpen)
    setSelectedAgentId(persisted.selectedAgentId)
    setSelectedProjectId(persisted.selectedProjectId)
    setActiveThreadId(persisted.activeThreadId)
    setHydrated(true)
  }, [userId])

  // --- Persist selection state ------------------------------------------------
  useEffect(() => {
    if (!hydrated || !userId) return
    store.save(userId, {
      isOpen,
      selectedAgentId,
      selectedProjectId,
      activeThreadId,
    })
  }, [hydrated, userId, isOpen, selectedAgentId, selectedProjectId, activeThreadId])

  const setOpen = useCallback((next: boolean) => setIsOpenState(next), [])
  const toggleOpen = useCallback(() => setIsOpenState(prev => !prev), [])

  // --- Load agents + projects once the panel first becomes open OR hydrates with isOpen=true ---
  const loadAgents = useCallback(async () => {
    if (!userId) return
    setIsLoadingAgents(true)
    try {
      const data = await api.getPlaygroundAgents()
      setAgents(data)
      // If nothing selected yet, auto-pick default or first
      setSelectedAgentId(curr => {
        if (curr != null && data.some(a => a.id === curr)) return curr
        if (data.length === 0) return null
        const def = data.find(a => a.is_default) || data[0]
        return def.id
      })
    } catch (err) {
      console.error('[PlaygroundMini] Failed to load agents:', err)
    } finally {
      setIsLoadingAgents(false)
    }
  }, [userId])

  const loadProjects = useCallback(async () => {
    if (!userId) return
    try {
      const data = await api.getProjects(false)
      const visible = data.filter(p => !p.is_archived)
      setProjects(visible)
      // Drop selection if the previously-selected project is archived or gone
      // from the visible set. Compare against the filtered list so an archived
      // project cannot remain selected even if it still returns from the API.
      setSelectedProjectId(curr => (curr != null && visible.some(p => p.id === curr) ? curr : null))
    } catch (err) {
      console.error('[PlaygroundMini] Failed to load projects:', err)
    }
  }, [userId])

  // Load agents + projects the first time the panel opens (or if opened via hydrate).
  // Reset the one-shot guard whenever the active user changes so a re-login on the
  // same tab re-fetches the new user's data instead of showing empty lists.
  const hasLoadedOnceRef = useRef(false)
  const prevUserIdRef = useRef<number | null | undefined>(undefined)
  useEffect(() => {
    if (prevUserIdRef.current !== userId) {
      hasLoadedOnceRef.current = false
      prevUserIdRef.current = userId
    }
  }, [userId])

  useEffect(() => {
    if (!hydrated || !userId) return
    if (!isOpen) return
    if (hasLoadedOnceRef.current) return
    hasLoadedOnceRef.current = true
    void loadAgents()
    void loadProjects()
  }, [hydrated, userId, isOpen, loadAgents, loadProjects])

  // --- Thread list depends on agent + project -------------------------------
  const loadThreads = useCallback(
    async (agentId: number | null, projectName: string | undefined) => {
      if (!agentId) {
        setThreads([])
        return
      }
      setIsLoadingThreads(true)
      try {
        const result = await api.listThreads(agentId, false, projectName)
        setThreads(result.threads)
      } catch (err) {
        console.error('[PlaygroundMini] Failed to load threads:', err)
        setThreads([])
      } finally {
        setIsLoadingThreads(false)
      }
    },
    [],
  )

  const currentProject = projects.find(p => p.id === selectedProjectId) || null

  useEffect(() => {
    if (!hydrated || !userId || !isOpen) return
    void loadThreads(selectedAgentId, currentProject?.name)
  }, [hydrated, userId, isOpen, selectedAgentId, selectedProjectId, loadThreads, currentProject?.name])

  // --- Load messages for active thread --------------------------------------
  useEffect(() => {
    if (!hydrated || !userId || !isOpen) return
    if (!activeThreadId) {
      setMessages([])
      setActiveThread(null)
      return
    }

    // Abort previous in-flight load
    if (threadAbortRef.current) {
      threadAbortRef.current.abort()
    }
    const controller = new AbortController()
    threadAbortRef.current = controller

    setIsLoadingMessages(true)
    api
      .getThread(activeThreadId, { signal: controller.signal })
      .then(data => {
        if (controller.signal.aborted) return
        setMessages(data.messages || [])
        setActiveThread({
          id: data.id,
          title: data.title,
          folder: data.folder,
          status: data.status,
          is_archived: data.is_archived,
          agent_id: data.agent_id,
          created_at: data.created_at,
          updated_at: data.updated_at,
        })
        // If the thread belongs to a different agent than the currently
        // selected one (e.g., restored from sessionStorage after agent change),
        // snap the agent selection to match the thread.
        if (data.agent_id && data.agent_id !== selectedAgentId) {
          setSelectedAgentId(data.agent_id)
        }
      })
      .catch(err => {
        if (controller.signal.aborted) return
        // Tenant drift, deleted thread, etc. — clear silently.
        console.warn('[PlaygroundMini] getThread failed, clearing active thread:', err)
        setActiveThreadId(null)
        setActiveThread(null)
        setMessages([])
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoadingMessages(false)
        }
      })

    return () => {
      controller.abort()
    }
  }, [hydrated, userId, isOpen, activeThreadId, selectedAgentId])

  // --- Actions --------------------------------------------------------------
  const selectAgent = useCallback((agentId: number) => {
    setSelectedAgentId(agentId)
    setActiveThreadId(null)
    setActiveThread(null)
    setMessages([])
    setSendError(null)
  }, [])

  const selectProject = useCallback((projectId: number | null) => {
    setSelectedProjectId(projectId)
    setActiveThreadId(null)
    setActiveThread(null)
    setMessages([])
    setSendError(null)
  }, [])

  const selectThread = useCallback(async (threadId: number) => {
    setActiveThreadId(threadId)
    setSendError(null)
  }, [])

  const newThread = useCallback(async () => {
    if (!selectedAgentId) return
    try {
      const folder = currentProject?.name || undefined
      const created = await api.createThread({
        agent_id: selectedAgentId,
        title: 'New Conversation',
        folder,
      })
      setThreads(prev => [created, ...prev.filter(t => t.id !== created.id)])
      setActiveThreadId(created.id)
      setActiveThread(created)
      setMessages([])
      setSendError(null)
    } catch (err) {
      console.error('[PlaygroundMini] Failed to create thread:', err)
      setSendError('Could not create a new thread')
    }
  }, [selectedAgentId, currentProject])

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim()
      if (!trimmed || !selectedAgentId) return
      // Synchronous in-flight guard via ref so a rapid double-submit is dropped
      // without making this callback's identity depend on `isSending`.
      if (sendingRef.current) return
      sendingRef.current = true

      const nowIso = new Date().toISOString()
      const optimisticUser: PlaygroundMessage = {
        role: 'user',
        content: trimmed,
        timestamp: nowIso,
      }
      // Append optimistic bubble and remember the exact object so we can roll
      // back by identity (safer than popping the last element in case a
      // concurrent update interleaves).
      setMessages(prev => [...prev, optimisticUser])
      const rollbackOptimistic = () =>
        setMessages(prev => prev.filter(m => m !== optimisticUser))

      setIsSending(true)
      setSendError(null)

      try {
        // Ensure a thread exists BEFORE sending so handover to the full Playground
        // can always include ?thread=<id>. If we sent with thread_id=undefined, the
        // backend would auto-create a thread but the response body doesn't echo the
        // new thread_id back, leaving us unable to deep-link into it on expand.
        let threadId = activeThreadId
        if (!threadId) {
          try {
            const folder = currentProject?.name || undefined
            const created = await api.createThread({
              agent_id: selectedAgentId,
              title: 'New Conversation',
              folder,
            })
            threadId = created.id
            setThreads(prev => [created, ...prev.filter(t => t.id !== created.id)])
            setActiveThreadId(created.id)
            setActiveThread(created)
          } catch (err) {
            console.error('[PlaygroundMini] Could not create thread before send:', err)
            rollbackOptimistic()
            setSendError('Could not create a thread for this conversation.')
            return
          }
        }

        const response = await api.sendPlaygroundMessage(
          selectedAgentId,
          trimmed,
          threadId,
          true, // sync
        )

        if (response.status === 'error') {
          rollbackOptimistic()
          setSendError(response.error || response.message || 'Failed to send message')
          return
        }

        const assistant: PlaygroundMessage = {
          role: 'assistant',
          content: response.message || '',
          timestamp: response.timestamp || new Date().toISOString(),
          kb_used: response.kb_used,
        }
        setMessages(prev => [...prev, assistant])

        // If the backend renamed the thread on first message, update the local thread title.
        if (response.thread_renamed && response.new_thread_title && threadId) {
          setActiveThread(prev =>
            prev && prev.id === threadId
              ? { ...prev, title: response.new_thread_title! }
              : prev,
          )
          setThreads(prev =>
            prev.map(t =>
              t.id === threadId ? { ...t, title: response.new_thread_title! } : t,
            ),
          )
        }

        // Refresh thread list so any new/renamed thread shows up.
        void loadThreads(selectedAgentId, currentProject?.name)
      } catch (err: any) {
        console.error('[PlaygroundMini] sendMessage failed:', err)
        rollbackOptimistic()
        setSendError(err?.message || 'Failed to send message')
      } finally {
        sendingRef.current = false
        setIsSending(false)
      }
    },
    [selectedAgentId, activeThreadId, loadThreads, currentProject],
  )

  const refresh = useCallback(async () => {
    if (!isOpen || !userId) return
    await Promise.all([loadAgents(), loadProjects()])
    await loadThreads(selectedAgentId, currentProject?.name)
  }, [isOpen, userId, loadAgents, loadProjects, loadThreads, selectedAgentId, currentProject])

  return {
    hydrated,
    isOpen,
    setOpen,
    toggleOpen,

    agents,
    projects,
    threads,

    selectedAgentId,
    selectedProjectId,
    activeThreadId,
    activeThread,

    messages,
    isSending,
    isLoadingAgents,
    isLoadingThreads,
    isLoadingMessages,
    sendError,

    selectAgent,
    selectProject,
    selectThread,
    newThread,
    sendMessage,
    refresh,
  }
}
