'use client'

/**
 * Renders the streamed Chromium frame and forwards mouse/keyboard events
 * back to the recorder backend.
 *
 * Frames arrive as base64-encoded JPEGs over WebSocket. We draw them into
 * a <canvas> so we can also paint overlays (e.g., captcha marker rect)
 * without forcing React re-renders on every frame.
 *
 * Coordinate translation: the canvas DOM size is whatever fits the modal;
 * the backend expects viewport-space coordinates. We scale x/y back into
 * viewport space before sending input events.
 */

import { useCallback, useEffect, useRef } from 'react'
import type { RecorderFrame } from './useRecorderSocket'

interface StreamCanvasProps {
  viewport: { width: number; height: number } | null
  onPointer?: (event: PointerInput) => void
  onKey?: (event: KeyInput) => void
  onText?: (text: string) => void
  onRectMark?: (rect: { x: number; y: number; width: number; height: number; kind: 'captcha' | 'extract' }) => void
  markerMode?: 'captcha' | 'extract' | null
  framePort: { latestFrame: RecorderFrame | null }
}

export interface PointerInput {
  action: 'move' | 'down' | 'up' | 'wheel'
  x: number
  y: number
  button?: 'left' | 'middle' | 'right'
  deltaX?: number
  deltaY?: number
  modifiers?: number
}

export interface KeyInput {
  action: 'down' | 'up'
  key: string
  code: string
  modifiers?: number
}

// CDP modifier bitfield: alt=1, ctrl=2, meta=4, shift=8
function modifierBitfield(e: { altKey?: boolean; ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean }): number {
  return (
    (e.altKey ? 1 : 0) |
    (e.ctrlKey ? 2 : 0) |
    (e.metaKey ? 4 : 0) |
    (e.shiftKey ? 8 : 0)
  )
}

function buttonName(button: number): 'left' | 'middle' | 'right' {
  if (button === 1) return 'middle'
  if (button === 2) return 'right'
  return 'left'
}

export default function StreamCanvas({
  viewport,
  onPointer,
  onKey,
  onText,
  onRectMark,
  markerMode,
  framePort,
}: StreamCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const imgRef = useRef<HTMLImageElement | null>(null)
  const dragStateRef = useRef<{ startX: number; startY: number; active: boolean } | null>(null)
  const lastDrawnFrameRef = useRef<string | null>(null)

  // Paint loop — RAF re-draws whenever a new frame arrives. We keep the
  // <img> element so the browser decodes JPEG asynchronously off the main
  // thread; once decoded, we copy it into the canvas.
  useEffect(() => {
    if (!imgRef.current) {
      imgRef.current = new Image()
    }
    const img = imgRef.current
    let raf = 0
    const tick = () => {
      const frame = framePort.latestFrame
      if (frame && frame.data && frame.data !== lastDrawnFrameRef.current) {
        lastDrawnFrameRef.current = frame.data
        img.onload = () => {
          const canvas = canvasRef.current
          if (!canvas) return
          const ctx = canvas.getContext('2d')
          if (!ctx) return
          // Match canvas internal size to the source frame so 1:1
          // coordinate mapping holds for input events.
          if (canvas.width !== img.naturalWidth || canvas.height !== img.naturalHeight) {
            canvas.width = img.naturalWidth || canvas.width
            canvas.height = img.naturalHeight || canvas.height
          }
          ctx.drawImage(img, 0, 0)
        }
        img.src = `data:image/jpeg;base64,${frame.data}`
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [framePort])

  // Map DOM event coordinates → viewport-space coordinates. The canvas's
  // CSS size may not equal its internal pixel size; scale back.
  const toViewportCoords = useCallback((clientX: number, clientY: number): { x: number; y: number } => {
    const canvas = canvasRef.current
    if (!canvas) return { x: 0, y: 0 }
    const rect = canvas.getBoundingClientRect()
    const scaleX = canvas.width / rect.width
    const scaleY = canvas.height / rect.height
    return {
      x: Math.round((clientX - rect.left) * scaleX),
      y: Math.round((clientY - rect.top) * scaleY),
    }
  }, [])

  const handlePointerDown = useCallback((e: React.PointerEvent<HTMLCanvasElement>) => {
    e.preventDefault()
    // BUG-767: pointerdown alone does NOT grab DOM focus in Chromium for
    // a canvas with tabIndex=0. Without explicit focus the next keystroke
    // goes to whatever was previously focused (URL bar, body), so the
    // recorder drops every fill the user types. setPointerCapture handles
    // pointer routing but not keyboard focus.
    canvasRef.current?.focus({ preventScroll: true })
    canvasRef.current?.setPointerCapture(e.pointerId)
    const { x, y } = toViewportCoords(e.clientX, e.clientY)

    if (markerMode) {
      dragStateRef.current = { startX: x, startY: y, active: true }
      return
    }
    onPointer?.({
      action: 'down',
      x, y,
      button: buttonName(e.button),
      modifiers: modifierBitfield(e),
    })
  }, [markerMode, onPointer, toViewportCoords])

  const handlePointerMove = useCallback((e: React.PointerEvent<HTMLCanvasElement>) => {
    const { x, y } = toViewportCoords(e.clientX, e.clientY)
    if (markerMode && dragStateRef.current?.active) {
      // We don't forward as input — we just track for the rect mark below.
      return
    }
    onPointer?.({
      action: 'move',
      x, y,
      modifiers: modifierBitfield(e),
    })
  }, [markerMode, onPointer, toViewportCoords])

  const handlePointerUp = useCallback((e: React.PointerEvent<HTMLCanvasElement>) => {
    e.preventDefault()
    const { x, y } = toViewportCoords(e.clientX, e.clientY)
    canvasRef.current?.releasePointerCapture(e.pointerId)

    if (markerMode && dragStateRef.current?.active) {
      const sx = dragStateRef.current.startX
      const sy = dragStateRef.current.startY
      const rect = {
        x: Math.min(sx, x),
        y: Math.min(sy, y),
        width: Math.abs(x - sx),
        height: Math.abs(y - sy),
        kind: markerMode,
      }
      dragStateRef.current = null
      if (rect.width > 4 && rect.height > 4) {
        onRectMark?.(rect)
      }
      return
    }
    onPointer?.({
      action: 'up',
      x, y,
      button: buttonName(e.button),
      modifiers: modifierBitfield(e),
    })
  }, [markerMode, onPointer, onRectMark, toViewportCoords])

  // React's onWheel prop is registered as `passive: true` by Chromium, so
  // `e.preventDefault()` inside a React-synthetic handler is a no-op — the
  // wheel still scrolls the parent modal instead of being forwarded to the
  // recorded page. Attaching the listener imperatively with
  // `{ passive: false }` lets us cancel the default and route the scroll
  // into the remote browser via CDP.
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const handler = (e: WheelEvent) => {
      e.preventDefault()
      const { x, y } = toViewportCoords(e.clientX, e.clientY)
      onPointer?.({
        action: 'wheel',
        x, y,
        deltaX: e.deltaX,
        deltaY: e.deltaY,
        modifiers: modifierBitfield(e),
      })
    }
    canvas.addEventListener('wheel', handler, { passive: false })
    return () => canvas.removeEventListener('wheel', handler)
  }, [onPointer, toViewportCoords])

  // Keyboard handling: we forward key events while the canvas is focused.
  // For "ordinary" printable keys we also send a text-insert so the
  // remote field receives the character even if the browser swallows the
  // synthesized keypress (modifier-aware, IME-safe).
  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLCanvasElement>) => {
    e.preventDefault()
    onKey?.({
      action: 'down',
      key: e.key,
      code: e.code,
      modifiers: modifierBitfield(e),
    })
    // Single printable character — also insert as text.
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      onText?.(e.key)
    }
  }, [onKey, onText])

  const handleKeyUp = useCallback((e: React.KeyboardEvent<HTMLCanvasElement>) => {
    e.preventDefault()
    onKey?.({
      action: 'up',
      key: e.key,
      code: e.code,
      modifiers: modifierBitfield(e),
    })
  }, [onKey])

  // Clipboard paste — read the host machine's clipboard and forward as
  // an `Input.insertText` into the remote browser. Cmd/Ctrl+V on its
  // own would only synthesize the key event over CDP, and Chromium-in-
  // container has an empty clipboard, so the paste would no-op. By
  // intercepting the `paste` event here we get the actual text via
  // `clipboardData.getData('text')` and feed it through the same
  // input.text channel a single keystroke uses.
  const handlePaste = useCallback((e: React.ClipboardEvent<HTMLCanvasElement>) => {
    e.preventDefault()
    const text = e.clipboardData?.getData('text/plain') || e.clipboardData?.getData('text') || ''
    if (text) onText?.(text)
  }, [onText])

  return (
    <canvas
      ref={canvasRef}
      tabIndex={0}
      width={viewport?.width || 1280}
      height={viewport?.height || 720}
      onPaste={handlePaste}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onKeyDown={handleKeyDown}
      onKeyUp={handleKeyUp}
      onContextMenu={(e) => e.preventDefault()}
      className={
        'w-full bg-black rounded-md outline-none ring-2 ring-transparent focus:ring-cyan-500/40 ' +
        (markerMode ? 'cursor-crosshair' : 'cursor-default')
      }
      style={{ aspectRatio: viewport ? `${viewport.width} / ${viewport.height}` : '16 / 9' }}
      aria-label="Recorded browser stream"
    />
  )
}
