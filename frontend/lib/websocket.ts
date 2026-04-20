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
  // BUG-620: Suppress repeated `Connection error: Event` noise. The browser
  // emits an onerror event for every transient blip (incl. normal close paths),
  // and a raw `Event` stringifies to `[object Event]`. We log once per
  // close-cycle and reset the flag after each onclose, so reconnect attempts
  // stay visible but redundant fires don't spam the console.
  private errorLoggedThisCycle: boolean = false

  constructor() {
    // SEC-005 Phase 3: No token needed — auth via httpOnly cookie on WS upgrade
    console.log('[WebSocket] Instance created (cookie auth)')
  }

  private getWebSocketUrl(): string {
    // v0.6.1 BUG-5/7/8 fix: build from window.location so the WS upgrade stays
    // same-origin with the page — httpOnly cookie rides along. Next.js rewrites
    // (see next.config.mjs) proxy /ws/* to the backend over the Docker network.
    // HIGH-001 FIX: Token no longer sent in URL query params for security.
    if (typeof window === 'undefined') return ''
    const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    return `${wsProtocol}://${window.location.host}/ws/playground`
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
      if (!url) {
        console.warn('[WebSocket] No WebSocket URL available (likely SSR); skipping connect')
        this.setConnectionState('disconnected')
        return
      }
      console.log('[WebSocket] Connecting to:', url)

      this.ws = new WebSocket(url)

      this.ws.onopen = () => {
        // SEC-005 Phase 3: httpOnly cookie is sent automatically with WS upgrade.
        // No first-message auth needed — backend authenticates from cookie.
        console.log('[WebSocket] Connection established (cookie auth)')
        this.setConnectionState('authenticating')
      }

      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data)
          this.handleMessage(message)
        } catch (err) {
          console.error('[WebSocket] Failed to parse message:', err)
        }
      }

      this.ws.onerror = (event) => {
        // BUG-620: `event` is a generic DOM Event — stringifying it yields
        // `[object Event]` which is useless. Pull diagnostics from the
        // underlying socket instead. Only surface as `warn` (not `error`)
        // and only once per close-cycle so routine reconnect blips don't
        // taint the "zero console errors" matrix.
        if (this.errorLoggedThisCycle) return
        this.errorLoggedThisCycle = true
        const ws = this.ws
        const diag = {
          readyState: ws?.readyState,
          readyStateLabel: ws ? ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED'][ws.readyState] : 'NO_SOCKET',
          url: ws?.url,
          type: (event as Event)?.type,
        }
        console.warn('[WebSocket] Connection error (pre-close):', diag)
        this.setConnectionState('error')
      }

      this.ws.onclose = (event) => {
        // Non-error clean closes are normal lifecycle events — log at debug
        // level (console.debug) to avoid poisoning the Playground QA matrix
        // with noise. Abnormal closes stay visible via console.log.
        if (event.code === 1000) {
          if (typeof console.debug === 'function') {
            console.debug('[WebSocket] Connection closed cleanly:', event.code, event.reason || '(no reason)')
          }
        } else {
          console.log('[WebSocket] Connection closed:', event.code, event.reason || '(no reason)')
        }
        this.stopPingInterval()
        // Reset the once-per-cycle error guard so the next connection attempt
        // can log its own error without being swallowed.
        this.errorLoggedThisCycle = false

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
