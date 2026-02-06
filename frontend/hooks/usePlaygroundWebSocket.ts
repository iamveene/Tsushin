/**
 * Custom Hook for Playground WebSocket (Phase 14.9)
 *
 * Manages WebSocket connection and streaming for Playground chat.
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { PlaygroundWebSocket, ConnectionState } from '@/lib/websocket'
import { PlaygroundMessage } from '@/lib/client'

interface UsePlaygroundWebSocketOptions {
  enabled: boolean
  onStreamingMessage: (message: Partial<PlaygroundMessage>) => void
  onMessageComplete: (message: PlaygroundMessage) => void
  onThreadCreated?: (threadId: number, title: string) => void
  onError: (error: string) => void
}

export function usePlaygroundWebSocket(
  token: string | null,
  options: UsePlaygroundWebSocketOptions
) {
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected')
  const [isStreaming, setIsStreaming] = useState(false)
  const wsRef = useRef<PlaygroundWebSocket | null>(null)
  const streamingMessageRef = useRef<string>('')
  const streamingMetadataRef = useRef<any>(null)
  const streamStartTimeRef = useRef<number>(0)

  // Initialize WebSocket connection
  useEffect(() => {
    if (!token || !options.enabled) {
      console.log('[WebSocket Hook] Skipping init - token:', !!token, 'enabled:', options.enabled)
      return
    }

    console.log('[WebSocket Hook] Initializing connection with token')
    const ws = new PlaygroundWebSocket(token)
    wsRef.current = ws

    // Connection state tracking
    ws.onStateChange((state) => {
      console.log('[WebSocket Hook] State changed:', state)
      setConnectionState(state)
    })

    // Handle incoming messages
    ws.on('connected', (message) => {
      console.log('[WebSocket Hook] Connected:', message)
    })

    ws.on('thinking', (message) => {
      console.log('[WebSocket Hook] Agent thinking:', message)
      setIsStreaming(true)
      streamingMessageRef.current = ''
      streamStartTimeRef.current = Date.now()

      // Notify parent with thinking indicator
      options.onStreamingMessage({
        role: 'assistant',
        content: '',
        timestamp: new Date().toISOString(),
      })
    })

    ws.on('thread_created', (message) => {
      console.log('[WebSocket Hook] Thread created:', message)
      if (options.onThreadCreated && message.thread_id) {
        options.onThreadCreated(message.thread_id, message.title)
      }
    })

    ws.on('token', (message) => {
      if (message.content) {
        streamingMessageRef.current += message.content

        // Notify parent with accumulated content
        options.onStreamingMessage({
          role: 'assistant',
          content: streamingMessageRef.current,
          timestamp: new Date().toISOString(),
        })
      }
    })

    ws.on('done', (message) => {
      console.log('[WebSocket Hook] Streaming complete:', message)
      setIsStreaming(false)

      const duration = Date.now() - streamStartTimeRef.current
      const completedMessage: PlaygroundMessage = {
        role: 'assistant',
        content: streamingMessageRef.current,
        timestamp: message.timestamp || new Date().toISOString(),
        message_id: message.message_id || `msg_${Date.now()}`,
        metadata: {
          tokenCount: message.token_usage?.total,
          duration,
          agent_name: message.agent_name,
          // Auto-rename info from backend
          thread_renamed: message.thread_renamed,
          new_thread_title: message.new_thread_title,
          thread_id: message.thread_id,
          // FIX 2026-01-30: Include agent_id for loadThreads callback
          agent_id: message.agent_id,
        },
      }

      // Notify parent of complete message
      options.onMessageComplete(completedMessage)

      // Reset streaming state
      streamingMessageRef.current = ''
      streamingMetadataRef.current = null
    })

    ws.on('error', (message) => {
      console.error('[WebSocket Hook] Error:', message)
      setIsStreaming(false)
      options.onError(message.error || 'WebSocket error')

      // Reset streaming state
      streamingMessageRef.current = ''
    })

    ws.on('pong', () => {
      // Heartbeat response - no action needed
    })

    // Connect
    ws.connect()

    // Cleanup on unmount
    return () => {
      console.log('[WebSocket Hook] Cleaning up')
      ws.disconnect()
      wsRef.current = null
    }
  }, [token, options.enabled])

  // Send message via WebSocket
  const sendMessage = useCallback((agentId: number, message: string, threadId?: number) => {
    if (!wsRef.current || connectionState !== 'connected') {
      console.warn('[WebSocket Hook] Not connected, cannot send message')
      return false
    }

    console.log('[WebSocket Hook] Sending message:', { agentId, message: message.substring(0, 50), threadId })

    wsRef.current.send({
      type: 'chat',
      agent_id: agentId,
      thread_id: threadId,
      message,
    })

    return true
  }, [connectionState])

  return {
    connectionState,
    isConnected: connectionState === 'connected',
    isStreaming,
    sendMessage,
  }
}
