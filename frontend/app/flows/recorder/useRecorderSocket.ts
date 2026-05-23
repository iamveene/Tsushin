'use client'

/**
 * WebSocket client for the Browser Recorder session.
 *
 * Mirrors the cookie-auth pattern from lib/websocket.ts (PlaygroundWebSocket):
 * httpOnly cookie rides the WS upgrade, no token in the URL. Same-origin
 * upgrade so Next.js rewrites proxy /ws/* to the backend.
 *
 * Wire protocol — see backend/browser_recorder/cdp_relay.py.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

export type RecorderFrame = { data: string; metadata?: Record<string, any> }
export type RecorderEventRow = { kind: string; payload: Record<string, any>; ts?: number }
export type RecorderSocketStatus = 'idle' | 'connecting' | 'authenticating' | 'open' | 'closing' | 'closed' | 'error'

export interface UseRecorderSocketOptions {
  sessionId: string
  enabled: boolean
  onFrame?: (frame: RecorderFrame) => void
  onEvent?: (event: RecorderEventRow) => void
  onError?: (message: string) => void
}

export interface UseRecorderSocketReturn {
  status: RecorderSocketStatus
  viewport: { width: number; height: number } | null
  send: (msg: Record<string, any>) => void
  close: () => void
}

const MAX_RECONNECT_ATTEMPTS = 4
const BASE_RECONNECT_DELAY_MS = 800

export function useRecorderSocket({
  sessionId,
  enabled,
  onFrame,
  onEvent,
  onError,
}: UseRecorderSocketOptions): UseRecorderSocketReturn {
  const wsRef = useRef<WebSocket | null>(null)
  const [status, setStatus] = useState<RecorderSocketStatus>('idle')
  const [viewport, setViewport] = useState<{ width: number; height: number } | null>(null)
  const attemptsRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onFrameRef = useRef(onFrame)
  const onEventRef = useRef(onEvent)
  const onErrorRef = useRef(onError)

  // Keep callback refs current without re-running the effect.
  useEffect(() => { onFrameRef.current = onFrame }, [onFrame])
  useEffect(() => { onEventRef.current = onEvent }, [onEvent])
  useEffect(() => { onErrorRef.current = onError }, [onError])

  const send = useCallback((msg: Record<string, any>) => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    try {
      ws.send(JSON.stringify(msg))
    } catch (err) {
      // Best-effort — the next reconnect cycle will resume the stream.
      console.warn('[RecorderSocket] send failed', err)
    }
  }, [])

  const close = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    const ws = wsRef.current
    if (ws) {
      setStatus('closing')
      try { ws.close(1000, 'client closing') } catch { /* noop */ }
    }
    wsRef.current = null
    attemptsRef.current = MAX_RECONNECT_ATTEMPTS // disable further reconnects
  }, [])

  useEffect(() => {
    if (!enabled || !sessionId || typeof window === 'undefined') return

    let cancelled = false
    attemptsRef.current = 0

    const connect = () => {
      if (cancelled) return
      const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const url = `${wsProtocol}://${window.location.host}/ws/recorder/${encodeURIComponent(sessionId)}`
      setStatus('connecting')

      let ws: WebSocket
      try {
        ws = new WebSocket(url)
      } catch (err) {
        setStatus('error')
        onErrorRef.current?.('Failed to open WebSocket')
        return
      }
      wsRef.current = ws

      ws.onopen = () => {
        setStatus('authenticating')
        // Cookie auth is automatic — nothing to send.
      }

      ws.onmessage = (event) => {
        let msg: any
        try {
          msg = JSON.parse(event.data)
        } catch {
          return
        }
        if (msg?.type === 'hello') {
          setStatus('open')
          if (msg.viewport) setViewport(msg.viewport)
          return
        }
        if (msg?.type === 'frame') {
          onFrameRef.current?.({ data: msg.data, metadata: msg.metadata })
          return
        }
        if (msg?.type === 'event') {
          onEventRef.current?.({ kind: msg.kind, payload: msg.payload, ts: Date.now() / 1000 })
          return
        }
        if (msg?.type === 'error') {
          onErrorRef.current?.(msg.message || 'recorder error')
          return
        }
        if (msg?.type === 'pong') {
          return
        }
      }

      ws.onerror = () => {
        // Browser fires a generic Event — actionable diagnostics come from onclose.
        setStatus('error')
      }

      ws.onclose = (event) => {
        wsRef.current = null
        const wasOpen = status === 'open' || status === 'authenticating'
        setStatus('closed')
        if (cancelled || attemptsRef.current >= MAX_RECONNECT_ATTEMPTS) return
        // Don't reconnect on clean closes initiated by us.
        if (event.code === 1000 && !wasOpen) return
        attemptsRef.current += 1
        const delay = BASE_RECONNECT_DELAY_MS * Math.pow(2, attemptsRef.current - 1)
        reconnectTimerRef.current = setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      const ws = wsRef.current
      if (ws) {
        try { ws.close(1000, 'unmount') } catch { /* noop */ }
      }
      wsRef.current = null
    }
    // Intentionally exclude `status` — it's a state we update inside the
    // effect and including it would cause reconnect loops.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, sessionId])

  return { status, viewport, send, close }
}
