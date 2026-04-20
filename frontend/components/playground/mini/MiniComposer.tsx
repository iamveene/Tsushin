'use client'

/**
 * MiniComposer — auto-growing textarea + send button for Playground Mini.
 * Enter = send, Shift+Enter = newline, Ctrl/Cmd+Enter = send.
 */

import React, { forwardRef, useImperativeHandle, useLayoutEffect, useRef, useState } from 'react'
import { SendIcon } from '@/components/ui/icons'

export interface MiniComposerHandle {
  focus: () => void
}

interface MiniComposerProps {
  disabled?: boolean
  isSending?: boolean
  placeholder?: string
  onSend: (text: string) => void
}

const MAX_ROWS = 4

const MiniComposer = forwardRef<MiniComposerHandle, MiniComposerProps>(function MiniComposer(
  { disabled = false, isSending = false, placeholder = 'Message your agent…', onSend },
  ref,
) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useImperativeHandle(ref, () => ({
    focus: () => textareaRef.current?.focus(),
  }))

  useLayoutEffect(() => {
    const el = textareaRef.current
    if (!el) return
    // Auto-grow: reset height, measure, clamp to MAX_ROWS worth of lineHeight.
    el.style.height = 'auto'
    const lineHeight = parseInt(window.getComputedStyle(el).lineHeight || '20', 10) || 20
    const maxHeight = lineHeight * MAX_ROWS + 16 // + vertical padding
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`
    el.style.overflowY = el.scrollHeight > maxHeight ? 'auto' : 'hidden'
  }, [value])

  const doSend = () => {
    const text = value.trim()
    if (!text || disabled || isSending) return
    onSend(text)
    setValue('')
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter = send, Shift+Enter = newline, Ctrl/Cmd+Enter = send, Alt+Enter = ignore
    if (e.key !== 'Enter') return
    if (e.shiftKey) return
    if (e.altKey) return
    e.preventDefault()
    doSend()
  }

  return (
    <form
      className="flex items-end gap-2 px-3 py-2 border-t border-tsushin-border bg-tsushin-surface"
      onSubmit={e => {
        e.preventDefault()
        doSend()
      }}
    >
      <textarea
        ref={textareaRef}
        rows={1}
        value={value}
        disabled={disabled}
        onChange={e => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={disabled ? 'Select an agent to chat' : placeholder}
        className="flex-1 resize-none bg-tsushin-elevated border border-tsushin-border rounded-md px-3 py-2 text-sm text-gray-100 placeholder:text-tsushin-muted focus:outline-none focus:ring-1 focus:ring-tsushin-accent focus:border-tsushin-accent disabled:opacity-50 disabled:cursor-not-allowed"
        aria-label="Message composer"
      />
      <button
        type="submit"
        disabled={disabled || isSending || !value.trim()}
        aria-label="Send message"
        className="flex-shrink-0 w-9 h-9 rounded-md bg-tsushin-indigo hover:bg-tsushin-indigo-glow disabled:bg-tsushin-muted disabled:cursor-not-allowed text-white flex items-center justify-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tsushin-accent"
      >
        <SendIcon size={16} />
      </button>
    </form>
  )
})

export default MiniComposer
