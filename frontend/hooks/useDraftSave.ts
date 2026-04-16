'use client'

/**
 * Auto-Save Drafts Hook
 *
 * Persists unsent message drafts per-thread to localStorage.
 * Uses debounced saves (500ms) and reads directly from the
 * DOM-driven textarea via inputRef.
 */

import { useRef, useCallback, useEffect } from 'react'

const DRAFT_KEY_PREFIX = 'tsushin_draft_'

function getDraftKey(threadId: number | null): string {
  return threadId ? `${DRAFT_KEY_PREFIX}${threadId}` : `${DRAFT_KEY_PREFIX}new`
}

export function useDraftSave(
  activeThreadId: number | null,
  inputRef: React.RefObject<HTMLTextAreaElement>
) {
  const debounceRef = useRef<NodeJS.Timeout | null>(null)

  const saveDraft = useCallback(() => {
    if (typeof window === 'undefined') return

    // Cancel any pending debounce
    if (debounceRef.current) {
      clearTimeout(debounceRef.current)
    }

    debounceRef.current = setTimeout(() => {
      const value = inputRef.current?.value || ''
      const key = getDraftKey(activeThreadId)

      if (value.trim()) {
        localStorage.setItem(key, value)
      } else {
        localStorage.removeItem(key)
      }
    }, 500)
  }, [activeThreadId, inputRef])

  /**
   * Flush the draft to localStorage immediately (no debounce).
   * Accepts an optional threadId override for use during thread switching,
   * where the hook's activeThreadId may have already changed.
   */
  const saveDraftImmediate = useCallback((threadIdOverride?: number | null) => {
    if (typeof window === 'undefined') return

    // Cancel any pending debounce
    if (debounceRef.current) {
      clearTimeout(debounceRef.current)
      debounceRef.current = null
    }

    const value = inputRef.current?.value || ''
    const key = getDraftKey(threadIdOverride !== undefined ? threadIdOverride : activeThreadId)

    if (value.trim()) {
      localStorage.setItem(key, value)
    } else {
      localStorage.removeItem(key)
    }
  }, [activeThreadId, inputRef])

  const restoreDraft = useCallback(() => {
    if (typeof window === 'undefined') return

    const key = getDraftKey(activeThreadId)
    const saved = localStorage.getItem(key)

    if (inputRef.current) {
      if (saved) {
        inputRef.current.value = saved
        // Adjust textarea height to fit content
        inputRef.current.style.height = 'auto'
        inputRef.current.style.height = Math.min(inputRef.current.scrollHeight, 120) + 'px'
      } else {
        inputRef.current.value = ''
        inputRef.current.style.height = 'auto'
      }
    }
  }, [activeThreadId, inputRef])

  const clearDraft = useCallback(() => {
    if (typeof window === 'undefined') return

    // Cancel any pending debounce
    if (debounceRef.current) {
      clearTimeout(debounceRef.current)
      debounceRef.current = null
    }

    const key = getDraftKey(activeThreadId)
    localStorage.removeItem(key)
  }, [activeThreadId, inputRef])

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
      }
    }
  }, [])

  return { saveDraft, saveDraftImmediate, restoreDraft, clearDraft }
}
