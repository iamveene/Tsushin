/**
 * WebSocket client for Playground real-time streaming
 * BUG-PLAYGROUND-004 FIX: Full implementation replacing stub
 * HIGH-001 FIX: Token now sent via first message instead of URL query params
 *
 * Features:
 * - Real WebSocket connection using browser's WebSocket API
 * - Secure authentication via first message (not URL params)
 * - Automatic reconnection with exponential backoff
 * - Ping/pong heartbeat for connection health
 * - Event-based message handling
 */

export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'authenticating' | 'error'

interface WebSocketMessage {
  type: string
  [key: string]: any
}

export class PlaygroundWebSocket {
  private token: string
  private ws: WebSocket | null = null
  private connectionState: ConnectionState = 'disconnected'
  private handlers: Map<string, Function[]> = new Map()
  private stateHandlers: ((state: ConnectionState) => void)[] = []
  private reconnectAttempts: number = 0
  private maxReconnectAttempts: number = 5
  private reconnectDelay: number = 1000
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null
  private pingInterval: ReturnType<typeof setInterval> | null = null
  private pingIntervalMs: number = 30000 // 30 seconds

  constructor(token: string) {
    this.token = token
    console.log('[WebSocket] Instance created with token:', !!token)
  }

  private getWebSocketUrl(): string {
    // Convert HTTP(S) API URL to WS(S) URL
    // HIGH-001 FIX: Token no longer sent in URL query params for security
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8081'
    const wsProtocol = apiUrl.startsWith('https') ? 'wss' : 'ws'
    const host = apiUrl.replace(/^https?:\/\//, '').replace(/\/$/, '')
    return `${wsProtocol}://${host}/ws/playground`
  }

  connect() {
    if (this.connectionState === 'connecting' || this.connectionState === 'connected' || this.connectionState === 'authenticating') {
      console.log('[WebSocket] Already connecting/connected, skipping')
      return
    }

    // Check if WebSocket is available (SSR guard)
    if (typeof WebSocket === 'undefined') {
      console.warn('[WebSocket] WebSocket not available in this environment')
      return
    }

    this.setConnectionState('connecting')

    try {
      const url = this.getWebSocketUrl()
      console.log('[WebSocket] Connecting to:', url)

      this.ws = new WebSocket(url)

      this.ws.onopen = () => {
        console.log('[WebSocket] Connection established, sending auth message...')
        this.setConnectionState('authenticating')

        // HIGH-001 FIX: Send token in first message after connection (secure method)
        // This prevents token from appearing in browser history, server logs, and referrer headers
        try {
          this.ws?.send(JSON.stringify({
            type: 'auth',
            token: this.token
          }))
          console.log('[WebSocket] Auth message sent')
        } catch (err) {
          console.error('[WebSocket] Failed to send auth message:', err)
          this.setConnectionState('error')
        }
      }

      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data)
          this.handleMessage(message)
        } catch (err) {
          console.error('[WebSocket] Failed to parse message:', err)
        }
      }

      this.ws.onerror = (error) => {
        console.error('[WebSocket] Connection error:', error)
        this.setConnectionState('error')
      }

      this.ws.onclose = (event) => {
        console.log('[WebSocket] Connection closed:', event.code, event.reason)
        this.stopPingInterval()

        if (event.code !== 1000) { // Not a clean close
          this.setConnectionState('disconnected')
          this.attemptReconnect()
        } else {
          this.setConnectionState('disconnected')
        }
      }
    } catch (err) {
      console.error('[WebSocket] Failed to create connection:', err)
      this.setConnectionState('error')
    }
  }

  disconnect() {
    console.log('[WebSocket] Disconnecting...')
    this.stopPingInterval()
    this.clearReconnectTimeout()

    if (this.ws) {
      this.ws.close(1000, 'Client disconnect')
      this.ws = null
    }

    this.setConnectionState('disconnected')
  }

  /**
   * Send a structured message to the server
   * Used by usePlaygroundWebSocket hook
   */
  send(message: WebSocketMessage): boolean {
    if (!this.ws || this.connectionState !== 'connected') {
      console.warn('[WebSocket] Cannot send - not connected')
      return false
    }

    try {
      this.ws.send(JSON.stringify(message))
      return true
    } catch (err) {
      console.error('[WebSocket] Send failed:', err)
      return false
    }
  }

  /**
   * Legacy method for backwards compatibility
   * @deprecated Use send() instead
   */
  sendMessage(message: string): boolean {
    return this.send({ type: 'chat', message })
  }

  on(event: string, handler: Function) {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, [])
    }
    this.handlers.get(event)!.push(handler)
  }

  off(event: string, handler: Function) {
    const handlers = this.handlers.get(event)
    if (handlers) {
      const index = handlers.indexOf(handler)
      if (index !== -1) {
        handlers.splice(index, 1)
      }
    }
  }

  onStateChange(handler: (state: ConnectionState) => void) {
    this.stateHandlers.push(handler)
  }

  getConnectionState(): ConnectionState {
    return this.connectionState
  }

  private setConnectionState(state: ConnectionState) {
    if (this.connectionState !== state) {
      this.connectionState = state
      this.stateHandlers.forEach(handler => handler(state))
    }
  }

  private handleMessage(message: WebSocketMessage) {
    const type = message.type

    // HIGH-001 FIX: Handle auth confirmation and transition to connected state
    if (type === 'connected' && this.connectionState === 'authenticating') {
      console.log('[WebSocket] Authentication successful, fully connected')
      this.setConnectionState('connected')
      this.reconnectAttempts = 0
      this.startPingInterval()
    }

    const handlers = this.handlers.get(type)

    if (handlers && handlers.length > 0) {
      handlers.forEach(handler => handler(message))
    } else if (type !== 'connected') {
      // Don't log 'connected' as unhandled since we handle it above
      console.log('[WebSocket] Unhandled message type:', type, message)
    }
  }

  private startPingInterval() {
    this.stopPingInterval()
    this.pingInterval = setInterval(() => {
      if (this.connectionState === 'connected') {
        this.send({ type: 'ping' })
      }
    }, this.pingIntervalMs)
  }

  private stopPingInterval() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval)
      this.pingInterval = null
    }
  }

  private attemptReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log('[WebSocket] Max reconnect attempts reached')
      this.setConnectionState('error')
      return
    }

    this.reconnectAttempts++
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1) // Exponential backoff

    console.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`)

    this.reconnectTimeout = setTimeout(() => {
      this.connect()
    }, delay)
  }

  private clearReconnectTimeout() {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout)
      this.reconnectTimeout = null
    }
  }
}
