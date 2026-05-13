'use client'

import { useCallback, useRef } from 'react'
import type { MouseEvent as ReactMouseEvent } from 'react'

/**
 * Returns props for a modal backdrop element so that it dismisses only
 * when the gesture both STARTS and ENDS on the backdrop itself.
 *
 * Why: the previous `onClick` + `e.target === e.currentTarget` pattern
 * fired on text-selection drags that began inside the modal (e.g. on
 * an `<input>`) and released on the backdrop — the synthetic `click`
 * lands on the common ancestor (the backdrop), so the modal would
 * incorrectly dismiss.
 *
 * Spread the returned object onto the backdrop element:
 *
 *     const dismiss = useBackdropDismiss(onClose)
 *     <div className="fixed inset-0 ..." {...dismiss}>
 *       <div onMouseDown={(e) => e.stopPropagation()} ...>
 *         {children}
 *       </div>
 *     </div>
 */
export function useBackdropDismiss(onDismiss: () => void) {
  const downOnBackdrop = useRef(false)

  const onMouseDown = useCallback((e: ReactMouseEvent<HTMLElement>) => {
    downOnBackdrop.current = e.target === e.currentTarget
  }, [])

  const onMouseUp = useCallback(
    (e: ReactMouseEvent<HTMLElement>) => {
      const wasDownOnBackdrop = downOnBackdrop.current
      downOnBackdrop.current = false
      if (wasDownOnBackdrop && e.target === e.currentTarget) {
        onDismiss()
      }
    },
    [onDismiss],
  )

  return { onMouseDown, onMouseUp }
}
