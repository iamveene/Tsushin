'use client'

/**
 * Playground Interface - Professional IDE-style Chat Interface
 * Information-dense, keyboard-driven, feature-rich
 */

import React, { useState, useRef, useEffect } from 'react'
import { PlaygroundAgentInfo, PlaygroundMessage, SlashCommand, ProjectSession, Project, AudioCapabilities, PlaygroundThread } from '@/lib/client'
import { ConnectionState } from '@/lib/websocket'
import { formatTime } from '@/lib/dateUtils'
import {
  BotIcon,
  FolderIcon,
  FolderOpenIcon,
  MessageIcon,
  LightningIcon,
  BrainIcon,
  BookIcon,
  BugIcon,
  SettingsIcon,
  TargetIcon,
  ArchiveIcon,
  SearchIcon,
  WrenchIcon,
  GlobeIcon,
  TerminalIcon,
  LinkIcon,
  DatabaseIcon
} from '@/components/ui/icons'
import InlineCommands from './InlineCommands'
import MemoryInspector from './MemoryInspector'
import DebugPanel from './DebugPanel'
import ConfigPanel from './ConfigPanel'
import SkillsPanel from './SkillsPanel'
import KnowledgeTab from './KnowledgeTab'
import KBUsageBadge from './KBUsageBadge'
import QuickToolInvoke from './QuickToolInvoke'
import ThreadListSidebar from './ThreadListSidebar'
import ThreadHeader from './ThreadHeader'
import MessageActions from './MessageActions'
import CollapsibleNavSection from './CollapsibleNavSection'
import StreamingMessage from './StreamingMessage'

type InspectorTab = 'memory' | 'debug' | 'config' | 'skills' | 'knowledge'

interface SelectedTool {
  id: string
  name: string
  icon: string
  description: string
}

interface ExpertModeProps {
  agents: PlaygroundAgentInfo[]
  projects: Project[]
  selectedAgentId: number | null
  agentName: string
  messages: PlaygroundMessage[]
  isSending: boolean
  isLoadingHistory: boolean
  projectSession: ProjectSession | null
  isLoadingProjectSession?: boolean
  slashCommands: SlashCommand[]
  error: string | null
  onAgentSelect: (id: number) => void
  onProjectSelect: (id: number) => void
  onSendMessage: () => void
  onClearHistory: () => void
  onExitProject: () => void
  onToolSelect: (toolName: string) => void
  inputRef: React.RefObject<HTMLTextAreaElement>
  onInputChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void
  onKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void
  inlineCommandsOpen: boolean
  inlineQuery: string
  inlineSelectedIndex: number
  onInlineCommandSelect: (cmd: SlashCommand) => void
  onCloseInlineCommands: () => void
  onNavigateInlineCommands: (dir: 'up' | 'down') => void
  availableTools?: string[]
  availableAgents?: string[]
  injectTargets?: string[]
  // Audio recording props
  audioCapabilities?: AudioCapabilities | null
  isRecording?: boolean
  recordingTime?: number
  audioBlob?: Blob | null
  audioUrl?: string | null
  onStartRecording?: () => void
  onStopRecording?: () => void
  onCancelRecording?: () => void
  onSendAudio?: () => void
  isProcessingAudio?: boolean
  // File upload props
  fileInputRef?: React.RefObject<HTMLInputElement>
  onFileUpload?: (files: FileList) => void
  documentsCount?: number
  // Phase 14.1 & 14.2: Thread Management props
  threads?: PlaygroundThread[]
  activeThreadId?: number | null
  activeThread?: PlaygroundThread | null
  showThreadSidebar?: boolean
  isLoadingThreads?: boolean
  isLoadingThread?: boolean
  threadLoadError?: string | null
  onNewThread?: () => void
  onThreadSelect?: (threadId: number) => void
  onThreadDeleted?: () => void
  onThreadUpdated?: () => void
  onThreadRenamed?: (threadId: number, newTitle: string) => void
  // Phase 14.5 & 14.6: Search and Knowledge props
  onOpenSearch?: () => void
  onExtractKnowledge?: () => void
  onToggleThreadSidebar?: () => void
  // Phase 14.9: WebSocket streaming props
  streamingMessage?: Partial<PlaygroundMessage> | null
  connectionState?: ConnectionState
}

interface QuickTool {
  id: string
  icon: React.ReactNode
  name: string
  description?: string
}

// Tool icon mapping using SVG icons
const TOOL_ICON_COMPONENTS: Record<string, React.FC<{size?: number; className?: string}>> = {
  'nmap': SearchIcon,
  'nuclei': LightningIcon,
  'katana': GlobeIcon,
  'httpx': GlobeIcon,
  'subfinder': SearchIcon,
  'dig': TerminalIcon,
  'whois_lookup': SearchIcon,
  'webhook': LinkIcon,
  'sqlmap': DatabaseIcon,
  'python': WrenchIcon,
  'default': WrenchIcon,
}

// Display name overrides for tools with acronyms or special casing
const TOOL_DISPLAY_NAMES: Record<string, string> = {
  'nmap': 'Nmap',
  'httpx': 'HTTPX',
  'sqlmap': 'SQLMap',
  'dig': 'DIG',
}

function formatToolName(rawName: string): string {
  if (TOOL_DISPLAY_NAMES[rawName]) return TOOL_DISPLAY_NAMES[rawName]
  return rawName
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

export default function ExpertMode({
  agents,
  projects,
  selectedAgentId,
  agentName,
  messages,
  isSending,
  isLoadingHistory,
  projectSession,
  isLoadingProjectSession = false,
  slashCommands,
  error,
  onAgentSelect,
  onProjectSelect,
  onSendMessage,
  onClearHistory,
  onExitProject,
  onToolSelect,
  inputRef,
  onInputChange,
  onKeyDown,
  inlineCommandsOpen,
  inlineQuery,
  inlineSelectedIndex,
  onInlineCommandSelect,
  onCloseInlineCommands,
  onNavigateInlineCommands,
  availableTools = [],
  availableAgents = [],
  injectTargets = [],
  // Audio recording props
  audioCapabilities = null,
  isRecording = false,
  recordingTime = 0,
  audioBlob = null,
  audioUrl = null,
  onStartRecording,
  onStopRecording,
  onCancelRecording,
  onSendAudio,
  isProcessingAudio = false,
  // File upload props
  fileInputRef,
  onFileUpload,
  documentsCount = 0,
  // Phase 14.1 & 14.2: Thread Management props
  threads = [],
  activeThreadId = null,
  activeThread = null,
  showThreadSidebar = true,
  isLoadingThreads = false,
  isLoadingThread = false,
  threadLoadError = null,
  onNewThread,
  onThreadSelect,
  onThreadDeleted,
  onThreadUpdated,
  onThreadRenamed,
  onToggleThreadSidebar,
  // Phase 14.5 & 14.6: Search and Knowledge props
  onOpenSearch,
  onExtractKnowledge,
  // Phase 14.9: WebSocket streaming props
  streamingMessage = null,
  connectionState = 'disconnected'
}: ExpertModeProps) {
  const [activeInspector, setActiveInspector] = useState<InspectorTab>('memory')
  const [leftCollapsed, setLeftCollapsed] = useState(false)
  const [rightCollapsed, setRightCollapsed] = useState(false)
  const [quickTools, setQuickTools] = useState<QuickTool[]>([])
  const [loadingTools, setLoadingTools] = useState(false)
  const [selectedToolForInvoke, setSelectedToolForInvoke] = useState<SelectedTool | null>(null)
  const [showAllTools, setShowAllTools] = useState(false)
  const [toolSearchQuery, setToolSearchQuery] = useState('')
  const [threadContextMenu, setThreadContextMenu] = useState<{ threadId: number; x: number; y: number } | null>(null)
  const [renamingThreadId, setRenamingThreadId] = useState<number | null>(null)
  const [renameTitle, setRenameTitle] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Accordion state for left panel sections
  const [expandedSection, setExpandedSection] = useState<'agents' | 'projects' | 'threads' | 'tools'>('agents')

  // Tools display limit in sidebar (show "View all" when more than this)
  const TOOLS_DISPLAY_LIMIT = 4

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // BUG-012 Fix: Fetch agent-specific tools instead of global tools
  useEffect(() => {
    const loadAvailableTools = async () => {
      if (!selectedAgentId) {
        setQuickTools([])
        return
      }

      setLoadingTools(true)
      try {
        const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8081'
        const token = localStorage.getItem('tsushin_auth_token')

        // Use agent-specific tools endpoint instead of global toolbox
        const response = await fetch(`${baseUrl}/api/playground/tools/${selectedAgentId}`, {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        })

        if (response.ok) {
          const data = await response.json()
          // Agent tools endpoint returns array directly (not { tools: [...] })
          const toolsArray = Array.isArray(data) ? data : (data.tools || [])
          const tools: QuickTool[] = toolsArray.map((tool: any) => {
            const toolName = tool.name || String(tool.id)
            const IconComponent = TOOL_ICON_COMPONENTS[toolName] || TOOL_ICON_COMPONENTS.default
            return {
              id: toolName,
              icon: <IconComponent size={16} />,
              name: formatToolName(toolName),
              description: tool.description || ''
            }
          })
          setQuickTools(tools)
        } else {
          // Fallback to empty if API fails
          setQuickTools([])
        }
      } catch (error) {
        console.error('Failed to load agent tools:', error)
        setQuickTools([])
      } finally {
        setLoadingTools(false)
      }
    }

    loadAvailableTools()
  }, [selectedAgentId])

  const formatTimestamp = (timestamp: string) => formatTime(timestamp)

  // Handler to open Quick Tool Invoke
  const handleQuickToolClick = (tool: QuickTool) => {
    setSelectedToolForInvoke({
      id: tool.id,
      name: tool.name,
      icon: tool.icon,
      description: tool.description || ''
    })
  }

  // Handler to execute tool command from QuickToolInvoke
  const handleToolExecute = (command: string) => {
    // Put the command in the input and send it
    if (inputRef.current) {
      inputRef.current.value = `/tool ${command}`
      // Trigger the send
      onSendMessage()
    }
  }

  // Thread management handlers
  const handleDeleteThread = async (threadId: number) => {
    if (!confirm('Delete this conversation? This action cannot be undone.')) return

    try {
      const { api } = await import('@/lib/client')
      await api.deleteThread(threadId)
      if (onThreadDeleted) {
        onThreadDeleted()
      }
      setThreadContextMenu(null)
    } catch (err) {
      console.error('Failed to delete thread:', err)
    }
  }

  const handleArchiveThread = async (threadId: number, currentArchived: boolean) => {
    try {
      const { api } = await import('@/lib/client')
      await api.updateThread(threadId, { is_archived: !currentArchived })
      if (onThreadUpdated) {
        onThreadUpdated()
      }
      setThreadContextMenu(null)
    } catch (err) {
      console.error('Failed to archive thread:', err)
    }
  }

  const handleExportThread = async (threadId: number) => {
    try {
      const { api } = await import('@/lib/client')
      const exportData = await api.exportThread(threadId)
      const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `thread-${threadId}-${new Date().toISOString().slice(0, 10)}.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      setThreadContextMenu(null)
    } catch (err) {
      console.error('Failed to export thread:', err)
    }
  }

  const handleStartRename = (threadId: number) => {
    const thread = threads.find(t => t.id === threadId)
    if (thread) {
      setRenamingThreadId(threadId)
      setRenameTitle(thread.title || '')
      setThreadContextMenu(null)
    }
  }

  const handleCancelRename = () => {
    setRenamingThreadId(null)
    setRenameTitle('')
  }

  const handleSaveRename = async () => {
    if (!renamingThreadId || !renameTitle.trim()) {
      handleCancelRename()
      return
    }

    try {
      const { api } = await import('@/lib/client')
      await api.updateThread(renamingThreadId, { title: renameTitle.trim() })
      if (onThreadUpdated) {
        onThreadUpdated()
      }
      handleCancelRename()
    } catch (err) {
      console.error('Failed to rename thread:', err)
    }
  }

  // Accordion section toggle handler
  const handleSectionToggle = (sectionId: string) => {
    setExpandedSection(sectionId as 'agents' | 'projects' | 'threads' | 'tools')
  }

  // Get preview content for collapsed sections
  const getAgentsPreview = () => {
    const selectedAgent = agents.find(a => a.id === selectedAgentId)
    if (selectedAgent) {
      return (
        <span className="flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full ${selectedAgent.is_active ? 'bg-green-500' : 'bg-gray-500'}`} />
          {selectedAgent.name}
        </span>
      )
    }
    return <span className="text-[var(--pg-text-muted)]">No agent selected</span>
  }

  const getProjectsPreview = () => {
    const activeProject = projects.find(p => p.id === projectSession?.project_id)
    if (activeProject) {
      return (
        <span className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--pg-accent)] animate-pulse" />
          {activeProject.name}
        </span>
      )
    }
    if (projects.length === 0) {
      return <span className="text-[var(--pg-text-muted)]">No projects</span>
    }
    return <span className="text-[var(--pg-text-muted)]">No project active</span>
  }

  const getThreadsPreview = () => {
    const activeThreadData = threads?.find(t => t.id === activeThreadId)
    if (activeThreadData) {
      return (
        <span className="truncate">
          {activeThreadData.title || 'New Conversation'}
        </span>
      )
    }
    if (threads && threads.length > 0) {
      return <span className="text-[var(--pg-text-muted)]">{threads.length} conversations</span>
    }
    return <span className="text-[var(--pg-text-muted)]">No threads</span>
  }

  const getToolsPreview = () => {
    if (loadingTools) {
      return <span className="text-[var(--pg-text-muted)]">Loading...</span>
    }
    if (quickTools.length > 0) {
      return <span className="text-[var(--pg-text-muted)]">{quickTools.length} available</span>
    }
    return <span className="text-[var(--pg-text-muted)]">No tools</span>
  }

  return (
    <div className="cockpit-mode flex flex-col h-full">
      {/* Project Session Banner (only shown when in project) */}
      {projectSession?.is_in_project && (
        <div className="flex items-center justify-between px-4 py-2 bg-[var(--pg-amber-glow)] border-b border-[var(--pg-amber)]/30">
          <div className="flex items-center gap-2 text-[var(--pg-amber)] text-xs font-medium">
            <FolderOpenIcon size={14} />
            <span>Working in: {projectSession.project_name}</span>
            {isLoadingProjectSession && (
              <span className="inline-block w-3 h-3 border-2 border-[var(--pg-amber)]/30 border-t-[var(--pg-amber)] rounded-full animate-spin" title="Refreshing..." />
            )}
          </div>
          <button
            onClick={onExitProject}
            className="text-[var(--pg-amber)] text-xs hover:underline"
          >
            Exit Project
          </button>
        </div>
      )}

      {/* Main Layout - Full Height */}
      <div className="cockpit-layout flex-1">
        {/* Left Navigator */}
        <aside className={`cockpit-nav ${leftCollapsed ? 'collapsed' : ''}`}>
          {/* Collapse Toggle */}
          <button
            onClick={() => setLeftCollapsed(!leftCollapsed)}
            className="btn-icon absolute top-2 right-1 z-10"
          >
            <svg className={`w-4 h-4 transition-transform ${leftCollapsed ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
            </svg>
          </button>

          {!leftCollapsed && (
            <div className="flex-1 flex flex-col min-h-0 gap-1 py-2">
              {/* Agents Section - Accordion */}
              <CollapsibleNavSection
                id="agents"
                icon={<BotIcon size={16} />}
                title="Agents"
                count={agents.length}
                isExpanded={expandedSection === 'agents'}
                onToggle={handleSectionToggle}
                preview={getAgentsPreview()}
              >
                <div className="space-y-0.5 px-2">
                  {agents.map(agent => (
                    <button
                      key={agent.id}
                      onClick={() => onAgentSelect(agent.id)}
                      className={`cockpit-nav-item ${agent.id === selectedAgentId ? 'active' : ''}`}
                    >
                      <span className={`cockpit-nav-dot ${agent.is_active ? 'online' : 'offline'}`} />
                      <span className="flex-1 truncate text-sm">{agent.name}</span>
                    </button>
                  ))}
                </div>
              </CollapsibleNavSection>

              {/* Projects Section - Accordion */}
              <CollapsibleNavSection
                id="projects"
                icon={<FolderIcon size={16} />}
                title="Projects"
                count={projects.length}
                isExpanded={expandedSection === 'projects'}
                onToggle={handleSectionToggle}
                preview={getProjectsPreview()}
              >
                <div className="space-y-0.5 px-2">
                  {projects.length === 0 ? (
                    <p className="text-xs text-[var(--pg-text-muted)] px-2 py-2">No projects</p>
                  ) : (
                    projects.map(project => (
                      <button
                        key={project.id}
                        onClick={() => onProjectSelect(project.id)}
                        className={`cockpit-nav-item ${project.id === projectSession?.project_id ? 'active' : ''}`}
                        title={project.id === projectSession?.project_id ? 'Click to exit project' : 'Click to enter project'}
                      >
                        <span className="text-sm flex items-center justify-center w-4 h-4">{project.id === projectSession?.project_id ? <FolderOpenIcon size={14} /> : <FolderIcon size={14} />}</span>
                        <span className="flex-1 truncate text-sm">{project.name}</span>
                        {project.id === projectSession?.project_id && (
                          <span className="w-2 h-2 bg-[var(--pg-accent)] rounded-full animate-pulse" title="Active" />
                        )}
                      </button>
                    ))
                  )}
                </div>
              </CollapsibleNavSection>

              {/* Threads Section - Accordion (conditionally rendered) */}
              {selectedAgentId && threads && threads.length > 0 && (
                <CollapsibleNavSection
                  id="threads"
                  icon={<MessageIcon size={16} />}
                  title="Threads"
                  count={threads.length}
                  isExpanded={expandedSection === 'threads'}
                  onToggle={handleSectionToggle}
                  preview={getThreadsPreview()}
                >
                  <div className="space-y-0.5 px-2">
                    {onNewThread && (
                      <button
                        onClick={onNewThread}
                        className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-[var(--pg-accent)]/20 hover:bg-[var(--pg-accent)]/30 text-[var(--pg-accent)] text-xs font-medium transition-colors mb-2"
                        title="New thread"
                      >
                        <span>+</span>
                        <span>New Thread</span>
                      </button>
                    )}
                    {threads.slice(0, 10).map(thread => (
                      <div
                        key={thread.id}
                        className={`thread-item-with-menu relative flex items-center gap-2 px-3 py-2.5 rounded-lg cursor-pointer transition-colors ${
                          thread.id === activeThreadId
                            ? 'bg-[var(--pg-accent-soft)] text-[var(--pg-accent)]'
                            : 'text-[var(--pg-text-secondary)] hover:bg-[var(--pg-surface)]/50 hover:text-[var(--pg-text)]'
                        }`}
                        onClick={() => onThreadSelect && onThreadSelect(thread.id)}
                        title={thread.title || 'Untitled'}
                      >
                        <span className="text-sm flex-shrink-0 flex items-center justify-center w-4 h-4">{thread.is_archived ? <ArchiveIcon size={14} /> : <MessageIcon size={14} />}</span>
                        <span className="flex-1 truncate text-sm">{thread.title || 'New Conversation'}</span>
                        {thread.message_count > 0 && (
                          <span className="text-[10px] text-[var(--pg-text-muted)] flex-shrink-0">{thread.message_count}</span>
                        )}
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setThreadContextMenu({ threadId: thread.id, x: e.clientX, y: e.clientY })
                          }}
                          className="thread-menu-btn flex-shrink-0 p-1 hover:bg-[var(--pg-surface)] rounded transition-all"
                          title="Thread options"
                          style={{ opacity: 0.3 }}
                        >
                          <svg className="w-3.5 h-3.5 text-[var(--pg-text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
                          </svg>
                        </button>
                      </div>
                    ))}
                  </div>
                </CollapsibleNavSection>
              )}

              {/* Quick Tools Section - Accordion */}
              <CollapsibleNavSection
                id="tools"
                icon={<WrenchIcon size={16} />}
                title="Sandboxed Tools"
                count={quickTools.length}
                isExpanded={expandedSection === 'tools'}
                onToggle={handleSectionToggle}
                preview={getToolsPreview()}
              >
                {loadingTools ? (
                  <div className="flex items-center justify-center py-4">
                    <div className="w-4 h-4 border-2 border-[var(--pg-accent)] border-t-transparent rounded-full animate-spin" />
                  </div>
                ) : (
                  <div className="px-2">
                    <div className="cockpit-tools-grid">
                      {quickTools.map(tool => (
                        <button
                          key={tool.id}
                          onClick={() => handleQuickToolClick(tool)}
                          className="cockpit-tool-btn group"
                          title={tool.description || `Click to run ${tool.name}`}
                        >
                          <span className="cockpit-tool-icon">{tool.icon}</span>
                          <span className="truncate">{tool.name}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </CollapsibleNavSection>
            </div>
          )}

          {/* Collapsed Icons */}
          {leftCollapsed && (
            <div className="flex flex-col items-center py-3 gap-2">
              <button className="btn-icon" title="Agents" onClick={() => setLeftCollapsed(false)}><BotIcon size={16} /></button>
              <button className="btn-icon" title="Projects" onClick={() => setLeftCollapsed(false)}><FolderIcon size={16} /></button>
              {selectedAgentId && threads && threads.length > 0 && (
                <button className="btn-icon" title="Threads" onClick={() => setLeftCollapsed(false)}><MessageIcon size={16} /></button>
              )}
              <button className="btn-icon" title="Sandboxed Tools" onClick={() => setLeftCollapsed(false)}><WrenchIcon size={16} /></button>
            </div>
          )}
        </aside>

        {/* Center - Chat */}
        <main className="cockpit-chat">
          {/* Project Session Badge */}
          {projectSession?.is_in_project && (
            <div className="project-session-badge">
              <div className="project-badge-content">
                <span className="project-badge-icon flex items-center justify-center"><FolderOpenIcon size={14} /></span>
                <span className="project-badge-label">Working in</span>
                <span className="project-badge-name">{projectSession.project_name}</span>
                {projectSession.document_count !== undefined && (
                  <span className="project-badge-docs">
                    {projectSession.document_count} docs
                  </span>
                )}
              </div>
              <button
                onClick={onExitProject}
                className="project-badge-exit"
                title="Exit project"
              >
                ✕
              </button>
            </div>
          )}

          {/* Phase 14.1: Thread Header */}
          {selectedAgentId && activeThread && onThreadUpdated && onThreadDeleted && (
            <div className="border-b border-[var(--pg-border)]">
              <ThreadHeader
                thread={activeThread}
                onThreadUpdated={onThreadUpdated}
                onThreadDeleted={onThreadDeleted}
                onThreadRenamed={onThreadRenamed}
                onOpenSearch={onOpenSearch}
                onExtractKnowledge={onExtractKnowledge}
                agentId={selectedAgentId}
              />
            </div>
          )}

          {/* Messages */}
          <div className="cockpit-messages">
            {isLoadingThread ? (
              <div className="empty-state h-full">
                <div className="empty-state-icon animate-pulse">
                  <div className="w-6 h-6 border-2 border-[var(--pg-accent)] border-t-transparent rounded-full animate-spin" />
                </div>
                <p className="text-[var(--pg-text-secondary)] mt-4">Loading conversation...</p>
              </div>
            ) : threadLoadError ? (
              <div className="empty-state h-full">
                <div className="empty-state-icon">
                  <svg className="w-16 h-16 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <h3 className="empty-state-title">Failed to Load Conversation</h3>
                <p className="empty-state-desc text-red-400">{threadLoadError}</p>
                {activeThreadId && onThreadSelect && (
                  <button
                    onClick={() => onThreadSelect(activeThreadId)}
                    className="mt-4 px-4 py-2 bg-[var(--pg-accent)] hover:bg-[var(--pg-accent)]/80 text-white rounded-lg transition-colors"
                  >
                    Retry
                  </button>
                )}
              </div>
            ) : isLoadingHistory ? (
              <div className="empty-state h-full">
                <div className="empty-state-icon animate-pulse">
                  <div className="w-6 h-6 border-2 border-[var(--pg-accent)] border-t-transparent rounded-full animate-spin" />
                </div>
                <p className="text-[var(--pg-text-secondary)] mt-4">Loading...</p>
              </div>
            ) : !selectedAgentId ? (
              <div className="empty-state h-full">
                <div className="empty-state-icon"><TargetIcon size={48} /></div>
                <h3 className="empty-state-title">Select an Agent</h3>
                <p className="empty-state-desc">Choose an agent from the navigator to start</p>
              </div>
            ) : messages.length === 0 && activeThreadId ? (
              <div className="empty-state h-full">
                <div className="empty-state-icon"><MessageIcon size={48} /></div>
                <h3 className="empty-state-title">No messages yet</h3>
                <p className="empty-state-desc">This conversation has no messages</p>
              </div>
            ) : messages.length === 0 ? (
              <div className="empty-state h-full">
                <div className="empty-state-icon"><MessageIcon size={48} /></div>
                <h3 className="empty-state-title">Ready to chat</h3>
                <p className="empty-state-desc">Start a conversation with {agentName}</p>
              </div>
            ) : (
              <div className="space-y-4">
                {messages.map((msg, idx) => {
                  const isUser = msg.role === 'user'
                  const messageKey = msg.message_id || `msg_${msg.timestamp}_${idx}`
                  return (
                    <div
                      key={messageKey}
                      className={`flex gap-3 animate-slide-up ${isUser ? 'flex-row-reverse' : ''}`}
                      style={{ animationDelay: `${idx * 15}ms` }}
                    >
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-semibold flex-shrink-0 ${
                        isUser
                          ? 'bg-[var(--pg-accent)] text-[var(--pg-void)]'
                          : 'bg-[var(--pg-surface)] border border-[var(--pg-border)] text-[var(--pg-text-secondary)]'
                      }`}>
                        {isUser ? 'U' : 'AI'}
                      </div>
                      <div className={`flex flex-col gap-1 max-w-[75%] ${isUser ? 'items-end' : ''}`}>
                        <div className="relative">
                          <div className={`px-4 py-3 rounded-xl text-sm leading-relaxed ${
                            isUser
                              ? 'bg-[var(--pg-accent)] text-[var(--pg-void)] rounded-tr-sm'
                              : 'bg-[var(--pg-surface)] border border-[var(--pg-border)] text-[var(--pg-text)] rounded-tl-sm'
                          }`}>
                            <div className="whitespace-pre-wrap break-words">{msg.content}</div>
                            {msg.audio_url && (
                              <audio
                                controls
                                src={msg.audio_url.startsWith('/api/')
                                  ? `${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8081'}${msg.audio_url}`
                                  : msg.audio_url
                                }
                                className="mt-2 h-8 w-full max-w-[200px]"
                              />
                            )}
                          </div>
                          {/* Phase 14.2: Message Actions */}
                          {selectedAgentId && activeThreadId && onThreadUpdated && (
                            <MessageActions
                              message={msg}
                              agentId={selectedAgentId}
                              threadId={activeThreadId}
                              onMessageUpdated={onThreadUpdated}
                            />
                          )}
                        </div>
                        <div className="px-1">
                          <span className="text-[10px] text-[var(--pg-text-muted)]">
                            {formatTimestamp(msg.timestamp)}
                            {msg.is_edited && <span className="ml-2 italic">(edited)</span>}
                            {msg.is_bookmarked && <span className="ml-1">⭐</span>}
                          </span>
                          {/* KB Usage Badge for assistant messages */}
                          {!isUser && msg.kb_used && msg.kb_used.length > 0 && (
                            <KBUsageBadge kb_used={msg.kb_used} />
                          )}
                        </div>
                      </div>
                    </div>
                  )
                })}

                {/* Phase 14.9: Streaming message */}
                {streamingMessage && (
                  <div className="flex gap-3 animate-slide-up">
                    <div className="w-8 h-8 rounded-lg bg-[var(--pg-surface)] border border-[var(--pg-border)] flex items-center justify-center text-xs font-semibold text-[var(--pg-text-secondary)]">
                      AI
                    </div>
                    <div className="flex flex-col gap-1 max-w-[75%]">
                      <div className="bg-[var(--pg-surface)] border border-[var(--pg-border)] rounded-xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed text-[var(--pg-text)]">
                        <StreamingMessage
                          content={streamingMessage.content || ''}
                          isStreaming={!!streamingMessage.content}
                          isComplete={false}
                        />
                      </div>
                    </div>
                  </div>
                )}

                {isSending && !streamingMessage && (
                  <div className="flex gap-3">
                    <div className="w-8 h-8 rounded-lg bg-[var(--pg-surface)] border border-[var(--pg-border)] flex items-center justify-center text-xs font-semibold text-[var(--pg-text-secondary)]">
                      AI
                    </div>
                    <div className="bg-[var(--pg-surface)] border border-[var(--pg-border)] rounded-xl rounded-tl-sm px-4 py-3">
                      <div className="typing-indicator">
                        <div className="typing-dot" />
                        <div className="typing-dot" />
                        <div className="typing-dot" />
                      </div>
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          {/* Error */}
          {error && (
            <div className="px-4 pb-2">
              <div className="bg-[var(--pg-error)]/10 border border-[var(--pg-error)]/30 rounded-lg p-3 flex items-center gap-2">
                <svg className="w-4 h-4 text-[var(--pg-error)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span className="text-sm text-[var(--pg-error)] flex-1">{error}</span>
              </div>
            </div>
          )}

          {/* Recording UI */}
          {(isRecording || audioBlob) && (
            <div className="px-4 pb-2">
              <div className="flex items-center gap-3 p-3 bg-[var(--pg-surface)] rounded-xl border border-[var(--pg-border)]">
                {isRecording ? (
                  <>
                    <div className="flex items-center gap-2 flex-1">
                      <div className="w-3 h-3 bg-red-500 rounded-full animate-pulse" />
                      <span className="text-sm text-red-400 font-mono">
                        {Math.floor(recordingTime / 60).toString().padStart(2, '0')}:{(recordingTime % 60).toString().padStart(2, '0')}
                      </span>
                      <div className="flex-1 flex items-center gap-1 px-2">
                        {[...Array(8)].map((_, i) => (
                          <div
                            key={i}
                            className="w-1 bg-red-500 rounded-full animate-pulse"
                            style={{ height: `${Math.random() * 16 + 8}px`, animationDelay: `${i * 0.1}s` }}
                          />
                        ))}
                      </div>
                    </div>
                    <button
                      onClick={onStopRecording}
                      className="p-2.5 bg-red-500 hover:bg-red-600 text-white rounded-lg transition-colors"
                    >
                      <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                        <rect x="6" y="6" width="12" height="12" rx="1" />
                      </svg>
                    </button>
                  </>
                ) : audioBlob && (
                  <>
                    <div className="flex-1 flex items-center gap-3">
                      <span className="text-sm text-[var(--pg-text-secondary)]">🎤 Ready to send</span>
                      {audioUrl && <audio controls src={audioUrl} className="h-8 flex-1 max-w-[200px]" />}
                    </div>
                    <button
                      onClick={onCancelRecording}
                      className="p-2 text-[var(--pg-text-secondary)] hover:text-[var(--pg-error)] rounded-lg transition-colors"
                    >
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                    <button
                      onClick={onSendAudio}
                      disabled={isProcessingAudio}
                      className="p-2.5 bg-[var(--pg-accent)] text-[var(--pg-void)] rounded-lg transition-all hover:opacity-90 disabled:opacity-50"
                    >
                      {isProcessingAudio ? (
                        <div className="w-5 h-5 border-2 border-[var(--pg-void)]/30 border-t-[var(--pg-void)] rounded-full animate-spin" />
                      ) : (
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" />
                        </svg>
                      )}
                    </button>
                  </>
                )}
              </div>
            </div>
          )}

          {/* Input */}
          <div className="cockpit-input-area">
            <div className="flex items-end gap-2">
              {/* Audio Recording Button */}
              {audioCapabilities?.has_transcript && !isRecording && !audioBlob && onStartRecording && (
                <button
                  onClick={onStartRecording}
                  disabled={!selectedAgentId || isSending}
                  className="h-11 w-11 flex-shrink-0 rounded-lg bg-[var(--pg-surface)] border border-[var(--pg-border)] text-[var(--pg-text-secondary)] hover:text-[var(--pg-accent)] hover:border-[var(--pg-accent)]/50 transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center"
                  title={audioCapabilities?.has_tts ? "Record audio (agent will respond with audio)" : "Record audio"}
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                  </svg>
                </button>
              )}

              {/* File Upload Button */}
              {selectedAgentId && !isRecording && !audioBlob && fileInputRef && onFileUpload && (
                <>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept=".pdf,.txt,.csv,.json,.xlsx,.xls,.docx,.doc,.md,.markdown,.rtf"
                    onChange={(e) => e.target.files && onFileUpload(e.target.files)}
                    className="hidden"
                  />
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    disabled={isSending}
                    className="h-11 w-11 flex-shrink-0 rounded-lg bg-[var(--pg-surface)] border border-[var(--pg-border)] text-[var(--pg-text-secondary)] hover:text-[var(--pg-accent)] hover:border-[var(--pg-accent)]/50 transition-all disabled:opacity-40 disabled:cursor-not-allowed relative flex items-center justify-center"
                    title="Attach documents"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                    </svg>
                    {documentsCount > 0 && (
                      <span className="absolute -top-1 -right-1 w-4 h-4 bg-[var(--pg-accent)] text-[var(--pg-void)] text-[10px] rounded-full flex items-center justify-center font-bold">
                        {documentsCount}
                      </span>
                    )}
                  </button>
                </>
              )}

              <div className="flex-1 relative">
                <InlineCommands
                  isOpen={inlineCommandsOpen}
                  query={inlineQuery}
                  commands={slashCommands}
                  selectedIndex={inlineSelectedIndex}
                  onSelect={onInlineCommandSelect}
                  onClose={onCloseInlineCommands}
                  onNavigate={onNavigateInlineCommands}
                  availableTools={availableTools}
                  availableAgents={availableAgents}
                  injectTargets={injectTargets}
                />
                <textarea
                  ref={inputRef}
                  placeholder={selectedAgentId ? "Type / for commands..." : "Select an agent"}
                  disabled={!selectedAgentId || isSending || isRecording}
                  onChange={onInputChange}
                  onKeyDown={onKeyDown}
                  className="w-full bg-[var(--pg-elevated)] border border-[var(--pg-border)] rounded-lg px-4 py-3 text-[var(--pg-text)] text-sm resize-none outline-none focus:border-[var(--pg-accent)] focus:ring-2 focus:ring-[var(--pg-accent-glow)] transition-all min-h-[44px] max-h-[120px]"
                  rows={1}
                  onInput={(e) => {
                    const target = e.currentTarget
                    target.style.height = 'auto'
                    target.style.height = Math.min(target.scrollHeight, 120) + 'px'
                  }}
                />
              </div>
              <button
                onClick={onSendMessage}
                disabled={!selectedAgentId || isSending || isRecording}
                className="h-11 px-4 rounded-lg bg-[var(--pg-accent)] text-[var(--pg-void)] font-medium text-sm transition-all hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {isSending ? (
                  <div className="w-4 h-4 border-2 border-[var(--pg-void)]/30 border-t-[var(--pg-void)] rounded-full animate-spin" />
                ) : (
                  <>
                    <span>Send</span>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" />
                    </svg>
                  </>
                )}
              </button>
            </div>
          </div>
        </main>

        {/* Right Inspector */}
        <aside className={`cockpit-inspector ${rightCollapsed ? 'collapsed' : ''}`}>
          {/* Collapse Toggle */}
          <button
            onClick={() => setRightCollapsed(!rightCollapsed)}
            className="btn-icon absolute top-2 left-1 z-10"
          >
            <svg className={`w-4 h-4 transition-transform ${rightCollapsed ? '' : 'rotate-180'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
            </svg>
          </button>

          {!rightCollapsed && (
            <>
              {/* Inspector Tabs */}
              <div className="cockpit-inspector-tabs">
                <button
                  onClick={() => setActiveInspector('memory')}
                  className={`cockpit-inspector-tab ${activeInspector === 'memory' ? 'active' : ''}`}
                >
                  <BrainIcon size={14} /> Memory
                </button>
                <button
                  onClick={() => setActiveInspector('skills')}
                  className={`cockpit-inspector-tab ${activeInspector === 'skills' ? 'active' : ''}`}
                >
                  <LightningIcon size={14} /> Skills
                </button>
                <button
                  onClick={() => setActiveInspector('knowledge')}
                  className={`cockpit-inspector-tab ${activeInspector === 'knowledge' ? 'active' : ''}`}
                >
                  <BookIcon size={14} /> Knowledge
                </button>
                <button
                  onClick={() => setActiveInspector('debug')}
                  className={`cockpit-inspector-tab ${activeInspector === 'debug' ? 'active' : ''}`}
                >
                  <BugIcon size={14} /> Debug
                </button>
                <button
                  onClick={() => setActiveInspector('config')}
                  className={`cockpit-inspector-tab ${activeInspector === 'config' ? 'active' : ''}`}
                >
                  <SettingsIcon size={14} /> Config
                </button>
              </div>

              {/* Inspector Content */}
              <div className="cockpit-inspector-content">
                {activeInspector === 'memory' && (
                  <MemoryInspector
                    agentId={selectedAgentId}
                    senderKey={activeThread?.recipient}
                  />
                )}
                {activeInspector === 'skills' && <SkillsPanel agentId={selectedAgentId} />}
                {activeInspector === 'knowledge' && <KnowledgeTab agentId={selectedAgentId} projectSession={projectSession} />}
                {activeInspector === 'debug' && <DebugPanel agentId={selectedAgentId} />}
                {activeInspector === 'config' && <ConfigPanel agentId={selectedAgentId} />}
              </div>
            </>
          )}

          {/* Collapsed Icons */}
          {rightCollapsed && (
            <div className="flex flex-col items-center py-3 gap-2 mt-8">
              <button
                onClick={() => { setRightCollapsed(false); setActiveInspector('memory'); }}
                className={`btn-icon ${activeInspector === 'memory' ? 'text-[var(--pg-accent)]' : ''}`}
                title="Memory"
              >
                <BrainIcon size={16} />
              </button>
              <button
                onClick={() => { setRightCollapsed(false); setActiveInspector('skills'); }}
                className={`btn-icon ${activeInspector === 'skills' ? 'text-[var(--pg-accent)]' : ''}`}
                title="Skills"
              >
                <LightningIcon size={16} />
              </button>
              <button
                onClick={() => { setRightCollapsed(false); setActiveInspector('knowledge'); }}
                className={`btn-icon ${activeInspector === 'knowledge' ? 'text-[var(--pg-accent)]' : ''}`}
                title="Knowledge"
              >
                <BookIcon size={16} />
              </button>
              <button
                onClick={() => { setRightCollapsed(false); setActiveInspector('debug'); }}
                className={`btn-icon ${activeInspector === 'debug' ? 'text-[var(--pg-accent)]' : ''}`}
                title="Debug"
              >
                <BugIcon size={16} />
              </button>
              <button
                onClick={() => { setRightCollapsed(false); setActiveInspector('config'); }}
                className={`btn-icon ${activeInspector === 'config' ? 'text-[var(--pg-accent)]' : ''}`}
                title="Config"
              >
                <SettingsIcon size={16} />
              </button>
            </div>
          )}
        </aside>
      </div>

      {/* Quick Tool Invoke Modal */}
      {selectedToolForInvoke && (
        <>
          <div className="quick-tool-overlay" onClick={() => setSelectedToolForInvoke(null)} />
          <QuickToolInvoke
            tool={selectedToolForInvoke}
            onClose={() => setSelectedToolForInvoke(null)}
            onExecute={handleToolExecute}
          />
        </>
      )}

      {/* All Tools Modal */}
      {showAllTools && (
        <>
          <div className="quick-tool-overlay" onClick={() => { setShowAllTools(false); setToolSearchQuery(''); }} />
          <div className="all-tools-modal">
            <div className="all-tools-header">
              <h3>All Tools</h3>
              <span className="all-tools-count">{quickTools.length} available</span>
              <button
                onClick={() => { setShowAllTools(false); setToolSearchQuery(''); }}
                className="all-tools-close"
              >
                ✕
              </button>
            </div>
            <div className="all-tools-search">
              <input
                type="text"
                placeholder="Search tools..."
                value={toolSearchQuery}
                onChange={(e) => setToolSearchQuery(e.target.value)}
                className="all-tools-search-input"
                autoFocus
              />
            </div>
            <div className="all-tools-grid">
              {quickTools
                .filter(tool =>
                  tool.name.toLowerCase().includes(toolSearchQuery.toLowerCase()) ||
                  (tool.description || '').toLowerCase().includes(toolSearchQuery.toLowerCase())
                )
                .map(tool => (
                  <button
                    key={tool.id}
                    onClick={() => {
                      setShowAllTools(false)
                      setToolSearchQuery('')
                      handleQuickToolClick(tool)
                    }}
                    className="all-tools-item"
                  >
                    <span className="all-tools-icon">{tool.icon}</span>
                    <div className="all-tools-info">
                      <span className="all-tools-name">{tool.name}</span>
                      {tool.description && (
                        <span className="all-tools-desc">{tool.description}</span>
                      )}
                    </div>
                  </button>
                ))}
              {quickTools.filter(tool =>
                tool.name.toLowerCase().includes(toolSearchQuery.toLowerCase()) ||
                (tool.description || '').toLowerCase().includes(toolSearchQuery.toLowerCase())
              ).length === 0 && (
                <p className="all-tools-empty">No tools match "{toolSearchQuery}"</p>
              )}
            </div>
          </div>
        </>
      )}

      {/* Thread Context Menu */}
      {threadContextMenu && (
        <>
          <div
            className="fixed inset-0"
            style={{ zIndex: 9998 }}
            onClick={() => setThreadContextMenu(null)}
          />
          <div
            className="fixed border border-[var(--pg-border)] rounded-lg shadow-2xl overflow-hidden"
            style={{
              left: threadContextMenu.x,
              top: threadContextMenu.y,
              zIndex: 9999,
              minWidth: '180px',
              background: '#0D1117',
              opacity: 1
            }}
          >
            <button
              onClick={() => handleStartRename(threadContextMenu.threadId)}
              className="w-full px-4 py-2.5 text-sm text-left hover:bg-[var(--pg-surface)]/30 flex items-center gap-3 text-[var(--pg-text)]"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
              Rename
            </button>
            <button
              onClick={() => handleExportThread(threadContextMenu.threadId)}
              className="w-full px-4 py-2.5 text-sm text-left hover:bg-[var(--pg-surface)]/30 flex items-center gap-3 text-[var(--pg-text)]"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Export as JSON
            </button>
            <button
              onClick={() => {
                const thread = threads.find(t => t.id === threadContextMenu.threadId)
                if (thread) {
                  handleArchiveThread(threadContextMenu.threadId, thread.is_archived)
                }
              }}
              className="w-full px-4 py-2.5 text-sm text-left hover:bg-[var(--pg-surface)]/30 flex items-center gap-3 text-[var(--pg-text)]"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
              </svg>
              {threads.find(t => t.id === threadContextMenu.threadId)?.is_archived ? 'Unarchive' : 'Archive'}
            </button>
            <button
              onClick={() => handleDeleteThread(threadContextMenu.threadId)}
              className="w-full px-4 py-2.5 text-sm text-left hover:bg-red-500/10 text-red-400 flex items-center gap-3 border-t border-[var(--pg-border)]"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
              Delete
            </button>
          </div>
        </>
      )}

      {/* Rename Modal */}
      {renamingThreadId && (
        <>
          <div
            className="fixed inset-0"
            style={{ zIndex: 10000, backgroundColor: 'rgba(0, 0, 0, 0.5)', backdropFilter: 'blur(4px)' }}
            onClick={handleCancelRename}
          />
          <div
            className="fixed inset-0 flex items-center justify-center p-4"
            style={{ zIndex: 10001 }}
          >
            <div
              className="border rounded-lg p-6 max-w-md w-full shadow-xl"
              style={{
                background: '#0D1117',
                borderColor: 'rgba(99, 102, 241, 0.2)'
              }}
            >
              <h3 className="text-lg font-semibold mb-4" style={{ color: '#f4f4f5' }}>Rename Conversation</h3>
              <input
                type="text"
                value={renameTitle}
                onChange={(e) => setRenameTitle(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    handleSaveRename()
                  } else if (e.key === 'Escape') {
                    handleCancelRename()
                  }
                }}
                className="w-full px-3 py-2 rounded-lg mb-4"
                style={{
                  background: '#161B22',
                  border: '1px solid rgba(99, 102, 241, 0.2)',
                  color: '#f4f4f5',
                  outline: 'none'
                }}
                placeholder="Enter conversation title"
                autoFocus
                maxLength={200}
              />
              <div className="flex gap-2 justify-end">
                <button
                  onClick={handleCancelRename}
                  className="px-4 py-2 text-sm rounded-lg transition-colors"
                  style={{
                    color: '#94a3b8',
                    background: 'transparent'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.color = '#f4f4f5'
                    e.currentTarget.style.background = 'rgba(22, 27, 34, 0.5)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.color = '#94a3b8'
                    e.currentTarget.style.background = 'transparent'
                  }}
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveRename}
                  className="px-4 py-2 text-sm rounded-lg transition-colors"
                  style={{
                    background: '#6366f1',
                    color: 'white'
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.background = '#5558e3'}
                  onMouseLeave={(e) => e.currentTarget.style.background = '#6366f1'}
                >
                  Save
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
