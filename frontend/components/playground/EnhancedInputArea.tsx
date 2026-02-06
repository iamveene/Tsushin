'use client'

/**
 * Phase 16: Enhanced Input Area Component
 *
 * Chat input with:
 * - Slash command detection and inline suggestions
 * - Audio recording support
 * - File attachment
 * - Submit handling
 */

import React, { useState, useRef, useEffect, useCallback } from 'react'
import InlineCommands from './InlineCommands'

interface Command {
  id: number
  category: string
  command_name: string
  description?: string
  aliases: string[]
}

interface EnhancedInputAreaProps {
  value: string
  onChange: (value: string) => void
  onSubmit: (message: string, isCommand?: boolean) => void
  onCommandSelect: (command: Command) => void
  commands: Command[]
  disabled?: boolean
  placeholder?: string
  isRecording?: boolean
  onStartRecording?: () => void
  onStopRecording?: () => void
  onAttachFile?: () => void
  hasAudioCapability?: boolean
}

export default function EnhancedInputArea({
  value,
  onChange,
  onSubmit,
  onCommandSelect,
  commands,
  disabled = false,
  placeholder = "Type a message or press / for commands...",
  isRecording = false,
  onStartRecording,
  onStopRecording,
  onAttachFile,
  hasAudioCapability = false
}: EnhancedInputAreaProps) {
  const [showCommands, setShowCommands] = useState(false)
  const [selectedCommandIndex, setSelectedCommandIndex] = useState(0)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Detect slash command input
  useEffect(() => {
    // Show commands when input starts with /
    const startsWithSlash = value.startsWith('/')
    const hasNoSpace = !value.includes(' ') || value.split(' ').length <= 2
    setShowCommands(startsWithSlash && hasNoSpace)

    if (startsWithSlash) {
      setSelectedCommandIndex(0)
    }
  }, [value])

  // Filter commands for inline display
  const filteredCommands = useCallback(() => {
    if (!value.startsWith('/')) return []

    const searchLower = value.toLowerCase().replace(/^\//, '').split(' ')[0]

    return commands.filter(cmd =>
      cmd.command_name.toLowerCase().startsWith(searchLower) ||
      cmd.aliases.some(a => a.toLowerCase().startsWith(searchLower))
    ).slice(0, 8)
  }, [commands, value])

  const currentCommands = filteredCommands()

  // Handle command selection
  const handleCommandSelect = useCallback((command: Command) => {
    const commandText = `/${command.command_name} `
    onChange(commandText)
    setShowCommands(false)
    textareaRef.current?.focus()
    onCommandSelect(command)
  }, [onChange, onCommandSelect])

  // Handle keyboard events
  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (showCommands && currentCommands.length > 0) {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault()
          setSelectedCommandIndex(prev =>
            Math.min(prev + 1, currentCommands.length - 1)
          )
          break
        case 'ArrowUp':
          e.preventDefault()
          setSelectedCommandIndex(prev => Math.max(prev - 1, 0))
          break
        case 'Tab':
        case 'Enter':
          if (currentCommands[selectedCommandIndex]) {
            e.preventDefault()
            handleCommandSelect(currentCommands[selectedCommandIndex])
          }
          break
        case 'Escape':
          e.preventDefault()
          setShowCommands(false)
          break
      }
      return
    }

    // Normal enter to submit (Shift+Enter for new line)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (value.trim()) {
        const isCommand = value.startsWith('/')
        onSubmit(value.trim(), isCommand)
      }
    }
  }, [showCommands, currentCommands, selectedCommandIndex, handleCommandSelect, value, onSubmit])

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`
    }
  }, [value])

  return (
    <div className="relative p-4 bg-[#14141f] border-t border-white/10">
      {/* Inline Commands Dropdown */}
      <InlineCommands
        isOpen={showCommands}
        query={value}
        commands={currentCommands}
        selectedIndex={selectedCommandIndex}
        onSelect={handleCommandSelect}
        onClose={() => setShowCommands(false)}
        onNavigate={direction => {
          if (direction === 'up') {
            setSelectedCommandIndex(prev => Math.max(prev - 1, 0))
          } else {
            setSelectedCommandIndex(prev => Math.min(prev + 1, currentCommands.length - 1))
          }
        }}
      />

      {/* Input Area */}
      <div className="flex items-end gap-3">
        {/* Recording Button */}
        {hasAudioCapability && (
          <button
            onClick={isRecording ? onStopRecording : onStartRecording}
            disabled={disabled}
            className={`
              p-2.5 rounded-xl transition-all
              ${isRecording
                ? 'bg-red-500 text-white animate-pulse'
                : 'bg-white/5 text-white/60 hover:text-white hover:bg-white/10'}
            `}
            title={isRecording ? "Stop recording" : "Start recording"}
          >
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              {isRecording ? (
                <rect x="6" y="6" width="12" height="12" rx="2" />
              ) : (
                <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.91-3c-.49 0-.9.36-.98.85C16.52 14.2 14.47 16 12 16s-4.52-1.8-4.93-4.15c-.08-.49-.49-.85-.98-.85-.61 0-1.09.54-1 1.14.49 3 2.89 5.35 5.91 5.78V20c0 .55.45 1 1 1s1-.45 1-1v-2.08c3.02-.43 5.42-2.78 5.91-5.78.1-.6-.39-1.14-1-1.14z" />
              )}
            </svg>
          </button>
        )}

        {/* Attach Button */}
        {onAttachFile && (
          <button
            onClick={onAttachFile}
            disabled={disabled}
            className="p-2.5 rounded-xl bg-white/5 text-white/60 hover:text-white hover:bg-white/10 transition-colors"
            title="Attach file"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
            </svg>
          </button>
        )}

        {/* Text Input */}
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={e => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder={placeholder}
            rows={1}
            className="
              w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl
              text-white placeholder:text-white/40 resize-none
              focus:outline-none focus:border-teal-500/50 focus:ring-2 focus:ring-teal-500/20
              disabled:opacity-50 disabled:cursor-not-allowed
            "
            style={{ minHeight: '48px', maxHeight: '200px' }}
          />
        </div>

        {/* Send Button */}
        <button
          onClick={() => {
            if (value.trim()) {
              const isCommand = value.startsWith('/')
              onSubmit(value.trim(), isCommand)
            }
          }}
          disabled={disabled || !value.trim()}
          className={`
            p-2.5 rounded-xl transition-all
            ${value.trim()
              ? 'bg-teal-500 text-white hover:bg-teal-600'
              : 'bg-white/5 text-white/30'}
          `}
          title="Send message"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
          </svg>
        </button>
      </div>

      {/* Hint */}
      <p className="mt-2 text-xs text-white/30 text-center">
        Press <span className="font-mono bg-white/5 px-1 rounded">⌘K</span> for command palette
        • <span className="font-mono bg-white/5 px-1 rounded">/</span> for quick commands
      </p>
    </div>
  )
}
