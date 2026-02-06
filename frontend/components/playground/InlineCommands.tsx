'use client'

/**
 * Phase 16: Inline Commands Component
 *
 * Shows command suggestions when user types "/" in the input field.
 * Discord/Slack-style command autocomplete.
 *
 * Enhanced to show tool suggestions when typing "/tool "
 */

import React, { useEffect, useRef, useCallback } from 'react'
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
  SyringeIcon,
  IconProps
} from '@/components/ui/icons'

interface InlineCommandsProps {
  isOpen: boolean
  query: string
  commands: SlashCommand[]
  selectedIndex: number
  onSelect: (command: SlashCommand) => void
  onClose: () => void
  onNavigate: (direction: 'up' | 'down') => void
  availableTools?: string[]  // Tool suggestions for /tool command
  availableAgents?: string[]  // Agent suggestions for /invoke and /switch
  injectTargets?: string[]  // Inject targets for /inject command
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

export default function InlineCommands({
  isOpen,
  query,
  commands,
  selectedIndex,
  onSelect,
  onClose,
  onNavigate,
  availableTools = [],
  availableAgents = [],
  injectTargets = []
}: InlineCommandsProps) {
  const listRef = useRef<HTMLDivElement>(null)

  // Utility to parse command hierarchy
  const parseCommandQuery = useCallback((query: string) => {
    const searchLower = query.toLowerCase().replace(/^\//, '')
    const parts = searchLower.trim().split(/\s+/)
    return {
      baseCommand: parts[0],
      subCommand: parts.slice(1).join(' '),
      hasSpace: searchLower.includes(' ')
    }
  }, [])

  // Filter commands based on query with hierarchical support
  const filteredCommands = useCallback(() => {
    if (!query) return commands.slice(0, 8)

    const searchLower = query.toLowerCase().replace(/^\//, '')
    const { baseCommand, subCommand, hasSpace } = parseCommandQuery(query)

    // Multi-level commands that support hierarchical filtering
    const hierarchicalCommands = ['project', 'agent', 'inject', 'invoke', 'switch', 'tool']

    if (hasSpace && hierarchicalCommands.includes(baseCommand)) {
      // For hierarchical commands with space, show matching subcommands
      const matchingCommands = commands.filter(cmd => {
        const cmdName = cmd.command_name.toLowerCase()
        // Check if this command belongs to the base command
        if (!cmdName.startsWith(baseCommand)) return false

        // If we have a subcommand search, filter by it
        if (subCommand) {
          const cmdSubpart = cmdName.replace(baseCommand, '').trim()
          return cmdSubpart.startsWith(subCommand)
        }

        // Otherwise show all commands for this base
        return true
      })

      return matchingCommands.slice(0, 8)
    }

    // Normal prefix matching when no space
    return commands.filter(cmd =>
      cmd.command_name.toLowerCase().startsWith(searchLower) ||
      cmd.aliases.some(a => a.toLowerCase().startsWith(searchLower))
    ).slice(0, 8)
  }, [commands, query, parseCommandQuery])

  const filtered = filteredCommands()

  // Determine which suggestion type to show
  const getSuggestionType = useCallback(() => {
    const searchLower = query.toLowerCase().replace(/^\//, '')

    if (searchLower.startsWith('tool ') && availableTools.length > 0) {
      return 'tools'
    }
    if ((searchLower.startsWith('invoke ') || searchLower.startsWith('switch ')) && availableAgents.length > 0) {
      return 'agents'
    }
    if (searchLower.startsWith('inject ') && injectTargets.length > 0) {
      return 'inject'
    }

    return 'commands'
  }, [query, availableTools, availableAgents, injectTargets])

  const suggestionType = getSuggestionType()

  // Filter tool suggestions
  const filteredToolSuggestions = useCallback(() => {
    if (suggestionType !== 'tools') return []

    const searchLower = query.toLowerCase().replace(/^\//, '')
    const afterTool = searchLower.replace(/^tool\s+/, '')

    if (!afterTool) return availableTools.slice(0, 8)

    return availableTools.filter(tool =>
      tool.toLowerCase().startsWith(afterTool)
    ).slice(0, 8)
  }, [query, availableTools, suggestionType])

  // Filter agent suggestions (for invoke/switch)
  const filteredAgentSuggestions = useCallback(() => {
    if (suggestionType !== 'agents') return []

    const searchLower = query.toLowerCase().replace(/^\//, '')
    const afterCommand = searchLower.replace(/^(invoke|switch)\s+/, '')

    if (!afterCommand) return availableAgents.slice(0, 8)

    return availableAgents.filter(agent =>
      agent.toLowerCase().startsWith(afterCommand)
    ).slice(0, 8)
  }, [query, availableAgents, suggestionType])

  // Filter inject target suggestions
  const filteredInjectSuggestions = useCallback(() => {
    if (suggestionType !== 'inject') return []

    const searchLower = query.toLowerCase().replace(/^\//, '')
    const afterInject = searchLower.replace(/^inject\s+/, '')

    if (!afterInject) return injectTargets.slice(0, 8)

    return injectTargets.filter(target =>
      target.toLowerCase().startsWith(afterInject)
    ).slice(0, 8)
  }, [query, injectTargets, suggestionType])

  const toolSuggestions = filteredToolSuggestions()
  const agentSuggestions = filteredAgentSuggestions()
  const injectSuggestions = filteredInjectSuggestions()

  // Total items for keyboard navigation
  const totalItems = suggestionType === 'tools' ? toolSuggestions.length :
                     suggestionType === 'agents' ? agentSuggestions.length :
                     suggestionType === 'inject' ? injectSuggestions.length :
                     filtered.length

  // Scroll selected item into view
  useEffect(() => {
    if (listRef.current) {
      const selectedEl = listRef.current.querySelector('[data-selected="true"]')
      selectedEl?.scrollIntoView({ block: 'nearest' })
    }
  }, [selectedIndex])

  if (!isOpen || (filtered.length === 0 && toolSuggestions.length === 0 && agentSuggestions.length === 0 && injectSuggestions.length === 0)) return null

  // Determine header text based on suggestion type
  const headerText = suggestionType === 'tools' ? 'Available Tools' :
                     suggestionType === 'agents' ? 'Available Agents' :
                     suggestionType === 'inject' ? 'Inject Targets' :
                     'Commands'

  return (
    <div
      ref={listRef}
      className="absolute bottom-full left-0 right-0 mb-2 bg-[#14141f] border border-white/10 rounded-xl overflow-hidden shadow-2xl max-h-[300px] overflow-y-auto animate-slide-up z-50"
    >
      {/* Header */}
      <div className="px-4 py-2 border-b border-white/10 flex items-center justify-between">
        <span className="text-xs text-white/50 font-semibold uppercase tracking-wider">
          {headerText}
        </span>
        <span className="text-xs text-white/30">↑↓ Navigate • Tab/Enter Select • Esc Close</span>
      </div>

      {/* Tool suggestions (when typing /tool) */}
      {suggestionType === 'tools' && (
        <div className="p-1">
          {toolSuggestions.map((tool, idx) => {
            const isSelected = idx === selectedIndex

            return (
              <div
                key={tool}
                data-selected={isSelected}
                onClick={() => {
                  // Insert the tool name into the input
                  const event = new CustomEvent('tool-selected', { detail: tool })
                  window.dispatchEvent(event)
                }}
                className={`
                  flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-colors
                  ${isSelected ? 'bg-teal-500/20 border border-teal-500/30' : 'hover:bg-white/5'}
                `}
              >
                <span className="text-white/60">
                  <WrenchIcon size={18} />
                </span>

                <div className="flex-1 min-w-0">
                  <span className="text-white font-mono text-sm font-medium">
                    {tool}
                  </span>
                  <p className="text-white/50 text-xs mt-0.5 truncate">
                    /tool {tool} [command] [args]
                  </p>
                </div>

                {isSelected && (
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-white/30 bg-[#0a0a0f] px-1.5 py-0.5 rounded">Tab</span>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Agent suggestions (when typing /invoke or /switch) */}
      {suggestionType === 'agents' && (
        <div className="p-1">
          {agentSuggestions.map((agent, idx) => {
            const isSelected = idx === selectedIndex

            return (
              <div
                key={agent}
                data-selected={isSelected}
                onClick={() => {
                  const event = new CustomEvent('agent-selected', { detail: agent })
                  window.dispatchEvent(event)
                }}
                className={`
                  flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-colors
                  ${isSelected ? 'bg-teal-500/20 border border-teal-500/30' : 'hover:bg-white/5'}
                `}
              >
                <span className="text-white/60">
                  <BotIcon size={18} />
                </span>

                <div className="flex-1 min-w-0">
                  <span className="text-white font-mono text-sm font-medium">
                    {agent}
                  </span>
                  <p className="text-white/50 text-xs mt-0.5 truncate">
                    {query.includes('invoke') ? `/invoke ${agent}` : `/switch ${agent}`}
                  </p>
                </div>

                {isSelected && (
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-white/30 bg-[#0a0a0f] px-1.5 py-0.5 rounded">Tab</span>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Inject target suggestions (when typing /inject) */}
      {suggestionType === 'inject' && (
        <div className="p-1">
          {injectSuggestions.map((target, idx) => {
            const isSelected = idx === selectedIndex

            return (
              <div
                key={target}
                data-selected={isSelected}
                onClick={() => {
                  const event = new CustomEvent('inject-selected', { detail: target })
                  window.dispatchEvent(event)
                }}
                className={`
                  flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-colors
                  ${isSelected ? 'bg-teal-500/20 border border-teal-500/30' : 'hover:bg-white/5'}
                `}
              >
                <span className="text-white/60">
                  <SyringeIcon size={18} />
                </span>

                <div className="flex-1 min-w-0">
                  <span className="text-white font-mono text-sm font-medium">
                    {target}
                  </span>
                  <p className="text-white/50 text-xs mt-0.5 truncate">
                    /inject {target}
                  </p>
                </div>

                {isSelected && (
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-white/30 bg-[#0a0a0f] px-1.5 py-0.5 rounded">Tab</span>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Command list (normal commands) */}
      {suggestionType === 'commands' && (
        <div className="p-1">
          {filtered.map((cmd, idx) => {
            const isSelected = idx === selectedIndex

            return (
              <div
                key={cmd.id}
                data-selected={isSelected}
                onClick={() => onSelect(cmd)}
                className={`
                  flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-colors
                  ${isSelected ? 'bg-teal-500/20 border border-teal-500/30' : 'hover:bg-white/5'}
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
                    <span className="text-white font-mono text-sm font-medium">
                      /{cmd.command_name}
                    </span>
                    {cmd.aliases.length > 0 && (
                      <span className="text-white/30 text-xs">
                        also: {cmd.aliases.map(a => `/${a}`).join(', ')}
                      </span>
                    )}
                  </div>
                  {cmd.description && (
                    <p className="text-white/50 text-xs mt-0.5 truncate">{cmd.description}</p>
                  )}
                </div>

                {isSelected && (
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-white/30 bg-[#0a0a0f] px-1.5 py-0.5 rounded">Tab</span>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      <style jsx>{`
        @keyframes slide-up {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-slide-up {
          animation: slide-up 0.15s ease-out;
        }
      `}</style>
    </div>
  )
}
