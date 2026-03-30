/**
 * Custom Hook for Watcher Activity WebSocket (Phase 8)
 *
 * Manages WebSocket connection for real-time activity updates in Graph View.
 * Receives agent processing events, skill usage events, and KB usage events.
 *
 * Uses a processing-session model: the agent processing lifecycle (start/end)
 * governs when ALL related nodes (channel, agent, skill, KB) glow together.
 */

import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import type { A2ASessionInfo } from '@/components/watcher/graph/types'

export type ActivityConnectionState = 'disconnected' | 'connecting' | 'authenticating' | 'connected' | 'error'

// Activity event types from backend
interface AgentProcessingEvent {
  type: 'agent_processing'
  agent_id: number
  status: 'start' | 'end'
  sender_key?: string
  channel?: string
  timestamp: string
}

interface SkillUsedEvent {
  type: 'skill_used'
  agent_id: number
  skill_type: string
  skill_name: string
  timestamp: string
}

interface KbUsedEvent {
  type: 'kb_used'
  agent_id: number
  doc_count: number
  chunk_count: number
  timestamp: string
}

// A2A communication event — emitted at session start and end
interface AgentCommunicationEvent {
  type: 'agent_communication'
  initiator_agent_id: number
  target_agent_id: number
  session_id: number
  status: 'start' | 'end'
  session_type: 'ask' | 'delegate'
  depth: number
  timestamp: string
}

type ActivityEvent = AgentProcessingEvent | SkillUsedEvent | KbUsedEvent | AgentCommunicationEvent

// Skill usage info for UI
export interface SkillUseInfo {
  skillType: string
  skillName: string
  timestamp: number
}

// KB usage info for UI
export interface KbUseInfo {
  docCount: number
  chunkCount: number
  timestamp: number
}

// Processing session: ties channel, skill, and KB activity to agent processing lifecycle
interface ProcessingSession {
  agentId: number
  channel: string | null
  startTime: number
  skillUsed: SkillUseInfo | null
  kbUsed: KbUseInfo | null
  isEnding: boolean  // true during post-processing coordinated fade-out
}

interface UseWatcherActivityOptions {
  enabled: boolean
  onConnectionStateChange?: (state: ActivityConnectionState) => void
}

interface UseWatcherActivityReturn {
  connectionState: ActivityConnectionState
  processingAgents: Set<number>
  activeChannels: Set<string>
  recentSkillUse: Map<number, SkillUseInfo>
  recentKbUse: Map<number, KbUseInfo>
  fadingAgents: Set<number>
  fadingChannels: Set<string>
  isConnected: boolean
  // A2A real-time session tracking
  activeA2ASessions: Map<string, A2ASessionInfo>
  fadingA2ASessions: Set<string>
  agentA2ADepths: Map<number, number>
}

/**
 * Hook for receiving real-time activity events from the Watcher Activity WebSocket.
 *
 * @param token - JWT auth token
 * @param options - Configuration options
 * @returns Activity state for Graph View
 */
export function useWatcherActivity(
  token: string | null,
  options: UseWatcherActivityOptions
): UseWatcherActivityReturn {
  const [connectionState, setConnectionState] = useState<ActivityConnectionState>('disconnected')
  const [processingAgents, setProcessingAgents] = useState<Set<number>>(new Set())
  // Session-based tracking: all activity tied to agent processing lifecycle
  const [processingSessions, setProcessingSessions] = useState<Map<number, ProcessingSession>>(new Map())

  // A2A session tracking
  const [a2aSessions, setA2aSessions] = useState<Map<string, A2ASessionInfo>>(new Map())
  const [fadingA2ASessions, setFadingA2ASessions] = useState<Set<string>>(new Set())

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const maxReconnectAttempts = 5
  const pingIntervalMs = 30000 // 30 seconds

  // Timeout refs
  const processingTimeoutRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map())
  const sessionFadeTimeoutRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map())
  const a2aFadeTimeoutRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())
  const a2aStartTimeRef = useRef<Map<string, number>>(new Map())

  const PROCESSING_TIMEOUT = 30000 // 30 seconds safety timeout
  const MIN_AGENT_GLOW_DURATION = 5000 // Minimum visible glow for fast operations
  const POST_PROCESSING_FADE_DURATION = 3000 // Coordinated fade-out after processing ends

  // Track when each agent started processing (for minimum glow duration)
  const agentStartTimeRef = useRef<Map<number, number>>(new Map())

  // Derive activeChannels from processing sessions
  const activeChannels = useMemo(() => {
    const channels = new Set<string>()
    processingSessions.forEach(session => {
      if (session.channel) channels.add(session.channel)
    })
    return channels
  }, [processingSessions])

  // Derive recentSkillUse from processing sessions
  const recentSkillUse = useMemo(() => {
    const map = new Map<number, SkillUseInfo>()
    processingSessions.forEach((session, agentId) => {
      if (session.skillUsed) map.set(agentId, session.skillUsed)
    })
    return map
  }, [processingSessions])

  // Derive recentKbUse from processing sessions
  const recentKbUse = useMemo(() => {
    const map = new Map<number, KbUseInfo>()
    processingSessions.forEach((session, agentId) => {
      if (session.kbUsed) map.set(agentId, session.kbUsed)
    })
    return map
  }, [processingSessions])

  // Derive fadingAgents from processing sessions
  const fadingAgents = useMemo(() => {
    const set = new Set<number>()
    processingSessions.forEach((session, agentId) => {
      if (session.isEnding) set.add(agentId)
    })
    return set
  }, [processingSessions])

  // Derive fadingChannels from processing sessions
  const fadingChannels = useMemo(() => {
    const channels = new Set<string>()
    processingSessions.forEach(session => {
      if (session.isEnding && session.channel) channels.add(session.channel)
    })
    return channels
  }, [processingSessions])

  // Derive max A2A depth per agent from active sessions (for depth badge on agent nodes)
  const agentA2ADepths = useMemo(() => {
    const map = new Map<number, number>()
    a2aSessions.forEach(session => {
      const existingInit = map.get(session.initiatorId) ?? 0
      if (session.depth > existingInit) map.set(session.initiatorId, session.depth)
      const existingTarget = map.get(session.targetId) ?? 0
      if (session.depth > existingTarget) map.set(session.targetId, session.depth)
    })
    return map
  }, [a2aSessions])

  const getWebSocketUrl = useCallback(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8081'
    const wsProtocol = apiUrl.startsWith('https') ? 'wss' : 'ws'
    const host = apiUrl.replace(/^https?:\/\//, '').replace(/\/$/, '')
    return `${wsProtocol}://${host}/ws/watcher/activity`
  }, [])

  const updateConnectionState = useCallback((state: ActivityConnectionState) => {
    setConnectionState(state)
    options.onConnectionStateChange?.(state)
  }, [options])

  const clearAllTimeouts = useCallback(() => {
    processingTimeoutRef.current.forEach(timeout => clearTimeout(timeout))
    processingTimeoutRef.current.clear()
    sessionFadeTimeoutRef.current.forEach(timeout => clearTimeout(timeout))
    sessionFadeTimeoutRef.current.clear()
    a2aFadeTimeoutRef.current.forEach(timeout => clearTimeout(timeout))
    a2aFadeTimeoutRef.current.clear()
  }, [])

  // Start coordinated fade-out for an agent's entire processing chain
  const startCoordinatedFadeOut = useCallback((agentId: number) => {
    // Remove agent from processingAgents (stops infinite pulse)
    setProcessingAgents(prev => {
      const next = new Set(prev)
      next.delete(agentId)
      return next
    })

    // Mark session as ending (triggers CSS fade-out classes on all nodes)
    setProcessingSessions(prev => {
      const next = new Map(prev)
      const session = next.get(agentId)
      if (session) {
        next.set(agentId, { ...session, isEnding: true })
      }
      return next
    })

    // After fade-out animation completes, remove the session entirely
    const cleanupTimeout = setTimeout(() => {
      setProcessingSessions(prev => {
        const next = new Map(prev)
        next.delete(agentId)
        return next
      })
      agentStartTimeRef.current.delete(agentId)
      sessionFadeTimeoutRef.current.delete(agentId)
    }, POST_PROCESSING_FADE_DURATION)

    sessionFadeTimeoutRef.current.set(agentId, cleanupTimeout)
  }, [])

  const handleMessage = useCallback((data: any) => {
    // Handle authentication response
    if (data.type === 'authenticated') {
      console.log('[WatcherActivity] Authenticated for tenant:', data.tenant_id)
      updateConnectionState('connected')
      reconnectAttemptsRef.current = 0
      return
    }

    if (data.type === 'error') {
      console.error('[WatcherActivity] Error:', data.message)
      updateConnectionState('error')
      return
    }

    if (data.type === 'pong') {
      // Ping-pong heartbeat response
      return
    }

    // Handle activity events
    if (data.type === 'agent_processing') {
      const event = data as AgentProcessingEvent


      if (event.status === 'start') {
        agentStartTimeRef.current.set(event.agent_id, Date.now())

        // Clear any existing fade timeout (new processing started during fade-out)
        const existingFade = sessionFadeTimeoutRef.current.get(event.agent_id)
        if (existingFade) {
          clearTimeout(existingFade)
          sessionFadeTimeoutRef.current.delete(event.agent_id)
        }

        setProcessingAgents(prev => {
          const next = new Set(prev)
          next.add(event.agent_id)
          return next
        })

        // Create processing session with channel
        setProcessingSessions(prev => {
          const next = new Map(prev)
          next.set(event.agent_id, {
            agentId: event.agent_id,
            channel: event.channel || null,
            startTime: Date.now(),
            skillUsed: null,
            kbUsed: null,
            isEnding: false
          })
          return next
        })

        // Set safety timeout to clear processing state
        const existingTimeout = processingTimeoutRef.current.get(event.agent_id)
        if (existingTimeout) clearTimeout(existingTimeout)

        const timeout = setTimeout(() => {
          // Safety: force clear everything after 30 seconds
          setProcessingAgents(p => {
            const n = new Set(p)
            n.delete(event.agent_id)
            return n
          })
          setProcessingSessions(p => {
            const n = new Map(p)
            n.delete(event.agent_id)
            return n
          })
          processingTimeoutRef.current.delete(event.agent_id)
          agentStartTimeRef.current.delete(event.agent_id)
        }, PROCESSING_TIMEOUT)
        processingTimeoutRef.current.set(event.agent_id, timeout)
      } else {
        // status === 'end'
        // Clear any safety timeout
        const existingTimeout = processingTimeoutRef.current.get(event.agent_id)
        if (existingTimeout) {
          clearTimeout(existingTimeout)
          processingTimeoutRef.current.delete(event.agent_id)
        }

        // Enforce minimum glow duration for fast operations
        const startTime = agentStartTimeRef.current.get(event.agent_id)
        const elapsed = startTime ? Date.now() - startTime : MIN_AGENT_GLOW_DURATION
        const remaining = Math.max(0, MIN_AGENT_GLOW_DURATION - elapsed)

        if (remaining > 0) {
          // Delay the coordinated fade-out so glow stays visible
          const delayTimeout = setTimeout(() => {
            startCoordinatedFadeOut(event.agent_id)
          }, remaining)
          processingTimeoutRef.current.set(event.agent_id, delayTimeout)
        } else {
          startCoordinatedFadeOut(event.agent_id)
        }
      }
    }

    if (data.type === 'skill_used') {
      const event = data as SkillUsedEvent


      // Update the processing session with skill info (no independent timer)
      setProcessingSessions(prev => {
        const next = new Map(prev)
        const session = next.get(event.agent_id)
        if (session) {
          next.set(event.agent_id, {
            ...session,
            skillUsed: {
              skillType: event.skill_type,
              skillName: event.skill_name,
              timestamp: Date.now()
            }
          })
        } else {
          // Edge case: skill event arrived without a processing session
          // Create a temporary session that will fade out
          next.set(event.agent_id, {
            agentId: event.agent_id,
            channel: null,
            startTime: Date.now(),
            skillUsed: {
              skillType: event.skill_type,
              skillName: event.skill_name,
              timestamp: Date.now()
            },
            kbUsed: null,
            isEnding: false
          })
          // Auto-fade this orphan session after a short delay
          const fadeTimeout = setTimeout(() => {
            startCoordinatedFadeOut(event.agent_id)
          }, MIN_AGENT_GLOW_DURATION)
          sessionFadeTimeoutRef.current.set(event.agent_id, fadeTimeout)
        }
        return next
      })
    }

    if (data.type === 'kb_used') {
      const event = data as KbUsedEvent


      // Update the processing session with KB info (no independent timer)
      setProcessingSessions(prev => {
        const next = new Map(prev)
        const session = next.get(event.agent_id)
        if (session) {
          next.set(event.agent_id, {
            ...session,
            kbUsed: {
              docCount: event.doc_count,
              chunkCount: event.chunk_count,
              timestamp: Date.now()
            }
          })
        } else {
          // Edge case: KB event arrived without a processing session
          next.set(event.agent_id, {
            agentId: event.agent_id,
            channel: null,
            startTime: Date.now(),
            skillUsed: null,
            kbUsed: {
              docCount: event.doc_count,
              chunkCount: event.chunk_count,
              timestamp: Date.now()
            },
            isEnding: false
          })
          const fadeTimeout = setTimeout(() => {
            startCoordinatedFadeOut(event.agent_id)
          }, MIN_AGENT_GLOW_DURATION)
          sessionFadeTimeoutRef.current.set(event.agent_id, fadeTimeout)
        }
        return next
      })
    }

    if (data.type === 'agent_communication') {
      const event = data as AgentCommunicationEvent
      const sessionKey = String(event.session_id)

      if (event.status === 'start') {
        a2aStartTimeRef.current.set(sessionKey, Date.now())

        // Cancel any pending fade for this session (re-used session_id edge case)
        const existingFade = a2aFadeTimeoutRef.current.get(sessionKey)
        if (existingFade) {
          clearTimeout(existingFade)
          a2aFadeTimeoutRef.current.delete(sessionKey)
        }

        setA2aSessions(prev => {
          const next = new Map(prev)
          next.set(sessionKey, {
            initiatorId: event.initiator_agent_id,
            targetId: event.target_agent_id,
            sessionType: event.session_type,
            depth: event.depth,
            startTime: Date.now(),
          })
          return next
        })
        setFadingA2ASessions(prev => {
          const next = new Set(prev)
          next.delete(sessionKey)
          return next
        })
      } else {
        // status === 'end': enforce minimum glow duration then fade
        const startTime = a2aStartTimeRef.current.get(sessionKey)
        const elapsed = startTime ? Date.now() - startTime : MIN_AGENT_GLOW_DURATION
        const remaining = Math.max(0, MIN_AGENT_GLOW_DURATION - elapsed)

        const startA2AFadeOut = () => {
          setFadingA2ASessions(prev => { const n = new Set(prev); n.add(sessionKey); return n })
          const cleanupTimeout = setTimeout(() => {
            setA2aSessions(prev => { const n = new Map(prev); n.delete(sessionKey); return n })
            setFadingA2ASessions(prev => { const n = new Set(prev); n.delete(sessionKey); return n })
            a2aStartTimeRef.current.delete(sessionKey)
            a2aFadeTimeoutRef.current.delete(sessionKey)
          }, POST_PROCESSING_FADE_DURATION)
          a2aFadeTimeoutRef.current.set(sessionKey, cleanupTimeout)
        }

        if (remaining > 0) {
          const delayTimeout = setTimeout(startA2AFadeOut, remaining)
          a2aFadeTimeoutRef.current.set(sessionKey, delayTimeout)
        } else {
          startA2AFadeOut()
        }
      }
    }
  }, [updateConnectionState, startCoordinatedFadeOut])

  const connect = useCallback(() => {
    if (!token || !options.enabled) {
      console.log('[WatcherActivity] Skipping connect - token:', !!token, 'enabled:', options.enabled)
      return
    }

    if (typeof WebSocket === 'undefined') {
      console.warn('[WatcherActivity] WebSocket not available (SSR)')
      return
    }

    if (wsRef.current?.readyState === WebSocket.OPEN ||
        wsRef.current?.readyState === WebSocket.CONNECTING) {
      console.log('[WatcherActivity] Already connecting/connected')
      return
    }

    updateConnectionState('connecting')

    try {
      const url = getWebSocketUrl()
      console.log('[WatcherActivity] Connecting to:', url)

      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        console.log('[WatcherActivity] Connection established, authenticating...')
        updateConnectionState('authenticating')

        // Send auth message with token
        ws.send(JSON.stringify({
          type: 'auth',
          token
        }))

        // Start ping interval
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current)
        }
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }))
          }
        }, pingIntervalMs)
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          handleMessage(data)
        } catch (err) {
          console.error('[WatcherActivity] Failed to parse message:', err)
        }
      }

      ws.onerror = (error) => {
        console.error('[WatcherActivity] WebSocket error:', error)
        updateConnectionState('error')
      }

      ws.onclose = (event) => {
        console.log('[WatcherActivity] Connection closed:', event.code, event.reason)
        updateConnectionState('disconnected')

        // Stop ping interval
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current)
          pingIntervalRef.current = null
        }

        // Attempt reconnect if not intentionally closed
        if (options.enabled && event.code !== 1000 && reconnectAttemptsRef.current < maxReconnectAttempts) {
          const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000)
          console.log(`[WatcherActivity] Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current + 1})`)
          reconnectAttemptsRef.current++

          reconnectTimeoutRef.current = setTimeout(() => {
            connect()
          }, delay)
        }
      }
    } catch (err) {
      console.error('[WatcherActivity] Failed to create WebSocket:', err)
      updateConnectionState('error')
    }
  }, [token, options.enabled, getWebSocketUrl, updateConnectionState, handleMessage])

  const disconnect = useCallback(() => {
    console.log('[WatcherActivity] Disconnecting...')

    // Clear reconnect timeout
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }

    // Clear ping interval
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current)
      pingIntervalRef.current = null
    }

    // Close WebSocket
    if (wsRef.current) {
      wsRef.current.close(1000, 'User disconnected')
      wsRef.current = null
    }

    // Clear activity timeouts
    clearAllTimeouts()

    // Reset state
    setProcessingAgents(new Set())
    setProcessingSessions(new Map())
    setA2aSessions(new Map())
    setFadingA2ASessions(new Set())
    updateConnectionState('disconnected')
  }, [clearAllTimeouts, updateConnectionState])

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    if (token && options.enabled) {
      connect()
    }

    return () => {
      disconnect()
    }
  }, [token, options.enabled]) // eslint-disable-line react-hooks/exhaustive-deps

  return {
    connectionState,
    processingAgents,
    activeChannels,
    recentSkillUse,
    recentKbUse,
    fadingAgents,
    fadingChannels,
    isConnected: connectionState === 'connected',
    activeA2ASessions: a2aSessions,
    fadingA2ASessions,
    agentA2ADepths,
  }
}
