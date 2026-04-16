'use client'

/**
 * TemplateTextarea Component
 *
 * Wraps a textarea with the StepVariablePanel for template variable injection.
 * Handles click-to-insert at cursor position and clipboard copy.
 *
 * This is a drop-in replacement for CursorSafeTextarea in locations
 * that support template variable injection (notification text, message templates, etc.)
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import StepVariablePanel from './StepVariablePanel'

interface StepInfo {
  name: string
  type: string
  position: number
  config?: Record<string, any>
}

interface TemplateTextareaProps {
  value: string
  onValueChange: (value: string) => void
  allSteps: StepInfo[]
  currentStepPosition: number
  rows?: number
  placeholder?: string
  className?: string
}

/**
 * Self-contained textarea with cursor-safe editing and variable panel.
 * Replicates CursorSafeTextarea logic internally to enable cursor-position insertion.
 */
export default function TemplateTextarea({
  value: externalValue,
  onValueChange,
  allSteps,
  currentStepPosition,
  rows = 3,
  placeholder,
  className = '',
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

  // Insert variable at cursor position
  const handleInsertVariable = useCallback((template: string) => {
    const pos = cursorPosRef.current
    const before = localValue.slice(0, pos)
    const after = localValue.slice(pos)
    const newValue = before + template + after
    const newCursorPos = pos + template.length

    setLocalValue(newValue)
    onValueChange(newValue)
    cursorPosRef.current = newCursorPos

    // Refocus and set cursor after insertion
    requestAnimationFrame(() => {
      const el = textareaRef.current
      if (el) {
        el.focus()
        el.selectionStart = newCursorPos
        el.selectionEnd = newCursorPos
      }
    })
  }, [localValue, onValueChange])

  const defaultClassName = `w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
    focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none`

  return (
    <div>
      <textarea
        ref={textareaRef}
        value={localValue}
        rows={rows}
        placeholder={placeholder}
        className={className || defaultClassName}
        onFocus={() => {
          isFocusedRef.current = true
          updateCursorPos()
        }}
        onBlur={() => {
          updateCursorPos()
          isFocusedRef.current = false
        }}
        onChange={(e) => {
          setLocalValue(e.target.value)
          onValueChange(e.target.value)
        }}
        onSelect={updateCursorPos}
        onKeyUp={updateCursorPos}
        onClick={updateCursorPos}
      />
      <StepVariablePanel
        allSteps={allSteps}
        currentStepPosition={currentStepPosition}
        onInsertVariable={handleInsertVariable}
      />
    </div>
  )
}
