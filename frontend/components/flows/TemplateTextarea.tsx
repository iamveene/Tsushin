'use client'

/**
 * TemplateTextarea Component
 *
 * Wraps a textarea with the StepVariablePanel for template variable injection.
 * Handles click-to-insert and drag-and-drop at cursor position, plus clipboard copy.
 *
 * Drop-in replacement for CursorSafeTextarea: accepts the full
 * <textarea> HTML attribute surface (rest spread) so existing call sites
 * can swap with just two extra props (allSteps + currentStepPosition)
 * without losing onBlur/disabled/id/etc.
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import type { TextareaHTMLAttributes, FocusEvent, DragEvent } from 'react'
import StepVariablePanel from './StepVariablePanel'

interface StepInfo {
  name: string
  type: string
  position: number
  config?: Record<string, any>
}

type NativeTextareaProps = Omit<
  TextareaHTMLAttributes<HTMLTextAreaElement>,
  'onChange' | 'value' | 'defaultValue'
>

interface TemplateTextareaProps extends NativeTextareaProps {
  value: string
  onValueChange: (value: string) => void
  allSteps: StepInfo[]
  currentStepPosition: number
}

/**
 * Self-contained textarea with cursor-safe editing and variable panel.
 * Replicates CursorSafeTextarea's local-state + onBlur-flush pattern so
 * debounced parent saves and on-blur form flushes keep working.
 */
export default function TemplateTextarea({
  value: externalValue,
  onValueChange,
  allSteps,
  currentStepPosition,
  className = '',
  onBlur: externalOnBlur,
  onFocus: externalOnFocus,
  ...rest
}: TemplateTextareaProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const cursorPosRef = useRef<number>(externalValue.length)
  const [localValue, setLocalValue] = useState(externalValue)
  const isFocusedRef = useRef(false)

  // Sync external value when not focused (same as CursorSafeTextarea)
  useEffect(() => {
    if (!isFocusedRef.current) {
      setLocalValue(externalValue)
    }
  }, [externalValue])

  // Track cursor position on any interaction
  const updateCursorPos = useCallback(() => {
    const el = textareaRef.current
    if (el) {
      cursorPosRef.current = el.selectionStart ?? localValue.length
    }
  }, [localValue.length])

  // Insert text at a specific position (used by both click-to-insert and drag-drop)
  const insertAt = useCallback((template: string, insertPos: number) => {
    const safePos = Math.max(0, Math.min(insertPos, localValue.length))
    const before = localValue.slice(0, safePos)
    const after = localValue.slice(safePos)
    const newValue = before + template + after
    const newCursorPos = safePos + template.length

    setLocalValue(newValue)
    onValueChange(newValue)
    cursorPosRef.current = newCursorPos

    requestAnimationFrame(() => {
      const el = textareaRef.current
      if (el) {
        el.focus()
        el.selectionStart = newCursorPos
        el.selectionEnd = newCursorPos
      }
    })
  }, [localValue, onValueChange])

  // Click-to-insert at last known cursor position
  const handleInsertVariable = useCallback((template: string) => {
    insertAt(template, cursorPosRef.current)
  }, [insertAt])

  // Drag-drop: insert at the drop point (caret position under the pointer).
  // Falls back to last known cursor position if caret APIs are unavailable.
  const handleDrop = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    const template = e.dataTransfer.getData('text/plain')
    if (!template) return

    let insertPos = cursorPosRef.current
    const el = textareaRef.current
    if (el) {
      // Modern Firefox API
      const docAny = document as any
      if (typeof docAny.caretPositionFromPoint === 'function') {
        const caret = docAny.caretPositionFromPoint(e.clientX, e.clientY)
        if (caret && caret.offsetNode === el.firstChild) {
          insertPos = caret.offset
        } else if (caret) {
          // Pointer over the textarea but not over its text node — append
          insertPos = el.value.length
        }
      } else if (typeof docAny.caretRangeFromPoint === 'function') {
        // Chromium API — caretRangeFromPoint inside <textarea> doesn't return
        // the textarea's text node directly; fall back to last cursor position.
        // (Browsers don't expose caret-in-textarea-from-point reliably.)
      }
    }
    insertAt(template, insertPos)
  }, [insertAt])

  const handleDragOver = useCallback((e: DragEvent<HTMLDivElement>) => {
    // Required to allow drop
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
  }, [])

  const defaultClassName = `w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
    focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none`

  return (
    <div>
      <div onDragOver={handleDragOver} onDrop={handleDrop}>
        <textarea
          {...rest}
          ref={textareaRef}
          value={localValue}
          className={className || defaultClassName}
          onFocus={(e: FocusEvent<HTMLTextAreaElement>) => {
            isFocusedRef.current = true
            updateCursorPos()
            if (externalOnFocus) externalOnFocus(e)
          }}
          onBlur={(e: FocusEvent<HTMLTextAreaElement>) => {
            updateCursorPos()
            isFocusedRef.current = false
            // Mirror CursorSafeTextarea's onBlur flush so parent debounced
            // saves don't lose pending input on blur.
            if (localValue !== externalValue) {
              onValueChange(localValue)
            }
            if (externalOnBlur) externalOnBlur(e)
          }}
          onChange={(e) => {
            setLocalValue(e.target.value)
            onValueChange(e.target.value)
          }}
          onSelect={updateCursorPos}
          onKeyUp={updateCursorPos}
          onClick={updateCursorPos}
        />
      </div>
      <StepVariablePanel
        allSteps={allSteps}
        currentStepPosition={currentStepPosition}
        onInsertVariable={handleInsertVariable}
      />
    </div>
  )
}
