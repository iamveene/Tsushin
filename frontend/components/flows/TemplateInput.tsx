'use client'

/**
 * TemplateInput Component
 *
 * Single-line mirror of TemplateTextarea. Wraps an <input type="text"> with
 * the StepVariablePanel for template variable injection — click-to-insert
 * and drag-and-drop. Drop-in replacement for CursorSafeInput on fields that
 * accept {{step_N.field}} templates (recipient, gate_source_step, etc.).
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import type { InputHTMLAttributes, FocusEvent, DragEvent } from 'react'
import StepVariablePanel from './StepVariablePanel'

interface StepInfo {
  name: string
  type: string
  position: number
  config?: Record<string, any>
}

type NativeInputProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  'onChange' | 'value' | 'defaultValue' | 'type'
>

interface TemplateInputProps extends NativeInputProps {
  value: string
  onValueChange: (value: string) => void
  allSteps: StepInfo[]
  currentStepPosition: number
  type?: 'text'
}

export default function TemplateInput({
  value: externalValue,
  onValueChange,
  allSteps,
  currentStepPosition,
  className = '',
  onBlur: externalOnBlur,
  onFocus: externalOnFocus,
  type: _type,  // ignored — always text
  ...rest
}: TemplateInputProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const cursorPosRef = useRef<number>(externalValue.length)
  const [localValue, setLocalValue] = useState(externalValue)
  const isFocusedRef = useRef(false)

  useEffect(() => {
    if (!isFocusedRef.current) {
      setLocalValue(externalValue)
    }
  }, [externalValue])

  const updateCursorPos = useCallback(() => {
    const el = inputRef.current
    if (el) {
      cursorPosRef.current = el.selectionStart ?? localValue.length
    }
  }, [localValue.length])

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
      const el = inputRef.current
      if (el) {
        el.focus()
        el.selectionStart = newCursorPos
        el.selectionEnd = newCursorPos
      }
    })
  }, [localValue, onValueChange])

  const handleInsertVariable = useCallback((template: string) => {
    insertAt(template, cursorPosRef.current)
  }, [insertAt])

  const handleDrop = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    const template = e.dataTransfer.getData('text/plain')
    if (!template) return
    // Inputs don't expose reliable caret-from-point; insert at last cursor.
    insertAt(template, cursorPosRef.current)
  }, [insertAt])

  const handleDragOver = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
  }, [])

  const defaultClassName = `w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm
    focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none`

  return (
    <div>
      <div onDragOver={handleDragOver} onDrop={handleDrop}>
        <input
          {...rest}
          type="text"
          ref={inputRef}
          value={localValue}
          className={className || defaultClassName}
          onFocus={(e: FocusEvent<HTMLInputElement>) => {
            isFocusedRef.current = true
            updateCursorPos()
            if (externalOnFocus) externalOnFocus(e)
          }}
          onBlur={(e: FocusEvent<HTMLInputElement>) => {
            updateCursorPos()
            isFocusedRef.current = false
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
