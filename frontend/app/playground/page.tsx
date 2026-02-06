'use client'

/**
 * Playground - Interactive Agent Chat Interface
 * Premium UI with glass effects and modern animations
 */

import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useRequireAuth } from '@/contexts/AuthContext'
import { api, PlaygroundAgentInfo, PlaygroundMessage, AudioCapabilities, PlaygroundDocument, PlaygroundSettings, ProjectSession, Project, SlashCommand, PlaygroundThread } from '@/lib/client'
import { formatTime } from '@/lib/dateUtils'
import DocumentPanel from '@/components/playground/DocumentPanel'
import PlaygroundSettingsModal from '@/components/playground/PlaygroundSettings'
import CommandPalette from '@/components/playground/CommandPalette'
import ProjectMemoryManager from '@/components/playground/ProjectMemoryManager'
import ExpertMode from '@/components/playground/ExpertMode'
import SearchBar from '@/components/playground/SearchBar'
import SearchResults from '@/components/playground/SearchResults'
import KnowledgePanel from '@/components/playground/KnowledgePanel'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { usePlaygroundWebSocket } from '@/hooks/usePlaygroundWebSocket'
import { getCachedProjectSession, setCachedProjectSession, clearCachedProjectSession } from '@/lib/projectSessionCache'
import { getCachedProjects, setCachedProjects } from '@/lib/projectsCache'
import { getCachedAgents, setCachedAgents } from '@/lib/agentsCache'
import StreamingMessage from '@/components/playground/StreamingMessage'
import './cockpit.css'
import './playground.css'

export default function PlaygroundPage() {
  const { user, loading } = useRequireAuth()

  const [agents, setAgents] = useState<PlaygroundAgentInfo[]>([])
  const [selectedAgentId, setSelectedAgentId] = useState<number | null>(null)
  const [messages, setMessages] = useState<PlaygroundMessage[]>([])
  const [isSending, setIsSending] = useState(false)
  const [isLoadingHistory, setIsLoadingHistory] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [agentName, setAgentName] = useState<string>('')
  const [autoScroll, setAutoScroll] = useState(true)
  const [showMobileSidebar, setShowMobileSidebar] = useState(false)

  // Phase 14.0: Audio recording state
  const [audioCapabilities, setAudioCapabilities] = useState<AudioCapabilities | null>(null)
  const [isRecording, setIsRecording] = useState(false)
  const [recordingTime, setRecordingTime] = useState(0)
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [isProcessingAudio, setIsProcessingAudio] = useState(false)

  // Phase 14.2: Document attachments state
  const [documents, setDocuments] = useState<PlaygroundDocument[]>([])
  const [isDocumentPanelOpen, setIsDocumentPanelOpen] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Phase 14.3: Settings state
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [playgroundSettings, setPlaygroundSettings] = useState<PlaygroundSettings | null>(null)

  // Phase 15: Skill Projects - Session state
  const [projectSession, setProjectSession] = useState<ProjectSession | null>(null)
  const [isLoadingProjectSession, setIsLoadingProjectSession] = useState(false)
  const [isExitingProject, setIsExitingProject] = useState(false)
  const [projects, setProjects] = useState<Project[]>([])

  // Phase 16: Command System State
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false)
  const [slashCommands, setSlashCommands] = useState<SlashCommand[]>([])
  const [inlineCommandsOpen, setInlineCommandsOpen] = useState(false)
  const [inlineQuery, setInlineQuery] = useState('')
  const [inlineSelectedIndex, setInlineSelectedIndex] = useState(0)
  const [availableTools, setAvailableTools] = useState<string[]>([])
  const [availableAgents, setAvailableAgents] = useState<string[]>([])
  const [injectTargets, setInjectTargets] = useState<string[]>([])
  const [isProjectMemoryOpen, setIsProjectMemoryOpen] = useState(false)

  // Phase 14.1: Thread Management State
  const [threads, setThreads] = useState<PlaygroundThread[]>([])
  const [activeThreadId, setActiveThreadId] = useState<number | null>(null)
  const [activeThread, setActiveThread] = useState<PlaygroundThread | null>(null)
  const [showThreadSidebar, setShowThreadSidebar] = useState(true)
  const [isLoadingThreads, setIsLoadingThreads] = useState(false)
  const [isLoadingThread, setIsLoadingThread] = useState(false)
  const [threadLoadError, setThreadLoadError] = useState<string | null>(null)

  // Phase 14.5: Search State
  const [isSearchOpen, setIsSearchOpen] = useState(false)
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [searchMode, setSearchMode] = useState<'full_text' | 'semantic' | 'combined'>('full_text')
  const [isSearchCollapsed, setIsSearchCollapsed] = useState(false)
  const [isSearching, setIsSearching] = useState(false)

  // Phase 14.6: Knowledge Panel State
  const [isKnowledgePanelOpen, setIsKnowledgePanelOpen] = useState(false)

  // Phase 14.9: WebSocket Streaming State
  const [useWebSocket, setUseWebSocket] = useState(true) // Feature flag
  const [streamingMessage, setStreamingMessage] = useState<Partial<PlaygroundMessage> | null>(null)

  // Message history for up arrow recall
  const [messageHistory, setMessageHistory] = useState<string[]>([])
  const [historyIndex, setHistoryIndex] = useState(-1)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const loadThreadsTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const recordingTimerRef = useRef<NodeJS.Timeout | null>(null)
  const activeThreadIdRef = useRef<number | null>(null)

  // Sync ref with state to avoid closure issues
  useEffect(() => {
    activeThreadIdRef.current = activeThreadId
  }, [activeThreadId])

  // Phase 14.9: WebSocket Hook for streaming - FORCE REBUILD v2
  const wsToken = typeof window !== 'undefined' ? localStorage.getItem('tsushin_auth_token') : null
  console.log('[Playground] Initializing WebSocket hook - token:', !!wsToken, 'user:', !!user, 'enabled:', useWebSocket && !!user)

  const websocketConnection = usePlaygroundWebSocket(
    wsToken,
    {
      enabled: useWebSocket && !!user,
      onStreamingMessage: (message) => {
        setStreamingMessage(message)
      },
      onMessageComplete: (message) => {
        // Add completed message to messages list
        setMessages((prev) => [...prev, message])
        setStreamingMessage(null)

        // Check if thread was auto-renamed via WebSocket
        if (message.metadata?.thread_renamed && message.metadata?.new_thread_title) {
          console.log('[Auto-rename WS] Thread renamed to:', message.metadata.new_thread_title)
          // Update local thread state with new title
          setActiveThread(prev => prev ? { ...prev, title: message.metadata!.new_thread_title } : null)
          // FIX 2026-01-30: Pass agentId from metadata to avoid stale closure issues
          const agentIdFromMetadata = message.metadata?.agent_id || selectedAgentId
          if (agentIdFromMetadata) {
            // Refresh thread list to show new title in sidebar
            loadThreads(agentIdFromMetadata)
          }
        }

        // Refresh thread if active (to get proper message IDs from backend)
        if (activeThreadId) {
          api.getThread(activeThreadId).then(threadData => {
            // Only update if messages have changed
            if (JSON.stringify(threadData.messages) !== JSON.stringify(messages)) {
              setMessages(threadData.messages || [])
            }
          }).catch(err => {
            console.error('Failed to refresh thread after streaming:', err)
          })
        }
      },
      onThreadCreated: (threadId, title) => {
        console.log('[Playground] Thread created via WebSocket:', threadId, title)
        setActiveThreadId(threadId)
        setActiveThread({ id: threadId, title } as any)
        handleThreadUpdated()
      },
      onError: (error) => {
        setError(error)
        setStreamingMessage(null)
      },
    }
  )

  // Auto-scroll to bottom when messages change
  const scrollToBottom = () => {
    if (autoScroll) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, autoScroll])

  // Load agents and commands on mount
  useEffect(() => {
    if (user) {
      loadAgents()
      loadCommands()
      loadProjects()
    }
  }, [user])

  // Listen for global refresh events
  useEffect(() => {
    const handleRefresh = () => {
      if (user) {
        loadAgents()
        loadCommands()
        loadProjects()
        if (selectedAgentId) {
          loadThreads(selectedAgentId)
        }
      }
    }
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => window.removeEventListener('tsushin:refresh', handleRefresh)
  }, [user, selectedAgentId])

  // Phase 16: Load slash commands
  const loadCommands = async () => {
    try {
      const commands = await api.getSlashCommands()
      setSlashCommands(commands)
    } catch (err) {
      console.error('Failed to load commands:', err)
    }
  }

  // Phase 16: Load projects for command palette (with caching)
  const loadProjects = async () => {
    if (!user) return

    try {
      // Check cache first for instant loading
      const cachedProjects = getCachedProjects(user.id)
      if (cachedProjects) {
        setProjects(cachedProjects)
      }

      // Fetch fresh data in background
      const data = await api.getProjects()
      setProjects(data)

      // Update cache with fresh data
      setCachedProjects(user.id, data)
    } catch (err) {
      console.error('Failed to load projects:', err)
    }
  }

  // Phase 14.5: Search handler
  const handleSearch = async (query: string, mode: 'full_text' | 'semantic' | 'combined', filters: any) => {
    setIsSearching(true)
    setSearchQuery(query)
    setSearchMode(mode)

    try {
      let response
      if (mode === 'semantic') {
        response = await api.searchConversationsSemantic(query, filters.agent_id)
      } else if (mode === 'combined') {
        response = await api.searchConversationsCombined(query, filters)
      } else {
        response = await api.searchConversations(query, filters)
      }

      setSearchResults(response.results || [])
      // Collapse search bar when results are shown
      if ((response.results || []).length > 0) {
        setIsSearchCollapsed(true)
      }
    } catch (err) {
      console.error('Search failed:', err)
      setSearchResults([])
    } finally {
      setIsSearching(false)
    }
  }

  // Phase 14.5: Navigate to search result
  const handleSearchResultClick = (threadId: number, messageId: string) => {
    setIsSearchOpen(false)
    setActiveThreadId(threadId)
    handleThreadSelect(threadId)
    // TODO: Scroll to specific message
  }

  // Phase 14.5: Direct keyboard shortcut for search (FIX for Cmd+K)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd+K or Ctrl+K for search
      if ((e.metaKey || e.ctrlKey) && e.key === 'k' && !e.shiftKey) {
        e.preventDefault()
        setIsSearchOpen(prev => !prev)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  // Keyboard shortcuts (cockpit mode is always active)
  useKeyboardShortcuts({
    onCommandPalette: () => {
      if (isSearchOpen) {
        setIsSearchOpen(false)
      } else {
        setIsSearchOpen(true)
      }
    },
    onToggleCockpit: () => {}, // No longer needed - always in cockpit mode
    onSwitchToSimple: () => {},
    onSwitchToExpert: () => {},
    onFocusInput: () => {
      if (inputRef.current) {
        inputRef.current.focus()
        inputRef.current.value = '/'
        setInlineCommandsOpen(true)
        setInlineQuery('')
      }
    },
    onEscape: () => {
      if (isSearchOpen) {
        setIsSearchOpen(false)
      } else if (isKnowledgePanelOpen) {
        setIsKnowledgePanelOpen(false)
      } else if (isCommandPaletteOpen) {
        setIsCommandPaletteOpen(false)
      } else if (projectSession?.is_in_project) {
        handleExitProject()
      }
    }
  })

  // Load agent capabilities when agent is selected
  useEffect(() => {
    if (selectedAgentId && user) {
      // Load audio capabilities only
      // Note: Project session is cleared when switching agents (see initializeThreads)
      loadAudioCapabilities(selectedAgentId).catch(err => {
        console.error('Error loading audio capabilities:', err)
      })
      // On mobile, close sidebar when agent is selected
      setShowMobileSidebar(false)
    }
  }, [selectedAgentId, user])

  // Track banner render timing
  useEffect(() => {
    if (projectSession?.is_in_project) {
      console.log(`[TIMING] ✅ Banner RENDERED for project: ${projectSession.project_name} at ${performance.now()}ms`)
    } else {
      console.log(`[TIMING] Banner cleared/hidden at ${performance.now()}ms`)
    }
  }, [projectSession?.is_in_project, projectSession?.project_name])

  // Phase 15: Load project session for selected agent (with caching)
  const loadProjectSession = async (agentId: number) => {
    if (!user) return

    try {
      // Check cache first for instant loading
      const cachedSession = getCachedProjectSession(user.id, agentId)
      if (cachedSession) {
        setProjectSession(cachedSession)
      } else {
        // Only show loading state if there's no cached data
        setIsLoadingProjectSession(true)
      }

      // Fetch fresh data in background
      const session = await api.getProjectSession(agentId, 'playground')
      setProjectSession(session)

      // Update cache with fresh data
      setCachedProjectSession(user.id, agentId, session)
    } catch (err) {
      console.error('Failed to load project session:', err)
      setProjectSession(null)
    } finally {
      setIsLoadingProjectSession(false)
    }
  }

  // Phase 15: Exit project session
  const handleExitProject = useCallback(async () => {
    if (!selectedAgentId || isExitingProject || !user) return

    setIsExitingProject(true)
    try {
      await api.exitProjectSession(selectedAgentId, 'playground')
      setProjectSession(null)

      // Clear cache when exiting project
      clearCachedProjectSession(user.id, selectedAgentId)

      // Show success message
      const exitMsg: PlaygroundMessage = {
        role: 'assistant',
        content: '✅ You have exited the project. Returning to normal chat mode.',
        timestamp: new Date().toISOString(),
        message_id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
      }
      setMessages(prev => [...prev, exitMsg])
    } catch (err: any) {
      setError(err.message || 'Failed to exit project')
    } finally {
      setIsExitingProject(false)
    }
  }, [selectedAgentId, isExitingProject, user])

  // Note: Escape key handling is now consolidated in useKeyboardShortcuts hook above

  // Clean up audio URL on unmount or when audio changes
  useEffect(() => {
    return () => {
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl)
      }
    }
  }, [audioUrl])

  // Phase 14.0: Load audio capabilities for selected agent
  const loadAudioCapabilities = async (agentId: number) => {
    try {
      const capabilities = await api.getAgentAudioCapabilities(agentId)
      setAudioCapabilities(capabilities)
    } catch (err) {
      console.error('Failed to load audio capabilities:', err)
      setAudioCapabilities(null)
    }
  }

  // Phase 14.0: Start recording audio
  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })

      // Try to use webm format, fallback to other formats
      const mimeTypes = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/ogg;codecs=opus',
        'audio/mp4',
      ]

      let mimeType = ''
      for (const type of mimeTypes) {
        if (MediaRecorder.isTypeSupported(type)) {
          mimeType = type
          break
        }
      }

      const mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      mediaRecorderRef.current = mediaRecorder
      audioChunksRef.current = []

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }

      mediaRecorder.onstop = () => {
        const blob = new Blob(audioChunksRef.current, { type: mimeType || 'audio/webm' })
        setAudioBlob(blob)
        setAudioUrl(URL.createObjectURL(blob))

        // Stop all tracks
        stream.getTracks().forEach(track => track.stop())
      }

      mediaRecorder.start(100) // Collect data every 100ms
      setIsRecording(true)
      setRecordingTime(0)

      // Start timer
      recordingTimerRef.current = setInterval(() => {
        setRecordingTime(prev => prev + 1)
      }, 1000)

    } catch (err: any) {
      console.error('Failed to start recording:', err)
      setError(err.message || 'Failed to access microphone. Please check permissions.')
    }
  }, [])

  // Phase 14.0: Stop recording
  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop()
      setIsRecording(false)

      if (recordingTimerRef.current) {
        clearInterval(recordingTimerRef.current)
        recordingTimerRef.current = null
      }
    }
  }, [isRecording])

  // Phase 14.0: Cancel recording
  const cancelRecording = useCallback(() => {
    stopRecording()
    setAudioBlob(null)
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl)
      setAudioUrl(null)
    }
    setRecordingTime(0)
  }, [stopRecording, audioUrl])

  // Phase 14.0: Send audio message
  const sendAudioMessage = useCallback(async () => {
    if (!audioBlob || !selectedAgentId || isProcessingAudio) return

    setIsProcessingAudio(true)
    setError(null)
    setAutoScroll(true)

    // Add user audio message placeholder to UI
    const userMsg: PlaygroundMessage = {
      role: 'user',
      content: '🎤 Audio message...',
      timestamp: new Date().toISOString(),
      message_id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    }
    setMessages(prev => [...prev, userMsg])

    try {
      const response = await api.sendPlaygroundAudio(selectedAgentId, audioBlob)

      // Update user message with transcript
      if (response.transcript) {
        setMessages(prev => {
          const updated = [...prev]
          const lastUserIdx = updated.length - 1
          if (updated[lastUserIdx]?.role === 'user') {
            updated[lastUserIdx] = {
              ...updated[lastUserIdx],
              content: `🎤 ${response.transcript}`
            }
          }
          return updated
        })
      }

      if (response.status === 'success' && response.message) {
        // Add agent response to UI
        const agentMsg: PlaygroundMessage = {
          role: 'assistant',
          content: response.message,
          timestamp: response.timestamp,
          message_id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          audio_url: response.audio_url,
          audio_duration: response.audio_duration
        }
        setMessages(prev => [...prev, agentMsg])
      } else if (response.error) {
        setError(response.error)
      }

    } catch (err: any) {
      setError(err.message || 'Failed to send audio message')
    } finally {
      setIsProcessingAudio(false)
      // Clear audio state
      setAudioBlob(null)
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl)
        setAudioUrl(null)
      }
      setRecordingTime(0)
    }
  }, [audioBlob, selectedAgentId, isProcessingAudio, audioUrl])

  // Format recording time as MM:SS
  const formatRecordingTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }

  // Phase 14.2: Load documents for selected agent
  const loadDocuments = useCallback(async () => {
    if (!selectedAgentId) return
    try {
      const result = await api.getPlaygroundDocuments(selectedAgentId)
      setDocuments(result.documents || [])
    } catch (err) {
      console.error('Failed to load documents:', err)
    }
  }, [selectedAgentId])

  // Phase 14.2: Load documents when agent changes
  useEffect(() => {
    if (selectedAgentId) {
      loadDocuments()
    } else {
      setDocuments([])
    }
  }, [selectedAgentId, loadDocuments])

  // Phase 14.2: Handle quick file upload from clip button
  const handleQuickFileUpload = useCallback(async (files: FileList) => {
    if (!selectedAgentId || files.length === 0) return

    setError(null)

    for (const file of Array.from(files)) {
      try {
        const result = await api.uploadPlaygroundDocument(selectedAgentId, file)
        if (result.status === 'error') {
          setError(result.error || 'Upload failed')
        }
      } catch (err: any) {
        setError(err.message || 'Failed to upload file')
      }
    }

    loadDocuments()
  }, [selectedAgentId, loadDocuments])

  const loadAgents = async () => {
    if (!user) return

    try {
      // Check cache first for instant loading
      const cachedAgents = getCachedAgents(user.id)
      if (cachedAgents) {
        setAgents(cachedAgents)
        // Auto-select first agent if available and none selected
        if (cachedAgents.length > 0) {
          setSelectedAgentId(currentId => currentId === null ? cachedAgents[0].id : currentId)
        }
      }

      // Fetch fresh data in background
      const data = await api.getPlaygroundAgents()
      setAgents(data)

      // Update cache with fresh data
      setCachedAgents(user.id, data)

      // Auto-select first agent if available and none selected
      if (data.length > 0) {
        setSelectedAgentId(currentId => currentId === null ? data[0].id : currentId)
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load agents')
    }
  }

  // Phase 14.1: Thread Management Functions
  // FIX 2026-01-30: Accept agentId parameter to avoid stale closure issues in callbacks
  // FIX 2026-01-31: Add debouncing and loading state
  const loadThreads = async (agentId?: number) => {
    const targetAgentId = agentId ?? selectedAgentId
    if (!targetAgentId) return

    // Debounce rapid calls
    if (loadThreadsTimeoutRef.current) {
      clearTimeout(loadThreadsTimeoutRef.current)
    }

    loadThreadsTimeoutRef.current = setTimeout(async () => {
      setIsLoadingThreads(true)
      try {
        const result = await api.listThreads(targetAgentId)
        setThreads(result.threads)
      } catch (err) {
        console.error('Failed to load threads:', err)
      } finally {
        setIsLoadingThreads(false)
      }
    }, 100)  // 100ms debounce
  }

  const handleNewThread = async () => {
    if (!selectedAgentId) return
    try {
      // Get agent name for thread title
      const agent = agents.find(a => a.id === selectedAgentId)
      const agentNameSuffix = agent ? ` (${agent.name})` : ''

      const newThread = await api.createThread({
        agent_id: selectedAgentId,
        title: `New Conversation${agentNameSuffix}`
      })

      // Navigate to the new thread immediately
      setActiveThreadId(newThread.id)
      setActiveThread(newThread)
      setMessages([])  // New thread has no messages yet

      // Refresh thread list in background
      await loadThreads()
    } catch (err) {
      console.error('Failed to create thread:', err)
    }
  }

  const handleThreadSelect = async (threadId: number) => {
    // Cancel previous request if still pending
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    abortControllerRef.current = new AbortController()
    const signal = abortControllerRef.current.signal

    setActiveThreadId(threadId)
    setIsLoadingThread(true)
    setThreadLoadError(null)

    if (!selectedAgentId) {
      setIsLoadingThread(false)
      return
    }

    try {
      const threadData = await api.getThread(threadId, { signal })

      // Check if request was aborted
      if (signal.aborted) return

      // Check for error code from backend
      if ((threadData as any).error_code === 'NO_MESSAGES_FOUND') {
        setThreadLoadError((threadData as any).error_message || 'Failed to load conversation history')
        setMessages([])
        setIsLoadingThread(false)
        return
      }

      // Validate messages exist
      if (!threadData.messages || !Array.isArray(threadData.messages)) {
        setThreadLoadError('Invalid response from server')
        setMessages([])
        setIsLoadingThread(false)
        return
      }

      setMessages(threadData.messages)
      // Use the fresh thread data from API, not the stale threads array
      setActiveThread({
        id: threadData.id,
        title: threadData.title,
        folder: threadData.folder,
        status: threadData.status,
        is_archived: threadData.is_archived,
        agent_id: threadData.agent_id,
        recipient: threadData.recipient,  // For Memory Inspector sender_key filtering
        created_at: threadData.created_at,
        updated_at: threadData.updated_at
      })
      setIsLoadingThread(false)
    } catch (err: any) {
      if (err.name === 'AbortError') return  // Ignore aborted requests
      console.error('Failed to load thread:', err)
      setThreadLoadError(err.message || 'Failed to load conversation')
      setMessages([])
      setIsLoadingThread(false)
    }
  }

  const handleThreadDeleted = () => {
    setActiveThreadId(null)
    setMessages([])
    loadThreads()
  }

  const handleThreadUpdated = async () => {
    await loadThreads()
    // Use ref to get current thread ID to avoid closure issues
    const currentThreadId = activeThreadIdRef.current
    if (currentThreadId && selectedAgentId) {
      await handleThreadSelect(currentThreadId)
    }
  }

  // Handle thread rename with optimistic UI update (BUG-PLAYGROUND-001 fix)
  const handleThreadRenamed = useCallback((threadId: number, newTitle: string) => {
    // Update activeThread if this is the current thread
    if (activeThread && activeThread.id === threadId) {
      setActiveThread(prev => prev ? { ...prev, title: newTitle } : null)
    }
    // Also update the threads list
    setThreads(prev => prev.map(t =>
      t.id === threadId ? { ...t, title: newTitle } : t
    ))
  }, [activeThread])

  // Phase 14.1: Load and initialize threads when agent changes
  useEffect(() => {
    // Clear project session and cache IMMEDIATELY when agent changes (synchronous)
    if (selectedAgentId) {
      setProjectSession(null)
      if (user) {
        clearCachedProjectSession(user.id, selectedAgentId)
      }
    }

    const initializeThreads = async () => {
      if (!selectedAgentId) return

      // Exit any active project session when switching agents
      try {
        await api.exitProjectSession(selectedAgentId, 'playground')
        console.log('[Phase 14.1] Exited project session for agent', selectedAgentId)
      } catch (err) {
        // Ignore errors if no active session
        console.log('[Phase 14.1] No active project to exit (or error):', err)
      }

      try {
        console.log('[Phase 14.1] Loading threads for agent', selectedAgentId)
        const result = await api.listThreads(selectedAgentId)
        const agentThreads = result.threads
        console.log('[Phase 14.1] Loaded threads:', agentThreads.length)

        setThreads(agentThreads)

        // Check if the most recent thread is empty (message_count === 0)
        // Sort threads by updated_at to find the most recent one
        const sortedThreads = [...agentThreads].sort((a, b) => {
          const dateA = a.updated_at ? new Date(a.updated_at).getTime() : 0
          const dateB = b.updated_at ? new Date(b.updated_at).getTime() : 0
          return dateB - dateA
        })

        const mostRecentThread = sortedThreads[0]

        if (mostRecentThread && mostRecentThread.message_count === 0) {
          // Reuse the empty thread but update its title to default
          console.log('[Phase 14.1] Reusing empty thread:', mostRecentThread.id)

          // Get agent name for thread title
          const agent = agents.find(a => a.id === selectedAgentId)
          const agentNameSuffix = agent ? ` (${agent.name})` : ''
          const defaultTitle = `General Conversation${agentNameSuffix}`

          // Update thread title to default if it's different
          if (mostRecentThread.title !== defaultTitle) {
            try {
              await api.updateThread(mostRecentThread.id, { title: defaultTitle })
              // Update local thread object with new title
              mostRecentThread.title = defaultTitle
            } catch (err) {
              console.warn('Failed to update thread title:', err)
            }
          }

          setActiveThreadId(mostRecentThread.id)
          setActiveThread(mostRecentThread)
          setMessages([])
        } else {
          // Create a new thread if no empty thread exists
          console.log('[Phase 14.1] Creating new thread for fresh conversation')

          // Get agent name for thread title
          const agent = agents.find(a => a.id === selectedAgentId)
          const agentNameSuffix = agent ? ` (${agent.name})` : ''

          const newThread = await api.createThread({
            agent_id: selectedAgentId,
            title: `General Conversation${agentNameSuffix}`
          })
          console.log('[Phase 14.1] Created thread:', newThread.id)
          setActiveThreadId(newThread.id)
          setActiveThread(newThread)
          setMessages([]) // Start with empty messages for new conversation

          // Refresh thread list to include the newly created thread
          const updatedResult = await api.listThreads(selectedAgentId)
          setThreads(updatedResult.threads)
        }
      } catch (err) {
        console.error('[Phase 14.1] Failed to initialize threads:', err)
      }
    }

    initializeThreads()
  }, [selectedAgentId])

  const handleSendMessage = async () => {
    // ALWAYS read from DOM (works with browser automation)
    const message = inputRef.current?.value?.trim() || ''

    if (!message || !selectedAgentId || isSending) {
      return
    }

    const userMessage = message

    // Store in message history for up arrow recall
    setMessageHistory(prev => [...prev, userMessage])
    setHistoryIndex(-1) // Reset history navigation

    // Clear the textarea
    if (inputRef.current) {
      inputRef.current.value = ''
      inputRef.current.style.height = '52px'
    }

    // Close inline commands if open
    setInlineCommandsOpen(false)
    setInlineQuery('')

    setIsSending(true)
    setError(null)

    // Reset auto-scroll to true when user sends a message
    setAutoScroll(true)

    // Add user message to UI immediately (Phase 14.2: with message_id)
    const messageId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    const userMsg: PlaygroundMessage = {
      role: 'user',
      content: userMessage,
      timestamp: new Date().toISOString(),
      message_id: messageId
    }
    setMessages((prev) => [...prev, userMsg])

    try {
      // Check if this is a slash command
      if (userMessage.startsWith('/')) {
        // Execute as slash command
        const result = await api.executeSlashCommand({
          message: userMessage,
          agent_id: selectedAgentId,
          channel: 'playground',
          thread_id: activeThreadId ?? undefined  // Include thread_id for Layer 5 tool buffer
        })

        // Refresh messages from backend to show slash commands in conversation history
        // This ensures complete conversation history including /inject, /tools, etc.
        if (activeThreadId) {
          const threadData = await api.getThread(activeThreadId)
          setMessages(threadData.messages || [])
        } else {
          // Fallback: Add result to local state (Phase 14.2: with message_id)
          const agentMsgId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
          const agentMsg: PlaygroundMessage = {
            role: 'assistant',
            content: result.message || 'Command executed.',
            timestamp: new Date().toISOString(),
            message_id: agentMsgId
          }
          setMessages((prev) => [...prev, agentMsg])
        }

        // Handle special command actions
        if (result.action === 'project_entered' && result.data) {
          loadProjectSession(selectedAgentId)
        } else if (result.action === 'project_exited') {
          setProjectSession(null)
        } else if (result.action === 'open_memory_manager' && projectSession?.project_id) {
          setIsProjectMemoryOpen(true)
        } else if (result.action === 'switch_agent') {
          // Handle /invoke and /switch commands - agent_id is in result.data from API wrapper
          const agentId = result.data?.agent_id || result.agent_id
          const agentName = result.data?.agent_name || result.agent_name

          if (agentId) {
            setSelectedAgentId(agentId)
            // Clear active thread so new messages go to the switched agent
            // (Threads are agent-specific, so we need a fresh thread for the new agent)
            setActiveThreadId(null)
            setActiveThread(null)
          } else if (agentName) {
            // Fallback to name matching (for backwards compatibility)
            const targetAgent = agents.find(a => a.name.toLowerCase() === agentName.toLowerCase())
            if (targetAgent) {
              setSelectedAgentId(targetAgent.id)
              // Clear active thread for switched agent
              setActiveThreadId(null)
              setActiveThread(null)
            }
          }
        }
      } else {
        // Phase 14.9: Try WebSocket first, fallback to HTTP
        let sentViaWebSocket = false

        if (useWebSocket && websocketConnection.isConnected) {
          console.log('[Playground] Sending via WebSocket')
          sentViaWebSocket = websocketConnection.sendMessage(
            selectedAgentId,
            userMessage,
            activeThreadId || undefined
          )
        }

        if (!sentViaWebSocket) {
          console.log('[Playground] Sending via HTTP (fallback)')

          // Send as regular message to agent with thread isolation (HTTP fallback)
          const response = await api.sendPlaygroundMessage(
            selectedAgentId,
            userMessage,
            activeThreadId || undefined  // Phase 14.1: Thread-specific messaging
          )

          if (response.status === 'success' && response.message) {
          // Phase 14.2 FIX: Refresh messages from backend to get correct message_ids
          // This ensures edit/regenerate operations use the IDs stored in the database
          if (activeThreadId) {
            const threadData = await api.getThread(activeThreadId)
            setMessages(threadData.messages || [])

            // Check if thread was auto-renamed
            if (response.thread_renamed && response.new_thread_title) {
              console.log('[Auto-rename] Thread renamed to:', response.new_thread_title)
              // Update local thread state
              setActiveThread(prev => prev ? { ...prev, title: response.new_thread_title } : null)
              // Refresh thread list to show new title
              handleThreadUpdated()
            }
          } else {
            // Fallback for non-thread messages (legacy behavior)
            const agentMsgId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
            const agentMsg: PlaygroundMessage = {
              role: 'assistant',
              content: response.message,
              timestamp: response.timestamp,
              message_id: agentMsgId
            }
            setMessages((prev) => [...prev, agentMsg])
          }
        } else if (response.error) {
          setError(response.error)
        }
        }
      }
    } catch (err: any) {
      setError(err.message || 'Failed to send message')
    } finally {
      // Only reset sending state if not streaming via WebSocket
      if (!websocketConnection.isStreaming) {
        setIsSending(false)
      }
      // Focus back on input
      inputRef.current?.focus()
    }
  }

  const handleClearHistory = async () => {
    if (!selectedAgentId) return

    if (!confirm('Are you sure you want to clear the conversation history with this agent?')) {
      return
    }

    try {
      await api.clearPlaygroundHistory(selectedAgentId)
      setMessages([])
      setError(null)
    } catch (err: any) {
      setError(err.message || 'Failed to clear history')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Handle Cmd/Ctrl + A for select all
    if ((e.metaKey || e.ctrlKey) && e.key === 'a') {
      // Allow default behavior (select all)
      return
    }

    // Phase 16: Handle message history recall with up/down arrows (when not in command mode)
    if (!inlineCommandsOpen && messageHistory.length > 0) {
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        // Navigate backwards through history
        const newIndex = historyIndex === -1 ? messageHistory.length - 1 : Math.max(0, historyIndex - 1)
        setHistoryIndex(newIndex)
        if (inputRef.current) {
          inputRef.current.value = messageHistory[newIndex]
          // Move cursor to end
          setTimeout(() => {
            if (inputRef.current) {
              inputRef.current.selectionStart = inputRef.current.value.length
              inputRef.current.selectionEnd = inputRef.current.value.length
            }
          }, 0)
        }
        return
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        // Navigate forwards through history
        if (historyIndex === -1) return // Already at the end
        const newIndex = historyIndex + 1
        if (newIndex >= messageHistory.length) {
          // Clear input when going past the end
          setHistoryIndex(-1)
          if (inputRef.current) {
            inputRef.current.value = ''
          }
        } else {
          setHistoryIndex(newIndex)
          if (inputRef.current) {
            inputRef.current.value = messageHistory[newIndex]
            // Move cursor to end
            setTimeout(() => {
              if (inputRef.current) {
                inputRef.current.selectionStart = inputRef.current.value.length
                inputRef.current.selectionEnd = inputRef.current.value.length
              }
            }, 0)
          }
        }
        return
      }
    }

    // Phase 16: Handle inline commands navigation
    if (inlineCommandsOpen) {
      const searchLower = inlineQuery.toLowerCase()
      const isToolSuggestion = searchLower.startsWith('tool ')

      if (isToolSuggestion) {
        // Handle tool suggestions
        const afterTool = searchLower.replace(/^tool\s+/, '')
        const filteredTools = availableTools.filter(tool =>
          tool.toLowerCase().startsWith(afterTool)
        ).slice(0, 8)

        if (e.key === 'ArrowDown') {
          e.preventDefault()
          setInlineSelectedIndex(prev => Math.min(prev + 1, filteredTools.length - 1))
          return
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault()
          setInlineSelectedIndex(prev => Math.max(prev - 1, 0))
          return
        }
        if (e.key === 'Tab' || (e.key === 'Enter' && filteredTools.length > 0)) {
          e.preventDefault()
          if (filteredTools[inlineSelectedIndex]) {
            // Dispatch custom event for consistency with other commands
            const event = new CustomEvent('tool-selected', { detail: filteredTools[inlineSelectedIndex] })
            window.dispatchEvent(event)
          }
          return
        }
      } else {
        // Handle command suggestions - apply same logic as /tool for consistency
        const hasSpace = searchLower.includes(' ')
        const baseCommand = searchLower.split(' ')[0]

        // Check what kind of suggestions we should show based on the command
        const isInvokeSuggestion = (baseCommand === 'invoke' || baseCommand === 'switch') && hasSpace
        const isInjectSuggestion = baseCommand === 'inject' && hasSpace

        // For invoke/inject with arguments, handle like /tool command
        if (isInvokeSuggestion || isInjectSuggestion) {
          // Get the filtered suggestions
          const afterCommand = isInvokeSuggestion ?
            searchLower.replace(/^(invoke|switch)\s+/, '') :
            searchLower.replace(/^inject\s+/, '')
          const suggestions = isInvokeSuggestion ?
            availableAgents.filter(a => a.toLowerCase().startsWith(afterCommand)).slice(0, 8) :
            injectTargets.filter(t => t.toLowerCase().startsWith(afterCommand)).slice(0, 8)

          if (e.key === 'ArrowDown') {
            e.preventDefault()
            setInlineSelectedIndex(prev => Math.min(prev + 1, suggestions.length - 1))
            return
          }
          if (e.key === 'ArrowUp') {
            e.preventDefault()
            setInlineSelectedIndex(prev => Math.max(prev - 1, 0))
            return
          }
          // For Tab or Enter - dispatch the custom event to trigger completion
          if (e.key === 'Tab' || (e.key === 'Enter' && suggestions.length > 0)) {
            e.preventDefault()
            if (suggestions[inlineSelectedIndex]) {
              // Dispatch the appropriate custom event
              const eventName = isInvokeSuggestion ? 'agent-selected' : 'inject-selected'
              const event = new CustomEvent(eventName, { detail: suggestions[inlineSelectedIndex] })
              window.dispatchEvent(event)
            }
            return
          }
        } else {
          // For regular command suggestions (no arguments yet, or subcommands)
          let filteredCommands

          if (hasSpace) {
            // For other commands with space, check for subcommands
            filteredCommands = slashCommands.filter(cmd => {
              const cmdName = cmd.command_name.toLowerCase()
              // Only show commands that start with the base command and have more after it
              if (!cmdName.startsWith(baseCommand)) return false
              // Check if this is a subcommand (has more text after the base command)
              const afterBase = cmdName.slice(baseCommand.length).trim()
              return afterBase.length > 0
            }).slice(0, 8)
          } else {
            // No space - show matching commands
            filteredCommands = slashCommands.filter(cmd =>
              cmd.command_name.toLowerCase().startsWith(searchLower) ||
              cmd.aliases.some(a => a.toLowerCase().startsWith(searchLower))
            ).slice(0, 8)
          }

          // Arrow key navigation
          if (e.key === 'ArrowDown') {
            e.preventDefault()
            setInlineSelectedIndex(prev => Math.min(prev + 1, filteredCommands.length - 1))
            return
          }
          if (e.key === 'ArrowUp') {
            e.preventDefault()
            setInlineSelectedIndex(prev => Math.max(prev - 1, 0))
            return
          }

          // Tab or Enter - ONLY intercept if there are actual command suggestions
          if (e.key === 'Tab' || (e.key === 'Enter' && filteredCommands.length > 0)) {
            e.preventDefault()
            if (filteredCommands[inlineSelectedIndex]) {
              handleInlineCommandSelect(filteredCommands[inlineSelectedIndex])
            }
            return
          }
        }

        // If Enter with no suggestions, don't prevent default - let it send the message
      }

      if (e.key === 'Escape') {
        e.preventDefault()
        setInlineCommandsOpen(false)
        return
      }
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendMessage()
    }
  }

  const handleTextareaResize = (e: React.FormEvent<HTMLTextAreaElement>) => {
    const target = e.currentTarget
    target.style.height = 'auto'
    target.style.height = Math.min(target.scrollHeight, 200) + 'px'
  }

  // Phase 16: Handle input change for slash command detection
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value

    // Detect slash command input
    if (value.startsWith('/')) {
      const query = value.slice(1) // Get everything after /
      setInlineQuery(query)
      setInlineCommandsOpen(true)
      setInlineSelectedIndex(0)

      // Parse command to detect base command
      const baseCommand = query.split(/\s+/)[0].toLowerCase()
      const hasSpace = query.includes(' ')

      // Fetch suggestions based on command type
      if (baseCommand === 'tool' && hasSpace && selectedAgentId && availableTools.length === 0) {
        fetchAvailableTools(selectedAgentId)
      }

      if ((baseCommand === 'invoke' || baseCommand === 'switch') && hasSpace && availableAgents.length === 0) {
        fetchAvailableAgents()
      }

      if (baseCommand === 'inject' && hasSpace && injectTargets.length === 0) {
        fetchInjectTargets()
      }
    } else {
      setInlineCommandsOpen(false)
      setInlineQuery('')
    }
  }

  // Fetch available tools for the current agent
  const fetchAvailableTools = async (agentId: number) => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8081'}/api/playground/tools/${agentId}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('tsushin_auth_token')}`
        }
      })

      if (response.ok) {
        const tools = await response.json()
        const toolNames = tools.map((tool: any) => tool.name)
        setAvailableTools(toolNames)
      }
    } catch (error) {
      console.error('Failed to fetch available tools:', error)
    }
  }

  // Fetch available agents for invoke/switch commands
  const fetchAvailableAgents = async () => {
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8081'}/api/playground/agents`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('tsushin_auth_token')}`
        }
      })

      if (response.ok) {
        const agentsData = await response.json()
        const agentNames = agentsData.map((agent: any) => agent.name)
        setAvailableAgents(agentNames)
      }
    } catch (error) {
      console.error('Failed to fetch available agents:', error)
    }
  }

  // Fetch inject targets for inject command
  const fetchInjectTargets = async () => {
    try {
      // For now, provide basic options
      // In future, can fetch from tool buffer API
      const targets = ['list', 'clear']
      setInjectTargets(targets)
    } catch (error) {
      console.error('Failed to fetch inject targets:', error)
    }
  }

  // Phase 16: Handle command selection from palette or inline
  const handleCommandSelect = async (command: SlashCommand, args?: string) => {
    if (!selectedAgentId) return

    setError(null)

    // Build the full command string
    const fullCommand = args ? `/${command.command_name} ${args}` : `/${command.command_name}`

    // Add command to messages as user input
    const userMsg: PlaygroundMessage = {
      role: 'user',
      content: fullCommand,
      timestamp: new Date().toISOString(),
      message_id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    }
    setMessages(prev => [...prev, userMsg])

    try {
      // Execute the command via API
      const result = await api.executeSlashCommand({
        message: fullCommand,
        agent_id: selectedAgentId,
        channel: 'playground',
        thread_id: activeThreadId ?? undefined  // Include thread_id for Layer 5 tool buffer
      })

      // Add result to messages
      const agentMsg: PlaygroundMessage = {
        role: 'assistant',
        content: result.message || `Command /${command.command_name} executed.`,
        timestamp: new Date().toISOString(),
        message_id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
      }
      setMessages(prev => [...prev, agentMsg])

      // Handle special command actions
      if (result.action === 'project_entered' && result.data) {
        // Refresh project session
        loadProjectSession(selectedAgentId)
      } else if (result.action === 'project_exited') {
        setProjectSession(null)
      } else if (result.action === 'open_memory_manager' && projectSession?.project_id) {
        setIsProjectMemoryOpen(true)
      }
    } catch (err: any) {
      setError(err.message || 'Failed to execute command')
    }

    // Clear input
    if (inputRef.current) {
      inputRef.current.value = ''
      inputRef.current.style.height = '52px'
    }
    setInlineCommandsOpen(false)
    setInlineQuery('')
  }

  // Phase 16: Handle inline command selection
  const handleInlineCommandSelect = (command: SlashCommand) => {
    if (inputRef.current) {
      // Replace input with full command, ready for args
      inputRef.current.value = `/${command.command_name} `
      inputRef.current.focus()
    }
    setInlineCommandsOpen(false)
    setInlineQuery('')
  }

  // Handle tool selection from InlineCommands
  useEffect(() => {
    const handleToolSelected = (e: any) => {
      const toolName = e.detail
      if (inputRef.current) {
        inputRef.current.value = `/tool ${toolName} `
        inputRef.current.focus()
      }
      setInlineCommandsOpen(false)
      setInlineQuery('')
    }

    const handleAgentSelected = (e: any) => {
      const agentName = e.detail
      if (inputRef.current) {
        const currentValue = inputRef.current.value
        const baseCommand = currentValue.split(' ')[0]
        inputRef.current.value = `${baseCommand} ${agentName} `
        inputRef.current.focus()
      }
      setInlineCommandsOpen(false)
      setInlineQuery('')
    }

    const handleInjectSelected = (e: any) => {
      const target = e.detail
      if (inputRef.current) {
        inputRef.current.value = `/inject ${target} `
        inputRef.current.focus()
      }
      setInlineCommandsOpen(false)
      setInlineQuery('')
    }

    window.addEventListener('tool-selected', handleToolSelected)
    window.addEventListener('agent-selected', handleAgentSelected)
    window.addEventListener('inject-selected', handleInjectSelected)

    return () => {
      window.removeEventListener('tool-selected', handleToolSelected)
      window.removeEventListener('agent-selected', handleAgentSelected)
      window.removeEventListener('inject-selected', handleInjectSelected)
    }
  }, [])

  const formatTimestamp = (timestamp: string) => formatTime(timestamp)

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <div className="relative w-16 h-16 mx-auto mb-4">
            <div className="absolute inset-0 rounded-full border-4 border-tsushin-surface"></div>
            <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-tsushin-indigo animate-spin"></div>
            <div className="absolute inset-2 rounded-full border-4 border-transparent border-t-tsushin-accent animate-spin" style={{ animationDirection: 'reverse', animationDuration: '1.5s' }}></div>
          </div>
          <p className="text-tsushin-slate font-medium">Loading Playground...</p>
        </div>
      </div>
    )
  }

  // Handler for tool selection in cockpit mode
  const handleToolSelect = (toolName: string) => {
    if (inputRef.current) {
      inputRef.current.value = `/tool ${toolName} `
      inputRef.current.focus()
    }
  }

  // Handler for project selection in cockpit mode - toggle enter/exit
  const handleProjectSelect = async (projectId: number) => {
    const project = projects.find(p => p.id === projectId)
    if (!project || !selectedAgentId || !user) return

    // Start timing the entire operation
    const timerId = `project-switch-${projectId}`
    console.time(timerId)
    console.log(`[TIMING] Project switch started at: ${performance.now()}ms`)

    try {
      // Check cached session instantly (no waiting)
      const cachedSession = getCachedProjectSession(user.id, selectedAgentId)

      // Check if clicking on currently active project (exit behavior)
      const isInThisProject = cachedSession?.is_in_project &&
        Number(cachedSession?.project_id) === Number(projectId)

      if (isInThisProject) {
        console.log('[PROJECT SWITCH] Exiting current project optimistically')
        // Optimistic update: immediately clear banner
        setProjectSession(null)
        clearCachedProjectSession(user.id, selectedAgentId)

        console.log(`[TIMING] Banner cleared at: ${performance.now()}ms`)
        console.timeEnd(timerId)

        // Show optimistic message
        const exitMsg: PlaygroundMessage = {
          role: 'assistant',
          content: `✅ Left project "${project.name}".`,
          timestamp: new Date().toISOString(),
          message_id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
        }
        setMessages(prev => [...prev, exitMsg])

        // Exit in background
        api.exitProjectSession(selectedAgentId, 'playground').catch(err => {
          console.error('Failed to exit project:', err)
          loadProjectSession(selectedAgentId)
        })
        return
      }

      console.log('[PROJECT SWITCH] Switching to project:', project.name, 'optimistically')
      console.log(`[TIMING] setProjectSession called at: ${performance.now()}ms`)

      // Optimistic update: IMMEDIATELY show new project banner (no waiting!)
      const optimisticSession: ProjectSession = {
        session_id: null,
        project_id: projectId,
        project_name: project.name,
        agent_id: selectedAgentId,
        channel: 'playground',
        conversation_id: null,
        entered_at: new Date().toISOString(),
        is_in_project: true
      }
      setProjectSession(optimisticSession)
      setIsLoadingProjectSession(true)

      console.log(`[TIMING] Banner state updated at: ${performance.now()}ms`)
      console.timeEnd(timerId)

      // Everything else happens in the background (non-blocking)
      ;(async () => {
        try {
          const bgStartTime = performance.now()
          console.log(`[TIMING] Background sync started at: ${bgStartTime}ms`)

          // Check actual current session in background
          const currentSession = await api.getProjectSession(selectedAgentId, 'playground')
          console.log(`[TIMING] Got current session at: ${performance.now()}ms`)

          // If in a different project, exit first
          if (currentSession?.is_in_project && Number(currentSession?.project_id) !== Number(projectId)) {
            await api.exitProjectSession(selectedAgentId, 'playground')
            console.log(`[TIMING] Exited old project at: ${performance.now()}ms`)
          }

          // Use direct API instead of slash command (much faster!)
          console.log(`[TIMING] Calling enterProjectSession API at: ${performance.now()}ms`)
          const enterResult = await api.enterProjectSession({
            project_id: projectId,
            project_name: project.name,
            agent_id: selectedAgentId,
            channel: 'playground'
          })
          console.log(`[TIMING] Enter API completed at: ${performance.now()}ms`)

          // Update with actual session data from enter response
          setProjectSession(enterResult)
          setCachedProjectSession(user.id, selectedAgentId, enterResult)
          setIsLoadingProjectSession(false)

          console.log(`[TIMING] Background sync completed in ${performance.now() - bgStartTime}ms`)

          const agentMsg: PlaygroundMessage = {
            role: 'assistant',
            content: `✅ Entered project "${project.name}"`,
            timestamp: new Date().toISOString(),
            message_id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
          }
          setMessages(prev => [...prev, agentMsg])
        } catch (err: any) {
          console.error('[PROJECT SWITCH] Background operation failed:', err)
          setError(err.message || 'Failed to enter/exit project')
          setIsLoadingProjectSession(false)
          // Reload actual state on error
          loadProjectSession(selectedAgentId)
        }
      })()

    } catch (err: any) {
      setError(err.message || 'Failed to enter/exit project')
      setIsLoadingProjectSession(false)
      if (user && selectedAgentId) {
        loadProjectSession(selectedAgentId)
      }
    }
  }

  // Context stats for cockpit mode
  const contextStats = {
    working_memory: messages.length,
    semantic_memory: 0,
    facts: 0,
    last_tool: undefined
  }

  // Render the full-featured playground interface
  return (
    <div className="h-full w-full overflow-hidden">
      <ExpertMode
        agents={agents}
        projects={projects}
        selectedAgentId={selectedAgentId}
        agentName={agentName}
        messages={messages}
        isSending={isSending || websocketConnection.isStreaming}
        isLoadingHistory={isLoadingHistory}
        projectSession={projectSession}
        isLoadingProjectSession={isLoadingProjectSession}
        slashCommands={slashCommands}
        error={error}
        // Phase 14.9: WebSocket streaming props
        streamingMessage={streamingMessage}
        connectionState={websocketConnection.connectionState}
        onAgentSelect={setSelectedAgentId}
        onProjectSelect={handleProjectSelect}
        onSendMessage={handleSendMessage}
        onClearHistory={handleClearHistory}
        onExitProject={handleExitProject}
        onToolSelect={handleToolSelect}
        inputRef={inputRef}
        onInputChange={handleInputChange}
        onKeyDown={handleKeyDown}
        inlineCommandsOpen={inlineCommandsOpen}
        inlineQuery={inlineQuery}
        inlineSelectedIndex={inlineSelectedIndex}
        onInlineCommandSelect={handleInlineCommandSelect}
        onCloseInlineCommands={() => setInlineCommandsOpen(false)}
        onNavigateInlineCommands={(dir) => setInlineSelectedIndex(prev =>
          dir === 'up' ? Math.max(prev - 1, 0) : Math.min(prev + 1, 7)
        )}
        availableTools={availableTools}
        availableAgents={availableAgents}
        injectTargets={injectTargets}
        // Audio recording props
        audioCapabilities={audioCapabilities}
        isRecording={isRecording}
        recordingTime={recordingTime}
        audioBlob={audioBlob}
        audioUrl={audioUrl}
        onStartRecording={startRecording}
        onStopRecording={stopRecording}
        onCancelRecording={cancelRecording}
        onSendAudio={sendAudioMessage}
        isProcessingAudio={isProcessingAudio}
        // File upload props
        fileInputRef={fileInputRef}
        onFileUpload={(files: FileList) => {
          handleQuickFileUpload(files)
          setIsDocumentPanelOpen(true)
        }}
        documentsCount={documents.length}
        // Phase 14.1 & 14.2: Thread Management props
        threads={threads}
        activeThreadId={activeThreadId}
        activeThread={activeThread}
        showThreadSidebar={showThreadSidebar}
        isLoadingThreads={isLoadingThreads}
        isLoadingThread={isLoadingThread}
        threadLoadError={threadLoadError}
        onNewThread={handleNewThread}
        onThreadSelect={handleThreadSelect}
        onThreadDeleted={handleThreadDeleted}
        onThreadUpdated={handleThreadUpdated}
        onThreadRenamed={handleThreadRenamed}
        onToggleThreadSidebar={() => setShowThreadSidebar(!showThreadSidebar)}
        // Phase 14.5 & 14.6: Search and Knowledge props
        onOpenSearch={() => setIsSearchOpen(true)}
        onExtractKnowledge={() => setIsKnowledgePanelOpen(true)}
      />

      {/* Modals */}
      {selectedAgentId && (
        <DocumentPanel
          agentId={selectedAgentId}
          documents={documents}
          onDocumentsChange={loadDocuments}
          isOpen={isDocumentPanelOpen}
          onClose={() => setIsDocumentPanelOpen(false)}
        />
      )}
      <PlaygroundSettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        onSettingsChange={setPlaygroundSettings}
      />
      <CommandPalette
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
        onCommandSelect={handleCommandSelect}
        commands={slashCommands}
        agents={agents}
        projects={projects}
      />
      {projectSession?.project_id && (
        <ProjectMemoryManager
          projectId={projectSession.project_id}
          projectName={projectSession.project_name || 'Project'}
          isOpen={isProjectMemoryOpen}
          onClose={() => setIsProjectMemoryOpen(false)}
        />
      )}

      {/* Phase 14.5: Search Modal */}
      {isSearchOpen && (
        <div className={`fixed inset-0 z-50 ${isSearchCollapsed && searchResults.length > 0 ? '' : 'bg-black/30'}`}>
          <SearchBar
            onSearch={handleSearch}
            onClose={() => {
              setIsSearchOpen(false)
              setIsSearchCollapsed(false)
              setSearchResults([])
            }}
            collapsed={isSearchCollapsed && searchResults.length > 0}
            onExpand={() => setIsSearchCollapsed(false)}
            currentQuery={searchQuery}
            currentMode={searchMode}
            resultCount={searchResults.length}
          />
          {searchResults.length > 0 && (
            <div className={`fixed inset-x-0 ${isSearchCollapsed ? 'top-20' : 'top-72'} bottom-0 z-[60] overflow-y-auto transition-all duration-200 bg-tsushin-ink`}>
              <div className="max-w-4xl mx-auto px-4 py-4">
                <SearchResults
                  results={searchResults}
                  total={searchResults.length}
                  searchMode={searchMode}
                  query={searchQuery}
                  onResultClick={handleSearchResultClick}
                  isLoading={isSearching}
                />
              </div>
            </div>
          )}
        </div>
      )}

      {/* Phase 14.6: Knowledge Panel */}
      {isKnowledgePanelOpen && selectedAgentId && activeThreadId && (
        <KnowledgePanel
          threadId={activeThreadId}
          agentId={selectedAgentId}
          onClose={() => setIsKnowledgePanelOpen(false)}
        />
      )}
    </div>
  )
}
