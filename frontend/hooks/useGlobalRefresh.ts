import { useEffect, useRef } from 'react'

/**
 * Subscribes a callback to the global `tsushin:refresh` event dispatched by
 * the header RefreshButton. Uses a ref internally so the listener always
 * invokes the LATEST callback, avoiding stale-closure bugs where pages that
 * attach the listener with empty deps (`[]`) end up calling a loader that
 * captured initial state.
 *
 * Usage:
 *   useGlobalRefresh(() => {
 *     loadData()
 *     checkHealth()
 *   })
 *
 * Safe to use in any page/component — handles mount/unmount cleanup.
 */
export function useGlobalRefresh(callback: () => void | Promise<void>) {
  const callbackRef = useRef(callback)

  // Keep ref pointing at the latest callback on every render
  useEffect(() => {
    callbackRef.current = callback
  })

  useEffect(() => {
    const handler = () => {
      void callbackRef.current()
    }
    window.addEventListener('tsushin:refresh', handler)
    return () => window.removeEventListener('tsushin:refresh', handler)
  }, [])
}
