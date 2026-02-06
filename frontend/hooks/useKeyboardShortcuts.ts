'use client'

/**
 * Phase 17: Global Keyboard Shortcuts Hook
 *
 * Provides global keyboard shortcuts for the playground:
 * - ⌘K / Ctrl+K: Open command palette
 * - ⌘1 / Ctrl+1: Switch to Simple/Chat tab
 * - ⌘2 / Ctrl+2: Switch to Expert/Cockpit tab
 * - ⌘. / Ctrl+.: Toggle cockpit mode (legacy)
 * - ⌘/ / Ctrl+/: Focus input with /
 * - ⌘T / Ctrl+T: Tool Sandbox
 * - ⌘M / Ctrl+M: Memory Panel
 * - Escape: Exit current mode/close modal
 */

import { useEffect, useCallback } from 'react'

interface ShortcutHandlers {
  onCommandPalette?: () => void
  onToggleCockpit?: () => void
  onSwitchToSimple?: () => void
  onSwitchToExpert?: () => void
  onFocusInput?: () => void
  onProjectSwitcher?: () => void
  onAgentSwitcher?: () => void
  onEscape?: () => void
  onToolMenu?: () => void
  onMemoryPanel?: () => void
}

export function useKeyboardShortcuts(handlers: ShortcutHandlers) {
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    // Check for modifier key (Meta on Mac, Ctrl on Windows/Linux)
    const modKey = e.metaKey || e.ctrlKey

    // Don't trigger shortcuts when typing in inputs (unless it's a shortcut)
    const isInputFocused =
      document.activeElement?.tagName === 'INPUT' ||
      document.activeElement?.tagName === 'TEXTAREA' ||
      (document.activeElement as HTMLElement)?.isContentEditable

    // ⌘K / Ctrl+K - Command Palette
    if (modKey && e.key === 'k') {
      e.preventDefault()
      handlers.onCommandPalette?.()
      return
    }

    // ⌘1 / Ctrl+1 - Switch to Simple/Chat tab
    if (modKey && e.key === '1') {
      e.preventDefault()
      handlers.onSwitchToSimple?.()
      return
    }

    // ⌘2 / Ctrl+2 - Switch to Expert/Cockpit tab
    if (modKey && e.key === '2') {
      e.preventDefault()
      handlers.onSwitchToExpert?.()
      return
    }

    // ⌘. / Ctrl+. - Toggle Cockpit Mode (legacy support)
    if (modKey && e.key === '.') {
      e.preventDefault()
      handlers.onToggleCockpit?.()
      return
    }

    // ⌘/ / Ctrl+/ - Focus Input with /
    if (modKey && e.key === '/') {
      e.preventDefault()
      handlers.onFocusInput?.()
      return
    }

    // ⌘P / Ctrl+P - Project Switcher (prevent browser print)
    if (modKey && e.key === 'p') {
      e.preventDefault()
      handlers.onProjectSwitcher?.()
      return
    }

    // ⌘E / Ctrl+E - Agent Switcher
    if (modKey && e.key === 'e') {
      e.preventDefault()
      handlers.onAgentSwitcher?.()
      return
    }

    // ⌘T / Ctrl+T - Tool Menu (without shift, doesn't conflict with browser new tab in most cases)
    if (modKey && !e.shiftKey && e.key === 't') {
      e.preventDefault()
      handlers.onToolMenu?.()
      return
    }

    // ⌘M / Ctrl+M - Memory Panel
    if (modKey && !e.shiftKey && e.key === 'm') {
      e.preventDefault()
      handlers.onMemoryPanel?.()
      return
    }

    // Escape - Close/Exit
    if (e.key === 'Escape') {
      // Only trigger if not in an input (let forms handle their own escape)
      if (!isInputFocused) {
        handlers.onEscape?.()
      }
      return
    }
  }, [handlers])

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])
}

/**
 * Helper to check if command key is pressed (platform-aware)
 */
export function isModifierKey(e: KeyboardEvent | React.KeyboardEvent): boolean {
  return e.metaKey || e.ctrlKey
}

/**
 * Get the modifier key symbol for display (⌘ on Mac, Ctrl on others)
 */
export function getModifierSymbol(): string {
  if (typeof navigator !== 'undefined' && navigator.platform.includes('Mac')) {
    return '⌘'
  }
  return 'Ctrl'
}

/**
 * Format a shortcut for display
 */
export function formatShortcut(key: string, shift = false): string {
  const mod = getModifierSymbol()
  if (shift) {
    return `${mod}⇧${key.toUpperCase()}`
  }
  return `${mod}${key.toUpperCase()}`
}
