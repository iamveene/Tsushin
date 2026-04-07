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
  // Message Queue event handlers
  onQueueProcessingStarted?: (queueId: number) => void
  onQueueMessageCompleted?: (queueId: number, result: any) => void
}

export function usePlaygroundWebSocket(
  options: UsePlaygroundWebSocketOptions
) {
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected')
  const [isStreaming, setIsStreaming] = useState(false)
  const wsRef = useRef<PlaygroundWebSocket | null>(null)
  const streamingMessageRef = useRef<string>('')
  const streamingMetadataRef = useRef<any>(null)
  const streamStartTimeRef = useRef<number>(0)

  // BUG-376: Use refs for callbacks to avoid stale closures in WebSocket event handlers.
  // The useEffect that registers ws.on() handlers runs only when options.enabled changes,
  // but the callbacks passed in options change on every parent render. Without refs,
  // the event handlers capture the initial callback references and never see updates,
  // causing setMessages to operate on stale state snapshots.
  const optionsRef = useRef(options)
  useEffect(() => { optionsRef.current = options }, [options])

  // Initialize WebSocket connection
  useEffect(() => {
    if (!options.enabled) {
      console.log('[WebSocket Hook] Skipping init - enabled:', options.enabled)
      return
    }

    console.log('[WebSocket Hook] Initializing connection (cookie auth)')
    const ws = new PlaygroundWebSocket()
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
      optionsRef.current.onStreamingMessage({
        role: 'assistant',
        content: '',
        timestamp: new Date().toISOString(),
      })
    })

    ws.on('thread_created', (message) => {
      console.log('[WebSocket Hook] Thread created:', message)
      if (optionsRef.current.onThreadCreated && message.thread_id) {
        optionsRef.current.onThreadCreated(message.thread_id, message.title)
      }
    })

    ws.on('token', (message) => {
      if (message.content) {
        streamingMessageRef.current += message.content

        // Notify parent with accumulated content
        optionsRef.current.onStreamingMessage({
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
        image_url: message.image_url || undefined,  // Phase 6: Image generation
        image_urls: message.image_urls || undefined,  // Phase 6: All generated images
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
      optionsRef.current.onMessageComplete(completedMessage)

      // Reset streaming state
      streamingMessageRef.current = ''
      streamingMetadataRef.current = null
    })

    ws.on('error', (message) => {
      console.error('[WebSocket Hook] Error:', message)
      setIsStreaming(false)
      optionsRef.current.onError(message.error || 'WebSocket error')

      // Reset streaming state
      streamingMessageRef.current = ''
    })

    ws.on('pong', () => {
      // Heartbeat response - no action needed
    })

    // Message Queue events
    ws.on('queue_processing_started', (message: any) => {
      console.log('[WebSocket Hook] Queue processing started:', message.queue_id)
      if (optionsRef.current.onQueueProcessingStarted) {
        optionsRef.current.onQueueProcessingStarted(message.queue_id)
      }
    })

    ws.on('queue_message_completed', (message: any) => {
      console.log('[WebSocket Hook] Queue message completed:', message.queue_id)
      if (optionsRef.current.onQueueMessageCompleted) {
        optionsRef.current.onQueueMessageCompleted(message.queue_id, message.result)
      }
    })

    // Connect
    ws.connect()

    // Cleanup on unmount
    return () => {
      console.log('[WebSocket Hook] Cleaning up')
      ws.disconnect()
      wsRef.current = null
    }
  }, [options.enabled])

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
