'use client'

/**
 * Phase 16: Command Palette Component
 *
 * A VS Code/Raycast-inspired command palette for quick access to all
 * commands and actions. Triggered by ⌘K or Ctrl+K.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react'
import { SlashCommand } from '@/lib/client'
import {
  BotIcon,
  FolderIcon,
  LightningIcon,
  WrenchIcon,
  BrainIcon,
  BookIcon,
  SettingsIcon,
  ClipboardIcon,
  IconProps
} from '@/components/ui/icons'

interface CommandPaletteProps {
  isOpen: boolean
  onClose: () => void
  onCommandSelect: (command: SlashCommand, args?: string) => void
  commands: SlashCommand[]
  agents?: Array<{ id: number; name: string; is_active?: boolean }>
  projects?: Array<{ id: number; name: string; document_count?: number }>
}

const CATEGORY_ICONS: Record<string, React.FC<IconProps>> = {
  invocation: BotIcon,
  project: FolderIcon,
  agent: LightningIcon,
  tool: WrenchIcon,
  memory: BrainIcon,
  kb: BookIcon,
  config: SettingsIcon,
  system: ClipboardIcon,
}

const CATEGORY_ORDER = ['invocation', 'project', 'agent', 'tool', 'memory', 'kb', 'config', 'system']

export default function CommandPalette({
  isOpen,
  onClose,
  onCommandSelect,
  commands,
  agents = [],
  projects = []
}: CommandPaletteProps) {
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  // Filter and organize commands
  const filteredCommands = useCallback(() => {
    let filtered = commands

    if (query) {
      const searchLower = query.toLowerCase().replace('/', '')
      filtered = commands.filter(cmd =>
        cmd.command_name.toLowerCase().includes(searchLower) ||
        cmd.description?.toLowerCase().includes(searchLower) ||
        cmd.aliases.some(a => a.toLowerCase().includes(searchLower)) ||
        cmd.category.toLowerCase().includes(searchLower)
      )
    }

    // Group by category
    const grouped: Record<string, SlashCommand[]> = {}
    for (const cmd of filtered) {
      if (!grouped[cmd.category]) {
        grouped[cmd.category] = []
      }
      grouped[cmd.category].push(cmd)
    }

    // Sort within categories
    for (const cat of Object.keys(grouped)) {
      grouped[cat].sort((a, b) => a.sort_order - b.sort_order)
    }

    // Build flat list with category headers
    const items: Array<{ type: 'category' | 'command'; data: string | SlashCommand }> = []
    for (const cat of CATEGORY_ORDER) {
      if (grouped[cat]?.length) {
        items.push({ type: 'category', data: cat })
        for (const cmd of grouped[cat]) {
          items.push({ type: 'command', data: cmd })
        }
      }
    }

    return items
  }, [commands, query])

  const items = filteredCommands()
  const commandItems = items.filter(i => i.type === 'command')

  // Reset selection when query changes
  useEffect(() => {
    setSelectedIndex(0)
  }, [query])

  // Focus input when opened
  useEffect(() => {
    if (isOpen) {
      setQuery('')
      setSelectedIndex(0)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [isOpen])

  // Scroll selected item into view
  useEffect(() => {
    if (listRef.current) {
      const selectedEl = listRef.current.querySelector('[data-selected="true"]')
      selectedEl?.scrollIntoView({ block: 'nearest' })
    }
  }, [selectedIndex])

  // Handle keyboard navigation
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    switch (e.key) {
      case 'Escape':
        e.preventDefault()
        onClose()
        break
      case 'ArrowDown':
        e.preventDefault()
        setSelectedIndex(prev =>
          Math.min(prev + 1, commandItems.length - 1)
        )
        break
      case 'ArrowUp':
        e.preventDefault()
        setSelectedIndex(prev => Math.max(prev - 1, 0))
        break
      case 'Enter':
        e.preventDefault()
        if (commandItems[selectedIndex]) {
          const cmd = commandItems[selectedIndex].data as SlashCommand
          onCommandSelect(cmd, query.includes(' ') ? query.split(' ').slice(1).join(' ') : undefined)
          onClose()
        }
        break
    }
  }, [commandItems, selectedIndex, onCommandSelect, onClose, query])

  if (!isOpen) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] bg-black/50 backdrop-blur-sm animate-fade-in"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[600px] bg-[#14141f] border border-white/10 rounded-2xl overflow-hidden shadow-2xl animate-slide-up"
        onClick={e => e.stopPropagation()}
      >
        {/* Search Input */}
        <div className="relative">
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a command or search..."
            className="w-full px-5 py-4 bg-transparent border-b border-white/10 text-white text-base outline-none placeholder:text-white/40"
          />
          <div className="absolute right-4 top-1/2 -translate-y-1/2 flex items-center gap-2">
            <span className="text-xs text-white/30 bg-[#0a0a0f] px-2 py-1 rounded">ESC</span>
          </div>
        </div>

        {/* Results */}
        <div ref={listRef} className="max-h-[400px] overflow-y-auto p-2">
          {items.length === 0 ? (
            <div className="p-8 text-center text-white/50">
              No commands found
            </div>
          ) : (
            items.map((item, idx) => {
              if (item.type === 'category') {
                return (
                  <div
                    key={`cat-${item.data}`}
                    className="px-3 py-2 text-xs font-semibold text-white/50 uppercase tracking-wider flex items-center gap-2"
                  >
                    {(() => {
                      const CategoryIcon = CATEGORY_ICONS[item.data as string] || ClipboardIcon
                      return <CategoryIcon size={14} />
                    })()}
                    {item.data}
                  </div>
                )
              }

              const cmd = item.data as SlashCommand
              const commandIndex = commandItems.findIndex(ci =>
                (ci.data as SlashCommand).id === cmd.id
              )
              const isSelected = commandIndex === selectedIndex

              return (
                <div
                  key={cmd.id}
                  data-selected={isSelected}
                  onClick={() => {
                    onCommandSelect(cmd)
                    onClose()
                  }}
                  className={`
                    flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-colors
                    ${isSelected ? 'bg-[#1a1a2e]' : 'hover:bg-[#1a1a2e]'}
                  `}
                >
                  <span className="text-white/60">
                    {(() => {
                      const CmdIcon = CATEGORY_ICONS[cmd.category] || ClipboardIcon
                      return <CmdIcon size={18} />
                    })()}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-white font-mono text-sm">/{cmd.command_name}</span>
                      {cmd.aliases.length > 0 && (
                        <span className="text-white/30 text-xs">
                          ({cmd.aliases.map(a => `/${a}`).join(', ')})
                        </span>
                      )}
                    </div>
                    {cmd.description && (
                      <p className="text-white/50 text-xs mt-0.5 truncate">{cmd.description}</p>
                    )}
                  </div>
                  {isSelected && (
                    <span className="text-xs text-white/30 bg-[#0a0a0f] px-2 py-1 rounded">↵</span>
                  )}
                </div>
              )
            })
          )}
        </div>

        {/* Footer hints */}
        <div className="px-4 py-3 border-t border-white/10 flex items-center gap-4 text-xs text-white/30">
          <span>↑↓ Navigate</span>
          <span>↵ Select</span>
          <span>⎋ Close</span>
        </div>
      </div>

      <style jsx>{`
        @keyframes fade-in {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes slide-up {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-fade-in {
          animation: fade-in 0.15s ease-out;
        }
        .animate-slide-up {
          animation: slide-up 0.2s ease-out;
        }
      `}</style>
    </div>
  )
}
