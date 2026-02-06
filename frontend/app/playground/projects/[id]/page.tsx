'use client'

/**
 * Playground Project Workspace Page
 * Simplified chat interface for project conversations.
 * Configuration is done in Studio > Projects.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useRequireAuth } from '@/contexts/AuthContext'
import { api, Project, ProjectConversation, SlashCommand } from '@/lib/client'
import InlineCommands from '@/components/playground/InlineCommands'

export default function ProjectWorkspacePage() {
  useRequireAuth()
  const params = useParams()
  const projectId = Number(params.id)

  const [project, setProject] = useState<Project | null>(null)
  const [conversations, setConversations] = useState<ProjectConversation[]>([])
  const [selectedConversation, setSelectedConversation] = useState<ProjectConversation | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSending, setIsSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showSidebar, setShowSidebar] = useState(true)

  // Slash command state
  const [slashCommands, setSlashCommands] = useState<SlashCommand[]>([])
  const [inlineCommandsOpen, setInlineCommandsOpen] = useState(false)
  const [inlineQuery, setInlineQuery] = useState('')
  const [inlineSelectedIndex, setInlineSelectedIndex] = useState(0)

  // Message history for up arrow recall
  const [messageHistory, setMessageHistory] = useState<string[]>([])
  const [historyIndex, setHistoryIndex] = useState(-1)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const loadProject = useCallback(async () => {
    try {
      const data = await api.getProject(projectId)
      setProject(data)
    } catch (err: any) {
      setError(err.message || 'Failed to load project')
    }
  }, [projectId])

  const loadConversations = useCallback(async () => {
    try {
      const data = await api.getProjectConversations(projectId)
      setConversations(data)
      // Select first conversation or create new one
      if (data.length > 0 && !selectedConversation) {
        setSelectedConversation(data[0])
      }
    } catch (err: any) {
      console.error('Failed to load conversations:', err)
    }
  }, [projectId, selectedConversation])

  useEffect(() => {
    const init = async () => {
      setIsLoading(true)
      await loadProject()
      await loadConversations()
      // Load slash commands
      try {
        const commands = await api.getSlashCommands()
        setSlashCommands(commands)
      } catch (err) {
        console.error('Failed to load slash commands:', err)
      }
      setIsLoading(false)
    }
    init()
  }, [loadProject, loadConversations])

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [selectedConversation?.messages])

  // Listen for global refresh events
  useEffect(() => {
    const handleRefresh = async () => {
      await loadProject()
      await loadConversations()
    }
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => window.removeEventListener('tsushin:refresh', handleRefresh)
  }, [loadProject, loadConversations])

  const handleCreateConversation = async () => {
    try {
      const conv = await api.createProjectConversation(projectId)
      setConversations(prev => [conv, ...prev])
      setSelectedConversation(conv)
    } catch (err: any) {
      setError(err.message || 'Failed to create conversation')
    }
  }

  const handleSelectConversation = async (conv: ProjectConversation) => {
    try {
      const fullConv = await api.getProjectConversation(projectId, conv.id)
      setSelectedConversation(fullConv)
    } catch (err: any) {
      setError(err.message || 'Failed to load conversation')
    }
  }

  const handleSendMessage = async () => {
    if (!inputRef.current?.value.trim() || !selectedConversation || isSending) return

    const message = inputRef.current.value.trim()

    // Store in message history for up arrow recall
    setMessageHistory(prev => [...prev, message])
    setHistoryIndex(-1) // Reset history navigation

    inputRef.current.value = ''

    setIsSending(true)
    setError(null)

    try {
      const result = await api.sendProjectMessage(projectId, selectedConversation.id, message)

      if (result.conversation) {
        setSelectedConversation(result.conversation)
        // Update in list
        setConversations(prev => prev.map(c =>
          c.id === result.conversation.id ? result.conversation : c
        ))
      }
    } catch (err: any) {
      setError(err.message || 'Failed to send message')
    } finally {
      setIsSending(false)
      inputRef.current?.focus()
    }
  }

  const handleDeleteConversation = async (convId: number, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('Delete this conversation?')) return

    try {
      await api.deleteProjectConversation(projectId, convId)
      setConversations(prev => prev.filter(c => c.id !== convId))
      if (selectedConversation?.id === convId) {
        setSelectedConversation(conversations.find(c => c.id !== convId) || null)
      }
    } catch (err: any) {
      setError(err.message || 'Failed to delete conversation')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Handle message history recall with up/down arrows (when not in command mode)
    if (!inlineCommandsOpen && messageHistory.length > 0) {
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        // Navigate backwards through history
        const newIndex = historyIndex === -1 ? messageHistory.length - 1 : Math.max(0, historyIndex - 1)
        setHistoryIndex(newIndex)
        if (inputRef.current) {
          inputRef.current.value = messageHistory[newIndex]
          // Move cursor to end
          setTimeout(() => {
            if (inputRef.current) {
              inputRef.current.selectionStart = inputRef.current.value.length
              inputRef.current.selectionEnd = inputRef.current.value.length
            }
          }, 0)
        }
        return
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        // Navigate forwards through history
        if (historyIndex === -1) return // Already at the end
        const newIndex = historyIndex + 1
        if (newIndex >= messageHistory.length) {
          // Clear input when going past the end
          setHistoryIndex(-1)
          if (inputRef.current) {
            inputRef.current.value = ''
          }
        } else {
          setHistoryIndex(newIndex)
          if (inputRef.current) {
            inputRef.current.value = messageHistory[newIndex]
            // Move cursor to end
            setTimeout(() => {
              if (inputRef.current) {
                inputRef.current.selectionStart = inputRef.current.value.length
                inputRef.current.selectionEnd = inputRef.current.value.length
              }
            }, 0)
          }
        }
        return
      }
    }

    // Handle inline commands navigation
    if (inlineCommandsOpen) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setInlineSelectedIndex(prev => Math.min(prev + 1, 7))
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setInlineSelectedIndex(prev => Math.max(prev - 1, 0))
        return
      }
      if (e.key === 'Tab' || e.key === 'Enter') {
        e.preventDefault()
        // Get filtered commands to select from
        const searchLower = inlineQuery.toLowerCase()
        const filtered = slashCommands.filter(cmd =>
          cmd.command_name.toLowerCase().startsWith(searchLower) ||
          cmd.aliases.some(a => a.toLowerCase().startsWith(searchLower))
        ).slice(0, 8)
        if (filtered[inlineSelectedIndex]) {
          handleInlineCommandSelect(filtered[inlineSelectedIndex])
        }
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        setInlineCommandsOpen(false)
        return
      }
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendMessage()
    }
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value

    // Detect slash command input
    if (value.startsWith('/')) {
      const query = value.slice(1).split(' ')[0] // Get the command part only
      setInlineQuery(query)
      setInlineCommandsOpen(true)
      setInlineSelectedIndex(0)
    } else {
      setInlineCommandsOpen(false)
      setInlineQuery('')
    }
  }

  const handleInlineCommandSelect = (command: SlashCommand) => {
    if (inputRef.current) {
      // Replace input with full command, ready for args
      inputRef.current.value = `/${command.command_name} `
      inputRef.current.focus()
    }
    setInlineCommandsOpen(false)
    setInlineQuery('')
  }

  const getColorClass = (color: string) => {
    const colors: Record<string, string> = {
      blue: 'bg-blue-500',
      teal: 'bg-teal-500',
      indigo: 'bg-indigo-500',
      purple: 'bg-purple-500',
      pink: 'bg-pink-500',
      orange: 'bg-orange-500',
      green: 'bg-green-500',
    }
    return colors[color] || colors.blue
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-tsushin-bg via-gray-900 to-gray-950 flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-tsushin-teal/30 border-t-tsushin-teal rounded-full animate-spin"></div>
      </div>
    )
  }

  if (!project) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-tsushin-bg via-gray-900 to-gray-950 flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-lg text-tsushin-pearl mb-2">Project not found</h2>
          <Link href="/playground/projects" className="text-tsushin-teal hover:underline">
            Back to projects
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-tsushin-bg via-gray-900 to-gray-950 flex">
      {/* Sidebar */}
      {showSidebar && (
        <div className="w-64 flex-shrink-0 glass-card border-t-0 border-b-0 border-l-0 rounded-none flex flex-col">
          {/* Project Header */}
          <div className="p-4 border-b border-white/10">
            <div className="flex items-center gap-3 mb-3">
              <div className={`w-10 h-10 rounded-lg ${getColorClass(project.color)} flex items-center justify-center text-xl`}>
                {project.icon}
              </div>
              <div className="flex-1 min-w-0">
                <h2 className="font-semibold text-white truncate">{project.name}</h2>
              </div>
            </div>
            <Link
              href={`/agents/projects/${projectId}`}
              className="w-full py-1.5 px-2 text-xs text-white/50 hover:text-white hover:bg-white/5 rounded-lg flex items-center gap-2 transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              Configure in Studio
            </Link>
          </div>

          {/* New Conversation */}
          <div className="p-3">
            <button
              onClick={handleCreateConversation}
              className="w-full py-2 px-3 text-sm text-tsushin-slate hover:text-tsushin-pearl hover:bg-tsushin-surface rounded-lg flex items-center gap-2 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              New Conversation
            </button>
          </div>

          {/* Conversations List */}
          <div className="flex-1 overflow-y-auto px-3">
            <div className="space-y-1">
              {conversations.map((conv) => (
                <button
                  key={conv.id}
                  onClick={() => handleSelectConversation(conv)}
                  className={`w-full py-2 px-3 text-sm rounded-lg text-left group transition-colors ${
                    selectedConversation?.id === conv.id
                      ? 'bg-tsushin-teal/20 text-tsushin-pearl'
                      : 'text-tsushin-slate hover:text-tsushin-pearl hover:bg-tsushin-surface'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="truncate flex-1">{conv.title || 'New Conversation'}</span>
                    <button
                      onClick={(e) => handleDeleteConversation(conv.id, e)}
                      className="p-1 opacity-0 group-hover:opacity-100 text-tsushin-slate hover:text-tsushin-vermilion transition-all"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                  <span className="text-xs text-tsushin-muted">{conv.message_count} messages</span>
                </button>
              ))}
            </div>
          </div>

          {/* Footer */}
          <div className="p-3 border-t border-tsushin-border">
            <Link
              href="/playground/projects"
              className="flex items-center gap-2 text-sm text-tsushin-slate hover:text-tsushin-pearl transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              All Projects
            </Link>
          </div>
        </div>
      )}

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <header className="glass-card border-t-0 border-l-0 border-r-0 rounded-none px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowSidebar(!showSidebar)}
              className="p-2 text-white/50 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <span className="text-sm text-white">
              {selectedConversation?.title || 'Select or create a conversation'}
            </span>
          </div>
          <Link
            href={`/agents/projects/${projectId}`}
            className="p-2 text-white/50 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
            title="Configure in Studio"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </Link>
        </header>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4">
          {!selectedConversation ? (
            <div className="h-full flex items-center justify-center text-tsushin-muted text-sm">
              Select a conversation or create a new one
            </div>
          ) : selectedConversation.messages.length === 0 ? (
            <div className="h-full flex items-center justify-center">
              <div className="text-center">
                <div className={`w-16 h-16 mx-auto mb-4 rounded-2xl ${getColorClass(project.color)} flex items-center justify-center text-3xl`}>
                  {project.icon}
                </div>
                <p className="text-tsushin-pearl mb-1">Start a conversation</p>
                <p className="text-sm text-tsushin-muted max-w-md">
                  Ask questions about your uploaded documents or discuss topics related to this project.
                </p>
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto space-y-4">
              {selectedConversation.messages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div className={`
                    max-w-[80%] px-4 py-3 rounded-2xl text-sm whitespace-pre-wrap
                    ${msg.role === 'user'
                      ? 'bg-gradient-to-br from-teal-500 to-cyan-400 text-white rounded-tr-sm'
                      : 'glass-card rounded-tl-sm text-gray-100'
                    }
                  `}>
                    {msg.content}
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="px-4 py-2 bg-tsushin-vermilion/10 border-t border-tsushin-vermilion/20 flex items-center gap-2">
            <span className="text-sm text-tsushin-vermilion flex-1">{error}</span>
            <button onClick={() => setError(null)} className="text-tsushin-vermilion/80 hover:text-tsushin-vermilion">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        {/* Input */}
        <div className="glass-card border-b-0 border-l-0 border-r-0 rounded-none p-4">
          <div className="max-w-3xl mx-auto flex items-end gap-3">
            <div className="flex-1 relative">
              {/* Inline Commands Suggestions */}
              <InlineCommands
                isOpen={inlineCommandsOpen}
                query={inlineQuery}
                commands={slashCommands}
                selectedIndex={inlineSelectedIndex}
                onSelect={handleInlineCommandSelect}
                onClose={() => setInlineCommandsOpen(false)}
                onNavigate={(dir) => setInlineSelectedIndex(prev =>
                  dir === 'up' ? Math.max(prev - 1, 0) : Math.min(prev + 1, 7)
                )}
              />
              <textarea
                ref={inputRef}
                onKeyDown={handleKeyDown}
                onChange={handleInputChange}
                disabled={!selectedConversation || isSending}
                placeholder={selectedConversation ? "Type / for commands or a message..." : "Select a conversation first"}
                className="input w-full min-h-[52px] max-h-[200px] resize-none rounded-xl"
                rows={1}
              />
            </div>
            <button
              onClick={handleSendMessage}
              disabled={!selectedConversation || isSending}
              className="p-3.5 btn-primary rounded-xl disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSending ? (
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
              ) : (
                <svg className="w-5 h-5 transform rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </div>

    </div>
  )
}
